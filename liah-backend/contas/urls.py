"""
URLs do app contas. Cada path liga um ENDEREÇO a uma VIEW e ganha um NOME.
Nos templates e no código usamos o nome: {% url 'contas:entrar' %} / reverse("contas:entrar").
Assim, se um dia o endereço mudar, só mexemos aqui.
"""
from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy
from django.views.generic import TemplateView

from . import views
from .forms import EntrarForm

app_name = "contas"

urlpatterns = [
    path("cadastro/", views.escolher_cadastro, name="cadastro"),
    path("cadastro/para-mim/", views.cadastro_proprio, name="cadastro_proprio"),
    path("cadastro/dependente/", views.cadastro_dependente, name="cadastro_dependente"),
    path("cadastro/enviado/", views.cadastro_enviado, name="cadastro_enviado"),
    path("confirmar-email/<uidb64>/<token>/", views.confirmar_email, name="confirmar_email"),
    path("autorizar/<token>/", views.autorizar_responsavel, name="autorizar_responsavel"),
    path(
        "entrar/",
        auth_views.LoginView.as_view(
            template_name="contas/entrar.html",
            authentication_form=EntrarForm,
            redirect_authenticated_user=True,
        ),
        name="entrar",
    ),
    path("sair/", auth_views.LogoutView.as_view(), name="sair"),
    path("painel/", views.painel, name="painel"),
    path("configuracoes/excluir-conta/", views.excluir_minha_conta, name="excluir_conta"),
    path("conta-excluida/", views.conta_excluida, name="conta_excluida"),
    path("dependentes/<int:pk>/excluir/", views.excluir_dependente, name="excluir_dependente"),

    # ---- Esqueci minha senha (views prontas do Django, com as nossas páginas)
    path(
        "senha/esqueci/",
        views.EsqueciSenhaView.as_view(),   # a do Django + limite de pedidos
        name="senha_esqueci",
    ),
    path(
        "senha/esqueci/enviado/",
        auth_views.PasswordResetDoneView.as_view(template_name="contas/senha_esqueci_enviado.html"),
        name="senha_esqueci_enviado",
    ),
    path(
        "senha/redefinir/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="contas/senha_redefinir.html",
            success_url=reverse_lazy("contas:senha_redefinida"),
        ),
        name="senha_redefinir",
    ),
    path(
        "senha/redefinida/",
        auth_views.PasswordResetCompleteView.as_view(template_name="contas/senha_redefinida.html"),
        name="senha_redefinida",
    ),
    path("confirmacao/reenviar/", views.reenviar_confirmacao, name="reenviar_confirmacao"),

    # ---- Configurações da conta
    path("configuracoes/perfil/", views.editar_perfil, name="editar_perfil"),
    path("configuracoes/senha/", views.trocar_senha, name="trocar_senha"),
    path("configuracoes/privacidade/", views.privacidade, name="privacidade"),
    path("configuracoes/privacidade/baixar/", views.baixar_meus_dados, name="baixar_meus_dados"),

    # ---- Páginas legais (TemplateView: só mostra um HTML, sem lógica)
    path("termos/", TemplateView.as_view(template_name="contas/termos.html"), name="termos"),
    path(
        "politica-de-privacidade/",
        TemplateView.as_view(template_name="contas/politica_privacidade.html"),
        name="politica_privacidade",
    ),

    # ---- Continuar com Google
    path("google/entrar/", views.google_entrar, name="google_entrar"),
    path("google/retorno/", views.google_retorno, name="google_retorno"),
    path("google/completar/", views.google_completar, name="google_completar"),
]
