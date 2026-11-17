"""
IA ONLINE da Liah: tudo que usa as duas IAs passa por aqui.

  gerar_resposta()       -> PRINCIPAL conversa com o usuário (usa o dicionário aprovado)
  analisar_mensagem()    -> PRINCIPAL lê o dicionário e diz quais regras a fala "encaixa"
  gerar_fala_treino()    -> SECUNDÁRIA escreve uma fala fictícia nas entrelinhas (treino)
  sugerir_regras()       -> PRINCIPAL propõe regras novas (entram como RASCUNHO)

Se algo falhar, levanta IAIndisponivel: o núcleo cai para regras + resposta básica,
e o site nunca quebra por causa da IA.
"""
import json
import re

from django.core.cache import cache

from . import provedores
from .dicionario import texto_dicionario_completo, texto_regras
from .models import Categoria, ConfiguracaoIA, Encaminhamento, RegraDicionario
from .prompts import montar_mensagens


class IAIndisponivel(Exception):
    """A IA online não respondeu (desligada, sem chave, sem crédito, fora do ar...)."""


# DISJUNTOR (circuit breaker): se a IA falhou, ficamos 60 s sem tentar de novo.
# Assim, com a OpenAI fora do ar, cada mensagem não espera 15 s à toa: cai direto nas regras.
PAUSA_APOS_FALHA = 60


def _chave_disjuntor(qual):
    return f"liah:ia:fora:{qual}"


def _chamar(qual, mensagens, max_tokens=600, json_saida=False):
    if cache.get(_chave_disjuntor(qual)):
        raise IAIndisponivel(f"A IA {qual} falhou há pouco; tentando de novo em até {PAUSA_APOS_FALHA} s.")
    cfg = ConfiguracaoIA.carregar()
    pronta = cfg.principal_pronta if qual == "principal" else cfg.secundaria_pronta
    if not pronta:
        raise IAIndisponivel(f"A IA {qual} não está configurada (área interna > IA).")
    provedor = getattr(cfg, f"provedor_{qual}" if qual == "principal" else "provedor_secundario")
    modelo = getattr(cfg, "modelo_principal" if qual == "principal" else "modelo_secundario")
    try:
        texto = provedores.conversar(provedor, modelo, cfg.chave(qual), mensagens, max_tokens, json_saida)
    except provedores.ErroProvedor as erro:
        cache.set(_chave_disjuntor(qual), True, PAUSA_APOS_FALHA)   # "desarma" o disjuntor
        raise IAIndisponivel(str(erro)) from erro
    return texto, f"{provedor}:{modelo}"


def _ler_json(texto):
    """A IA às vezes coloca o JSON dentro de ```json ... ```; pegamos só o que está entre { }."""
    achado = re.search(r"\{.*\}", texto, re.S)
    if not achado:
        raise IAIndisponivel("A IA não devolveu um JSON válido.")
    try:
        return json.loads(achado.group(0))
    except json.JSONDecodeError as erro:
        raise IAIndisponivel("A IA devolveu um JSON quebrado.") from erro


# ============================================================ CONVERSA

def gerar_resposta(mensagem, historico, nivel_risco, perfil="usuario"):
    # Só os contextos ligados à fala de AGORA (veja dicionario.selecionar).
    dicionario = texto_dicionario_completo(mensagem, historico, nivel_risco) if perfil in ("usuario", "menor") else ""
    mensagens = montar_mensagens(historico, mensagem, nivel_risco, perfil, dicionario)
    texto, _ = _chamar("principal", mensagens, max_tokens=500)
    return texto


# ============================================================ ANÁLISE (IA principal)

PROMPT_ANALISE = """Você é o módulo de ANÁLISE da Liah, um sistema de apoio emocional supervisionado por psicólogo.
Você recebe um DICIONÁRIO de regras (cada uma com um número) e a FALA de uma pessoa.
Decida quais regras se aplicam ao que a pessoa diz, inclusive NAS ENTRELINHAS (o que ela não diz
diretamente). Não invente regras fora do dicionário. Se nenhuma se aplicar, devolva lista vazia.

Responda SOMENTE com um JSON neste formato:
{"regras": [números das regras], "nivel_risco": "nenhum" | "atencao" | "alto",
 "encaminhamento": "nenhum" | "psicologo" | "psiquiatra" | "emergencia",
 "justificativa": "explicação curta em português"}"""


def analisar_mensagem(texto, regras=None):
    regras = list(regras) if regras is not None else list(RegraDicionario.objects.exclude(status="arquivada"))
    if not regras:
        raise IAIndisponivel("O dicionário está vazio: cadastre ou aprove regras primeiro.")
    mensagens = [
        {"role": "system", "content": PROMPT_ANALISE},
        {"role": "user", "content": f"DICIONÁRIO:\n{texto_regras(regras, com_orientacao=False)}\n\nFALA DA PESSOA:\n{texto}"},
    ]
    resposta, quem = _chamar("principal", mensagens, max_tokens=700, json_saida=True)
    dados = _ler_json(resposta)
    dados["regras"] = [int(n) for n in dados.get("regras", []) if str(n).isdigit()]
    return dados, quem


# ============================================================ GERAÇÃO DE TREINO (IA secundária)

PROMPT_GERADOR = """Você ajuda a TREINAR um sistema de PREVENÇÃO em saúde mental, supervisionado por psicólogo.
Sua tarefa: escrever UMA mensagem FICTÍCIA, como se fosse uma pessoa real escrevendo para um chat de apoio.

Regras da escrita:
- Português do Brasil coloquial, primeira pessoa, 2 a 5 frases.
- A pessoa NUNCA diz o problema diretamente: o sinal aparece só NAS ENTRELINHAS
  (no que ela conta, no jeito de falar, no que ela evita).
- Não copie as frases de exemplo; crie uma situação nova e verossímil.
- Não inclua métodos, instruções ou detalhes de como se machucar.
- Responda SOMENTE com a mensagem, sem aspas e sem explicações."""


def gerar_fala_treino(regra):
    d = regra.detalhes or {}
    pedido = (
        f"Tema a ser expresso nas entrelinhas: {regra.titulo} ({regra.get_categoria_display()}).\n"
        f"Situação: {d.get('situacao') or '-'}\n"
        f"Sinais que um bom ouvinte deveria perceber: {regra.sinais}\n"
        f"Exemplos (NÃO copie): {' | '.join(regra.lista_exemplos()[:3]) or '-'}"
    )
    mensagens = [{"role": "system", "content": PROMPT_GERADOR}, {"role": "user", "content": pedido}]
    texto, quem = _chamar("secundaria", mensagens, max_tokens=400)
    return texto.strip().strip('"'), quem


# ============================================================ SUGESTÃO DE REGRAS (IA principal)

PROMPT_SUGESTAO = """Você ajuda a montar o DICIONÁRIO de um sistema de apoio emocional que será REVISADO por psicólogo.
Proponha regras para perceber sinais NAS ENTRELINHAS (o que a pessoa não diz diretamente).
Seja cuidadoso e baseado em boas práticas de saúde mental. Não inclua métodos de autolesão.

Responda SOMENTE com um JSON:
{"regras": [{"titulo": "...", "sinais": "...", "exemplos": ["frase 1", "frase 2", "frase 3"],
  "nivel_risco": "nenhum" | "atencao" | "alto",
  "orientacao": "como a Liah deve responder",
  "encaminhamento": "nenhum" | "psicologo" | "psiquiatra" | "emergencia"}]}"""


def sugerir_regras(categoria, quantidade=3):
    nome = Categoria(categoria).label
    existentes = ", ".join(RegraDicionario.objects.filter(categoria=categoria).values_list("titulo", flat=True)) or "nenhuma"
    mensagens = [
        {"role": "system", "content": PROMPT_SUGESTAO},
        {"role": "user", "content": f"Categoria: {nome}. Quantidade: {quantidade}. Regras que JÁ existem (não repita): {existentes}"},
    ]
    resposta, _ = _chamar("principal", mensagens, max_tokens=1800, json_saida=True)
    criadas = []
    for item in _ler_json(resposta).get("regras", [])[:quantidade]:
        if not item.get("titulo") or not item.get("sinais"):
            continue
        criadas.append(RegraDicionario.objects.create(
            titulo=str(item["titulo"])[:120],
            categoria=categoria,
            sinais=str(item["sinais"]),
            exemplos="\n".join(str(e) for e in item.get("exemplos", [])),
            nivel_risco=item.get("nivel_risco") if item.get("nivel_risco") in ("nenhum", "atencao", "alto") else "nenhum",
            orientacao=str(item.get("orientacao", "")),
            encaminhamento=item.get("encaminhamento") if item.get("encaminhamento") in Encaminhamento.values else "nenhum",
            status=RegraDicionario.Status.RASCUNHO,   # SEMPRE rascunho: o psicólogo decide
            origem=RegraDicionario.Origem.IA,
        ))
    return criadas


# ============================================================ TESTE DE CONEXÃO

def testar(qual):
    """Usado pelo botão 'Testar' da área interna: lista os modelos e faz uma pergunta simples."""
    cache.delete(_chave_disjuntor(qual))   # testar "rearma" o disjuntor na hora
    cfg = ConfiguracaoIA.carregar()
    provedor = cfg.provedor_principal if qual == "principal" else cfg.provedor_secundario
    if not provedor or not cfg.chave(qual):
        raise IAIndisponivel("Escolha o provedor e cadastre a chave antes de testar.")
    try:
        modelos = provedores.listar_modelos(provedor, cfg.chave(qual))
    except provedores.ErroProvedor as erro:
        raise IAIndisponivel(str(erro)) from erro
    modelo = cfg.modelo_principal if qual == "principal" else cfg.modelo_secundario
    try:
        resposta = provedores.conversar(provedor, modelo, cfg.chave(qual),
                                        [{"role": "user", "content": "Responda apenas: OK"}], max_tokens=50)
    except provedores.ErroProvedor as erro:
        raise IAIndisponivel(f"A chave funciona, mas o modelo '{modelo}' falhou: {erro}") from erro
    return resposta, modelos
