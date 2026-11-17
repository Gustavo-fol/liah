from django.urls import path

from . import views

app_name = "interno"

urlpatterns = [
    path("", views.painel, name="painel"),
    path("usuarios/<int:pk>/plano/", views.mudar_plano, name="mudar_plano"),
    path("backup/fazer/", views.fazer_backup, name="fazer_backup"),
    path("backup/baixar/", views.baixar_backup, name="baixar_backup"),
    path("ia/", views.configurar_ia, name="ia"),
    path("dicionario/", views.dicionario, name="dicionario"),
    path("dicionario/importar/", views.dicionario_importar, name="dicionario_importar"),
    path("dicionario/nova/", views.regra_editar, name="regra_nova"),
    path("dicionario/<int:pk>/", views.regra_editar, name="regra_editar"),
    path("dicionario/<int:pk>/apagar/", views.regra_apagar, name="regra_apagar"),
    path("dicionario/sugerir/", views.regras_sugerir, name="regras_sugerir"),
    path("dicionario/exportar/", views.dicionario_exportar, name="dicionario_exportar"),
    path("contextos/novo/", views.contexto_editar, name="contexto_novo"),
    path("contextos/<int:pk>/", views.contexto_editar, name="contexto_editar"),
    path("laboratorio/", views.laboratorio, name="laboratorio"),
    path("relatorios/", views.relatorios_view, name="relatorios"),
    path("relatorios/exportar/resumo/", views.exportar_resumo, name="exportar_resumo"),
    path("relatorios/exportar/usuarios/", views.exportar_usuarios, name="exportar_usuarios"),
    path("relatorios/exportar/seguranca/", views.exportar_seguranca, name="exportar_seguranca"),
    path("relatorios/exportar/laboratorio/", views.exportar_laboratorio, name="exportar_laboratorio"),
]
