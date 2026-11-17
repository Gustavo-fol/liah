"""
COMANDO: python manage.py rotacionar_chave

TROCA DA CHAVE DE CRIPTOGRAFIA (faça se desconfiar que a LIAH_FERNET_KEY vazou):

  1) Faça um backup:              python manage.py backup_banco
  2) Gere uma chave nova:         python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
  3) No .env:
        LIAH_FERNET_KEY=<a NOVA>
        LIAH_FERNET_KEYS_ANTIGAS=<a ANTIGA>
  4) Rode:                        python manage.py rotacionar_chave
  5) Deu tudo certo? Apague a linha LIAH_FERNET_KEYS_ANTIGAS do .env
     e guarde a chave NOVA no Bitwarden (no lugar da antiga).

O comando decifra cada dado com a chave antiga e cifra de novo com a nova:
CPFs, mensagens das conversas e as chaves das IAs. Tudo numa transação:
se algo falhar no meio, nada é alterado.
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from contas.models import AutorizacaoResponsavel, Usuario
from contas.seguranca import recifrar
from nucleo.models import ConfiguracaoIA, Mensagem

# (model, [campos cifrados])
ALVOS = [
    (Usuario, ["cpf_cifrado"]),
    (AutorizacaoResponsavel, ["cpf_cifrado"]),
    (Mensagem, ["texto_cifrado"]),
    (ConfiguracaoIA, ["chave_principal_cifrada", "chave_secundaria_cifrada"]),
]


class Command(BaseCommand):
    help = "Recifra todos os dados com a LIAH_FERNET_KEY atual (rotação de chave)."

    def handle(self, *args, **opcoes):
        total = 0
        try:
            with transaction.atomic():
                for model, campos in ALVOS:
                    feitos = 0
                    # iterator(): lê aos poucos, sem carregar a tabela inteira na memória
                    for obj in model.objects.all().iterator(chunk_size=500):
                        mudou = []
                        for campo in campos:
                            valor = getattr(obj, campo)
                            if valor:
                                setattr(obj, campo, recifrar(valor))
                                mudou.append(campo)
                        if mudou:
                            # .update() direto: não dispara save() (nem o auto_now das datas)
                            model.objects.filter(pk=obj.pk).update(**{c: getattr(obj, c) for c in mudou})
                            feitos += 1
                    self.stdout.write(f"  {model._meta.verbose_name_plural}: {feitos}")
                    total += feitos
        except Exception as erro:   # InvalidToken = alguma chave errada no .env
            raise CommandError(
                f"Nada foi alterado. Confira LIAH_FERNET_KEY e LIAH_FERNET_KEYS_ANTIGAS no .env. ({erro!r})"
            )
        self.stdout.write(self.style.SUCCESS(
            f"Pronto: {total} registro(s) recifrado(s). Agora apague LIAH_FERNET_KEYS_ANTIGAS do .env."
        ))
