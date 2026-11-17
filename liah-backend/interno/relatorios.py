"""
RELATÓRIOS da área interna: só NÚMEROS, nunca o conteúdo das conversas.

Cada função devolve dados prontos para a página (gráficos) e para as planilhas (CSV).
Técnica principal: TruncDate("campo") agrupa os registros por DIA no próprio banco,
e Count() conta quantos tem em cada dia. O banco faz a conta, não o Python (mais rápido).
"""
import csv
import platform
from datetime import datetime, timedelta

import django
from django.conf import settings
from django.db.models import Count
from django.db.models.functions import TruncDate
from django.http import HttpResponse
from django.utils import timezone

from contas.models import Consentimento, RegistroSeguranca, Usuario, calcular_idade
from nucleo.models import ConfiguracaoIA, Conversa, ExemploTreino, Mensagem, RegraDicionario

PERIODOS = (7, 30, 90)


def periodo(request):
    """Lê ?dias= da URL, aceitando só os valores permitidos."""
    try:
        dias = int(request.GET.get("dias", 30))
    except ValueError:
        dias = 30
    return dias if dias in PERIODOS else 30


def _datas(dias):
    hoje = timezone.localdate()
    return [hoje - timedelta(days=i) for i in range(dias - 1, -1, -1)]


def _inicio(dias):
    return timezone.now() - timedelta(days=dias)


def _por_dia(queryset, campo, dias, contar="pk", distinto=False):
    """{data: quantidade} agrupando pelo dia do campo de data."""
    linhas = (
        queryset.filter(**{f"{campo}__gte": _inicio(dias)})
        .annotate(dia=TruncDate(campo))
        .values("dia")
        .annotate(n=Count(contar, distinct=distinto))
    )
    return {linha["dia"]: linha["n"] for linha in linhas}


# ============================================================ SÉRIES POR DIA

def series_diarias(dias):
    msgs_usuario = Mensagem.objects.filter(autor=Mensagem.Autor.USUARIO)
    eventos = RegistroSeguranca.objects.all()
    brutos = {
        "novos_usuarios": _por_dia(Usuario.objects.all(), "date_joined", dias),
        "conversas": _por_dia(Conversa.objects.all(), "criada_em", dias),
        "mensagens": _por_dia(msgs_usuario, "criada_em", dias),
        "usuarios_ativos": _por_dia(msgs_usuario, "criada_em", dias, contar="conversa__usuario", distinto=True),
        "alertas_atencao": _por_dia(msgs_usuario.filter(risco="atencao"), "criada_em", dias),
        "alertas_alto": _por_dia(msgs_usuario.filter(risco="alto"), "criada_em", dias),
        "logins_ok": _por_dia(eventos.filter(tipo="login_ok"), "criado_em", dias),
        "logins_falhos": _por_dia(eventos.filter(tipo__in=["login_falhou", "login_bloqueado"]), "criado_em", dias),
    }
    return [{"dia": d, **{nome: valores.get(d, 0) for nome, valores in brutos.items()}} for d in _datas(dias)]


def grafico(series, campo):
    """Prepara as barras: cada dia vira {dia, n, pct} (pct = altura da barra em %)."""
    maior = max((linha[campo] for linha in series), default=0) or 1
    return [{"dia": d["dia"], "n": d[campo], "pct": round(d[campo] * 100 / maior)} for d in series]


# ============================================================ RESUMOS

FAIXAS = [(12, 17, "12 a 17"), (18, 24, "18 a 24"), (25, 34, "25 a 34"), (35, 49, "35 a 49"), (50, 200, "50 ou mais")]


def faixa_etaria(data_nascimento):
    if not data_nascimento:
        return "sem data"
    idade = calcular_idade(data_nascimento)
    if idade < 12:
        return "menor de 12"
    for minimo, maximo, nome in FAIXAS:
        if minimo <= idade <= maximo:
            return nome
    return "sem data"


def perfil_usuarios():
    usuarios = Usuario.objects.filter(is_staff=False)
    faixas = {}
    for nasc in usuarios.values_list("data_nascimento", flat=True):
        nome = faixa_etaria(nasc)
        faixas[nome] = faixas.get(nome, 0) + 1
    ordem = ["menor de 12"] + [f[2] for f in FAIXAS] + ["sem data"]
    total = usuarios.count()
    treino = Consentimento.objects.filter(tipo="treino_ia", revogado_em__isnull=True).values("usuario").distinct().count()
    return {
        "total": total,
        "faixas": [(nome, faixas[nome]) for nome in ordem if nome in faixas],
        "situacoes": [(Usuario.Situacao(s).label, n) for s, n in usuarios.values_list("situacao").annotate(n=Count("pk"))],
        "planos": [(Usuario.Plano(p).label, n) for p, n in usuarios.values_list("plano").annotate(n=Count("pk"))],
        "com_google": usuarios.filter(google_sub__isnull=False).count(),
        "criancas": usuarios.filter(responsavel__isnull=False).count(),
        "treino_pct": round(treino * 100 / total) if total else 0,
    }


def origem_respostas(dias):
    """De onde vieram as respostas da Liah: ia, regra, crise ou basica (reserva)."""
    nomes = {"ia": "IA online", "regra": "Regras fixas", "crise": "Protocolo de crise", "basica": "Reserva (sem IA)"}
    linhas = (
        Mensagem.objects.filter(autor=Mensagem.Autor.LIAH, criada_em__gte=_inicio(dias))
        .values_list("origem").annotate(n=Count("pk"))
    )
    total = sum(n for _, n in linhas) or 1
    return [(nomes.get(o, o or "?"), n, round(n * 100 / total)) for o, n in linhas]


def avaliacoes(dias):
    """
    Quanto as respostas AJUDARAM, pela avaliação das próprias pessoas (👍/👎), separado por origem.
    Ótimo para o TCC: dá para comparar IA x regras x reserva sem ninguém ler conversa nenhuma.
    """
    nomes = {"ia": "IA online", "regra": "Regras fixas", "crise": "Protocolo de crise", "basica": "Reserva (sem IA)"}
    base = Mensagem.objects.filter(autor=Mensagem.Autor.LIAH, criada_em__gte=_inicio(dias)).exclude(avaliacao="")
    util = base.filter(avaliacao="util").count()
    total = base.count()
    por_origem = []
    for origem, nome in nomes.items():
        da_origem = base.filter(origem=origem)
        n = da_origem.count()
        if n:
            u = da_origem.filter(avaliacao="util").count()
            por_origem.append((nome, n, round(u * 100 / n)))
    return {"total": total, "util": util, "nao_util": total - util,
            "pct": round(util * 100 / total) if total else 0, "por_origem": por_origem}


def laboratorio():
    testados = ExemploTreino.objects.filter(acertou__isnull=False)
    total = testados.count()
    acertos = testados.filter(acertou=True).count()
    return {"total": total, "acertos": acertos, "pct": round(acertos * 100 / total) if total else 0}


def saude_do_sistema(dias):
    """Os 'sinais vitais' do site, com alerta quando algo precisa de atenção."""
    pasta_bd = settings.ROOT_DIR / "liah-bd"
    banco = pasta_bd / "db.sqlite3"
    backups = sorted((pasta_bd / "backups").glob("liah-*.sqlite3"), key=lambda p: p.stat().st_mtime)

    ultimo_backup = None
    if backups:
        ultimo_backup = datetime.fromtimestamp(backups[-1].stat().st_mtime, tz=timezone.get_current_timezone())
    backup_velho = ultimo_backup is None or timezone.now() - ultimo_backup > timedelta(days=7)

    cfg = ConfiguracaoIA.carregar()
    respostas = Mensagem.objects.filter(autor=Mensagem.Autor.LIAH, criada_em__gte=_inicio(dias))
    total = respostas.count()
    reserva = respostas.filter(origem="basica").count()
    falha_ia_pct = round(reserva * 100 / total) if total else 0

    return {
        "ultimo_backup": ultimo_backup,
        "backup_velho": backup_velho,
        "qtd_backups": len(backups),
        "tamanho_banco_mb": round(banco.stat().st_size / 1_048_576, 2) if banco.exists() else 0,
        "ia_pronta": cfg.principal_pronta,
        "ia_ativa": cfg.ativa,
        "falha_ia_pct": falha_ia_pct,
        "falha_ia_alerta": cfg.principal_pronta and falha_ia_pct > 10,
        "email_modo": settings.LIAH_EMAIL_MODO,
        "google_login": bool(settings.GOOGLE_CLIENT_ID),
        "debug": settings.DEBUG,
        "regras_pendentes": RegraDicionario.objects.filter(status="rascunho").count(),
        "versao_django": django.get_version(),
        "versao_python": platform.python_version(),
    }


def acoes_equipe(limite=40):
    return RegistroSeguranca.objects.filter(tipo=RegistroSeguranca.Tipo.ACAO_EQUIPE).select_related("usuario")[:limite]


# ============================================================ PLANILHAS (CSV)

def resposta_csv(nome_arquivo, cabecalho, linhas):
    """
    CSV que o Excel em português abre certinho:
      - "\\ufeff" no começo (BOM): o Excel entende os acentos
      - delimiter=";": o Excel brasileiro usa ponto e vírgula para separar colunas
    """
    resposta = HttpResponse(content_type="text/csv; charset=utf-8")
    resposta["Content-Disposition"] = f'attachment; filename="{nome_arquivo}-{timezone.localdate()}.csv"'
    resposta.write("﻿")
    escritor = csv.writer(resposta, delimiter=";")
    escritor.writerow(cabecalho)
    escritor.writerows(linhas)
    return resposta
