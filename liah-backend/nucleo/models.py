"""
MODELS do núcleo: as conversas.

O texto de TODA mensagem é guardado CRIPTOGRAFADO (Fernet, a mesma chave do CPF).
É dado sensível (LGPD art. 11): se o banco vazar, ninguém lê as conversas.
Nem o admin: o painel mostra que a conversa existe e o nível de risco, nunca o conteúdo.
"""
from django.conf import settings
from django.core.cache import cache
from django.db import models
from django.utils import timezone

from contas.seguranca import cifrar, decifrar


class Conversa(models.Model):
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,     # excluiu a conta => as conversas vão junto
        related_name="conversas",
        verbose_name="usuário",
    )
    criada_em = models.DateTimeField("criada em", auto_now_add=True)
    atualizada_em = models.DateTimeField("atualizada em", auto_now=True)

    class Meta:
        verbose_name = "conversa"
        verbose_name_plural = "conversas"
        ordering = ["-atualizada_em"]
        # ÍNDICE = "sumário" do banco: a lista de conversas de uma pessoa sai direto, sem ler a tabela toda.
        indexes = [models.Index(fields=["usuario", "-atualizada_em"], name="conversa_usuario_data")]

    def __str__(self):
        return f"Conversa #{self.pk}"

    @property
    def titulo(self):
        # Título pela DATA, não pelo texto: assim não guardamos conteúdo sensível sem cifrar.
        return f"Conversa de {timezone.localtime(self.criada_em):%d/%m/%Y %H:%M}"


class Mensagem(models.Model):
    class Autor(models.TextChoices):
        USUARIO = "usuario", "Usuário"
        LIAH = "liah", "Liah"

    class Risco(models.TextChoices):
        NENHUM = "nenhum", "Nenhum"
        ATENCAO = "atencao", "Atenção"
        ALTO = "alto", "Alto"

    conversa = models.ForeignKey(Conversa, on_delete=models.CASCADE, related_name="mensagens")
    autor = models.CharField(max_length=10, choices=Autor.choices)
    texto_cifrado = models.TextField(editable=False)
    # De onde veio a resposta da Liah: crise, regra, ia ou basica (vazio nas mensagens do usuário).
    origem = models.CharField(max_length=10, blank=True)
    risco = models.CharField(max_length=10, choices=Risco.choices, default=Risco.NENHUM)
    # "Isso ajudou?" (👍/👎) que a PESSOA dá numa resposta da Liah. Vazio = não avaliou.
    # A equipe vê só a contagem nos relatórios, nunca o texto avaliado.
    avaliacao = models.CharField(
        "avaliação", max_length=10, blank=True,
        choices=[("util", "Ajudou"), ("nao_util", "Não ajudou")],
    )
    criada_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "mensagem"
        verbose_name_plural = "mensagens"
        ordering = ["criada_em"]
        # Relatórios e o contador do painel filtram por autor + data.
        indexes = [models.Index(fields=["autor", "criada_em"], name="mensagem_autor_data")]

    def __str__(self):
        # Nunca mostra o TEXTO (é sigiloso): só quem escreveu e quando.
        return f"Mensagem #{self.pk} ({self.autor}, {self.criada_em:%d/%m/%Y %H:%M})"

    # @property + .setter: o código usa "mensagem.texto" normalmente,
    # mas por baixo o valor é cifrado ao gravar e decifrado ao ler.
    @property
    def texto(self):
        return decifrar(self.texto_cifrado) if self.texto_cifrado else ""

    @texto.setter
    def texto(self, valor):
        self.texto_cifrado = cifrar(valor)


# ============================================================ IA ONLINE

class ConfiguracaoIA(models.Model):
    """
    Configuração das duas IAs, editada pela área interna (só o superusuário).
    Existe UMA linha só nesta tabela (id=1): o "singleton".

      principal  -> conversa com o usuário e analisa as mensagens com o dicionário
      secundária -> só para TREINO: escreve falas fictícias "nas entrelinhas"

    As chaves de API ficam CRIPTOGRAFADAS (mesma chave Fernet do CPF).
    """

    class Provedor(models.TextChoices):
        DESLIGADO = "", "Desligado"
        OPENAI = "openai", "OpenAI"
        GEMINI = "gemini", "Google Gemini"

    provedor_principal = models.CharField("provedor da IA principal", max_length=20, choices=Provedor.choices, blank=True, default="")
    modelo_principal = models.CharField("modelo da IA principal", max_length=80, blank=True, default="gpt-4o-mini")
    chave_principal_cifrada = models.TextField(blank=True, editable=False)

    provedor_secundario = models.CharField("provedor da IA secundária", max_length=20, choices=Provedor.choices, blank=True, default="")
    modelo_secundario = models.CharField("modelo da IA secundária", max_length=80, blank=True, default="gemini-3.5-flash")
    chave_secundaria_cifrada = models.TextField(blank=True, editable=False)

    # Botão de emergência: desliga a IA online no site inteiro (a Liah volta às regras).
    ativa = models.BooleanField("IA online ligada", default=True)

    atualizada_em = models.DateTimeField(auto_now=True)
    atualizada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        verbose_name = "configuração da IA"
        verbose_name_plural = "configuração da IA"

    CHAVE_CACHE = "liah:config_ia"

    def __str__(self):
        return "Configuração da IA"

    def save(self, *args, **kwargs):
        self.pk = 1  # sempre a mesma linha
        super().save(*args, **kwargs)
        cache.delete(self.CHAVE_CACHE)   # mudou a configuração => todo mundo lê a nova

    @classmethod
    def carregar(cls):
        """
        Toda mensagem lê esta configuração. Guardamos 60 s no CACHE para não ir ao banco toda vez.
        (Nos testes não usa cache, porque o banco é desfeito entre um teste e outro.)
        """
        if not settings.TESTANDO:
            obj = cache.get(cls.CHAVE_CACHE)
            if obj is not None:
                return obj
        obj, _ = cls.objects.get_or_create(pk=1)
        if not settings.TESTANDO:
            cache.set(cls.CHAVE_CACHE, obj, 60)
        return obj

    # ---- chaves: guardar cifrado, ler só quando for chamar a API
    def definir_chave(self, qual, chave):
        setattr(self, f"chave_{qual}_cifrada", cifrar(chave.strip()) if chave else "")

    def chave(self, qual):
        valor = getattr(self, f"chave_{qual}_cifrada")
        return decifrar(valor) if valor else ""

    def final_da_chave(self, qual):
        """Para mostrar na tela sem revelar a chave: ••••abcd"""
        chave = self.chave(qual)
        return f"••••{chave[-4:]}" if chave else "não cadastrada"

    # Templates do Django não chamam métodos com argumento: por isso estas duas "atalho".
    @property
    def final_chave_principal(self):
        return self.final_da_chave("principal")

    @property
    def final_chave_secundaria(self):
        return self.final_da_chave("secundaria")

    @property
    def principal_pronta(self):
        return bool(self.ativa and self.provedor_principal and self.modelo_principal and self.chave_principal_cifrada)

    @property
    def secundaria_pronta(self):
        return bool(self.provedor_secundario and self.modelo_secundario and self.chave_secundaria_cifrada)


# ============================================================ DICIONÁRIO DA LIAH

class Categoria(models.TextChoices):
    LUTO = "luto", "Luto e perdas"
    ANSIEDADE = "ansiedade", "Ansiedade"
    TRISTEZA = "tristeza", "Tristeza persistente / depressão"
    IDEACAO = "ideacao", "Ideação suicida (passiva ou ativa)"
    AUTOLESAO = "autolesao", "Autolesão"
    ISOLAMENTO = "isolamento", "Solidão e isolamento"
    ESTRESSE = "estresse", "Estresse e pressão"
    AUTOESTIMA = "autoestima", "Autoestima"
    SONO = "sono", "Sono e cansaço"
    RELACIONAMENTOS = "relacionamentos", "Relacionamentos e família"
    VIOLENCIA = "violencia", "Violência e abuso"
    OUTRO = "outro", "Outro"


class Encaminhamento(models.TextChoices):
    NENHUM = "nenhum", "Nenhum (só acolher)"
    PSICOLOGO = "psicologo", "Sugerir psicólogo"
    PSIQUIATRA = "psiquiatra", "Sugerir psiquiatra"
    EMERGENCIA = "emergencia", "Emergência (CVV 188 / SAMU 192)"


class RegraDicionario(models.Model):
    """
    Uma regra do "dicionário" da Liah: QUE SINAIS observar nas entrelinhas,
    COMO responder e PARA QUEM encaminhar.

    Ciclo de vida:  rascunho (IA sugeriu ou você escreveu)
                    -> revisada pelo psicólogo -> aprovada
    O núcleo da Liah SÓ usa regras APROVADAS.
    """

    class Status(models.TextChoices):
        RASCUNHO = "rascunho", "Rascunho (aguardando psicólogo)"
        APROVADA = "aprovada", "Aprovada"
        ARQUIVADA = "arquivada", "Arquivada"

    class Origem(models.TextChoices):
        MANUAL = "manual", "Escrita pela equipe"
        IA = "ia", "Sugerida pela IA"
        ARQUIVO = "arquivo", "Arquivo do dicionário (liah-dicionario/)"

    titulo = models.CharField("título", max_length=120)
    categoria = models.CharField("categoria", max_length=20, choices=Categoria.choices)
    sinais = models.TextField("sinais nas entrelinhas", help_text="O que observar na fala da pessoa (o que ela NÃO diz diretamente).")
    exemplos = models.TextField("frases de exemplo", blank=True, help_text="Uma frase por linha.")
    nivel_risco = models.CharField("nível de risco", max_length=10, choices=Mensagem.Risco.choices, default=Mensagem.Risco.NENHUM)
    orientacao = models.TextField("como a Liah deve responder")
    encaminhamento = models.CharField("encaminhamento", max_length=20, choices=Encaminhamento.choices, default=Encaminhamento.NENHUM)

    status = models.CharField("status", max_length=10, choices=Status.choices, default=Status.RASCUNHO)
    revisado_por_psicologo = models.BooleanField("revisada por psicólogo", default=False)
    observacoes_psicologo = models.TextField("observações do psicólogo", blank=True)
    origem = models.CharField("origem", max_length=10, choices=Origem.choices, default=Origem.MANUAL)

    # ---- Vindo dos ARQUIVOS do dicionário (python manage.py importar_dicionario) ----
    # chave: o "id" do contexto no arquivo. É ela que liga o arquivo à linha do banco:
    # importar de novo ATUALIZA a mesma regra em vez de duplicar.
    chave = models.CharField("chave no arquivo", max_length=80, unique=True, null=True, blank=True)
    arquivo = models.CharField("arquivo de origem", max_length=120, blank=True)
    palavras_chave = models.TextField(
        "palavras-chave", blank=True,
        help_text="Uma por linha. Servem para a Liah achar este contexto quando a pessoa fala desse assunto.")
    # Tudo o que o arquivo traz (entrelinhas, falsos positivos, o que evitar, resposta-modelo...).
    detalhes = models.JSONField("detalhes do contexto", default=dict, blank=True)

    criada_em = models.DateTimeField(auto_now_add=True)
    atualizada_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "regra do dicionário"
        verbose_name_plural = "regras do dicionário"
        ordering = ["categoria", "titulo"]

    def __str__(self):
        return f"[{self.get_categoria_display()}] {self.titulo}"

    def lista_exemplos(self):
        return [linha.strip() for linha in self.exemplos.splitlines() if linha.strip()]

    def lista_palavras_chave(self):
        return [linha.strip() for linha in self.palavras_chave.splitlines() if linha.strip()]

    @property
    def veio_do_arquivo(self):
        return self.origem == self.Origem.ARQUIVO


class ContextoReferencia(models.Model):
    """
    Textos de apoio enviados pelo psicólogo (orientações, explicações, casos-modelo).
    A IA principal lê os APROVADOS como base para interpretar as conversas.
    """
    titulo = models.CharField("título", max_length=150)
    conteudo = models.TextField("conteúdo")
    fonte = models.CharField("fonte", max_length=150, blank=True, help_text="Ex.: Psicólogo(a) Fulano, 15/11/2026")
    aprovado = models.BooleanField("aprovado para uso", default=False)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "contexto de referência"
        verbose_name_plural = "contextos de referência"
        ordering = ["titulo"]

    def __str__(self):
        return self.titulo


class ExemploTreino(models.Model):
    """
    Laboratório das duas IAs: a SECUNDÁRIA escreve uma fala fictícia a partir de uma regra,
    a PRINCIPAL analisa sem saber qual regra era, e guardamos se ela acertou.
    São dados FICTÍCIOS (nenhuma pessoa real), por isso não precisam de criptografia.
    """
    regra = models.ForeignKey(RegraDicionario, on_delete=models.CASCADE, related_name="exemplos_treino")
    texto = models.TextField("fala gerada")
    gerado_por = models.CharField(max_length=80, blank=True)
    analise = models.JSONField("análise da IA principal", null=True, blank=True)
    analisado_por = models.CharField(max_length=80, blank=True)
    acertou = models.BooleanField(null=True)   # None = ainda não analisado
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "exemplo de treino"
        verbose_name_plural = "exemplos de treino"
        ordering = ["-criado_em"]

    def __str__(self):
        return f"Exemplo de treino #{self.pk}"
