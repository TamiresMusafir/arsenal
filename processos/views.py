from django.shortcuts import render, redirect
from .models import Processo

# Create your views here.
def processos(request):
    processos = Processo.objects.all().order_by("-id")
    return render(request, "processos.html", {"processos": processos})

def novo_processo(request):
    if request.method == 'POST':
        Processo.objects.create(numero = request.POST["numero"],
                                descricao = request.POST["descricao"],
                                valor_estimado = request.POST["valor_estimado"])

        return redirect("processos")
    
    return render(request, "novoprocesso.html")

def documentos(request):
    return render(request, "documentos.html")

def mapas_gerados(request):
    return render(request, "mapasgerados.html")
