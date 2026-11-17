"""
COMANDO: python manage.py manutencao

Apaga sessões vencidas e registros de segurança com mais de 180 dias.
(O Painel da equipe já faz isso sozinho 1 vez por dia; este comando é para rodar na mão.)
"""
from django.core.management.base import BaseCommand

from contas.manutencao import DIAS_REGISTROS, fazer_manutencao


class Command(BaseCommand):
    help = "Faxina: sessões vencidas e registros de segurança antigos."

    def handle(self, *args, **opcoes):
        r = fazer_manutencao()
        self.stdout.write(self.style.SUCCESS(
            f"Pronto: {r['sessoes']} sessão(ões) vencida(s) e "
            f"{r['registros']} registro(s) com mais de {DIAS_REGISTROS} dias apagados."
        ))
