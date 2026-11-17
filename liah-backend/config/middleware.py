"""
MIDDLEWARES da Liah = código que roda em TODA resposta, antes de ela sair para o navegador.
"""


class PermissoesNavegadorMiddleware:
    """
    Permissions-Policy: diz ao navegador quais recursos do aparelho a Liah pode pedir.
      microfone -> só a própria Liah (modos de voz)
      câmera, localização, pagamento, USB... -> ninguém
    Se algum dia entrar um script estranho na página, ele não consegue ligar a câmera.
    """

    POLITICA = "microphone=(self), camera=(), geolocation=(), payment=(), usb=(), interest-cohort=()"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        resposta = self.get_response(request)
        resposta.setdefault("Permissions-Policy", self.POLITICA)
        return resposta
