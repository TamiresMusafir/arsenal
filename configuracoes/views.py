from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from usuarios.models import Perfil

@login_required
def configuracoes(request):
    return render(request, "configuracoes.html")

@login_required
def conta(request):
    usuario = request.user

    return render(request, "conta.html", {"usuario": usuario,})

@login_required
def editar_conta(request):
    usuario = request.user
    perfil, created = Perfil.objects.get_or_create(usuario=usuario)

    if request.method == "POST":
    
        # Atualizar dados do usuário
        usuario.first_name = request.POST.get("nome")
        usuario.last_name = request.POST.get("sobrenome")
        usuario.email = request.POST.get("email")

        usuario.save()

        # Atualizar foto
        if request.FILES.get("foto"):
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
