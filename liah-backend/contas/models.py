"""
MODELS do app contas = os "moldes" que viram tabelas no banco (liah-bd/db.sqlite3).

- Usuario:                quem usa a Liah.
- Consentimento:          o "recibo" de cada autorização (LGPD).
- AutorizacaoResponsavel: o pedido enviado por e-mail ao responsável de um menor (12 a 17).

Regras de idade da Liah:
  - menor de 12  -> só um responsável (com conta própria) cria a conta
  - 12 a 17      -> cadastro próprio + autorização do responsável por e-mail
  - 18 ou mais   -> cadastro próprio, só confirma o e-mail
"""
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone

from .managers import UsuarioManager
from .seguranca import cifrar, decifrar, gerar_hmac, mascarar_cpf

IDADE_MINIMA_CADASTRO_PROPRIO = 12
MAIORIDADE = 18


def calcular_idade(data_nascimento):
    """Idade em anos completos numa data de nascimento (date)."""
    hoje = timezone.localdate()
    # (mes, dia) < (mes, dia) compara as tuplas: True vale 1, False vale 0.
    ainda_nao_fez_aniversario = (hoje.month, hoje.day) < (data_nascimento.month, data_nascimento.day)
    return hoje.year - data_nascimento.year - ainda_nao_fez_aniversario


class Usuario(AbstractUser):
    """
    Herdamos de AbstractUser: ele já traz senha (com hash), first_name, last_name,
    is_active, is_staff, is_superuser, grupos, permissões, last_login e date_joined.
    """

    class Plano(models.TextChoices):
        GRATUITO = "gratuito", "Gratuito"
        PREMIUM = "premium", "Premium"

    class Tema(models.TextChoices):
        SISTEMA = "sistema", "Igual ao aparelho"
        CLARO = "claro", "Claro"
        ESCURO = "escuro", "Escuro"

    class Situacao(models.TextChoices):
        PENDENTE_EMAIL = "pendente_email", "Aguardando confirmação de e-mail"
        PENDENTE_RESPONSAVEL = "pendente_responsavel", "Aguardando autorização do responsável"
        ATIVA = "ativa", "Ativa"
        BLOQUEADA = "bloqueada", "Bloqueada"

    # Login pelo e-mail, sem username.
    username = None
    email = models.EmailField("e-mail", unique=True)

    data_nascimento = models.DateField("data de nascimento", null=True, blank=True)
    email_confirmado = models.BooleanField("e-mail confirmado", default=False)
    plano = models.CharField("plano", max_length=20, choices=Plano.choices, default=Plano.GRATUITO)

    # Preferência visual: salva na conta para valer em qualquer aparelho.
    tema = models.CharField("tema", max_length=10, choices=Tema.choices, default=Tema.SISTEMA)

    # Só usuário com situação ATIVA consegue entrar no site.
    situacao = models.CharField(
        "situação da conta", max_length=30, choices=Situacao.choices, default=Situacao.PENDENTE_EMAIL
    )

    # CPF guardado de 2 jeitos (editable=False: não aparece em formulário nem no admin).
    #   cpf_hmac    -> impressão digital, unique=True impede o mesmo CPF em 2 contas
    #   cpf_cifrado -> o número trancado com a chave Fernet (dá pra ler com a chave)
    # null=True no HMAC: o superusuário criado pelo terminal não tem CPF.
    cpf_hmac = models.CharField(max_length=64, unique=True, null=True, blank=True, editable=False)
    cpf_cifrado = models.TextField(blank=True, editable=False)

    # "sub" = o identificador PERMANENTE da pessoa no Google (o e-mail pode mudar, o sub não).
    # Preenchido quando a pessoa entra com "Continuar com Google".
    google_sub = models.CharField(max_length=255, unique=True, null=True, blank=True, editable=False)

    # Preenchido quando a conta foi criada POR um responsável (crianças menores de 12).
    # CASCADE: se o responsável excluir a conta dele, as contas dos dependentes vão junto.
    responsavel = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="dependentes",
        verbose_name="responsável",
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UsuarioManager()

    class Meta:
        verbose_name = "usuário"
        verbose_name_plural = "usuários"

    def __str__(self):
        return self.email

    # ------------------------------------------------ idade
    @property
    def idade(self):
        return calcular_idade(self.data_nascimento) if self.data_nascimento else None

    def eh_maior_de_idade(self):
        return self.idade is not None and self.idade >= MAIORIDADE

    def precisa_autorizacao_responsavel(self):
        """Menor de 18 que se cadastrou SOZINHO precisa do 'ok' do responsável por e-mail."""
        return self.idade is not None and self.idade < MAIORIDADE and self.responsavel_id is None

    def pode_ser_responsavel(self):
        """Só adulto, com conta ativa e CPF cadastrado pode criar conta para criança."""
        return self.eh_maior_de_idade() and self.situacao == self.Situacao.ATIVA and bool(self.cpf_hmac)

    # ------------------------------------------------ CPF
    def definir_cpf(self, cpf_digitos):
        """Recebe o CPF já validado (só números) e guarda nas duas formas."""
        self.cpf_hmac = gerar_hmac(cpf_digitos)
        self.cpf_cifrado = cifrar(cpf_digitos)

    def ler_cpf(self):
        """Devolve o CPF de verdade. Use SÓ quando for realmente necessário."""
        return decifrar(self.cpf_cifrado) if self.cpf_cifrado else ""

    def cpf_mascarado(self):
        return mascarar_cpf(self.ler_cpf())
    cpf_mascarado.short_description = "CPF"

    # ------------------------------------------------ consentimento
    def tem_consentimento(self, tipo):
        return self.consentimentos.filter(tipo=tipo, revogado_em__isnull=True).exists()


class Consentimento(models.Model):
    """
    LGPD art. 11: dado sensível (emocional/saúde) exige consentimento ESPECÍFICO
    e DESTACADO. Cada aceite vira uma linha aqui, com a versão do texto e a data.
    Ninguém edita um consentimento: se a pessoa desistir, marcamos revogado_em.
    """

    class Tipo(models.TextChoices):
        TERMOS = "termos", "Termos de uso e política de privacidade"
        DADOS_SENSIVEIS = "dados_sensiveis", "Tratamento de dados emocionais (LGPD art. 11)"
        TREINO_IA = "treino_ia", "Uso anonimizado das conversas para treinar a IA (opcional)"

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="consentimentos",
        verbose_name="usuário",
    )
    # Quando um responsável aceita EM NOME da criança, guardamos quem foi.
    concedido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="consentimentos_concedidos",
        verbose_name="concedido por (responsável)",
    )
    tipo = models.CharField("tipo", max_length=30, choices=Tipo.choices)
    versao = models.CharField("versão do texto", max_length=20)
    aceito_em = models.DateTimeField("aceito em", auto_now_add=True)
    revogado_em = models.DateTimeField("revogado em", null=True, blank=True)

    class Meta:
        verbose_name = "consentimento"
        verbose_name_plural = "consentimentos"
        ordering = ["-aceito_em"]

    def __str__(self):
        situacao = "revogado" if self.revogado_em else "ativo"
        return f"{self.usuario} - {self.get_tipo_display()} ({situacao})"

    @property
    def ativo(self):
        return self.revogado_em is None

    def revogar(self):
        self.revogado_em = timezone.now()
        self.save(update_fields=["revogado_em"])


class AutorizacaoResponsavel(models.Model):
    """
    Pedido de autorização mandado ao responsável de um adolescente (12 a 17 anos).
    O link do e-mail carrega um token aleatório; no banco fica só o HASH dele.
    """

    menor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="autorizacoes",
        verbose_name="menor de idade",
    )
    nome_responsavel = models.CharField("nome do responsável", max_length=150)
    email_responsavel = models.EmailField("e-mail do responsável")
    cpf_hmac = models.CharField(max_length=64, editable=False)
    cpf_cifrado = models.TextField(editable=False)
    token_hash = models.CharField(max_length=64, unique=True, editable=False)

    criada_em = models.DateTimeField("criada em", auto_now_add=True)
    expira_em = models.DateTimeField("expira em")
    autorizada_em = models.DateTimeField("autorizada em", null=True, blank=True)
    negada_em = models.DateTimeField("negada em", null=True, blank=True)

    class Meta:
        verbose_name = "autorização de responsável"
        verbose_name_plural = "autorizações de responsáveis"
        ordering = ["-criada_em"]

    def __str__(self):
        return f"{self.nome_responsavel} -> {self.menor}"

    @property
    def respondida(self):
        return self.autorizada_em is not None or self.negada_em is not None

    @property
    def expirada(self):
        return timezone.now() > self.expira_em

    def cpf_mascarado(self):
        return mascarar_cpf(decifrar(self.cpf_cifrado))
    cpf_mascarado.short_description = "CPF do responsável"


class RegistroSeguranca(models.Model):
    """Diário de bordo de segurança (ver contas/auditoria.py)."""

    class Tipo(models.TextChoices):
        LOGIN_OK = "login_ok", "Login realizado"
        LOGIN_FALHOU = "login_falhou", "Login falhou (e-mail ou senha errados)"
        LOGIN_BLOQUEADO = "login_bloqueado", "Login bloqueado (muitas tentativas)"
        LOGOUT = "logout", "Saiu"
        SENHA_BLOQUEADA = "senha_bloqueada", "Confirmação de senha bloqueada (muitas tentativas)"
        CONTA_EXCLUIDA = "conta_excluida", "Conta excluída"
        ACAO_EQUIPE = "acao_equipe", "Ação da equipe (área interna)"

    tipo = models.CharField("evento", max_length=30, choices=Tipo.choices)
    # SET_NULL: se a conta for excluída, o registro fica, mas sem apontar para ninguém.
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="registros_seguranca",
        verbose_name="usuário",
    )
    ip = models.GenericIPAddressField("IP", null=True, blank=True)
    detalhe = models.CharField("detalhe", max_length=255, blank=True)
    criado_em = models.DateTimeField("quando", auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "registro de segurança"
        verbose_name_plural = "registros de segurança"
        ordering = ["-criado_em"]
        # O limitador de tentativas e os relatórios filtram por tipo + data.
        indexes = [models.Index(fields=["tipo", "criado_em"], name="registro_tipo_data")]

    def __str__(self):
        return f"{self.get_tipo_display()} - {self.criado_em:%d/%m/%Y %H:%M}"
