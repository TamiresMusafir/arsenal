from django.urls import path
from . import views
from django.contrib.auth import views as auth_views

urlpatterns = [
    path("", views.configuracoes, name="configuracoes"),
    path("conta/", views.conta, name="conta"),
    path("preferencias/", views.preferencias, name="preferencias"),
    path("alterar-senha/", auth_views.PasswordChangeView.as_view(template_name="alterarsenha.html", success_url="/configuracoes/conta/"), name="alterar_senha")
]
