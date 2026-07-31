from django.urls import path
from . import views
from django.contrib.auth import views as auth_views
from usuarios.views import AlterarSenha

urlpatterns = [
    path("", views.configuracoes, name="configuracoes"),
    path("conta/", views.conta, name="conta"),
    path("preferencias/", views.preferencias, name="preferencias"),
    path("alterar-tema/", views.alterar_tema, name="alterar_tema"),
    path("alterar-senha/", AlterarSenha.as_view(), name="alterar_senha"),
    path("editar-conta/", views.editar_conta, name="editar_conta")
]
