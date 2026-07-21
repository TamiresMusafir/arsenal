from django.shortcuts import render

# Create your views here.
def processos(request):
    return render(request, "processos.html")
