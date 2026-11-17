"""
MANAGER = o "fabricante" de usuários.

O Django padrão cria usuários pelo "username". A Liah usa o E-MAIL como login,
então precisamos ensinar ao Django como criar um usuário comum e um superusuário
sem username. É este arquivo que o comando `createsuperuser` vai usar.
"""
from django.contrib.auth.models import BaseUserManager


class UsuarioManager(BaseUserManager):
    use_in_migrations = True

    def _criar(self, email, password, **campos_extras):
        if not email:
            raise ValueError("O e-mail é obrigatório.")
        # Tudo minúsculo: evita duas contas "Ana@gmail.com" e "ana@gmail.com".
        email = self.normalize_email(email).lower()
        usuario = self.model(email=email, **campos_extras)
        # set_password NUNCA guarda a senha em texto: guarda só o hash.
        usuario.set_password(password)
        usuario.save(using=self._db)
        return usuario

    def create_user(self, email, password=None, **campos_extras):
        """Usuário comum: sem acesso ao painel admin."""
        campos_extras.setdefault("is_staff", False)
        campos_extras.setdefault("is_superuser", False)
        return self._criar(email, password, **campos_extras)

    def create_superuser(self, email, password=None, **campos_extras):
        """Super admin: acesso total. Só você."""
        campos_extras.setdefault("is_staff", True)
        campos_extras.setdefault("is_superuser", True)
        campos_extras.setdefault("email_confirmado", True)
        campos_extras.setdefault("situacao", "ativa")

        if campos_extras.get("is_staff") is not True:
            raise ValueError("Superusuário precisa ter is_staff=True.")
        if campos_extras.get("is_superuser") is not True:
            raise ValueError("Superusuário precisa ter is_superuser=True.")

        return self._criar(email, password, **campos_extras)
