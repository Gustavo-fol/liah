"""
ÁREA INTERNA da Liah (/interno/): só para a equipe (is_staff).
  - painel: visão geral
  - ia: chaves e provedores das duas IAs (só superusuário)
  - dicionário: regras + contextos do psicólogo, sugestões da IA, exportar planilha
  - laboratório: as duas IAs treinando (gerar fala -> analisar -> acertou?)
"""
import csv
from datetime import timedelta

from django.contrib import messages
from django.db.models import Count, Q
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from contas import backup, manutencao
from contas.auditoria import registrar_evento
from contas.models import RegistroSeguranca, Usuario
from nucleo import ia, projeto
from nucleo.models import (
    Categoria, ConfiguracaoIA, ContextoReferencia, Conversa, ExemploTreino, Mensagem, RegraDicionario,
)

from . import relatorios
from .acesso import equipe_obrigatoria, superusuario_obrigatorio
from .forms import ConfiguracaoIAForm, ContextoForm, RegraForm, SugerirRegrasForm


def registrar_acao(request, texto):
    """Guarda QUEM fez O QUÊ na área interna (o "histórico de atualizações" do site)."""
    registrar_evento(RegistroSeguranca.Tipo.ACAO_EQUIPE, request=request, usuario=request.user, detalhe=texto)


# ============================================================ PAINEL

def mascarar_email(email):
    """gustavo@gmail.com -> gu*****@gmail.com (a equipe identifica a conta sem ver o e-mail inteiro)."""
    nome, _, dominio = (email or "").partition("@")
    return f"{nome[:2]}{'*' * max(len(nome) - 2, 3)}@{dominio}" if dominio else "-"


@equipe_obrigatoria
def painel(request):
    hoje = timezone.localdate()

    # BACKUP AUTOMÁTICO: o PythonAnywhere grátis não tem tarefa agendada,
    # então toda vez que a equipe abre o Painel conferimos: passou de 24 h? faz um novo.
    novo_backup = backup.backup_se_preciso(horas=24)
    if novo_backup:
        registrar_acao(request, f"Backup automático criado: {novo_backup.name}")

    # FAXINA AUTOMÁTICA (1x por dia): sessões vencidas e registros de segurança antigos.
    faxina = manutencao.manutencao_se_preciso()
    if faxina and (faxina["sessoes"] or faxina["registros"]):
        registrar_acao(request, f"Faxina: {faxina['sessoes']} sessões e {faxina['registros']} registros antigos")

    # ---- Usuários e planos (veio do admin antigo) ----
    # Busca só por e-mail EXATO: dá para achar uma pessoa que pediu ajuda,
    # mas não dá para "navegar" pelos e-mails de todo mundo.
    busca = (request.GET.get("email") or "").strip().lower()
    usuarios = Usuario.objects.annotate(
        qtd_conversas=Count("conversas", distinct=True),
    ).order_by("-date_joined")
    usuarios = usuarios.filter(email__iexact=busca) if busca else usuarios[:20]
    linhas = [{
        "u": u,
        "email": mascarar_email(u.email),
        "papel": "equipe" if u.is_staff else ("criança" if u.responsavel_id else "usuário"),
    } for u in usuarios]

    return render(request, "interno/painel.html", {
        "total_usuarios": Usuario.objects.count(),
        "usuarios_ativos": Usuario.objects.filter(situacao="ativa").count(),
        "conversas_hoje": Conversa.objects.filter(atualizada_em__date=hoje).count(),
        "mensagens_24h": Mensagem.objects.filter(
            autor="usuario", criada_em__gte=timezone.now() - timedelta(hours=24)).count(),
        "alertas_semana": Mensagem.objects.filter(
            risco__in=["atencao", "alto"], autor="usuario",
            criada_em__gte=timezone.now() - timedelta(days=7),
        ).count(),
        "sem_ia_semana": Mensagem.objects.filter(
            autor="liah", origem="basica", criada_em__gte=timezone.now() - timedelta(days=7)).count(),
        "regras": RegraDicionario.objects.aggregate(
            aprovadas=Count("pk", filter=Q(status="aprovada")),
            rascunhos=Count("pk", filter=Q(status="rascunho")),
        ),
        "cfg": ConfiguracaoIA.carregar(),
        "origens": relatorios.origem_respostas(30),
        "linhas": linhas,
        "busca": busca,
        "planos": Usuario.Plano.choices,
        "resumo": projeto.resumo(),
        "backup_idade": _tempo_legivel(backup.idade_do_ultimo_backup()),
        "backup_ultimo": backup.ultimo_backup(),
        "backup_qtd": len(backup.listar_backups()),
    })


def _tempo_legivel(delta):
    """timedelta -> 'menos de 1 hora' / '5 h' / '3 dias'."""
    if delta is None:
        return ""
    horas = int(delta.total_seconds() // 3600)
    if horas < 1:
        return "menos de 1 hora"
    return f"{horas} h" if horas < 48 else f"{horas // 24} dias"


@superusuario_obrigatorio
@require_POST
def fazer_backup(request):
    try:
        destino, _ = backup.fazer_backup()
    except backup.ErroBackup as erro:
        messages.error(request, str(erro))
    else:
        registrar_acao(request, f"Backup manual criado: {destino.name}")
        messages.success(request, f"Backup criado: {destino.name}")
    return redirect("interno:painel")


@superusuario_obrigatorio
def baixar_backup(request):
    """
    Baixa o último backup: é a sua CÓPIA FORA DO SERVIDOR (se o PythonAnywhere sumir, você tem os dados).
    Guarde num lugar diferente do .env: sem a chave, os dados cifrados do backup são ilegíveis.
    """
    ultimo = backup.ultimo_backup()
    if ultimo is None:
        raise Http404
    registrar_acao(request, f"Backup baixado: {ultimo.name}")
    return FileResponse(open(ultimo, "rb"), as_attachment=True, filename=ultimo.name)


@superusuario_obrigatorio
@require_POST
def mudar_plano(request, pk):
    """Ativa/desativa o premium à mão (enquanto o pagamento automático não existe)."""
    alvo = get_object_or_404(Usuario, pk=pk)
    novo = request.POST.get("plano")
    if novo not in Usuario.Plano.values:
        messages.error(request, "Plano inválido.")
    elif novo != alvo.plano:
        antigo = alvo.get_plano_display()
        alvo.plano = novo
        alvo.save(update_fields=["plano"])
        registrar_acao(request, f"Plano da conta nº {alvo.pk} mudou de {antigo} para {alvo.get_plano_display()}")
        messages.success(request, f"Conta nº {alvo.pk} agora está no plano {alvo.get_plano_display()}.")
    return redirect("interno:painel")


# ============================================================ IA

@superusuario_obrigatorio
@require_http_methods(["GET", "POST"])
def configurar_ia(request):
    cfg = ConfiguracaoIA.carregar()
    form = ConfiguracaoIAForm(request.POST or None, instance=cfg)
    modelos = None

    if request.method == "POST":
        acao = request.POST.get("acao", "salvar")
        if form.is_valid():
            cfg = form.save(request.user)
            # Nunca registramos a chave: só que a configuração mudou.
            registrar_acao(request, f"Configuração da IA salva (principal: {cfg.provedor_principal or 'desligada'} "
                                    f"{cfg.modelo_principal}; secundária: {cfg.provedor_secundario or 'desligada'}; "
                                    f"ativa: {'sim' if cfg.ativa else 'não'})")
            if acao == "salvar":
                messages.success(request, "Configuração salva.")
                return redirect("interno:ia")
            # acao = testar_principal / testar_secundaria
            qual = "principal" if acao == "testar_principal" else "secundaria"
            try:
                resposta, modelos = ia.testar(qual)
                messages.success(request, f"IA {qual} funcionando! Ela respondeu: \"{resposta[:60]}\"")
            except ia.IAIndisponivel as erro:
                messages.error(request, f"Teste da IA {qual} falhou: {erro}")
            form = ConfiguracaoIAForm(instance=cfg)

    return render(request, "interno/ia.html", {"form": form, "cfg": cfg, "modelos": modelos})


# ============================================================ DICIONÁRIO

@equipe_obrigatoria
def dicionario(request):
    regras = RegraDicionario.objects.all()
    status = request.GET.get("status", "")
    categoria = request.GET.get("categoria", "")
    if status:
        regras = regras.filter(status=status)
    if categoria:
        regras = regras.filter(categoria=categoria)
    return render(request, "interno/dicionario.html", {
        "regras": regras,
        "status": status,
        "categoria": categoria,
        "status_opcoes": RegraDicionario.Status.choices,
        "categorias": Categoria.choices,
        "contextos": ContextoReferencia.objects.all(),
        "form_sugerir": SugerirRegrasForm(),
    })


@equipe_obrigatoria
@require_http_methods(["GET", "POST"])
def regra_editar(request, pk=None):
    regra = get_object_or_404(RegraDicionario, pk=pk) if pk else None
    form = RegraForm(request.POST or None, instance=regra)
    if request.method == "POST" and form.is_valid():
        salva = form.save()
        from nucleo.dicionario import limpar_indice
        limpar_indice()
        registrar_acao(request, f"Regra #{salva.pk} '{salva.titulo}' salva (status: {salva.get_status_display()})")
        messages.success(request, "Regra salva.")
        return redirect("interno:dicionario")
    return render(request, "interno/regra_form.html", {"form": form, "regra": regra})


@superusuario_obrigatorio
@require_POST
def dicionario_importar(request):
    """Mesmo que 'python manage.py importar_dicionario', mas por um botão (útil no PythonAnywhere)."""
    from nucleo import dicionario_arquivos
    from nucleo.dicionario import limpar_indice

    leitura, contagem = dicionario_arquivos.importar(arquivar_ausentes=request.POST.get("arquivar") == "1")
    if leitura.erros:
        for erro in leitura.erros[:15]:
            messages.error(request, erro)
        messages.error(request, f"{len(leitura.erros)} problema(s) nos arquivos: nada foi importado.")
    else:
        limpar_indice()
        registrar_acao(request, f"Dicionário importado dos arquivos: {contagem['criadas']} novo(s), "
                                f"{contagem['atualizadas']} atualizado(s), {contagem['aprovadas']} aprovado(s)")
        messages.success(request, f"Importado: {contagem['criadas']} novo(s), {contagem['atualizadas']} atualizado(s), "
                                  f"{contagem['arquivadas']} arquivado(s). Aprovados: {contagem['aprovadas']}.")
    return redirect("interno:dicionario")


@equipe_obrigatoria
@require_POST
def regra_apagar(request, pk):
    regra = get_object_or_404(RegraDicionario, pk=pk)
    registrar_acao(request, f"Regra #{regra.pk} '{regra.titulo}' apagada")
    regra.delete()
    messages.success(request, "Regra apagada.")
    return redirect("interno:dicionario")


@equipe_obrigatoria
@require_POST
def regras_sugerir(request):
    form = SugerirRegrasForm(request.POST)
    if form.is_valid():
        try:
            criadas = ia.sugerir_regras(form.cleaned_data["categoria"], form.cleaned_data["quantidade"])
            registrar_acao(request, f"IA sugeriu {len(criadas)} regra(s) em '{form.cleaned_data['categoria']}'")
            messages.success(request, f"A IA sugeriu {len(criadas)} regra(s). Elas entraram como RASCUNHO para o psicólogo revisar.")
        except ia.IAIndisponivel as erro:
            messages.error(request, f"Não foi possível sugerir: {erro}")
    return redirect("interno:dicionario")


@equipe_obrigatoria
def dicionario_exportar(request):
    """
    Planilha para o psicólogo revisar (abre direto no Excel).
    utf-8-sig: o Excel reconhece os acentos. delimiter=";": padrão do Excel em português.
    """
    resposta = HttpResponse(content_type="text/csv; charset=utf-8")
    resposta["Content-Disposition"] = f'attachment; filename="dicionario-liah-{timezone.localdate()}.csv"'
    resposta.write("﻿")
    escritor = csv.writer(resposta, delimiter=";")
    escritor.writerow([
        "ID", "Título", "Categoria", "Sinais nas entrelinhas", "Exemplos", "Risco", "Como responder",
        "Encaminhamento", "Status", "Revisada", "Observações do psicólogo", "Origem",
    ])
    for r in RegraDicionario.objects.all():
        escritor.writerow([
            r.pk, r.titulo, r.get_categoria_display(), r.sinais, " | ".join(r.lista_exemplos()),
            r.get_nivel_risco_display(), r.orientacao, r.get_encaminhamento_display(), r.get_status_display(),
            "sim" if r.revisado_por_psicologo else "não", r.observacoes_psicologo, r.get_origem_display(),
        ])
    return resposta


@equipe_obrigatoria
@require_http_methods(["GET", "POST"])
def contexto_editar(request, pk=None):
    contexto = get_object_or_404(ContextoReferencia, pk=pk) if pk else None
    form = ContextoForm(request.POST or None, instance=contexto)
    if request.method == "POST":
        if request.POST.get("acao") == "apagar" and contexto:
            registrar_acao(request, f"Contexto '{contexto.titulo}' apagado")
            contexto.delete()
            messages.success(request, "Contexto apagado.")
            return redirect("interno:dicionario")
        if form.is_valid():
            salvo = form.save()
            registrar_acao(request, f"Contexto '{salvo.titulo}' salvo (aprovado: {'sim' if salvo.aprovado else 'não'})")
            messages.success(request, "Contexto salvo.")
            return redirect("interno:dicionario")
    return render(request, "interno/contexto_form.html", {"form": form, "contexto": contexto})


# ============================================================ LABORATÓRIO

@equipe_obrigatoria
@require_http_methods(["GET", "POST"])
def laboratorio(request):
    if request.method == "POST":
        regra = get_object_or_404(RegraDicionario, pk=request.POST.get("regra"))
        try:
            texto, gerador = ia.gerar_fala_treino(regra)
            exemplo = ExemploTreino.objects.create(regra=regra, texto=texto, gerado_por=gerador)
            # A principal analisa SEM saber qual regra originou a fala.
            analise, analisador = ia.analisar_mensagem(texto)
            exemplo.analise = analise
            exemplo.analisado_por = analisador
            exemplo.acertou = regra.pk in analise.get("regras", [])
            exemplo.save()
            if exemplo.acertou:
                messages.success(request, "A IA principal identificou a regra certa.")
            else:
                messages.warning(request, "A IA principal NÃO identificou a regra. Vale revisar os sinais dessa regra.")
        except ia.IAIndisponivel as erro:
            messages.error(request, f"O teste falhou: {erro}")
        return redirect("interno:laboratorio")

    estatisticas = (
        RegraDicionario.objects.annotate(
            total=Count("exemplos_treino", filter=Q(exemplos_treino__acertou__isnull=False)),
            acertos=Count("exemplos_treino", filter=Q(exemplos_treino__acertou=True)),
        ).filter(total__gt=0)
    )
    return render(request, "interno/laboratorio.html", {
        "regras": RegraDicionario.objects.exclude(status="arquivada"),
        "exemplos": ExemploTreino.objects.select_related("regra")[:30],
        "estatisticas": estatisticas,
        "cfg": ConfiguracaoIA.carregar(),
    })


# ============================================================ RELATÓRIOS

@equipe_obrigatoria
def relatorios_view(request):
    dias = relatorios.periodo(request)
    series = relatorios.series_diarias(dias)
    totais = {campo: sum(linha[campo] for linha in series) for campo in series[0] if campo != "dia"}
    return render(request, "interno/relatorios.html", {
        "dias": dias,
        "periodos": relatorios.PERIODOS,
        "totais": totais,
        "graficos": [
            ("Mensagens dos usuários por dia", relatorios.grafico(series, "mensagens"), "azul"),
            ("Usuários ativos por dia", relatorios.grafico(series, "usuarios_ativos"), "ciano"),
            ("Novos cadastros por dia", relatorios.grafico(series, "novos_usuarios"), "verde"),
            ("Mensagens com sinal de risco por dia", relatorios.grafico(
                [{**d, "risco": d["alertas_atencao"] + d["alertas_alto"]} for d in series], "risco"), "laranja"),
            ("Tentativas de login com erro por dia", relatorios.grafico(series, "logins_falhos"), "vermelho"),
        ],
        "perfil": relatorios.perfil_usuarios(),
        "origens": relatorios.origem_respostas(dias),
        "lab": relatorios.laboratorio(),
        "avaliacoes": relatorios.avaliacoes(dias),
        "saude": relatorios.saude_do_sistema(dias),
        "acoes": relatorios.acoes_equipe(),
    })


@equipe_obrigatoria
def exportar_resumo(request):
    dias = relatorios.periodo(request)
    series = relatorios.series_diarias(dias)
    registrar_acao(request, f"Planilha 'resumo diário' exportada ({dias} dias)")
    return relatorios.resposta_csv(
        "liah-resumo-diario",
        ["Data", "Novos usuários", "Conversas novas", "Mensagens", "Usuários ativos",
         "Alertas (atenção)", "Alertas (alto)", "Logins ok", "Logins com erro"],
        [[d["dia"].strftime("%d/%m/%Y"), d["novos_usuarios"], d["conversas"], d["mensagens"], d["usuarios_ativos"],
          d["alertas_atencao"], d["alertas_alto"], d["logins_ok"], d["logins_falhos"]] for d in series],
    )


@equipe_obrigatoria
def exportar_usuarios(request):
    """
    PSEUDONIMIZADO (LGPD, princípio da necessidade): sem nome, e-mail ou CPF.
    Cada pessoa aparece só pelo número da conta: dá para analisar o uso sem expor quem é.
    """
    usuarios = (
        Usuario.objects.filter(is_staff=False)
        .annotate(qtd_conversas=Count("conversas", distinct=True), qtd_mensagens=Count("conversas__mensagens"))
        .order_by("pk")
    )
    registrar_acao(request, "Planilha 'usuários (anônima)' exportada")
    return relatorios.resposta_csv(
        "liah-usuarios-anonimo",
        ["Conta nº", "Criada em", "Faixa etária", "Plano", "Situação", "Entra com Google",
         "Conta de criança", "Conversas", "Mensagens (total)", "Último login"],
        [[u.pk, timezone.localtime(u.date_joined).strftime("%d/%m/%Y"), relatorios.faixa_etaria(u.data_nascimento),
          u.get_plano_display(), u.get_situacao_display(), "sim" if u.google_sub else "não",
          "sim" if u.responsavel_id else "não", u.qtd_conversas, u.qtd_mensagens,
          timezone.localtime(u.last_login).strftime("%d/%m/%Y %H:%M") if u.last_login else "-"] for u in usuarios],
    )


@superusuario_obrigatorio
def exportar_seguranca(request):
    """Tem IP (dado pessoal): só o superusuário exporta, e a exportação fica registrada."""
    dias = relatorios.periodo(request)
    eventos = RegistroSeguranca.objects.filter(criado_em__gte=timezone.now() - timedelta(days=dias)).order_by("criado_em")
    registrar_acao(request, f"Planilha 'registros de segurança' exportada ({dias} dias)")
    return relatorios.resposta_csv(
        "liah-seguranca",
        ["Data e hora", "Evento", "Conta nº", "IP", "Detalhe"],
        [[timezone.localtime(e.criado_em).strftime("%d/%m/%Y %H:%M:%S"), e.get_tipo_display(),
          e.usuario_id or "-", e.ip or "-", e.detalhe] for e in eventos],
    )


@equipe_obrigatoria
def exportar_laboratorio(request):
    """Resultados do laboratório das duas IAs (dados fictícios): base para o artigo/TCC."""
    exemplos = ExemploTreino.objects.select_related("regra").order_by("criado_em")
    return relatorios.resposta_csv(
        "liah-laboratorio",
        ["Data", "Regra-alvo", "Categoria", "Fala gerada", "Gerado por", "Analisado por",
         "Regras detectadas", "Risco detectado", "Encaminhamento", "Acertou", "Justificativa"],
        [[timezone.localtime(e.criado_em).strftime("%d/%m/%Y %H:%M"), e.regra.titulo, e.regra.get_categoria_display(),
          e.texto, e.gerado_por, e.analisado_por,
          ", ".join(str(n) for n in (e.analise or {}).get("regras", [])),
          (e.analise or {}).get("nivel_risco", ""), (e.analise or {}).get("encaminhamento", ""),
          {True: "sim", False: "não", None: "-"}[e.acertou], (e.analise or {}).get("justificativa", "")]
         for e in exemplos],
    )
