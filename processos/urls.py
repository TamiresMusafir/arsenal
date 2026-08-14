from django.urls import path

from . import views

urlpatterns = [
    path("", views.processos, name="processos"),
    path("novo/", views.novo_processo, name="novo_processo"),
    path("documentos/", views.documentos, name="documentos"),
    path("mapasgerados/", views.mapas_gerados, name="mapas_gerados"),
    path("download/<str:tipo>/<int:processo_id>/",
         views.download_arquivo, name="download_arquivo"),
]
