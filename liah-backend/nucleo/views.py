"""
Páginas (HTML) do núcleo. A conversa em si acontece pela API (api.py).
"""
import json

from django.shortcuts import render
from django.templatetags.static import static
from django.views.decorators.cache import cache_control
from django.views.decorators.csrf import ensure_csrf_cookie

from contas.models import Consentimento

from . import api, projeto


@ensure_csrf_cookie   # garante o cookie csrftoken, que o JavaScript manda de volta nos POSTs
def chat(request):
    """
    Aberta para TODOS:
      - visitante: assistente geral, 15 mensagens por dia, nada salvo;
      - logado: o serviço completo da Liah, com histórico e acompanhamento.
    """
    usuario = request.user
    # Equipe sem a autorização de dados emocionais: conversa liberada, mas sem salvar nada.
    modo_teste = bool(usuario.is_authenticated and usuario.is_staff
                      and not usuario.tem_consentimento(Consentimento.Tipo.DADOS_SENSIVEIS))
    return render(request, "nucleo/chat.html", {
        "visitante": not usuario.is_authenticated,
        "modo_teste": modo_teste,
        "limite_visitante": api.LIMITE_VISITANTE_DIA,
    })


def sobre(request):
    """
    Página pública "Sobre a Liah": o que ela é, como decide o que responder,
    o que já funciona (situação AO VIVO) e as etapas do projeto.
    Não mostra nenhum dado de usuário.
    """
    etapas = [
        {"n": i, "nome": nome, "texto": texto,
         "estado": "feita" if i < projeto.ETAPA_ATUAL else ("agora" if i == projeto.ETAPA_ATUAL else "futura")}
        for i, (nome, texto) in enumerate(projeto.ETAPAS, start=1)
    ]
    return render(request, "nucleo/sobre.html", {
        "pipeline": projeto.PIPELINE,
        # vai para o JavaScript destacar o caminho da última mensagem desta visita
        "caminhos_json": json.dumps(projeto.CAMINHO_POR_ORIGEM),
        "partes": projeto.partes_do_sistema(),
        "etapas": etapas,
        "resumo": projeto.resumo(),
        "limite_visitante": api.LIMITE_VISITANTE_DIA,
    })


def inicio(request):
    """Página de apresentação: o que é a Liah, em uma tela. O "/" continua indo direto para o chat."""
    return render(request, "nucleo/inicio.html", {
        "limite_visitante": api.LIMITE_VISITANTE_DIA,
        "resumo": projeto.resumo(),
    })


def offline(request):
    """Mostrada pelo app instalado quando não há internet (o service worker guarda esta página)."""
    return render(request, "nucleo/offline.html")


@cache_control(no_cache=True)   # o navegador sempre confere se há versão nova do service worker
def service_worker(request):
    """
    SERVICE WORKER = um script que o navegador roda "por trás" do site.
    Na Liah ele só faz uma coisa: sem internet, mostra a página offline (nada de conversa fica guardado).
    É servido por uma VIEW (e não como arquivo estático) porque precisa estar na raiz "/sw.js"
    para valer para o site inteiro.
    """
    return render(request, "nucleo/sw.js", {
        "url_offline": "/offline/",
        "arquivos": [static("css/base.css"), static("img/liah.svg")],
    }, content_type="application/javascript")
