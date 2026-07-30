from .models import Perfil

def perfil_usuario(request):
	if request.user.is_authenticated:
		perfil, created = Perfil.objects.get_or_create(usuario=request.user)

		return {"perfil":perfil}

	return{}
