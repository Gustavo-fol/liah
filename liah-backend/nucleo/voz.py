"""
VOZ PELO SERVIDOR (para o robô / Raspberry Pi e navegadores sem reconhecimento de voz).

  POST /api/v1/voz/transcrever/  -> manda o áudio gravado (campo "audio"), recebe {"texto": "..."}
  POST /api/v1/voz/falar/        -> manda {"texto": "..."}, recebe o áudio MP3 da Liah

Usa a chave da OpenAI cadastrada na área interna > IA (principal ou secundária, a que for OpenAI).
O áudio NÃO é guardado: passa pela memória, vai para a OpenAI e é descartado.

Proteções:
  - limite por pessoa/rede (cada chamada custa crédito da API);
  - tamanho máximo do áudio e do texto;
  - CSRF igual ao resto da API (o JavaScript manda o X-CSRFToken).
"""
import json

from django.core.cache import cache
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_POST

from contas.auditoria import ip_do_pedido

from . import provedores
from .models import ConfiguracaoIA

AUDIO_MAXIMO = 5 * 1024 * 1024    # 5 MB (~1 minuto de fala)
TEXTO_MAXIMO = 1200               # caracteres lidos em voz alta por vez
LIMITE_POR_MINUTO = 12
TIPOS_ACEITOS = ("audio/webm", "audio/ogg", "audio/wav", "audio/x-wav", "audio/mpeg", "audio/mp4", "audio/m4a")


def _erro(mensagem, status):
    return JsonResponse({"erro": mensagem}, status=status)


def _chave_openai():
    """A chave da OpenAI cadastrada (principal primeiro, depois a secundária)."""
    cfg = ConfiguracaoIA.carregar()
    if not cfg.ativa:
        return ""
    if cfg.provedor_principal == "openai" and cfg.chave_principal_cifrada:
        return cfg.chave("principal")
    if cfg.provedor_secundario == "openai" and cfg.chave_secundaria_cifrada:
        return cfg.chave("secundaria")
    return ""


def _passou_do_limite(request):
    quem = request.user.pk if request.user.is_authenticated else (ip_do_pedido(request) or "-")
    if request.user.is_authenticated and request.user.is_staff:
        return False
    chave = f"liah:voz:{quem}"
    cache.add(chave, 0, 60)
    try:
        return cache.incr(chave) > LIMITE_POR_MINUTO
    except ValueError:
        cache.set(chave, 1, 60)
        return False


@require_POST
def transcrever(request):
    arquivo = request.FILES.get("audio")
    if not arquivo:
        return _erro("Envie o áudio no campo 'audio'.", 400)
    if arquivo.size > AUDIO_MAXIMO:
        return _erro("Áudio muito longo. Fale por até 1 minuto.", 400)
    tipo = (arquivo.content_type or "").split(";")[0]
    if tipo not in TIPOS_ACEITOS:
        return _erro("Formato de áudio não aceito.", 400)
    if _passou_do_limite(request):
        return _erro("Muitas falas seguidas. Espere um minuto.", 429)
    chave = _chave_openai()
    if not chave:
        return _erro("A voz pelo servidor precisa de uma chave da OpenAI (área interna > IA).", 503)
    try:
        texto = provedores.transcrever(chave, arquivo.read(), arquivo.name or "fala.webm", tipo)
    except provedores.ErroProvedor:
        return _erro("Não consegui entender o áudio agora. Tente de novo ou digite.", 502)
    return JsonResponse({"texto": texto})


@require_POST
def falar(request):
    try:
        texto = str(json.loads(request.body or "{}").get("texto", "")).strip()
    except json.JSONDecodeError:
        return _erro("Corpo do pedido não é um JSON válido.", 400)
    if not texto:
        return _erro("Mande um texto.", 400)
    texto = texto[:TEXTO_MAXIMO]
    if _passou_do_limite(request):
        return _erro("Muitas falas seguidas. Espere um minuto.", 429)
    chave = _chave_openai()
    if not chave:
        return _erro("A voz pelo servidor precisa de uma chave da OpenAI (área interna > IA).", 503)
    try:
        audio = provedores.falar(chave, texto)
    except provedores.ErroProvedor:
        return _erro("Não consegui gerar a voz agora.", 502)
    resposta = HttpResponse(audio, content_type="audio/mpeg")
    resposta["Cache-Control"] = "no-store"   # a fala pode ter conteúdo pessoal: não fica guardada
    return resposta
