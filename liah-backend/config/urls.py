"""
Mapa de endereços principal do site da Liah.
"""
from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    # Página inicial: vai DIRETO para o chat (aberto a todos: visitante usa o modo gratuito).
    # A apresentação da Liah fica em /inicio/.
    path("", RedirectView.as_view(pattern_name="nucleo:chat", permanent=False)),
    path("contas/", include("contas.urls")),
    path("", include("nucleo.urls")),    # chat/ e api/v1/...
    path("interno/", include("interno.urls")),   # área da equipe (só is_staff; os outros recebem 404)
    # O endereço do admin vem do .env (LIAH_ADMIN_URL). Não deixe "admin/" no site no ar.
    path(settings.LIAH_ADMIN_URL, admin.site.urls),
]
