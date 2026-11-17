"""
python manage.py testar_email seu-email@exemplo.com

Manda um e-mail de teste usando a configuração atual (console ou gmail).
Ótimo para descobrir se a senha de app está certa ANTES de testar o cadastro.
"""
from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Envia um e-mail de teste para conferir a configuração do Gmail."

    def add_arguments(self, parser):
        parser.add_argument("destino", help="E-mail que vai receber o teste")

    def handle(self, *args, **opcoes):
        modo = settings.LIAH_EMAIL_MODO
        self.stdout.write(f"Modo de e-mail: {modo}  |  Remetente: {settings.DEFAULT_FROM_EMAIL}")
        try:
            send_mail(
                "Liah - e-mail de teste",
                "Se você recebeu esta mensagem, o envio de e-mails da Liah está funcionando.",
                None,
                [opcoes["destino"]],
            )
        except OSError as erro:
            raise CommandError(
                f"Falhou: {erro}\n"
                "Confira: verificação em 2 etapas ligada, senha de APP (16 letras, sem espaços) "
                "e GMAIL_USUARIO certo no .env."
            )
        self.stdout.write(self.style.SUCCESS(f"Enviado para {opcoes['destino']}!"))
