"""
LIMITADOR DE TENTATIVAS (proteção contra "força bruta").

Força bruta = um robô tentando milhares de senhas até acertar.
Regra da Liah: 5 erros -> bloqueia por 15 minutos.

Onde guardamos a contagem? No CACHE do Django: uma memória rápida e temporária
(cada valor tem prazo de validade e some sozinho). Não precisa de tabela no banco.
"""
from django.core.cache import cache

from .seguranca import gerar_hmac

MAX_TENTATIVAS = 5
BLOQUEIO_SEGUNDOS = 15 * 60


def _chave(tipo, identificador, ip=""):
    # Usamos o HMAC do e-mail na chave: nem no cache o e-mail aparece em texto puro.
    return f"liah:tentativas:{tipo}:{gerar_hmac(identificador.lower())}:{ip or '-'}"


def esta_bloqueado(tipo, identificador, ip=""):
    return cache.get(_chave(tipo, identificador, ip), 0) >= MAX_TENTATIVAS


def registrar_falha(tipo, identificador, ip=""):
    chave = _chave(tipo, identificador, ip)
    # add() só cria se ainda não existir (começa em 0, com validade de 15 min).
    cache.add(chave, 0, BLOQUEIO_SEGUNDOS)
    try:
        # incr() soma 1 sem mexer na validade: a janela conta a partir do 1º erro.
        return cache.incr(chave)
    except ValueError:  # a chave expirou bem nesse instante
        cache.set(chave, 1, BLOQUEIO_SEGUNDOS)
        return 1


def limpar(tipo, identificador, ip=""):
    """Acertou a senha: zera a contagem."""
    cache.delete(_chave(tipo, identificador, ip))
