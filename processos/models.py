from django.db import models
from django.utils import timezone

# Create your models here.

class Processo(models.Model):
    numero = models.CharField(max_length=20)
    descricao = models.CharField(max_length=255)
    data_abertura = models.DateField(default=timezone.now)
    valor_estimado = models.DecimalField(max_digits=15, decimal_places=2)

    def __str__(self):
        return self.numero
