"""
CONTEXT PROCESSOR = função que coloca variáveis em TODOS os templates automaticamente.
Registrada em settings.TEMPLATES -> context_processors.
"""
from django.conf import settings


def liah(request):
    return {
        # O botão "Continuar com Google" só aparece se as chaves estiverem no .env.
        "google_ativo": bool(settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET),
        # Tema salvo na conta (vazio para visitante: aí vale o que estiver no navegador).
        "tema_usuario": request.user.tema if request.user.is_authenticated else "",
    }
