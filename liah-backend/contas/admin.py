"""
ADMIN = como os dados aparecem no painel do super adm.
CPF nunca aparece inteiro: só mascarado (***.***.***-09).
"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .forms import AdminEntrarForm, UsuarioAdminCriacaoForm, UsuarioAdminEdicaoForm
from .models import AutorizacaoResponsavel, Consentimento, RegistroSeguranca, Usuario

# Títulos do painel
admin.site.site_header = "Liah - Administração"
admin.site.site_title = "Liah Admin"
admin.site.index_title = "Painel de controle"
# Login do admin com limite de tentativas (ver forms.LimiteLoginMixin)
admin.site.login_form = AdminEntrarForm


class SomenteLeituraMixin:
    """
    Registros de prova (LGPD): ninguém cria pelo admin, e só o SUPERUSUÁRIO apaga.

    Por que o superusuário precisa poder apagar?
    Quando você exclui um USUÁRIO, o Django apaga junto (CASCADE) os consentimentos
    e autorizações dele. Antes de apagar, o admin confere se você tem permissão de
    apagar cada objeto relacionado. Se ninguém pudesse apagar consentimentos, seria
    impossível excluir qualquer conta, e a LGPD garante o direito de exclusão.
    """

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def get_actions(self, request):
        # Tira a ação "Excluir selecionados" da lista: nada de apagar prova em massa.
        acoes = super().get_actions(request)
        acoes.pop("delete_selected", None)
        return acoes


class ConsentimentoInline(SomenteLeituraMixin, admin.TabularInline):
    model = Consentimento
    fk_name = "usuario"  # Consentimento tem 2 FKs para Usuario; dizemos qual usar
    extra = 0
    can_delete = False
    readonly_fields = ("tipo", "versao", "concedido_por", "aceito_em", "revogado_em")


class AutorizacaoInline(SomenteLeituraMixin, admin.TabularInline):
    model = AutorizacaoResponsavel
    extra = 0
    can_delete = False
    fields = ("nome_responsavel", "email_responsavel", "cpf_mascarado", "criada_em", "autorizada_em", "negada_em")
    readonly_fields = fields


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    form = UsuarioAdminEdicaoForm
    add_form = UsuarioAdminCriacaoForm
    model = Usuario
    inlines = [ConsentimentoInline, AutorizacaoInline]

    list_display = ("email", "first_name", "situacao", "plano", "responsavel", "is_staff")
    list_filter = ("situacao", "plano", "email_confirmado", "is_staff", "is_superuser")
    search_fields = ("email", "first_name", "last_name")
    ordering = ("email",)
    readonly_fields = ("cpf_mascarado", "last_login", "date_joined")

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Dados pessoais", {"fields": ("first_name", "last_name", "data_nascimento", "cpf_mascarado")}),
        ("Conta", {"fields": ("situacao", "plano", "email_confirmado", "responsavel")}),
        ("Permissões", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Datas", {"fields": ("last_login", "date_joined")}),
    )

    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("email", "password1", "password2")}),
    )


@admin.register(Consentimento)
class ConsentimentoAdmin(SomenteLeituraMixin, admin.ModelAdmin):
    list_display = ("usuario", "tipo", "versao", "concedido_por", "aceito_em", "revogado_em")
    list_filter = ("tipo",)
    search_fields = ("usuario__email",)
    readonly_fields = ("usuario", "concedido_por", "tipo", "versao", "aceito_em", "revogado_em")


@admin.register(AutorizacaoResponsavel)
class AutorizacaoResponsavelAdmin(SomenteLeituraMixin, admin.ModelAdmin):
    list_display = ("menor", "nome_responsavel", "email_responsavel", "criada_em", "autorizada_em", "negada_em")
    search_fields = ("menor__email", "email_responsavel")
    readonly_fields = (
        "menor", "nome_responsavel", "email_responsavel", "cpf_mascarado",
        "criada_em", "expira_em", "autorizada_em", "negada_em",
    )
    exclude = ("cpf_hmac", "cpf_cifrado", "token_hash")


@admin.register(RegistroSeguranca)
class RegistroSegurancaAdmin(SomenteLeituraMixin, admin.ModelAdmin):
    list_display = ("criado_em", "tipo", "usuario", "ip", "detalhe")
    list_filter = ("tipo", "criado_em")
    search_fields = ("usuario__email", "ip", "detalhe")
    readonly_fields = ("criado_em", "tipo", "usuario", "ip", "detalhe")
    date_hierarchy = "criado_em"   # navegação por ano/mês/dia no topo da lista

    def has_change_permission(self, request, obj=None):
        return False  # registro de segurança ninguém edita
