"""
python manage.py diagnosticar_email

Testa a conexão com o Gmail ETAPA POR ETAPA, para descobrir onde ela cai:
  1) conectar  2) cumprimentar (EHLO)  3) criptografar  4) fazer login
Testa as portas 587 (TLS) e 465 (SSL), por IPv4 e IPv6.
NÃO mostra a senha: só o tamanho dela e se tem espaços.
"""
import os
import smtplib
import socket
import ssl

from django.core.management.base import BaseCommand

HOST = "smtp.gmail.com"


class Command(BaseCommand):
    help = "Diagnóstico da conexão com o Gmail (não envia e-mail)."

    def handle(self, *args, **opcoes):
        usuario = os.environ.get("GMAIL_USUARIO", "")
        senha = os.environ.get("GMAIL_SENHA_APP", "")

        self.stdout.write("=== Conferindo o .env ===")
        self.stdout.write(f"GMAIL_USUARIO: {usuario or '(VAZIO!)'}")
        self.stdout.write(
            f"GMAIL_SENHA_APP: {len(senha)} caracteres "
            f"(o certo é 16) | tem espaço? {'SIM (tire!)' if ' ' in senha else 'não'} "
            f"| tem aspas? {'SIM (tire!)' if chr(34) in senha or chr(39) in senha else 'não'}"
        )

        for familia, nome_rede in ((socket.AF_INET, "IPv4"), (socket.AF_INET6, "IPv6")):
            for porta, modo in ((587, "TLS"), (465, "SSL")):
                self.stdout.write(f"\n=== Porta {porta} ({modo}) via {nome_rede} ===")
                self.testar(familia, porta, modo, usuario, senha)

    def testar(self, familia, porta, modo, usuario, senha):
        etapa = "conectar"
        original = socket.getaddrinfo

        # Força a rede escolhida (IPv4 ou IPv6) só durante este teste.
        def so_essa_familia(*a, **k):
            return [r for r in original(*a, **k) if r[0] == familia]

        socket.getaddrinfo = so_essa_familia
        try:
            contexto = ssl.create_default_context()
            if modo == "SSL":
                servidor = smtplib.SMTP_SSL(HOST, porta, timeout=15, context=contexto)
            else:
                servidor = smtplib.SMTP(HOST, porta, timeout=15)
            self.ok("1) conectou")

            etapa = "EHLO"
            servidor.ehlo()
            self.ok("2) EHLO respondeu")

            if modo == "TLS":
                etapa = "STARTTLS"
                servidor.starttls(context=contexto)
                servidor.ehlo()
                self.ok("3) STARTTLS (criptografia) ok")
            else:
                self.ok("3) SSL (criptografia) ok")

            etapa = "login"
            servidor.login(usuario, senha)
            self.ok("4) LOGIN OK -> este caminho funciona!")
            servidor.quit()
        except smtplib.SMTPAuthenticationError as erro:
            self.erro(f"falhou no {etapa}: SENHA/USUÁRIO recusados pelo Google ({erro.smtp_code})")
        except ssl.SSLError as erro:
            self.erro(f"falhou no {etapa}: problema de certificado/SSL -> {erro} "
                      "(antivírus inspecionando a conexão?)")
        except (OSError, smtplib.SMTPException) as erro:
            self.erro(f"falhou no {etapa}: {type(erro).__name__}: {erro}")
        finally:
            socket.getaddrinfo = original

    def ok(self, texto):
        self.stdout.write(self.style.SUCCESS("   " + texto))

    def erro(self, texto):
        self.stdout.write(self.style.ERROR("   " + texto))
