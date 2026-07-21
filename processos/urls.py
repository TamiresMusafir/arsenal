from django.urls import path
from . import views

urlpatterns = [
    path("", views.processos, name="processos"),
    path("novo/", views.novo_processo, name="novo_processo"),
    path("documentos/", views.documentos, name="documentos"),
    path("mapasgerados/", views.documentos, name="mapas_gerados"),
]
