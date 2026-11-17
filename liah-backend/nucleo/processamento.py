"""
PROCESSAMENTO = o coração da Liah.

Evolução direta do seu chatbot de dúvidas: as funções respostabot_basica() e
processar_mensagem() continuam aqui, com os mesmos nomes e o mesmo papel.
O que mudou é que processar_mensagem() agora decide ENTRE várias fontes de resposta,
na ordem de segurança:

  1) risco ALTO  -> protocolo de crise (fixo, nunca passa pela IA)
  2) regra fixa  -> saudação, identidade, ajuda... (só se não houver risco)
  3) IA online   -> conversa natural, com o histórico
  4) básica      -> respostabot_basica(), se a IA estiver fora

Quem usa esta função: a página de chat, a API, o comando de terminal e,
no futuro, o robô (Raspberry Pi). Todos passam pelo MESMO cérebro.
"""
import re
from dataclasses import dataclass, field

from . import ia, regras
from .risco import ALTO, ATENCAO, NENHUM, NOTA_ATENCAO, RESPOSTA_CRISE, avaliar_risco


@dataclass
class Resposta:
    texto: str
    origem: str        # "crise" | "regra" | "ia" | "basica"
    risco: str         # "nenhum" | "atencao" | "alto"
    expressao: str     # rosto no display de LED: neutra, feliz, atenta, acolhedora, preocupada
    motivos_risco: list = field(default_factory=list)


def respostabot_basica(mensagem):
    """
    Resposta fixa (a do seu chatbot original).
    Continua existindo como RESERVA, quando a IA online não estiver disponível.
    """
    return (
        "Ainda estou aprendendo, mas estou aqui com você. "
        "Pode me contar mais sobre o que está sentindo?"
    )


# FILTRO DE SAÍDA: última barreira antes de a resposta da IA chegar à pessoa.
# A IA foi instruída a não indicar remédio, mas IA às vezes "escapa". Se a resposta
# trouxer DOSE de remédio (ex.: "tome 2 comprimidos", "50 mg"), trocamos por um texto seguro.
_DOSE = re.compile(
    r"\b\d+([.,]\d+)?\s*(mg|mcg|µg|ml|g|gotas?|comprimidos?|c[áa]psulas?|pílulas?)\b"
    r"|\b(tome|tomar|tomando)\s+(\d+|um|uma|dois|duas|tr[êe]s|meio|meia)\s+(comprimido|c[áa]psula|gota|p[íi]lula)",
    re.IGNORECASE,
)
RESPOSTA_SEM_DOSE = (
    "Sobre remédios e doses, quem pode orientar com segurança é um médico ou farmacêutico, "
    "e eu não posso indicar nenhum. Se for urgente, ligue 192 (SAMU). "
    "Se quiser, posso continuar aqui com você conversando sobre como está se sentindo."
)


def filtrar_saida(texto):
    """Devolve o texto da IA, ou a resposta segura se ele trouxer dose de medicamento."""
    return RESPOSTA_SEM_DOSE if _DOSE.search(texto or "") else texto


def processar_mensagem(mensagem, historico=None, perfil="usuario"):
    """
    Função central da Liah.

    mensagem:  o texto que a pessoa escreveu (ou falou)
    historico: lista de {"autor": "usuario"|"liah", "texto": "..."} da conversa atual
    perfil:    "usuario" (logado), "menor" (logado, 12-17 anos) ou "visitante" (sem conta)
    devolve:   um objeto Resposta
    """
    historico = historico or []

    # 1) Rede de segurança: sempre primeiro.
    risco = avaliar_risco(mensagem)
    if risco.nivel == ALTO:
        return Resposta(RESPOSTA_CRISE, "crise", ALTO, "preocupada", risco.motivos)

    # 2) Regras fixas: só quando não há nenhum sinal de risco.
    if risco.nivel == NENHUM:
        regra = regras.responder(mensagem)
        if regra:
            return Resposta(regra.texto, "regra", NENHUM, regra.expressao)

    # 3) IA online, com 4) a resposta básica como reserva.
    try:
        texto = filtrar_saida(ia.gerar_resposta(mensagem, historico, risco.nivel, perfil))
        origem = "ia"
    except ia.IAIndisponivel:
        texto = respostabot_basica(mensagem)
        origem = "basica"

    if risco.nivel == ATENCAO:
        # Garante o caminho de ajuda mesmo se a IA esquecer de mencionar.
        if "188" not in texto:
            texto += NOTA_ATENCAO
        return Resposta(texto, origem, ATENCAO, "acolhedora", risco.motivos)

    return Resposta(texto, origem, NENHUM, "atenta")
