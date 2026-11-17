"""
VIEWS = funções que recebem o pedido do navegador (request) e devolvem uma resposta.

Padrão usado nos formulários:
  - GET  (abriu a página)    -> mostra o formulário vazio
  - POST (clicou em enviar)  -> valida; se der certo salva e REDIRECIONA;
                                se der errado mostra o formulário com os erros
Redirecionar depois do POST evita que o F5 reenvie o cadastro.
"""
import time

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm, SetPasswordForm
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from django.views.decorators.http import require_http_methods

from . import google
from .forms import (
    CadastroDependenteForm,
    CadastroProprioForm,
    CompletarCadastroGoogleForm,
    ConfirmarSenhaForm,
    EditarPerfilForm,
    EntrarForm,
    ExcluirContaForm,
    ReenviarConfirmacaoForm,
)
from .limitador import esta_bloqueado, registrar_falha
from .auditoria import ip_do_pedido
from .models import AutorizacaoResponsavel, Consentimento, Usuario
from .seguranca import hash_token
from .servicos import (
    criar_autorizacao_responsavel,
    enviar_confirmacao_email,
    enviar_pedido_autorizacao,
    excluir_conta,
    exportar_dados,
    recalcular_situacao,
    registrar_consentimentos,
    resumo_exclusao,
)
from .tokens import token_confirmacao_email

T = Consentimento.Tipo


def escolher_cadastro(request):
    """Página com as duas opções: 'Para mim' e 'Para outra pessoa'."""
    return render(request, "contas/escolher_cadastro.html")


@require_http_methods(["GET", "POST"])
def cadastro_proprio(request):
    if request.user.is_authenticated:
        return redirect("contas:painel")

    # request.POST or None: no GET o form nasce vazio; no POST nasce com o que foi digitado.
    form = CadastroProprioForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        dados = form.cleaned_data
        autorizacao = token_resp = None

        # transaction.atomic(): ou salva TUDO, ou não salva NADA (se der erro no meio).
        with transaction.atomic():
            usuario = form.save()
            registrar_consentimentos(usuario, {
                T.TERMOS: True,
                T.DADOS_SENSIVEIS: True,
                T.TREINO_IA: dados["aceite_treino_ia"],
            })
            if usuario.precisa_autorizacao_responsavel():
                autorizacao, token_resp = criar_autorizacao_responsavel(
                    usuario, dados["nome_responsavel"], dados["email_responsavel"], dados["cpf_responsavel"]
                )

        enviou = enviar_confirmacao_email(request, usuario)
        if autorizacao:
            enviou = enviar_pedido_autorizacao(request, autorizacao, token_resp) and enviou
        if not enviou:
            messages.warning(
                request,
                "Sua conta foi criada, mas tivemos um problema para enviar o e-mail. "
                "Tente de novo mais tarde ou fale com o suporte da Liah.",
            )

        return redirect("contas:cadastro_enviado")

    return render(request, "contas/cadastro_proprio.html", {"form": form})


def cadastro_enviado(request):
    return render(request, "contas/cadastro_enviado.html")


@login_required  # se não estiver logado, manda para a página de login
@require_http_methods(["GET", "POST"])
def cadastro_dependente(request):
    if not request.user.pode_ser_responsavel():
        messages.error(
            request,
            "Para criar a conta de uma criança, você precisa ser maior de 18 anos, "
            "ter CPF cadastrado e estar com a conta ativa.",
        )
        return redirect("contas:painel")

    form = CadastroDependenteForm(request.POST or None, responsavel=request.user)

    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            crianca = form.save()
            registrar_consentimentos(
                crianca,
                {
                    T.TERMOS: True,
                    T.DADOS_SENSIVEIS: True,
                    T.TREINO_IA: form.cleaned_data["aceite_treino_ia"],
                },
                concedido_por=request.user,
            )
        messages.success(
            request,
            f"Conta de {crianca.first_name} criada. Ela já pode entrar com o e-mail e a senha que você definiu.",
        )
        return redirect("contas:painel")

    return render(request, "contas/cadastro_dependente.html", {"form": form})


def confirmar_email(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        usuario = Usuario.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, Usuario.DoesNotExist):
        usuario = None

    ok = usuario is not None and token_confirmacao_email.check_token(usuario, token)
    if ok:
        usuario.email_confirmado = True
        usuario.save(update_fields=["email_confirmado"])
        recalcular_situacao(usuario)

    return render(request, "contas/confirmacao_resultado.html", {"ok": ok, "usuario": usuario})


@require_http_methods(["GET", "POST"])
def autorizar_responsavel(request, token):
    """
    GET mostra a página com um botão; só o POST (clique) autoriza.
    Motivo: alguns e-mails "abrem" links sozinhos para checar vírus.
    Consentimento precisa ser um ato da pessoa, não de um robô.
    """
    autorizacao = (
        AutorizacaoResponsavel.objects.select_related("menor")
        .filter(token_hash=hash_token(token))
        .first()
    )

    if autorizacao is None or (autorizacao.expirada and not autorizacao.respondida):
        return render(request, "contas/autorizar_responsavel.html", {"invalido": True})

    if request.method == "POST" and not autorizacao.respondida:
        menor = autorizacao.menor
        if request.POST.get("acao") == "autorizar":
            autorizacao.autorizada_em = timezone.now()
            autorizacao.save(update_fields=["autorizada_em"])
            recalcular_situacao(menor)
        elif request.POST.get("acao") == "negar":
            autorizacao.negada_em = timezone.now()
            autorizacao.save(update_fields=["negada_em"])
            menor.situacao = Usuario.Situacao.BLOQUEADA
            menor.save(update_fields=["situacao"])
        return redirect("contas:autorizar_responsavel", token=token)

    return render(request, "contas/autorizar_responsavel.html", {"autorizacao": autorizacao})


@login_required
def painel(request):
    return render(request, "contas/painel.html", {"dependentes": request.user.dependentes.all()})


# ============================================================ EXCLUSÃO DE CONTA

@login_required
@require_http_methods(["GET", "POST"])
def excluir_minha_conta(request):
    usuario = request.user

    # Criança (conta criada por responsável) não exclui sozinha: quem exclui é o responsável.
    if usuario.responsavel_id:
        messages.error(request, "Sua conta é gerenciada pelo seu responsável. Peça para ele excluir pelo painel dele.")
        return redirect("contas:painel")

    # Proteção: o super admin não se apaga pelo site (você poderia ficar sem nenhum admin).
    if usuario.is_superuser:
        messages.error(request, "O superusuário não pode ser excluído pelo site. Use o /admin.")
        return redirect("contas:painel")

    form = ExcluirContaForm(request.POST or None, usuario=usuario)

    if request.method == "POST" and form.is_valid():
        excluir_conta(usuario, request=request)
        logout(request)  # encerra a sessão (a conta não existe mais)
        return redirect("contas:conta_excluida")

    return render(request, "contas/excluir_conta.html", {"form": form, "resumo": resumo_exclusao(usuario)})


def conta_excluida(request):
    return render(request, "contas/conta_excluida.html")


@login_required
@require_http_methods(["GET", "POST"])
def excluir_dependente(request, pk):
    """
    O responsável exclui a conta de uma criança.

    SEGURANÇA (IDOR): o id da criança vem na URL, e qualquer um pode trocar o número.
    Por isso buscamos com responsavel=request.user: se a criança não for DELE,
    o Django responde 404 (como se ela nem existisse).
    """
    crianca = get_object_or_404(Usuario, pk=pk, responsavel=request.user)
    form = ExcluirContaForm(request.POST or None, usuario=request.user)

    if request.method == "POST" and form.is_valid():
        nome = crianca.first_name
        excluir_conta(crianca, excluido_por_responsavel=True, request=request)
        messages.success(request, f"A conta de {nome} foi excluída, com todos os dados dela.")
        return redirect("contas:painel")

    return render(request, "contas/excluir_dependente.html", {"form": form, "crianca": crianca})


# ============================================================ REENVIAR CONFIRMAÇÃO

@require_http_methods(["GET", "POST"])
def reenviar_confirmacao(request):
    """
    SEGURANÇA: a mensagem final é SEMPRE a mesma, exista a conta ou não.
    Se disséssemos "esse e-mail não existe", um atacante descobriria quem usa a Liah
    (isso se chama "enumeração de usuários").
    """
    form = ReenviarConfirmacaoForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"]
        ip = ip_do_pedido(request) or ""

        if esta_bloqueado("reenvio", email, ip):
            messages.error(request, "Muitos pedidos seguidos. Aguarde 15 minutos e tente de novo.")
            return redirect("contas:reenviar_confirmacao")

        registrar_falha("reenvio", email, ip)  # aqui o "contador" conta pedidos, não erros
        usuario = Usuario.objects.filter(
            email=email, email_confirmado=False, responsavel__isnull=True
        ).first()
        if usuario:
            enviar_confirmacao_email(request, usuario)

        messages.info(
            request,
            "Se existir uma conta aguardando confirmação com esse e-mail, enviamos um novo link.",
        )
        return redirect("contas:entrar")

    return render(request, "contas/reenviar_confirmacao.html", {"form": form})


# ============================================================ CONFIGURAÇÕES

@login_required
@require_http_methods(["GET", "POST"])
def editar_perfil(request):
    # instance=request.user: o formulário já vem preenchido com os dados atuais.
    form = EditarPerfilForm(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Perfil atualizado.")
        return redirect("contas:painel")
    return render(request, "contas/editar_perfil.html", {"form": form})


@login_required
@require_http_methods(["GET", "POST"])
def trocar_senha(request):
    """
    Quem já tem senha: PasswordChangeForm (pede a senha atual).
    Quem entrou só pelo Google: SetPasswordForm (cria a primeira senha).
    """
    tem_senha = request.user.has_usable_password()
    Formulario = PasswordChangeForm if tem_senha else SetPasswordForm
    form = Formulario(request.user, request.POST or None)

    if request.method == "POST" and form.is_valid():
        form.save()
        # Trocar a senha muda o "crachá" da sessão; isto mantém a pessoa logada
        # AQUI e desloga automaticamente os OUTROS aparelhos.
        update_session_auth_hash(request, form.user)
        messages.success(request, "Senha salva com sucesso.")
        return redirect("contas:painel")

    return render(request, "contas/trocar_senha.html", {"form": form, "tem_senha": tem_senha})


@login_required
@require_http_methods(["GET", "POST"])
def privacidade(request):
    usuario = request.user
    gerenciada = bool(usuario.responsavel_id)  # conta de criança: quem decide é o responsável

    if request.method == "POST" and not gerenciada:
        acao = request.POST.get("acao")
        if acao == "revogar_treino":
            for c in usuario.consentimentos.filter(tipo=T.TREINO_IA, revogado_em__isnull=True):
                c.revogar()
            messages.success(request, "Pronto: suas conversas não serão usadas para treinar a IA.")
        elif acao == "conceder_treino" and not usuario.tem_consentimento(T.TREINO_IA):
            registrar_consentimentos(usuario, {T.TREINO_IA: True})
            messages.success(request, "Obrigado! Suas conversas, sem identificação, poderão ajudar a melhorar a Liah.")
        elif acao == "revogar_dados":
            # LGPD art. 8º §5º: a pessoa pode RETIRAR o consentimento a qualquer momento.
            # Sem ele, a Liah para de guardar conversas (a API passa a pedir a autorização de novo).
            for c in usuario.consentimentos.filter(tipo=T.DADOS_SENSIVEIS, revogado_em__isnull=True):
                c.revogar()
            if request.POST.get("apagar_conversas") == "1":
                usuario.conversas.all().delete()
                messages.success(request, "Autorização retirada e todas as suas conversas foram apagadas.")
            else:
                messages.success(request, "Autorização retirada. A Liah não vai mais guardar suas conversas.")
        elif acao == "conceder_dados" and not usuario.tem_consentimento(T.DADOS_SENSIVEIS):
            registrar_consentimentos(usuario, {T.DADOS_SENSIVEIS: True})
            messages.success(request, "Autorização registrada. Você já pode conversar com a Liah.")
        return redirect("contas:privacidade")

    return render(request, "contas/privacidade.html", {
        "consentimentos": usuario.consentimentos.all(),
        "treino_ativo": usuario.tem_consentimento(T.TREINO_IA),
        "dados_ativo": usuario.tem_consentimento(T.DADOS_SENSIVEIS),
        "gerenciada": gerenciada,
        "form": ConfirmarSenhaForm(usuario=usuario),
    })


@login_required
@require_http_methods(["POST"])
def baixar_meus_dados(request):
    form = ConfirmarSenhaForm(request.POST, usuario=request.user)
    if not form.is_valid():
        messages.error(request, "Senha incorreta. Seus dados não foram baixados.")
        return redirect("contas:privacidade")

    resposta = JsonResponse(
        exportar_dados(request.user),
        json_dumps_params={"ensure_ascii": False, "indent": 2},  # acentos legíveis e arquivo organizado
    )
    # Content-Disposition: attachment faz o navegador BAIXAR em vez de mostrar na tela.
    resposta["Content-Disposition"] = 'attachment; filename="meus-dados-liah.json"'
    return resposta


# ============================================================ GOOGLE

def google_entrar(request):
    if request.user.is_authenticated:
        return redirect("contas:painel")
    return redirect(google.montar_url_de_login(request))


def google_retorno(request):
    try:
        perfil = google.processar_retorno(request)
    except google.ErroGoogle as erro:
        messages.error(request, str(erro))
        return redirect("contas:entrar")

    usuario = (
        Usuario.objects.filter(google_sub=perfil["sub"]).first()
        or Usuario.objects.filter(email__iexact=perfil["email"]).first()
    )

    # ---- Pessoa NOVA: ainda não criamos nada no banco (só depois do consentimento).
    if usuario is None:
        request.session["google_perfil"] = {**perfil, "criado": time.time()}
        return redirect("contas:google_completar")

    # ---- Pessoa que JÁ TEM conta
    if usuario.responsavel_id:
        messages.error(request, "Contas de criança entram com e-mail e senha.")
        return redirect("contas:entrar")
    if usuario.google_sub and usuario.google_sub != perfil["sub"]:
        messages.error(request, "Esta conta da Liah está ligada a outra conta Google.")
        return redirect("contas:entrar")

    # Liga a conta ao Google; o Google já provou que o e-mail é dela.
    usuario.google_sub = perfil["sub"]
    usuario.email_confirmado = True
    usuario.save(update_fields=["google_sub", "email_confirmado"])
    recalcular_situacao(usuario)

    if usuario.situacao != Usuario.Situacao.ATIVA:
        messages.error(request, EntrarForm.MENSAGENS_SITUACAO.get(usuario.situacao, "Conta indisponível."))
        return redirect("contas:entrar")

    login(request, usuario, backend="django.contrib.auth.backends.ModelBackend")
    return redirect(settings.LOGIN_REDIRECT_URL)   # mesmo destino do login por senha (o chat)


@require_http_methods(["GET", "POST"])
def google_completar(request):
    perfil = request.session.get("google_perfil")
    if not perfil or time.time() - perfil["criado"] > 15 * 60:
        request.session.pop("google_perfil", None)
        messages.error(request, "O tempo para completar o cadastro acabou. Entre com o Google de novo.")
        return redirect("contas:entrar")

    form = CompletarCadastroGoogleForm(request.POST or None, email=perfil["email"])

    if request.method == "POST" and form.is_valid():
        dados = form.cleaned_data
        autorizacao = token_resp = None

        with transaction.atomic():
            usuario = Usuario(
                email=perfil["email"],
                first_name=perfil["first_name"],
                last_name=perfil["last_name"],
                data_nascimento=dados["data_nascimento"],
                google_sub=perfil["sub"],
                email_confirmado=True,   # o Google já confirmou
            )
            usuario.set_unusable_password()  # sem senha na Liah: entra pelo Google
            usuario.definir_cpf(dados["cpf"])
            usuario.save()
            registrar_consentimentos(usuario, {
                T.TERMOS: True,
                T.DADOS_SENSIVEIS: True,
                T.TREINO_IA: dados["aceite_treino_ia"],
            })
            if usuario.precisa_autorizacao_responsavel():
                autorizacao, token_resp = criar_autorizacao_responsavel(
                    usuario, dados["nome_responsavel"], dados["email_responsavel"], dados["cpf_responsavel"]
                )
            recalcular_situacao(usuario)

        del request.session["google_perfil"]

        if autorizacao:
            enviar_pedido_autorizacao(request, autorizacao, token_resp)
            messages.info(request, "Conta criada! Agora seu responsável precisa autorizar pelo e-mail que enviamos.")
            return redirect("contas:entrar")

        login(request, usuario, backend="django.contrib.auth.backends.ModelBackend")
        messages.success(request, f"Bem-vindo(a) à Liah, {usuario.first_name}!")
        return redirect(settings.LOGIN_REDIRECT_URL)

    return render(request, "contas/google_completar.html", {"form": form, "perfil": perfil})


# ============================================================ ESQUECI A SENHA (com limite)

class EsqueciSenhaView(auth_views.PasswordResetView):
    """
    A view do Django, com LIMITE: no máximo 5 pedidos por e-mail+rede a cada 15 min.
    Sem isso, um robô poderia lotar a caixa de alguém (e gastar a cota do Gmail).
    Quando passa do limite, NÃO envia, mas mostra a MESMA página de "enviamos":
    assim ninguém descobre quais e-mails têm conta (anti-enumeração).
    """
    template_name = "contas/senha_esqueci.html"
    email_template_name = "contas/emails/senha_redefinir.txt"
    subject_template_name = "contas/emails/senha_redefinir_assunto.txt"

    def get_success_url(self):
        from django.urls import reverse
        return reverse("contas:senha_esqueci_enviado")

    def form_valid(self, form):
        email = form.cleaned_data["email"]
        ip = ip_do_pedido(self.request)
        if esta_bloqueado("senha", email, ip):
            return redirect(self.get_success_url())
        registrar_falha("senha", email, ip)   # conta o pedido (não é "falha", mas usa o mesmo contador)
        return super().form_valid(form)
