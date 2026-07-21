from django.shortcuts import render

# Create your views here.
def processos(request):
    return render(request, "processos.html")

def novo_processo(request):
    return render(request, "novoprocesso.html")

def documentos(request):
    return render(request, "documentos.html")

def mapas_gerados(request):
    return render(request, "mapasgerados.html")
