"""
BACKUP DO BANCO (o "serviço": quem faz o trabalho de verdade).

Usado por:
  - python manage.py backup_banco          (você, no terminal ou no Agendador do Windows)
  - área interna > Painel                   (automático: se o último backup tiver mais de 24 h)
  - área interna > botão "Fazer backup agora"

Por que não copiar o arquivo com Ctrl+C / Ctrl+V?
  Se o site estiver gravando algo no exato momento, a cópia pode sair corrompida.
  A função .backup() do próprio SQLite copia de forma segura, mesmo com o site rodando.

O backup tem os mesmos dados do banco. CPFs, chaves de IA e conversas estão CIFRADOS:
sem a LIAH_FERNET_KEY ninguém lê. Por isso: NUNCA guarde o backup e o .env no mesmo lugar.
"""
import shutil
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.utils import timezone

PADRAO_MANTER = 10


class ErroBackup(Exception):
    pass


def pasta_backups():
    return Path(settings.DATABASES["default"]["NAME"]).parent / "backups"


def listar_backups():
    """Do mais antigo para o mais novo (o nome tem a data, então ordem alfabética = ordem de data)."""
    pasta = pasta_backups()
    return sorted(pasta.glob("liah-*.sqlite3")) if pasta.exists() else []


def ultimo_backup():
    backups = listar_backups()
    return backups[-1] if backups else None


def idade_do_ultimo_backup():
    """Há quanto tempo foi o último backup (timedelta), ou None se nunca houve."""
    ultimo = ultimo_backup()
    if ultimo is None:
        return None
    feito_em = datetime.fromtimestamp(ultimo.stat().st_mtime, tz=timezone.get_current_timezone())
    return timezone.now() - feito_em


def fazer_backup(manter=PADRAO_MANTER, copiar_para=None):
    """
    Copia o banco com segurança, confere a cópia e apaga os mais antigos.
    copiar_para: outra pasta para guardar uma 2ª cópia (ex.: pasta do OneDrive/Google Drive).
    Devolve (arquivo_criado, lista_de_removidos).
    """
    banco = Path(settings.DATABASES["default"]["NAME"])
    if not banco.exists():
        raise ErroBackup(f"Banco não encontrado: {banco}")

    pasta = pasta_backups()
    pasta.mkdir(exist_ok=True)
    destino = pasta / f"liah-{datetime.now():%Y%m%d-%H%M%S}.sqlite3"

    # closing() FECHA as conexões no fim (no Windows, arquivo aberto não pode ser apagado).
    with closing(sqlite3.connect(banco)) as origem, closing(sqlite3.connect(destino)) as copia:
        origem.backup(copia)
    with closing(sqlite3.connect(destino)) as copia:
        resultado = copia.execute("PRAGMA integrity_check").fetchone()[0]
    if resultado != "ok":
        destino.unlink()
        raise ErroBackup("A cópia saiu corrompida e foi apagada. Tente de novo.")

    if copiar_para:
        externa = Path(copiar_para)
        externa.mkdir(parents=True, exist_ok=True)
        shutil.copy2(destino, externa / destino.name)

    removidos = []
    if manter > 0:
        for antigo in listar_backups()[:-manter]:
            antigo.unlink()
            removidos.append(antigo.name)
    return destino, removidos


def backup_se_preciso(horas=24):
    """
    Backup AUTOMÁTICO sem tarefa agendada (o PythonAnywhere grátis não tem).
    Chamado quando a equipe abre o Painel: se o último tem mais de `horas`, faz um novo.
    Devolve o arquivo criado ou None. Nunca derruba a página: erro vira None.
    """
    # Banco que não é um arquivo (ex.: o banco temporário na MEMÓRIA dos testes): não há o que copiar.
    if not Path(settings.DATABASES["default"]["NAME"]).is_file():
        return None
    idade = idade_do_ultimo_backup()
    if idade is not None and idade < timedelta(hours=horas):
        return None
    try:
        destino, _ = fazer_backup()
        return destino
    except (ErroBackup, OSError, sqlite3.Error):
        import logging
        logging.getLogger(__name__).exception("Backup automático falhou")
        return None
