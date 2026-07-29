from django.shortcuts import render

# Create your views here.

def configuracoes(request):
    return render(request, "configuracoes.html")

def conta(request):
    return render(request, "conta.html")

def preferencias(request):
    return render(request, "preferencias.html")
