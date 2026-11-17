"""
PROVEDORES DE IA: como "falar" com cada API.

Cada provedor tem um jeito diferente de receber as mensagens e devolver a resposta.
Aqui a gente TRADUZ o nosso formato padrão
    [{"role": "system"|"user"|"assistant", "content": "..."}]
para o formato de cada um. O resto do sistema não precisa saber qual é qual.

Feito só com a biblioteca padrão (urllib), sem instalar nada.
No PythonAnywhere grátis, o urllib usa sozinho o "proxy" deles (variável https_proxy).
"""
import json
import logging
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

TEMPO_LIMITE = 15  # segundos esperando a IA antes de desistir (o PythonAnywhere grátis tem 1 só "worker": esperar muito trava o site todo)


class ErroProvedor(Exception):
    """Falha ao falar com a IA (chave errada, sem crédito, fora do ar, bloqueio...)."""


def _post(url, cabecalhos, corpo):
    pedido = urllib.request.Request(
        url, data=json.dumps(corpo).encode(), method="POST",
        headers={"Content-Type": "application/json", **cabecalhos},
    )
    return _abrir(pedido)


def _get(url, cabecalhos):
    return _abrir(urllib.request.Request(url, headers=cabecalhos))


def _abrir(pedido, bruto=False):
    """bruto=True devolve os BYTES da resposta (ex.: o áudio da voz) em vez de ler JSON."""
    try:
        with urllib.request.urlopen(pedido, timeout=TEMPO_LIMITE) as resposta:
            return resposta.read() if bruto else json.load(resposta)
    except urllib.error.HTTPError as erro:
        # Lemos a mensagem de erro do provedor para mostrar na área interna.
        try:
            detalhe = json.load(erro).get("error", {})
            texto = detalhe.get("message", "") if isinstance(detalhe, dict) else str(detalhe)
        except ValueError:
            texto = ""
        mensagens = {
            400: "Pedido recusado (confira o nome do modelo).",
            401: "Chave de API inválida.",
            403: "Acesso negado (chave sem permissão ou região bloqueada).",
            404: "Modelo não encontrado (confira o nome do modelo).",
            429: "Limite atingido ou sem crédito na conta da API.",
        }
        logger.warning("Provedor de IA respondeu %s", erro.code)  # nunca loga o conteúdo
        raise ErroProvedor(f"{mensagens.get(erro.code, f'Erro {erro.code} do provedor.')} {texto[:200]}".strip()) from erro
    except (urllib.error.URLError, TimeoutError, ValueError) as erro:
        raise ErroProvedor("Não foi possível conectar com a IA (internet ou provedor fora do ar).") from erro


# ============================================================ OpenAI

def _openai_chat(modelo, chave, mensagens, max_tokens, json_saida):
    corpo = {
        "model": modelo,
        "messages": mensagens,
        # max_completion_tokens: o limite de tamanho da resposta (aceito pelos modelos atuais)
        "max_completion_tokens": max_tokens,
    }
    if json_saida:
        corpo["response_format"] = {"type": "json_object"}
    dados = _post("https://api.openai.com/v1/chat/completions", {"Authorization": f"Bearer {chave}"}, corpo)
    try:
        texto = dados["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError) as erro:
        raise ErroProvedor("Resposta inesperada da OpenAI.") from erro
    if not texto.strip():
        raise ErroProvedor("A OpenAI devolveu uma resposta vazia.")
    return texto.strip()


def _openai_modelos(chave):
    dados = _get("https://api.openai.com/v1/models", {"Authorization": f"Bearer {chave}"})
    return sorted(m["id"] for m in dados.get("data", []) if m.get("id", "").startswith(("gpt", "o")))


# ============================================================ Google Gemini

def _gemini_chat(modelo, chave, mensagens, max_tokens, json_saida):
    # O Gemini separa a instrução de sistema e chama o papel do assistente de "model".
    sistema = "\n\n".join(m["content"] for m in mensagens if m["role"] == "system")
    conteudos = [
        {"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]}
        for m in mensagens if m["role"] != "system"
    ]
    corpo = {"contents": conteudos, "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.8}}
    if sistema:
        corpo["system_instruction"] = {"parts": [{"text": sistema}]}
    if json_saida:
        corpo["generationConfig"]["responseMimeType"] = "application/json"

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"
    dados = _post(url, {"x-goog-api-key": chave}, corpo)

    candidatos = dados.get("candidates") or []
    if not candidatos:
        motivo = (dados.get("promptFeedback") or {}).get("blockReason", "")
        raise ErroProvedor(f"O Gemini bloqueou o pedido pelo filtro de segurança dele. {motivo}".strip())
    partes = (candidatos[0].get("content") or {}).get("parts") or []
    texto = "".join(p.get("text", "") for p in partes).strip()
    if not texto:
        raise ErroProvedor(f"O Gemini não devolveu texto (motivo: {candidatos[0].get('finishReason', '?')}).")
    return texto


def _gemini_modelos(chave):
    dados = _get("https://generativelanguage.googleapis.com/v1beta/models?pageSize=200", {"x-goog-api-key": chave})
    return sorted(
        m["name"].removeprefix("models/") for m in dados.get("models", [])
        if "generateContent" in m.get("supportedGenerationMethods", [])
    )


# ============================================================ escolha do provedor

_CHAT = {"openai": _openai_chat, "gemini": _gemini_chat}
_MODELOS = {"openai": _openai_modelos, "gemini": _gemini_modelos}


def conversar(provedor, modelo, chave, mensagens, max_tokens=600, json_saida=False):
    if provedor not in _CHAT:
        raise ErroProvedor("Provedor de IA desconhecido.")
    return _CHAT[provedor](modelo, chave, mensagens, max_tokens, json_saida)


def listar_modelos(provedor, chave):
    if provedor not in _MODELOS:
        raise ErroProvedor("Provedor de IA desconhecido.")
    return _MODELOS[provedor](chave)


# ============================================================ VOZ (OpenAI): para o robô e o Raspberry Pi
# O Chromium do Raspberry Pi não tem o reconhecimento de voz do Google, então a fala
# vai para o SERVIDOR da Liah, que usa a API de áudio da OpenAI.

MODELO_TRANSCRICAO = "gpt-4o-mini-transcribe"
MODELO_FALA = "gpt-4o-mini-tts"
VOZ = "nova"


def transcrever(chave, audio, nome_arquivo="fala.webm", tipo="audio/webm"):
    """Áudio (bytes) -> texto em português. Usa multipart/form-data, montado à mão (sem bibliotecas)."""
    import uuid
    fronteira = uuid.uuid4().hex
    partes = []
    for campo, valor in (("model", MODELO_TRANSCRICAO), ("language", "pt"), ("response_format", "json")):
        partes.append(f'--{fronteira}\r\nContent-Disposition: form-data; name="{campo}"\r\n\r\n{valor}\r\n'.encode())
    partes.append(
        f'--{fronteira}\r\nContent-Disposition: form-data; name="file"; filename="{nome_arquivo}"\r\n'
        f"Content-Type: {tipo}\r\n\r\n".encode() + audio + b"\r\n"
    )
    partes.append(f"--{fronteira}--\r\n".encode())
    pedido = urllib.request.Request(
        "https://api.openai.com/v1/audio/transcriptions", data=b"".join(partes), method="POST",
        headers={"Authorization": f"Bearer {chave}", "Content-Type": f"multipart/form-data; boundary={fronteira}"},
    )
    return (_abrir(pedido).get("text") or "").strip()


def falar(chave, texto):
    """Texto -> áudio MP3 (bytes) com a voz da Liah."""
    pedido = urllib.request.Request(
        "https://api.openai.com/v1/audio/speech", method="POST",
        data=json.dumps({
            "model": MODELO_FALA, "voice": VOZ, "input": texto, "response_format": "mp3",
            "instructions": "Fale em português do Brasil, com voz calma, acolhedora e gentil.",
        }).encode(),
        headers={"Authorization": f"Bearer {chave}", "Content-Type": "application/json"},
    )
    return _abrir(pedido, bruto=True)
