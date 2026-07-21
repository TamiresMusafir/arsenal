from django.shortcuts import render

# Create your views here.

def configuracoes(request):
    return render(request, "configuracoes.html")
