from django.urls import path
from . import views

urlpatterns = [
    path("", views.mapa, name="mapa"),
    path("processar-upload/", views.processar_upload, name="processar_upload"),    path("carregar/", views.carregar_ultimo_mapa, name="carregar_ultimo_mapa"),
     path("baixar-mapa/", views.baixar_mapa, name="baixar_mapa"),
]   
