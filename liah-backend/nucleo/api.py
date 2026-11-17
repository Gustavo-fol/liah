"""
API v1 DA LIAH = endereços que trocam DADOS (JSON), não páginas.

Quem usa: a página de chat (JavaScript) e, no futuro, o robô e outros apps.
O "v1" no endereço permite criar uma v2 um dia sem quebrar quem usa a v1.

  GET    /api/v1/status/                 -> a Liah está no ar? a IA online está ligada?
  POST   /api/v1/mensagens/              -> envia {"mensagem": "...", "conversa_id": 5 ou null}
  GET    /api/v1/conversas/              -> lista as conversas do usuário logado
  GET    /api/v1/conversas/<id>/         -> mensagens de uma conversa
  DELETE /api/v1/conversas/<id>/         -> apaga uma conversa
  POST   /api/v1/visitante/mensagens/    -> chat SEM conta (15 por dia, nada é salvo)
  POST   /api/v1/preferencias/           -> salva o tema {"tema": "claro"|"escuro"|"sistema"}
  POST   /api/v1/mensagens/<id>/avaliacao/ -> {"avaliacao": "util"|"nao_util"|""} (👍/👎 numa resposta)

Códigos HTTP usados (o "status" da resposta):
  200 ok | 201 criado | 400 pedido inválido | 401 não logado | 403 sem permissão
  404 não existe (ou não é seu) | 405 método errado | 429 muitas mensagens seguidas
"""
import json
from functools import wraps

from django.conf import settings
from django.core.cache import cache
from django.db.models import Count
from django.http import JsonResponse
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from contas.auditoria import ip_do_pedido
from contas.models import Consentimento, Usuario

from .models import ConfiguracaoIA, Conversa, Mensagem
from .processamento import processar_mensagem
from .servicos import conversar
from .texto import normalizar

TAMANHO_MAXIMO = 2000          # caracteres por mensagem
LIMITE_POR_MINUTO = 20         # mensagens por usuário por minuto (protege o custo da IA)
# Limites do visitante e diários: vêm do settings (ajustáveis pelo .env, ex.: no dia da feira).
LIMITE_VISITANTE_DIA = settings.LIAH_VISITANTE_DIA         # mensagens por dia para quem não tem conta
LIMITE_VISITANTE_IP_DIA = settings.LIAH_VISITANTE_IP_DIA   # teto por rede (robô apagando cookies)
HISTORICO_VISITANTE = 10       # quantas mensagens anteriores o visitante pode mandar como contexto
HISTORICO_VISITANTE_CARACTERES = 4000   # e no máximo isto de texto somado (protege o custo da IA)
UM_DIA = 60 * 60 * 24


def erro(mensagem, status):
    return JsonResponse({"erro": mensagem}, status=status)


def api_login_obrigatorio(view):
    """
    DECORATOR = função que "embrulha" outra. Igual ao @login_required do Django,
    mas em vez de redirecionar para a página de login (que não serve para uma API),
    responde JSON com status 401.
    """
    @wraps(view)
    def embrulho(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return erro("Faça login para conversar com a Liah.", 401)
        return view(request, *args, **kwargs)
    return embrulho


def _passou_do_limite(usuario):
    if usuario.is_staff:   # a equipe testa à vontade, sem limite por minuto
        return False
    chave = f"liah:chat:{usuario.pk}"
    cache.add(chave, 0, 60)
    try:
        return cache.incr(chave) > LIMITE_POR_MINUTO
    except ValueError:
        cache.set(chave, 1, 60)
        return False


def _passou_do_limite_do_dia(usuario):
    """
    Teto DIÁRIO por plano (gratuito/premium). Protege o crédito da IA contra uso abusivo
    ou uma conta roubada. A equipe não tem limite. A chave leva a data: vira à meia-noite sozinha.
    """
    if usuario.is_staff:
        return False
    teto = settings.LIAH_LIMITE_DIA.get(usuario.plano, settings.LIAH_LIMITE_DIA["gratuito"])
    chave = f"liah:dia:{usuario.pk}:{timezone.localdate().isoformat()}"
    return _contar(chave, UM_DIA) > teto


def _resposta_json(resposta):
    return {
        "texto": resposta.texto,
        "origem": resposta.origem,
        "risco": resposta.risco,
        "expressao": resposta.expressao,   # para o rosto no display do robô
    }


def _mensagem_json(m):
    return {
        "id": m.pk,
        "avaliacao": m.avaliacao,
        "autor": m.autor,
        "texto": m.texto,
        "risco": m.risco,
        "criada_em": m.criada_em.isoformat(),
    }


@require_GET
def status(request):
    return JsonResponse({
        "nome": "Liah",
        "versao_api": "v1",
        "online": True,
        "ia_online": ConfiguracaoIA.carregar().principal_pronta,
        "hora": timezone.now().isoformat(),
    })


@api_login_obrigatorio
@require_POST
def enviar_mensagem(request):
    usuario = request.user

    try:
        corpo = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return erro("Corpo do pedido não é um JSON válido.", 400)

    # A Liah só GUARDA conversa de quem autorizou o tratamento de dados emocionais (LGPD art. 11).
    autorizado = usuario.tem_consentimento(Consentimento.Tipo.DADOS_SENSIVEIS)
    if not autorizado and not usuario.is_staff:
        return JsonResponse({
            "erro": "Para conversar, é preciso autorizar o tratamento de dados emocionais.",
            "consentimento": True,
            "url": reverse("contas:privacidade"),
        }, status=403)

    texto = str(corpo.get("mensagem", "")).strip()
    if not texto:
        return erro("Digite uma mensagem.", 400)
    if len(texto) > TAMANHO_MAXIMO:
        return erro(f"A mensagem pode ter no máximo {TAMANHO_MAXIMO} caracteres.", 400)

    if _passou_do_limite(usuario):
        return erro("Você enviou muitas mensagens seguidas. Respire um pouco e tente de novo em um minuto.", 429)
    if _passou_do_limite_do_dia(usuario):
        return erro("Você chegou ao limite de mensagens de hoje. Amanhã a gente continua. "
                    "Se precisar de ajuda agora, ligue 188 (CVV, 24 h, grátis).", 429)

    if not autorizado:
        # MODO TESTE DA EQUIPE: a equipe conversa livremente para avaliar a Liah,
        # mas como não deu a autorização, NADA é gravado (igual ao visitante, sem limite).
        resposta = processar_mensagem(texto, _limpar_historico(corpo.get("historico")))
        return JsonResponse({"teste": True, "resposta": _resposta_json(resposta)}, status=201)

    conversa = None
    conversa_id = corpo.get("conversa_id")
    if conversa_id:
        # filter(usuario=usuario): proteção contra IDOR (só abre conversa que é SUA).
        conversa = Conversa.objects.filter(pk=conversa_id, usuario=usuario).first()
        if conversa is None:
            return erro("Conversa não encontrada.", 404)

    conversa, resposta = conversar(usuario, texto, conversa)

    return JsonResponse({
        "conversa_id": conversa.pk,
        "mensagem_id": getattr(resposta, "mensagem_id", None),
        "resposta": _resposta_json(resposta),
    }, status=201)


@api_login_obrigatorio
@require_GET
def listar_conversas(request):
    """
    GET /api/v1/conversas/?busca=texto
    Devolve as conversas da PRÓPRIA pessoa, com uma prévia da primeira mensagem dela.
    A prévia e a busca decifram o texto aqui no servidor, só para o dono da conversa:
    nada disso fica salvo sem criptografia.
    """
    busca = normalizar(request.GET.get("busca", ""))[:100]
    resultado = []

    # Contagem feita pelo BANCO (annotate), sem carregar as mensagens.
    conversas = request.user.conversas.annotate(total=Count("mensagens"))

    if busca:
        # Busca precisa decifrar o texto (ele é guardado cifrado), então carrega as mensagens.
        conversas = conversas.prefetch_related("mensagens")[:200]
    else:
        conversas = conversas[:50]

    for c in conversas:
        if busca:
            mensagens = list(c.mensagens.all())
            if not any(busca in normalizar(m.texto) for m in mensagens):
                continue
            primeira = next((m.texto for m in mensagens if m.autor == Mensagem.Autor.USUARIO), "")
        else:
            # Sem busca: decifra só UMA mensagem por conversa (a primeira da pessoa).
            m = c.mensagens.filter(autor=Mensagem.Autor.USUARIO).order_by("criada_em").first()
            primeira = m.texto if m else ""
        resultado.append({
            "id": c.pk,
            "titulo": c.titulo,
            "previa": (primeira[:70] + "…") if len(primeira) > 70 else primeira,
            "mensagens": c.total,
            "atualizada_em": c.atualizada_em.isoformat(),
        })
        if len(resultado) >= 50:
            break
    return JsonResponse({"conversas": resultado})


@api_login_obrigatorio
@require_http_methods(["GET", "DELETE"])
def conversa(request, pk):
    conversa = Conversa.objects.filter(pk=pk, usuario=request.user).first()
    if conversa is None:
        return erro("Conversa não encontrada.", 404)

    if request.method == "DELETE":
        conversa.delete()
        return JsonResponse({"apagada": True})

    return JsonResponse({
        "id": conversa.pk,
        "titulo": conversa.titulo,
        "mensagens": [_mensagem_json(m) for m in conversa.mensagens.all()],
    })


@api_login_obrigatorio
@require_POST
def avaliar_mensagem(request, pk):
    """
    👍/👎 numa resposta da Liah. Só vale para resposta DA LIAH, numa conversa DA PRÓPRIA pessoa
    (o filtro por conversa__usuario é a proteção contra IDOR). Mandar "" apaga a avaliação.
    """
    try:
        valor = json.loads(request.body or "{}").get("avaliacao", "")
    except json.JSONDecodeError:
        return erro("Corpo do pedido não é um JSON válido.", 400)
    if valor not in ("util", "nao_util", ""):
        return erro("Avaliação inválida.", 400)

    mensagem = Mensagem.objects.filter(
        pk=pk, autor=Mensagem.Autor.LIAH, conversa__usuario=request.user
    ).first()
    if mensagem is None:
        return erro("Resposta não encontrada.", 404)

    mensagem.avaliacao = valor
    mensagem.save(update_fields=["avaliacao"])
    return JsonResponse({"id": mensagem.pk, "avaliacao": valor})


# ============================================================ VISITANTE (sem conta)

def _contar(chave, validade):
    """Soma 1 num contador do cache e devolve o novo valor."""
    cache.add(chave, 0, validade)
    try:
        return cache.incr(chave)
    except ValueError:
        cache.set(chave, 1, validade)
        return 1


def _limpar_historico(bruto):
    """
    O visitante não tem nada salvo no servidor: o histórico vem do navegador.
    Como veio de fora, NÃO confiamos: só aceitamos o formato certo e cortamos o tamanho.
    """
    if not isinstance(bruto, list):
        return []
    limpo = []
    total = 0
    # Do mais NOVO para o mais antigo, parando quando passar do teto de caracteres.
    for item in reversed(bruto[-HISTORICO_VISITANTE:]):
        if isinstance(item, dict) and item.get("autor") in ("usuario", "liah"):
            texto = str(item.get("texto", ""))[:TAMANHO_MAXIMO]
            total += len(texto)
            if total > HISTORICO_VISITANTE_CARACTERES:
                break
            limpo.append({"autor": item["autor"], "texto": texto})
    limpo.reverse()
    return limpo


@require_POST
def enviar_mensagem_visitante(request):
    """
    LGPD: o visitante NÃO deu consentimento para dados sensíveis, então aqui
    nada é gravado (nem banco, nem log com texto). A Liah funciona como assistente geral.
    A detecção de risco e o CVV continuam ligados, porque a segurança vale para todos.
    """
    if request.user.is_authenticated:
        return erro("Você está logado: suas mensagens usam /api/v1/mensagens/.", 400)

    try:
        corpo = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return erro("Corpo do pedido não é um JSON válido.", 400)

    texto = str(corpo.get("mensagem", "")).strip()
    if not texto:
        return erro("Digite uma mensagem.", 400)
    if len(texto) > TAMANHO_MAXIMO:
        return erro(f"A mensagem pode ter no máximo {TAMANHO_MAXIMO} caracteres.", 400)

    # O limite é por SESSÃO (o cookie do navegador). Visitante não tem sessão até
    # o Django precisar de uma, então criamos aqui.
    if not request.session.session_key:
        request.session.save()
    chave_sessao = f"liah:visitante:s:{request.session.session_key}"
    chave_ip = f"liah:visitante:ip:{ip_do_pedido(request) or '-'}"

    usadas = cache.get(chave_sessao, 0)
    if usadas >= LIMITE_VISITANTE_DIA or cache.get(chave_ip, 0) >= LIMITE_VISITANTE_IP_DIA:
        return JsonResponse({
            "erro": "Você usou as mensagens gratuitas de hoje. Crie uma conta grátis para continuar conversando.",
            "limite": True,
            "restantes": 0,
        }, status=429)

    usadas = _contar(chave_sessao, UM_DIA)
    _contar(chave_ip, UM_DIA)

    resposta = processar_mensagem(texto, _limpar_historico(corpo.get("historico")), perfil="visitante")

    return JsonResponse({
        "resposta": {
            "texto": resposta.texto,
            "origem": resposta.origem,
            "risco": resposta.risco,
            "expressao": resposta.expressao,
        },
        "restantes": max(LIMITE_VISITANTE_DIA - usadas, 0),
    })


# ============================================================ PREFERÊNCIAS

@api_login_obrigatorio
@require_POST
def salvar_preferencias(request):
    try:
        corpo = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return erro("Corpo do pedido não é um JSON válido.", 400)

    tema = corpo.get("tema")
    if tema not in Usuario.Tema.values:   # só aceita os valores que existem
        return erro("Tema inválido.", 400)

    request.user.tema = tema
    request.user.save(update_fields=["tema"])
    return JsonResponse({"tema": tema})
