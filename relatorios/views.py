from django.shortcuts import render

# Create your views here.
def relatorios(request):
    return render(request, "relatorios.html")
