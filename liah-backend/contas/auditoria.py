"""
AUDITORIA = o "diário de bordo" de segurança da Liah.

Registra eventos importantes (login, erro de senha, bloqueio, saída, exclusão de conta)
com data, hora e IP. Serve para:
  - descobrir ataques (ex.: 50 erros de senha seguidos numa conta)
  - investigar um incidente (a LGPD exige que você saiba o que aconteceu)
  - cumprir o Marco Civil da Internet, que manda guardar registros de acesso

Nunca guardamos aqui o que a pessoa digitou na senha, nem o conteúdo das conversas.
"""
from django.conf import settings

from .models import RegistroSeguranca


def ip_do_pedido(request):
    """
    REMOTE_ADDR = o IP de quem fez o pedido (certo no seu PC).

    No servidor, o pedido passa por um proxy antes de chegar ao Django, e o REMOTE_ADDR
    vira o IP do proxy (igual para todo mundo). O proxy coloca o IP real num cabeçalho,
    configurado em LIAH_IP_HEADER no .env do servidor.
    Só use um cabeçalho que o SEU proxy preenche: cabeçalhos vindos do visitante
    (como X-Forwarded-For) podem ser falsificados.
    """
    if request is None:
        return None
    if settings.LIAH_IP_HEADER:
        ip = request.META.get(settings.LIAH_IP_HEADER, "").split(",")[0].strip()
        if ip:
            return ip
    return request.META.get("REMOTE_ADDR") or None


def registrar_evento(tipo, request=None, usuario=None, detalhe=""):
    # usuario.pk vazio = conta que acabou de ser apagada; não dá pra ligar o registro a ela.
    if usuario is not None and not getattr(usuario, "pk", None):
        usuario = None
    RegistroSeguranca.objects.create(
        tipo=tipo,
        usuario=usuario,
        ip=ip_do_pedido(request),
        detalhe=detalhe[:255],
    )
