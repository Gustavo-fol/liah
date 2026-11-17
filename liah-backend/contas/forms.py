"""
FORMS = classes que validam o que foi digitado antes de salvar.

Como o Django valida um formulário (form.is_valid()):
  1) cada campo se valida sozinho (tipo, obrigatório, tamanho...)
  2) roda clean_<nome_do_campo>() para cada campo que tiver esse método
  3) roda clean() para regras que envolvem VÁRIOS campos (ex.: idade x responsável)
Qualquer ValidationError vira mensagem de erro na tela.
"""
from datetime import date

from django import forms
from django.contrib.admin.forms import AdminAuthenticationForm
from django.contrib.auth.forms import AuthenticationForm, UserChangeForm, UserCreationForm
from django.core.exceptions import ValidationError

from .models import (
    IDADE_MINIMA_CADASTRO_PROPRIO,
    MAIORIDADE,
    Usuario,
    calcular_idade,
)
from .auditoria import ip_do_pedido, registrar_evento
from .limitador import BLOQUEIO_SEGUNDOS, esta_bloqueado, limpar, registrar_falha
from .models import RegistroSeguranca
from .seguranca import gerar_hmac, validar_cpf

MINUTOS_BLOQUEIO = BLOQUEIO_SEGUNDOS // 60


# ============================================================ ADMIN

class UsuarioAdminCriacaoForm(UserCreationForm):
    class Meta:
        model = Usuario
        fields = ("email",)


class UsuarioAdminEdicaoForm(UserChangeForm):
    class Meta:
        model = Usuario
        fields = "__all__"


# ============================================================ LOGIN

class LimiteLoginMixin:
    """
    Pedaço reaproveitado pelos DOIS logins (site e admin):
    e-mail em minúsculo + limite de tentativas.
    """

    def clean_username(self):
        # Os e-mails são salvos em minúsculo; "Ana@Gmail.com" precisa achar "ana@gmail.com".
        return self.cleaned_data["username"].strip().lower()

    def clean(self):
        """
        Envolve a checagem normal do Django com o limitador de tentativas.
        A chave é e-mail + IP: o atacante não consegue travar a conta de alguém
        de outro lugar, e a pessoa de verdade continua conseguindo entrar.
        """
        email = self.cleaned_data.get("username") or ""
        ip = ip_do_pedido(self.request) or ""

        if email and esta_bloqueado("login", email, ip):
            registrar_evento(RegistroSeguranca.Tipo.LOGIN_BLOQUEADO, request=self.request)
            raise ValidationError(
                f"Muitas tentativas erradas. Aguarde {MINUTOS_BLOQUEIO} minutos e tente de novo.",
                code="bloqueado",
            )

        try:
            dados = super().clean()   # aqui o Django confere e-mail e senha
        except ValidationError as erro:
            if email and getattr(erro, "code", None) == "invalid_login":
                registrar_falha("login", email, ip)
            raise

        limpar("login", email, ip)
        return dados


class EntrarForm(LimiteLoginMixin, AuthenticationForm):
    """Login do SITE: além de e-mail e senha certos, a conta precisa estar ATIVA."""

    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": "E-mail ou senha incorretos.",
    }

    MENSAGENS_SITUACAO = {
        Usuario.Situacao.PENDENTE_EMAIL: "Confirme seu e-mail antes de entrar (veja sua caixa de entrada).",
        Usuario.Situacao.PENDENTE_RESPONSAVEL: "Sua conta está aguardando a autorização do seu responsável.",
        Usuario.Situacao.BLOQUEADA: "Esta conta está bloqueada. Fale com o suporte da Liah.",
    }

    # Vira True quando a conta existe mas falta confirmar o e-mail:
    # o template usa isso para mostrar o link "enviar um novo link".
    pendente_email = False

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)  # checa is_active
        self.pendente_email = user.situacao == Usuario.Situacao.PENDENTE_EMAIL
        if user.situacao != Usuario.Situacao.ATIVA:
            raise ValidationError(self.MENSAGENS_SITUACAO.get(user.situacao), code="conta_nao_ativa")


class AdminEntrarForm(LimiteLoginMixin, AdminAuthenticationForm):
    """Login do ADMIN: o mesmo limite de tentativas (é o alvo mais valioso)."""


# ============================================================ CADASTRO

CAMPO_DATA = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")
CAMPO_CPF = forms.TextInput(attrs={"inputmode": "numeric", "placeholder": "000.000.000-00"})


class ValidacoesCadastroMixin:
    """
    MIXIN = pedaço de classe reaproveitado. Os dois cadastros (para mim / dependente)
    validam e-mail, CPF e data de nascimento do mesmo jeito.
    """

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if Usuario.objects.filter(email__iexact=email).exists():
            raise ValidationError("Já existe uma conta com este e-mail.")
        return email

    def clean_cpf(self):
        cpf = validar_cpf(self.cleaned_data["cpf"])
        if Usuario.objects.filter(cpf_hmac=gerar_hmac(cpf)).exists():
            raise ValidationError("Já existe uma conta com este CPF.")
        return cpf

    def clean_data_nascimento(self):
        nascimento = self.cleaned_data["data_nascimento"]
        if nascimento > date.today():
            raise ValidationError("A data de nascimento não pode estar no futuro.")
        if calcular_idade(nascimento) > 120:
            raise ValidationError("Confira a data de nascimento.")
        return nascimento

    def clean_cpf_responsavel(self):
        valor = self.cleaned_data.get("cpf_responsavel")
        return validar_cpf(valor) if valor else ""


def aplicar_regras_de_idade(form, dados, email):
    """
    Regras de idade do cadastro PRÓPRIO (usadas no cadastro com e-mail E no do Google):
      - menor de 12  -> não pode (precisa que um responsável crie a conta)
      - 12 a 17      -> dados do responsável obrigatórios
    Fica numa função para as duas telas seguirem EXATAMENTE a mesma regra.
    """
    nascimento = dados.get("data_nascimento")
    if not nascimento:
        return dados

    idade = calcular_idade(nascimento)
    if idade < IDADE_MINIMA_CADASTRO_PROPRIO:
        raise ValidationError(
            "Menores de 12 anos não podem criar conta sozinhos. "
            "Peça para seu responsável criar a conta para você."
        )

    if idade < MAIORIDADE:
        for campo in ("nome_responsavel", "email_responsavel", "cpf_responsavel"):
            if not dados.get(campo) and campo not in form.errors:
                form.add_error(campo, "Obrigatório para menores de 18 anos.")

        if dados.get("cpf_responsavel") and dados.get("cpf_responsavel") == dados.get("cpf"):
            form.add_error("cpf_responsavel", "O CPF do responsável não pode ser o seu.")

        email_resp = (dados.get("email_responsavel") or "").lower()
        if email_resp and email and email_resp == email.lower():
            form.add_error("email_responsavel", "O e-mail do responsável não pode ser o seu.")
        dados["email_responsavel"] = email_resp

    return dados


# Campos repetidos nos cadastros: funções que "fabricam" um campo novo a cada uso.
def campo_nome_responsavel():
    return forms.CharField(label="Nome completo do responsável", max_length=150, required=False)


def campo_email_responsavel():
    return forms.EmailField(label="E-mail do responsável", required=False)


def campo_cpf_responsavel():
    return forms.CharField(label="CPF do responsável", max_length=14, required=False, widget=CAMPO_CPF)


def campo_aceite_termos():
    return forms.BooleanField(label="Li e aceito os Termos de Uso e a Política de Privacidade.", required=True)


def campo_aceite_dados_sensiveis():
    return forms.BooleanField(
        label=(
            "Autorizo a Liah a tratar o conteúdo emocional das minhas conversas "
            "(dado sensível, LGPD art. 11) para conversar comigo e manter meu histórico."
        ),
        required=True,
    )


def campo_aceite_treino_ia():
    return forms.BooleanField(
        label="(Opcional) Autorizo usar minhas conversas, sem identificação, para melhorar a IA da Liah.",
        required=False,
    )




class CadastroProprioForm(ValidacoesCadastroMixin, UserCreationForm):
    """'Para mim': 12 anos ou mais. De 12 a 17 exige dados do responsável."""

    cpf = forms.CharField(label="CPF", max_length=14, widget=CAMPO_CPF)

    # Responsável: required=False aqui; aplicar_regras_de_idade() torna obrigatório para menores de 18.
    nome_responsavel = campo_nome_responsavel()
    email_responsavel = campo_email_responsavel()
    cpf_responsavel = campo_cpf_responsavel()

    aceite_termos = campo_aceite_termos()
    aceite_dados_sensiveis = campo_aceite_dados_sensiveis()
    aceite_treino_ia = campo_aceite_treino_ia()

    class Meta:
        model = Usuario
        fields = ("first_name", "last_name", "email", "data_nascimento")
        widgets = {"data_nascimento": CAMPO_DATA}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["first_name"].required = True
        self.fields["data_nascimento"].required = True

    def clean(self):
        dados = super().clean()
        return aplicar_regras_de_idade(self, dados, email=dados.get("email"))

    def save(self, commit=True):
        usuario = super().save(commit=False)  # UserCreationForm já aplica set_password
        usuario.definir_cpf(self.cleaned_data["cpf"])
        usuario.situacao = Usuario.Situacao.PENDENTE_EMAIL
        if commit:
            usuario.save()
        return usuario


class CadastroDependenteForm(ValidacoesCadastroMixin, UserCreationForm):
    """'Para outra pessoa': o responsável (logado) cria a conta de uma criança menor de 12."""

    cpf = forms.CharField(label="CPF da criança", max_length=14, widget=CAMPO_CPF)

    aceite_termos = forms.BooleanField(
        label="Como responsável, li e aceito os Termos de Uso e a Política de Privacidade.",
        required=True,
    )
    aceite_dados_sensiveis = forms.BooleanField(
        label=(
            "Como responsável legal, autorizo a Liah a tratar o conteúdo emocional das "
            "conversas desta criança (dado sensível, LGPD arts. 11 e 14)."
        ),
        required=True,
    )
    aceite_treino_ia = forms.BooleanField(
        label="(Opcional) Autorizo usar as conversas da criança, sem identificação, para melhorar a IA.",
        required=False,
    )

    class Meta:
        model = Usuario
        fields = ("first_name", "last_name", "email", "data_nascimento")
        labels = {
            "first_name": "Nome da criança",
            "last_name": "Sobrenome da criança",
            "email": "E-mail de login da criança",
        }
        widgets = {"data_nascimento": CAMPO_DATA}

    def __init__(self, *args, responsavel=None, **kwargs):
        self.responsavel = responsavel
        super().__init__(*args, **kwargs)
        self.fields["first_name"].required = True
        self.fields["data_nascimento"].required = True

    def clean_data_nascimento(self):
        nascimento = super().clean_data_nascimento()
        if calcular_idade(nascimento) >= IDADE_MINIMA_CADASTRO_PROPRIO:
            raise ValidationError(
                "A partir de 12 anos, a própria pessoa faz o cadastro em 'Para mim' "
                "e você autoriza pelo link que chega no seu e-mail."
            )
        return nascimento

    def clean_cpf(self):
        cpf = super().clean_cpf()
        if self.responsavel and gerar_hmac(cpf) == self.responsavel.cpf_hmac:
            raise ValidationError("Este é o seu CPF. Informe o CPF da criança.")
        return cpf

    def save(self, commit=True):
        crianca = super().save(commit=False)
        crianca.definir_cpf(self.cleaned_data["cpf"])
        crianca.responsavel = self.responsavel
        # O responsável é um adulto já verificado, então a conta já nasce ativa.
        crianca.situacao = Usuario.Situacao.ATIVA
        if commit:
            crianca.save()
        return crianca


# ============================================================ EXCLUSÃO DE CONTA

PALAVRA_CONFIRMACAO = "EXCLUIR"


class ConfirmarSenhaForm(forms.Form):
    """
    Pede a SENHA de quem está logado antes de uma ação importante
    (excluir conta, baixar meus dados). Prova que é o dono, não alguém com o celular na mão.

    Quem entrou SÓ pelo Google não tem senha na Liah: nesse caso o campo some
    (has_usable_password() == False) e a proteção fica por conta do Google.
    """

    senha = forms.CharField(
        label="Sua senha",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )

    def __init__(self, *args, usuario, **kwargs):
        # usuario = quem está logado (o dono da senha que vamos conferir)
        self.usuario = usuario
        super().__init__(*args, **kwargs)
        if not usuario.has_usable_password():
            del self.fields["senha"]

    def clean_senha(self):
        senha = self.cleaned_data["senha"]
        email = self.usuario.email

        # Mesmo logado, limitamos: quem pegou o celular desbloqueado não pode
        # ficar chutando a senha.
        if esta_bloqueado("senha", email):
            registrar_evento(RegistroSeguranca.Tipo.SENHA_BLOQUEADA, usuario=self.usuario)
            raise ValidationError(f"Muitas tentativas. Aguarde {MINUTOS_BLOQUEIO} minutos.")

        # check_password compara a senha digitada com o HASH guardado no banco.
        if not self.usuario.check_password(senha):
            registrar_falha("senha", email)
            raise ValidationError("Senha incorreta.")

        limpar("senha", email)
        return senha


class ExcluirContaForm(ConfirmarSenhaForm):
    """
    Confirmação dupla antes de apagar: senha (herdada) + digitar EXCLUIR.
    Usado também quando o responsável exclui a conta da criança (a senha é a do responsável).
    """

    confirmacao = forms.CharField(
        label=f"Digite {PALAVRA_CONFIRMACAO} para confirmar",
        max_length=20,
        widget=forms.TextInput(attrs={"autocomplete": "off"}),
    )

    def clean_confirmacao(self):
        texto = self.cleaned_data["confirmacao"].strip().upper()
        if texto != PALAVRA_CONFIRMACAO:
            raise ValidationError(f"Digite exatamente {PALAVRA_CONFIRMACAO}.")
        return texto


# ============================================================ CONFIGURAÇÕES DA CONTA

class EditarPerfilForm(forms.ModelForm):
    """
    O "U" (Update) do CRUD. Só nome e sobrenome:
      - e-mail: trocar exige confirmar o NOVO e-mail (etapa futura)
      - data de nascimento e CPF: definem as regras de idade; mudar exige suporte
    """

    class Meta:
        model = Usuario
        fields = ("first_name", "last_name")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["first_name"].required = True


class ReenviarConfirmacaoForm(forms.Form):
    email = forms.EmailField(label="E-mail da sua conta")

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()


# ============================================================ GOOGLE

class CompletarCadastroGoogleForm(ValidacoesCadastroMixin, forms.Form):
    """
    Quem entra pelo Google já chega com nome e e-mail confirmados.
    Falta o que o Google não informa: nascimento, CPF, responsável e consentimentos.
    """

    data_nascimento = forms.DateField(label="Data de nascimento", widget=CAMPO_DATA)
    cpf = forms.CharField(label="CPF", max_length=14, widget=CAMPO_CPF)

    nome_responsavel = campo_nome_responsavel()
    email_responsavel = campo_email_responsavel()
    cpf_responsavel = campo_cpf_responsavel()

    aceite_termos = campo_aceite_termos()
    aceite_dados_sensiveis = campo_aceite_dados_sensiveis()
    aceite_treino_ia = campo_aceite_treino_ia()

    def __init__(self, *args, email, **kwargs):
        self.email = email  # o e-mail que veio do Google
        super().__init__(*args, **kwargs)

    def clean(self):
        dados = super().clean()
        # Alguém pode ter criado conta com esse e-mail enquanto a pessoa preenchia.
        if Usuario.objects.filter(email__iexact=self.email).exists():
            raise ValidationError("Já existe uma conta com este e-mail. Entre pela tela de login.")
        return aplicar_regras_de_idade(self, dados, email=self.email)
