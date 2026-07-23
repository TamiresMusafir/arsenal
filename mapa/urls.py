from django.urls import path
from . import views

urlpatterns = [
    path("", views.mapa, name="mapa"),
    path("processar-upload/", views.processar_upload, name="processar_upload"),
    path("baixar-modelo-base/", views.baixar_modelo_base, name="baixar_modelo_base"),
]   
