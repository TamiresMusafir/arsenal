from django.shortcuts import render
from processos.models import Processo
# Create your views here.

def dashboard(request):
    processos = Processo.objects.all().order_by("-id")[:5]
    total_processos = Processo.objects.count()

    return render(request, "dashboard.html", {"processos": processos, "total_processos": total_processos})
