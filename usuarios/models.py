from django.db import models
from django.contrib.auth.models import User

# Create your models here.

class Perfil(models.Model):
    usuario = models.OneToOneField(User, on_delete=models.CASCADE)
    foto = models.ImageField(upload_to="perfil/", null=True, blank=True)
    tema_escuro = models.BooleanField(default=False)

    def __str__(self):
        return self.usuario.username
