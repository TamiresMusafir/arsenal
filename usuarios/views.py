from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login
from django.contrib.auth import views as auth_views
from django.urls import reverse_lazy


def login_view(request):
    if request.method == "POST":
        username = request.POST["username"]
        password = request.POST["password"]

        usuario = authenticate(request, username=username, password=password)

        if usuario is not None:
            login(request, usuario)
            return redirect("home")

    return render(request, "login.html")


class AlterarSenha(auth_views.PasswordChangeView):
    template_name = "alterarsenha.html"
    success_url = reverse_lazy("conta")

    def get_form(self, form_class=None):
        form = super().get_form(form_class)

        for field in form.fields.values():
            field.widget.attrs.update({"class": "form-control"})

        return form
