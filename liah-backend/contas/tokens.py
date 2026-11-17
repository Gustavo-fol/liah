"""
TOKEN do link "confirme seu e-mail".

O Django já tem um gerador de tokens seguro (o mesmo do "esqueci minha senha").
Ele assina com a SECRET_KEY e tem validade (PASSWORD_RESET_TIMEOUT, padrão 3 dias).
Nós só dizemos QUAIS dados entram na assinatura: se algum mudar, o link morre.
Como email_confirmado entra na conta, o link deixa de funcionar depois de usado.
"""
from django.contrib.auth.tokens import PasswordResetTokenGenerator


class ConfirmacaoEmailTokenGenerator(PasswordResetTokenGenerator):
    key_salt = "liah.contas.ConfirmacaoEmailTokenGenerator"

    def _make_hash_value(self, user, timestamp):
        return f"{user.pk}{user.email}{user.email_confirmado}{timestamp}"


token_confirmacao_email = ConfirmacaoEmailTokenGenerator()
