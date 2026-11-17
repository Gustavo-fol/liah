from django.urls import path

from . import api, views, voz

app_name = "nucleo"

urlpatterns = [
    # Página
    path("chat/", views.chat, name="chat"),
    path("sobre/", views.sobre, name="sobre"),
    path("inicio/", views.inicio, name="inicio"),          # apresentação da Liah (para a feira e para o link)
    path("offline/", views.offline, name="offline"),       # o app instalado mostra esta página sem internet
    path("sw.js", views.service_worker, name="service_worker"),   # precisa ficar na RAIZ do site

    # API v1 (JSON)
    path("api/v1/status/", api.status, name="api_status"),
    path("api/v1/mensagens/", api.enviar_mensagem, name="api_enviar"),
    path("api/v1/mensagens/<int:pk>/avaliacao/", api.avaliar_mensagem, name="api_avaliar"),
    path("api/v1/conversas/", api.listar_conversas, name="api_conversas"),
    path("api/v1/conversas/<int:pk>/", api.conversa, name="api_conversa"),
    path("api/v1/visitante/mensagens/", api.enviar_mensagem_visitante, name="api_visitante"),
    path("api/v1/preferencias/", api.salvar_preferencias, name="api_preferencias"),
    path("api/v1/voz/transcrever/", voz.transcrever, name="api_voz_transcrever"),
    path("api/v1/voz/falar/", voz.falar, name="api_voz_falar"),
]
