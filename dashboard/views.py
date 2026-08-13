from django.shortcuts import render
from processos.models import Processo
from django.contrib.auth.decorators import login_required
# Create your views here.

@login_required
def dashboard(request):
    processos = Processo.objects.filter(usuario=request.user).order_by("-id")[:5]
    total_processos = Processo.objects.count()

    return render(request, "dashboard.html", {"processos": processos, "total_processos": total_processos})
