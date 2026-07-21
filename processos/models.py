from django.db import models

# Create your models here.

class Processo(models.Model):
    numero = models.CharField(max_length=20)
    descricao = models.CharField(max_length=255)
    data_abertura = models.DateField()
    valor_estimado = models.DecimalField(max_digits=15, decimal_places=2)

    def __str__(self):
        return self.numero
