"""
DETECÇÃO DE RISCO = a rede de segurança da Liah.

Roda ANTES de qualquer IA e não depende de internet. Dois níveis:

  ALTO    -> fala explícita sobre se ferir ou tirar a própria vida.
             A Liah NÃO conversa normalmente: responde com o protocolo de crise (CVV 188).
  ATENCAO -> sinais "nas entrelinhas" (ideação passiva). Ex.: depois de falar do
             cachorro que morreu, "queria estar junto com ele".
             A Liah continua acolhendo, mas sempre oferece ajuda profissional.

IMPORTANTE:
  - Estas listas são um PONTO DE PARTIDA e precisam ser revisadas por um psicólogo.
  - Regras erram para os dois lados (falso positivo e falso negativo). Mais pra frente,
    a camada de ML (treinada com o psicólogo) ajuda a pegar o que as regras não pegam.
    Mas estas regras NUNCA saem: são a última barreira, mesmo se a IA falhar.
"""
from dataclasses import dataclass, field

from .texto import contem, normalizar

NENHUM = "nenhum"
ATENCAO = "atencao"
ALTO = "alto"

# Padrões em regex, sobre o texto JÁ normalizado (sem acento, minúsculo).
# \b = "borda de palavra"; (?! ...) = "desde que NÃO venha seguido de ..."
PADROES_ALTO = [
    r"\bme matar\b(?! de (rir|trabalhar|estudar|tanto))",
    r"\bsuicid",
    r"\btirar (a )?minha (propria )?vida\b",
    r"\bacabar com (a )?minha vida\b",
    r"\bquero morrer\b",
    r"\bvou morrer\b(?! de (rir|vergonha|fome|sono|tedio|saudade))",
    r"\bnao quero (mais )?viver\b",
    r"\bme (cortar|cortando|machucar|machucando|enforcar)\b",
    r"\bpular d[aeo] (predio|ponte|janela|viaduto)\b",
    r"\btomar todos os (remedios|comprimidos)\b",
    r"\boverdose\b",
]

PADROES_ATENCAO = [
    r"\bqueria (estar|ficar|ir) (junto )?com (ele|ela|eles|elas)\b",
    r"\bqueria ir junto\b",
    r"\b(seria|era) melhor se eu nao (existisse|estivesse aqui|tivesse nascido)\b",
    r"\bninguem (vai |iria )?sentir(ia)? (a )?minha falta\b",
    r"\bninguem (se )?importa(ria)? comigo\b",
    r"\bnao aguento mais\b",
    r"\bquero sumir\b",
    r"\bsumir (pra|para) sempre\b",
    r"\bdormir e nao acordar\b",
    r"\bnao vejo (mais )?saida\b",
    r"\bcansei de (tudo|viver)\b",
    r"\bnada (mais )?faz sentido\b",
    r"\bsou um peso\b",
    r"\b(estou|to|tou) me despedindo\b",
    r"\bdesistir de tudo\b",
    r"\bnao tenho (mais )?(motivo|razao) (pra|para) (viver|continuar)\b",
]

RESPOSTA_CRISE = (
    "Sinto muito que você esteja passando por isso. O que você está sentindo importa, "
    "e você não precisa enfrentar isso sozinho(a).\n\n"
    "Por favor, fale agora com alguém que pode te ajudar:\n"
    "• CVV: ligue 188 (24 horas, gratuito) ou acesse cvv.org.br\n"
    "• SAMU: 192, se você estiver em perigo agora\n"
    "• Ou vá ao pronto-socorro mais próximo\n\n"
    "Se puder, chame alguém de confiança para ficar com você. Eu continuo aqui."
)

NOTA_ATENCAO = (
    "\n\nPercebi que você pode estar passando por um momento muito difícil. "
    "Se em algum momento pensar em se machucar, ligue para o CVV no 188 (24h, gratuito). "
    "Conversar com um psicólogo também pode ajudar muito."
)


@dataclass
class AvaliacaoRisco:
    """dataclass = classe só para guardar dados, sem precisar escrever o __init__."""
    nivel: str = NENHUM
    motivos: list = field(default_factory=list)  # quais padrões bateram (para revisão)


def avaliar_risco(mensagem):
    texto = normalizar(mensagem)
    motivos = contem(texto, PADROES_ALTO)
    if motivos:
        return AvaliacaoRisco(ALTO, motivos)
    motivos = contem(texto, PADROES_ATENCAO)
    if motivos:
        return AvaliacaoRisco(ATENCAO, motivos)
    return AvaliacaoRisco()
