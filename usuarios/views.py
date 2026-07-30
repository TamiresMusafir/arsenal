from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login

# Create your views here.

def login_view(request):
  if request.method == "POST":
    username = request.POST["username"]
    password = request.POST["password"]

    usuario = authenticate(request, username=username, password=password)

    if usuario is not None:
      login(request, usuario)
      return redirect("home")

  return render(request, "login.html")