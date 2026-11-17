"""
LOGIN COM GOOGLE (OAuth 2.0 + OpenID Connect), feito só com a biblioteca padrão do Python.

Como funciona (o "baile" do OAuth):
  1) Liah manda a pessoa para o Google com: quem somos (client_id), para onde voltar
     (redirect_uri), o que queremos (scope: e-mail e nome) e 3 códigos de segurança.
  2) A pessoa escolhe a conta e aceita, NO SITE DO GOOGLE (a Liah nunca vê a senha).
  3) O Google devolve a pessoa para a Liah com um "code" (vale uma vez, por pouco tempo).
  4) A Liah, servidor-com-servidor, troca o code por um "id_token" com os dados da pessoa.

Os 3 códigos de segurança:
  - state:  número aleatório guardado na sessão. Na volta, tem que ser igual.
            Impede que um site malicioso "injete" o login de OUTRA pessoa (CSRF).
  - nonce:  vai dentro do id_token. Impede reaproveitar um token antigo (replay).
  - PKCE:   "code_verifier" secreto + "code_challenge" (o hash dele). Mesmo que alguém
            roube o code no caminho, sem o verifier não consegue trocar pelo token.
"""
import base64
import hashlib
import json
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings
from django.urls import reverse

URL_AUTORIZACAO = "https://accounts.google.com/o/oauth2/v2/auth"
URL_TOKEN = "https://oauth2.googleapis.com/token"
EMISSORES_VALIDOS = ("https://accounts.google.com", "accounts.google.com")
CHAVE_SESSAO = "google_oauth"


class ErroGoogle(Exception):
    """Qualquer problema no login com Google vira este erro, com mensagem para o usuário."""


def _base64url(dados_bytes):
    # base64 "seguro para URL" e sem os "=" do final (exigência do PKCE)
    return base64.urlsafe_b64encode(dados_bytes).rstrip(b"=").decode()


def _redirect_uri(request):
    # Tem que ser IDÊNTICO ao cadastrado no Google Cloud (inclusive a barra final).
    return request.build_absolute_uri(reverse("contas:google_retorno"))


def montar_url_de_login(request):
    """Passo 1: cria os códigos de segurança, guarda na sessão e monta o link do Google."""
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = _base64url(hashlib.sha256(verifier.encode()).digest())

    request.session[CHAVE_SESSAO] = {
        "state": state,
        "nonce": nonce,
        "verifier": verifier,
        "criado": time.time(),
    }

    parametros = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": _redirect_uri(request),
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "nonce": nonce,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "prompt": "select_account",   # sempre deixa a pessoa escolher a conta
    }
    return f"{URL_AUTORIZACAO}?{urllib.parse.urlencode(parametros)}"


def processar_retorno(request):
    """
    Passos 3 e 4: confere o state, troca o code pelo id_token e devolve um dicionário:
    {"sub", "email", "first_name", "last_name"}. Qualquer problema -> ErroGoogle.
    """
    guardado = request.session.pop(CHAVE_SESSAO, None)  # pop: só vale UMA vez

    if request.GET.get("error"):
        raise ErroGoogle("O login com Google foi cancelado.")
    if not guardado or time.time() - guardado["criado"] > 600:
        raise ErroGoogle("O login com Google expirou. Tente de novo.")
    if not secrets.compare_digest(request.GET.get("state", ""), guardado["state"]):
        # compare_digest compara sem "vazar" pelo tempo de resposta quantos caracteres batem.
        raise ErroGoogle("Pedido de login inválido. Tente de novo.")

    code = request.GET.get("code")
    if not code:
        raise ErroGoogle("O Google não devolveu a autorização. Tente de novo.")

    # ---- Troca o code pelo token (conversa direta Liah <-> Google, por HTTPS)
    corpo = urllib.parse.urlencode({
        "code": code,
        "client_id": settings.GOOGLE_CLIENT_ID,
        "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "redirect_uri": _redirect_uri(request),
        "grant_type": "authorization_code",
        "code_verifier": guardado["verifier"],
    }).encode()
    pedido = urllib.request.Request(
        URL_TOKEN, data=corpo, method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(pedido, timeout=10) as resposta:
            tokens = json.load(resposta)
    except (urllib.error.URLError, ValueError) as erro:
        raise ErroGoogle("Não foi possível falar com o Google agora. Tente de novo.") from erro

    dados = _ler_id_token(tokens.get("id_token", ""))

    # ---- Conferências do id_token
    if dados.get("iss") not in EMISSORES_VALIDOS:
        raise ErroGoogle("Resposta do Google inválida (emissor).")
    if dados.get("aud") != settings.GOOGLE_CLIENT_ID:
        raise ErroGoogle("Resposta do Google inválida (destinatário).")
    if dados.get("exp", 0) < time.time():
        raise ErroGoogle("A resposta do Google expirou. Tente de novo.")
    if not secrets.compare_digest(dados.get("nonce", ""), guardado["nonce"]):
        raise ErroGoogle("Resposta do Google inválida (nonce).")
    if not dados.get("email_verified"):
        raise ErroGoogle("Seu e-mail do Google não está verificado.")

    return {
        "sub": dados["sub"],
        "email": dados["email"].strip().lower(),
        "first_name": (dados.get("given_name") or "")[:150],
        "last_name": (dados.get("family_name") or "")[:150],
    }


def _ler_id_token(id_token):
    """
    O id_token é um JWT: tres partes em base64 separadas por ponto: cabeçalho.dados.assinatura.
    Lemos só a parte do meio (os dados).

    Por que não conferimos a assinatura? Porque este token veio DIRETO do Google,
    numa conexão HTTPS que NÓS abrimos com oauth2.googleapis.com (passo 4).
    A documentação do OpenID Connect permite pular a assinatura nesse caso.
    (Se um dia o token vier pelo navegador, aí a assinatura é obrigatória.)
    """
    try:
        parte_dados = id_token.split(".")[1]
        parte_dados += "=" * (-len(parte_dados) % 4)  # devolve os "=" que o JWT tira
        return json.loads(base64.urlsafe_b64decode(parte_dados))
    except (IndexError, ValueError) as erro:
        raise ErroGoogle("Resposta do Google inválida.") from erro
