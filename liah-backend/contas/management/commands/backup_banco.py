"""
COMANDO: python manage.py backup_banco

  python manage.py backup_banco                      -> backup em liah-bd/backups/ (guarda os 10 últimos)
  python manage.py backup_banco --manter 30          -> guarda os 30 últimos
  python manage.py backup_banco --copiar-para "C:\\Users\\quarto\\OneDrive\\Liah-backups"
        -> também deixa uma cópia em outra pasta (ex.: uma pasta sincronizada na nuvem)

O trabalho de verdade está em contas/backup.py (o site usa a mesma função).
"""
from django.core.management.base import BaseCommand, CommandError

from contas.backup import PADRAO_MANTER, ErroBackup, fazer_backup


class Command(BaseCommand):
    help = "Faz um backup seguro do banco SQLite da Liah em liah-bd/backups/"

    def add_arguments(self, parser):
        parser.add_argument("--manter", type=int, default=PADRAO_MANTER,
                            help=f"Quantos backups manter (padrão: {PADRAO_MANTER})")
        parser.add_argument("--copiar-para", help="Pasta extra para uma 2ª cópia (ex.: OneDrive).")

    def handle(self, *args, **opcoes):
        try:
            destino, removidos = fazer_backup(opcoes["manter"], opcoes["copiar_para"])
        except ErroBackup as erro:
            raise CommandError(str(erro))
        self.stdout.write(self.style.SUCCESS(f"Backup criado: {destino.name}"))
        if opcoes["copiar_para"]:
            self.stdout.write(f"Cópia extra em: {opcoes['copiar_para']}")
        for nome in removidos:
            self.stdout.write(f"Backup antigo removido: {nome}")
