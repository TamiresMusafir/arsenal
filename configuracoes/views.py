from django.shortcuts import render
from django.contrib.auth.decorators import login_required

@login_required
def configuracoes(request):
    return render(request, "configuracoes.html")

@login_required
def conta(request):
    usuario = request.user

    if request.method == "POST":
        usuario.first_name = request.POST["nome"]
        usuario.last_name = request.POST["sobrenome"]
        usuario.email = request.POST["email"]

        usuario.save()

    return render(request, "conta.html", {"usuario": usuario})

@login_required
def preferencias(request):
    return render(request, "preferencias.html")
