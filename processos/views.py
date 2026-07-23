from django.shortcuts import render, redirect
from django.utils import timezone
from .models import Processo
from django.db.models import Q
from django.core.paginator import Paginator
import re

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
    elif ordem == "maior_valor":
        processos = processos.order_by("-valor_estimado")
    elif ordem == "menor_valor":
        processos = processos.order_by("valor_estimado")

    #Paginação
    paginator = Paginator(processos, 10)
    page = request.GET.get("page")
    processos = paginator.get_page(page)

    return render(request, "processos.html", {"processos": processos})

def novo_processo(request):
    if request.method == 'POST':

        numero = request.POST.get("numero")
        descricao = request.POST.get("descricao")
        valor_estimado = request.POST.get("valor_estimado")

        erros = []

        if not numero or not descricao or not valor_estimado:
            erros.append("Todos os campos são obrigatórios!")
        
        if not re.match(r'^[0-9./-]+$', numero):
            erros.append("O número do processo deve conter apenas números e os caracteres / . -")

        try: 
            valor_estimado = float(valor_estimado)

            if valor_estimado < 0:
                erros.append("O valor estimado deve ser maior que zero.")

        except ValueError:
            erros.append("O valor estimado deve ser um número.")
        
    
        if erros:
            return render(request, "novoprocesso.html", {"erros": erros})

        Processo.objects.create(numero = numero,
                                descricao = descricao,
                                valor_estimado = valor_estimado)

        return redirect("processos")
    
    return render(request, "novoprocesso.html")

def documentos(request):
    return render(request, "documentos.html")

def mapas_gerados(request):
    return render(request, "mapasgerados.html")
