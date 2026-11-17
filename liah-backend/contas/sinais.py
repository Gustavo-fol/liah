"""
SINAIS (signals) = "avisos" que o Django dispara quando algo acontece.

Em vez de espalhar código de log em todo lugar, a gente "escuta" os avisos:
  user_logged_in     -> alguém entrou (no site OU no admin)
  user_logged_out    -> alguém saiu
  user_login_failed  -> alguém errou e-mail/senha

@receiver(sinal) liga a função ao aviso. Este arquivo é carregado em apps.py (ready).
"""
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver

from .auditoria import registrar_evento
from .models import RegistroSeguranca, Usuario

Tipo = RegistroSeguranca.Tipo


@receiver(user_logged_in)
def ao_entrar(sender, request, user, **kwargs):
    registrar_evento(Tipo.LOGIN_OK, request=request, usuario=user)


@receiver(user_logged_out)
def ao_sair(sender, request, user, **kwargs):
    if user is not None:
        registrar_evento(Tipo.LOGOUT, request=request, usuario=user)


@receiver(user_login_failed)
def ao_falhar(sender, credentials, request=None, **kwargs):
    # credentials já vem com a senha escondida pelo Django ("********").
    email = (credentials.get("username") or "").strip().lower()
    usuario = Usuario.objects.filter(email=email).first() if email else None
    # Se o e-mail não existe, NÃO guardamos o que foi digitado (pode ser até uma senha
    # digitada no campo errado).
    registrar_evento(Tipo.LOGIN_FALHOU, request=request, usuario=usuario)
