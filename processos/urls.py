from django.urls import path
from . import views

urlpatterns = [
    path("", views.processos, name="processos"),
    path("documentos/", views.documentos, name="documentos"),
    path("mapasgerados/", views.mapas_gerados, name="mapas_gerados"),
    path("novo/", views.novo_processo, name="novo_processo"),
    path("<str:numero_slug>/", views.visualizar_processo, name="visualizar_processo"),
    path("<str:numero_slug>/editar/", views.editar_processo, name="editar_processo"),
    path("download/<str:tipo>/<int:processo_id>/", views.download_arquivo, name="download_arquivo"),
]
