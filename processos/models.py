from django.db import models
from django.utils import timezone

class Processo(models.Model):
    numero = models.CharField(max_length=20, unique=True)
    descricao = models.CharField(max_length=255)
    data_abertura = models.DateField()
    data_criacao = models.DateTimeField(auto_now_add=True)
    valor_estimado = models.DecimalField(max_digits=15, decimal_places=2)
    arquivo_processo = models.FileField(upload_to='processos/', null=True, blank=True)
    status = models.CharField(max_length=50, default='pendente')
    arquivo_gerado_xlsx = models.FileField(upload_to='processos/gerados/', null=True, blank=True)
    arquivo_gerado_odt = models.FileField(upload_to='processos/gerados/', null=True, blank=True)

    class Meta:
        ordering = ['-data_criacao']

    def __str__(self):
        return f"{self.numero} - {self.descricao[:50]}"
