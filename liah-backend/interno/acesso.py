"""
CONTROLE DE ACESSO da área interna.

Quem NÃO é da equipe recebe 404 ("página não existe"), e não 403 ("proibido").
Assim um curioso nem descobre que a área interna existe.
"""
from functools import wraps

from django.http import Http404


def equipe_obrigatoria(view):
    @wraps(view)
    def embrulho(request, *args, **kwargs):
        if not (request.user.is_authenticated and request.user.is_staff):
            raise Http404
        return view(request, *args, **kwargs)
    return embrulho


def superusuario_obrigatorio(view):
    """Para o que é sensível (chaves de API): só o super admin."""
    @wraps(view)
    def embrulho(request, *args, **kwargs):
        if not (request.user.is_authenticated and request.user.is_superuser):
            raise Http404
        return view(request, *args, **kwargs)
    return embrulho
