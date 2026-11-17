from django.apps import AppConfig


class ContasConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "contas"
    verbose_name = "Contas e usuários"

    def ready(self):
        # ready() roda quando o Django termina de ligar.
        # Importar o arquivo de sinais aqui é o que "liga" os @receiver.
        from . import sinais  # noqa: F401
