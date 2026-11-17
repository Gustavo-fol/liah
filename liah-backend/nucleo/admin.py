"""
Admin das conversas: mostra QUE a conversa existe e o MAIOR nível de risco,
mas NUNCA o conteúdo. Privacidade por padrão (LGPD): nem o administrador lê
as conversas pelo painel.
"""
from django.contrib import admin
from django.db.models import Count

from .models import Conversa, Mensagem


@admin.register(Conversa)
class ConversaAdmin(admin.ModelAdmin):
    list_display = ("id", "usuario", "criada_em", "atualizada_em", "total_mensagens", "maior_risco")
    list_filter = ("mensagens__risco",)
    search_fields = ("usuario__email",)
    readonly_fields = ("usuario", "criada_em", "atualizada_em")

    def get_queryset(self, request):
        # annotate: o banco já conta as mensagens junto da busca (mais rápido).
        return super().get_queryset(request).annotate(qtd=Count("mensagens")).distinct()

    @admin.display(description="mensagens", ordering="qtd")
    def total_mensagens(self, obj):
        return obj.qtd

    @admin.display(description="maior risco")
    def maior_risco(self, obj):
        riscos = set(obj.mensagens.values_list("risco", flat=True))
        for nivel in (Mensagem.Risco.ALTO, Mensagem.Risco.ATENCAO):
            if nivel in riscos:
                return Mensagem.Risco(nivel).label
        return Mensagem.Risco.NENHUM.label

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
