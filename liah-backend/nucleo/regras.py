"""
REGRAS FIXAS (o "pouco hardcode").

Herdeiro do seu dicionário de respostas antigo (saudacoes, identidade, status):
cada regra tem padrões, uma resposta e a EXPRESSÃO do rosto (para o display de LED).

Saudação, despedida e agradecimento só valem se forem a MENSAGEM INTEIRA
(o "^...$" do regex): "oi" é saudação, mas "oi, meu cachorro morreu" tem que ir
para a IA, que vai acolher de verdade.
"""
from dataclasses import dataclass

from .texto import contem, normalizar

MAX_PALAVRAS_REGRA = 6


@dataclass
class RespostaRegra:
    nome: str
    texto: str
    expressao: str


REGRAS = [
    {
        "nome": "saudacao",
        "padroes": [r"^(oi|ola|oie|eai|e ai|hey|bom dia|boa tarde|boa noite|salve)( liah)?( tudo bem| como vai| td bem| tudo bom)?( liah)?$"],
        "resposta": "Olá! Eu sou a Liah. Como você está se sentindo hoje?",
        "expressao": "feliz",
    },
    {
        "nome": "identidade",
        "padroes": [r"\bquem (e|eh) (voce|vc|a liah)\b", r"\bqual (e |eh )?(o )?seu nome\b", r"\bo que (e|eh) (a )?liah\b"],
        "resposta": (
            "Eu sou a Liah, um protótipo de robô interativo com inteligência artificial, "
            "criado para estudar a comunicação entre pessoas e máquinas e oferecer um apoio "
            "emocional inicial. Não substituo um psicólogo, mas posso te ouvir."
        ),
        "expressao": "feliz",
    },
    {
        "nome": "capacidades",
        "padroes": [r"\bo que (voce|vc) (faz|sabe fazer|consegue fazer)\b", r"^ajuda$", r"\bcomo (voce|vc) funciona\b"],
        "resposta": (
            "Atualmente eu consigo conversar com você, guardar o histórico das nossas conversas "
            "e perceber quando alguém pode precisar de ajuda profissional. No futuro, quero "
            "conversar por voz e ter um corpo robótico."
        ),
        "expressao": "atenta",
    },
    {
        "nome": "status",
        "padroes": [r"\b(voce|vc) (esta|ta) pronta\b"],
        "resposta": "Ainda estou em desenvolvimento, mas esta versão já é uma parte importante da minha evolução.",
        "expressao": "feliz",
    },
    {
        "nome": "despedida",
        "padroes": [r"^(tchau|ate logo|ate mais|ate amanha|falou|flw|adeus)( liah)?$"],
        "resposta": "Até logo! Cuide-se, e volte quando quiser conversar.",
        "expressao": "feliz",
    },
    {
        "nome": "agradecimento",
        "padroes": [r"^(muito )?(obrigad[oa]|valeu|vlw)( liah)?$"],
        "resposta": "Eu que agradeço por conversar comigo. Estou aqui sempre que precisar.",
        "expressao": "feliz",
    },
]


def responder(mensagem):
    """Devolve uma RespostaRegra ou None (None = nenhuma regra serve)."""
    texto = normalizar(mensagem)
    if not texto or len(texto.split()) > MAX_PALAVRAS_REGRA:
        return None
    for regra in REGRAS:
        if contem(texto, regra["padroes"]):
            return RespostaRegra(regra["nome"], regra["resposta"], regra["expressao"])
    return None
