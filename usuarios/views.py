from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login
from django.contrib.auth import views as auth_views
from django.urls import reverse_lazy
from django.http import JsonResponse
from django.views.decorators.http import require_POST


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


@require_POST
def alterar_tema(request):
    perfil, _ = Perfil.objects.get_or_create(usuario=request.user)

    valor = request.POST.get("tema_escuro")
    if valor is None:
        perfil.tema_escuro = not perfil.tema_escuro          # alterna
    else:
        perfil.tema_escuro = valor in ("1", "true", "on", "True")

    perfil.save(update_fields=["tema_escuro"])

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({"ok": True, "tema_escuro": perfil.tema_escuro})
    return redirect("preferencias")
