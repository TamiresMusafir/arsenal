import os
import json

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from usuarios.models import Perfil
from django.http import JsonResponse

@login_required
def configuracoes(request):
    return render(request, "configuracoes.html")

@login_required
def conta(request):
    usuario = request.user

    return render(request, "conta.html", {
        "usuario": usuario,
    })

@login_required
def editar_conta(request):
    usuario = request.user
    perfil, created = Perfil.objects.get_or_create(usuario=usuario)

    if request.method == "POST":
        usuario.first_name = request.POST.get("nome")
        usuario.last_name = request.POST.get("sobrenome")
        usuario.email = request.POST.get("email")
        usuario.save()

        if request.FILES.get("foto"):
            if perfil.foto and os.path.exists(perfil.foto.path):
                os.remove(perfil.foto.path)

            perfil.foto = request.FILES["foto"]
            perfil.save()

        return redirect("conta")

    return render(request, "editarconta.html", {
        "usuario": usuario,
        "perfil": perfil
    })

@login_required
def preferencias(request):
    return render(request, "preferencias.html")

@login_required
def alterar_tema(request):

    dados = json.loads(request.body)

    perfil, created = Perfil.objects.get_or_create(
        usuario=request.user
    )

    perfil.tema_escuro = dados["tema_escuro"]
    perfil.save()

    print(perfil.usuario.username, perfil.tema_escuro)

    return JsonResponse({
        "status": "ok"
    })
