"""
SERVIÇOS = as "regras de negócio" do cadastro, separadas das views.

A view só recebe o pedido e responde; quem DECIDE o que acontece são estas funções.
Vantagem: o mesmo serviço pode ser usado pelo site, pela API e pelo robô no futuro.
"""
import logging
import secrets
from datetime import timedelta

from django.core.mail import send_mail
from django.db import transaction
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from .auditoria import registrar_evento
from .models import AutorizacaoResponsavel, Consentimento, RegistroSeguranca, Usuario
from .seguranca import cifrar, gerar_hmac, hash_token
from .tokens import token_confirmacao_email

logger = logging.getLogger(__name__)


def enviar_email(assunto, corpo, destinatarios):
    """
    Envia um e-mail e devolve True/False em vez de quebrar o site.

    Se o Gmail estiver fora do ar ou a senha de app estiver errada, o send_mail
    levanta um erro (OSError). Sem este try/except, a pessoa veria uma página de erro
    no meio do cadastro. Com ele, o cadastro continua e o erro vai para o log.
    """
    try:
        send_mail(assunto, corpo, None, destinatarios)
        return True
    except OSError:
        # logger.exception grava a mensagem + o erro completo no terminal/log.
        logger.exception("Falha ao enviar e-mail '%s'", assunto)
        return False


# Mude a versão sempre que mudar o texto dos termos (o usuário aceitou AQUELA versão).
VERSAO_TEXTOS = "2026-11"
DIAS_VALIDADE_AUTORIZACAO = 7


def registrar_consentimentos(usuario, aceites, concedido_por=None):
    """
    aceites é um dicionário {tipo: True/False}.
    Só grava o que foi aceito (consentimento não aceito = não existe).
    """
    for tipo, aceito in aceites.items():
        if aceito:
            Consentimento.objects.create(
                usuario=usuario, tipo=tipo, versao=VERSAO_TEXTOS, concedido_por=concedido_por
            )


def recalcular_situacao(usuario):
    """
    Decide a situação da conta olhando os fatos, em ordem.
    Funciona não importa o que aconteça primeiro (o menor confirmar o e-mail
    ou o responsável autorizar).
    """
    S = Usuario.Situacao
    if usuario.situacao == S.BLOQUEADA:
        return  # bloqueio só sai manualmente pelo admin

    if usuario.responsavel_id is None and not usuario.email_confirmado:
        nova = S.PENDENTE_EMAIL
    elif usuario.precisa_autorizacao_responsavel() and not usuario.autorizacoes.filter(
        autorizada_em__isnull=False
    ).exists():
        nova = S.PENDENTE_RESPONSAVEL
    else:
        nova = S.ATIVA

    usuario.situacao = nova
    usuario.save(update_fields=["situacao"])


def criar_autorizacao_responsavel(menor, nome, email, cpf_digitos):
    """
    Cria o pedido e devolve (autorizacao, token).
    O token "puro" só existe aqui, na memória, para ir no link do e-mail.
    secrets.token_urlsafe(32): 32 bytes aleatórios do sistema operacional -> ~43 caracteres.
    """
    token = secrets.token_urlsafe(32)
    autorizacao = AutorizacaoResponsavel.objects.create(
        menor=menor,
        nome_responsavel=nome,
        email_responsavel=email,
        cpf_hmac=gerar_hmac(cpf_digitos),
        cpf_cifrado=cifrar(cpf_digitos),
        token_hash=hash_token(token),
        expira_em=timezone.now() + timedelta(days=DIAS_VALIDADE_AUTORIZACAO),
    )
    return autorizacao, token


def enviar_confirmacao_email(request, usuario):
    # uid: o id do usuário em base64 (só para não aparecer "5" puro no link).
    uid = urlsafe_base64_encode(force_bytes(usuario.pk))
    token = token_confirmacao_email.make_token(usuario)
    # reverse() monta a URL pelo NOME da rota; build_absolute_uri() põe http://dominio na frente.
    link = request.build_absolute_uri(reverse("contas:confirmar_email", args=[uid, token]))
    corpo = render_to_string("contas/emails/confirmar_email.txt", {"usuario": usuario, "link": link})
    # Em desenvolvimento, o e-mail aparece no TERMINAL do runserver (MAILERS console).
    return enviar_email("Liah - confirme seu e-mail", corpo, [usuario.email])


def enviar_pedido_autorizacao(request, autorizacao, token):
    link = request.build_absolute_uri(reverse("contas:autorizar_responsavel", args=[token]))
    corpo = render_to_string(
        "contas/emails/autorizar_responsavel.txt",
        {
            "autorizacao": autorizacao,
            "menor": autorizacao.menor,
            "link": link,
            "dias": DIAS_VALIDADE_AUTORIZACAO,
        },
    )
    return enviar_email(
        "Liah - pedido de autorização de cadastro",
        corpo,
        [autorizacao.email_responsavel],
    )


# ============================================================ EXCLUSÃO DE CONTA

def resumo_exclusao(usuario):
    """O que vai ser apagado junto (para mostrar na tela ANTES de confirmar)."""
    return {
        "consentimentos": usuario.consentimentos.count(),
        "dependentes": list(usuario.dependentes.all()),
    }


def excluir_conta(usuario, excluido_por_responsavel=False, request=None):
    """
    Apaga a conta e TUDO ligado a ela (CASCADE): consentimentos, autorizações
    e as contas das crianças que ela gerencia.

    Os e-mails precisam ser coletados ANTES do delete(): depois disso,
    os dados não existem mais.
    """
    nome = usuario.first_name or "usuário(a)"
    email_usuario = usuario.email

    # Adolescente que se cadastrou sozinho: avisamos o(s) responsável(is) que autorizaram.
    emails_responsaveis = []
    if usuario.precisa_autorizacao_responsavel():
        emails_responsaveis = list(
            usuario.autorizacoes.filter(autorizada_em__isnull=False)
            .values_list("email_responsavel", flat=True)
            .distinct()
        )

    id_conta = usuario.pk
    with transaction.atomic():
        usuario.delete()
        quem = "pelo responsável" if excluido_por_responsavel else "pelo próprio usuário"
        registrar_evento(
            RegistroSeguranca.Tipo.CONTA_EXCLUIDA,
            request=request,
            detalhe=f"Conta #{id_conta} excluída {quem}",
        )

    # Confirmação para o próprio dono da conta (se foi o responsável que excluiu
    # a conta da criança, quem recebe a confirmação é o responsável, na view).
    if not excluido_por_responsavel:
        corpo = render_to_string("contas/emails/conta_excluida.txt", {"nome": nome})
        enviar_email("Liah - sua conta foi excluída", corpo, [email_usuario])

    for email in emails_responsaveis:
        corpo = render_to_string("contas/emails/aviso_responsavel_exclusao.txt", {"nome": nome})
        enviar_email("Liah - aviso de exclusão de conta", corpo, [email])


# ============================================================ LGPD: MEUS DADOS

def exportar_dados(usuario):
    """
    Direito de ACESSO e PORTABILIDADE (LGPD art. 18): tudo o que a Liah guarda
    sobre a pessoa, num formato que qualquer programa lê (JSON).
    """
    def data(valor):
        # datas viram texto no padrão ISO (ex.: 2026-11-15T14:30:00-03:00)
        return valor.isoformat() if valor else None

    return {
        "gerado_em": data(timezone.now()),
        "controlador": "Projeto Liah - contato: liahrobo.oficial@gmail.com",
        "conta": {
            "nome": usuario.first_name,
            "sobrenome": usuario.last_name,
            "email": usuario.email,
            "data_nascimento": data(usuario.data_nascimento),
            "cpf": usuario.ler_cpf() or None,
            "plano": usuario.get_plano_display(),
            "situacao": usuario.get_situacao_display(),
            "email_confirmado": usuario.email_confirmado,
            "entrou_com_google": bool(usuario.google_sub),
            "criada_em": data(usuario.date_joined),
            "ultimo_login": data(usuario.last_login),
            "responsavel": usuario.responsavel.get_full_name() if usuario.responsavel else None,
        },
        "consentimentos": [
            {
                "tipo": c.get_tipo_display(),
                "versao_do_texto": c.versao,
                "aceito_em": data(c.aceito_em),
                "revogado_em": data(c.revogado_em),
                "concedido_pelo_responsavel": bool(c.concedido_por_id),
            }
            for c in usuario.consentimentos.all()
        ],
        "autorizacoes_de_responsavel": [
            {
                "nome_responsavel": a.nome_responsavel,
                "email_responsavel": a.email_responsavel,
                "pedida_em": data(a.criada_em),
                "autorizada_em": data(a.autorizada_em),
                "negada_em": data(a.negada_em),
            }
            for a in usuario.autorizacoes.all()
        ],
        "contas_que_eu_gerencio": [
            {"nome": d.get_full_name(), "email": d.email} for d in usuario.dependentes.all()
        ],
        "registros_de_seguranca": [
            {"evento": r.get_tipo_display(), "quando": data(r.criado_em), "ip": r.ip}
            for r in usuario.registros_seguranca.all()[:200]
        ],
        "conversas": [
            {
                "titulo": c.titulo,
                "mensagens": [
                    {"autor": m.get_autor_display(), "texto": m.texto, "quando": data(m.criada_em)}
                    for m in c.mensagens.all()
                ],
            }
            # prefetch: busca TODAS as mensagens numa consulta só (em vez de uma por conversa)
            for c in usuario.conversas.prefetch_related("mensagens")
        ],
    }
