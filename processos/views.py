from django.shortcuts import render, redirect
from django.utils import timezone
from .models import Processo
from django.db.models import Q

# Create your views here.
def processos(request):
    processos = Processo.objects.all()

    ordem = request.GET.get("ordem")
    data  = request.GET.get("data")
    busca = request.GET.get("busca")

    #Filtro de busca
    if busca: 
        palavras = busca.split()

        for palavra in palavras:
            processos = processos.filter(Q(numero__icontains=palavra) | Q(descricao__icontains=palavra))

    #Filtro de data
    hoje = timezone.now().date()

    if data == "hoje":
        processos = processos.filter(data_abertura=hoje)
    elif data == "mes":
        processos = processos.filter(data_abertura__month=hoje.month, 
                                data_abertura__year=hoje.year)
    elif data == "ano":
        processos = processos.filter(data_abertura__year=hoje.year)
    elif data == "qualquer":
        pass

    #Filtro de ordenação
    if ordem == "antigos":
        processos = processos.order_by("id")
    elif ordem == "numero":
        processos = processos.order_by("numero")
    elif ordem == "recentes":
        processos = processos.order_by("-id")

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
