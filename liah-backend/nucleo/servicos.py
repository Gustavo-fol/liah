"""
SERVIÇOS do núcleo: liga o cérebro (processamento.py) ao banco de dados.
A API, a página de chat e o robô chamam conversar(); ninguém mexe no banco direto.
"""
import logging

from django.db import transaction

from .models import Conversa, Mensagem
from .processamento import processar_mensagem
from .risco import ALTO

logger = logging.getLogger(__name__)

# Quantas mensagens anteriores a Liah "lembra" a cada resposta.
# Mais = mais contexto, mas a IA online fica mais cara e mais lenta.
LIMITE_HISTORICO = 20


def historico_da_conversa(conversa):
    ultimas = list(conversa.mensagens.order_by("-criada_em")[:LIMITE_HISTORICO])
    ultimas.reverse()  # do mais antigo para o mais novo
    return [{"autor": m.autor, "texto": m.texto} for m in ultimas]


def conversar(usuario, texto, conversa=None):
    """Recebe a mensagem, gera a resposta, salva as duas e devolve (conversa, resposta)."""
    if conversa is None:
        conversa = Conversa.objects.create(usuario=usuario)

    # Adolescente (12-17) recebe um cuidado extra no prompt da IA.
    idade = getattr(usuario, "idade", None)
    perfil = "menor" if idade is not None and idade < 18 else "usuario"
    resposta = processar_mensagem(texto, historico_da_conversa(conversa), perfil=perfil)

    with transaction.atomic():
        pergunta = Mensagem(conversa=conversa, autor=Mensagem.Autor.USUARIO, risco=resposta.risco)
        pergunta.texto = texto
        pergunta.save()

        retorno = Mensagem(
            conversa=conversa, autor=Mensagem.Autor.LIAH, origem=resposta.origem, risco=resposta.risco
        )
        retorno.texto = resposta.texto
        retorno.save()

        conversa.save(update_fields=["atualizada_em"])

    # O navegador precisa do número da resposta para a pessoa poder avaliar (👍/👎).
    resposta.mensagem_id = retorno.pk

    if resposta.risco == ALTO:
        # No log vai SÓ o número da conversa, nunca o texto.
        logger.warning("Risco ALTO detectado na conversa #%s", conversa.pk)

    return conversa, resposta


def duvidas_repetidas(mensagens):
    """
    A sua lógica original do chatbot de dúvidas: o que foi perguntado mais de uma vez.
    Vai ser útil para descobrir quais regras/respostas faltam na Liah.
    """
    return {m for m in mensagens if mensagens.count(m) > 1}
