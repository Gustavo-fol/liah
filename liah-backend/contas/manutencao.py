"""
MANUTENÇÃO AUTOMÁTICA (faxina do banco).

O PythonAnywhere grátis não tem tarefa agendada, então, igual ao backup,
o Painel da equipe roda esta faxina no máximo 1 vez por dia:

  - apaga SESSÕES vencidas (cada login/visitante cria uma; sem faxina a tabela só cresce);
  - apaga REGISTROS DE SEGURANÇA com mais de 180 dias (LGPD: não guardar além do necessário).

Também dá para rodar na mão:  python manage.py manutencao
"""
from datetime import timedelta

from django.contrib.sessions.models import Session
from django.core.cache import cache
from django.utils import timezone

from .models import RegistroSeguranca

DIAS_REGISTROS = 180
CHAVE_ULTIMA = "liah:manutencao:ultima"


def fazer_manutencao():
    """Faz a faxina e devolve {"sessoes": n, "registros": n} com quantos itens saíram."""
    agora = timezone.now()
    sessoes, _ = Session.objects.filter(expire_date__lt=agora).delete()
    registros, _ = RegistroSeguranca.objects.filter(
        criado_em__lt=agora - timedelta(days=DIAS_REGISTROS)
    ).delete()
    cache.set(CHAVE_ULTIMA, agora.isoformat(), None)
    return {"sessoes": sessoes, "registros": registros}


def manutencao_se_preciso():
    """Roda a faxina se a última foi há mais de 1 dia. Devolve o resultado ou None."""
    # add() só grava se a chave NÃO existir: funciona como "trava" de 1 dia.
    if not cache.add("liah:manutencao:trava", True, 60 * 60 * 24):
        return None
    return fazer_manutencao()
