from django.db import models

# Create your models here.

class Mapa(models.Model):
    nome = models.CharField(max_length=255)
    arquivo = models.FileField(upload_to="arquivos/")
    data_upload = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.nome

class DadosMapa(models.Model):
    mapa = models.ForeignKey(Mapa, on_delete=models.CASCADE, related_name='dados')
    linha = models.IntegerField()
    coluna = models.CharField(max_length=255)
    valor =  models.TextField()

    def __str__(self):
        return f"{self.mapa.nome} - Linha {self.linha} - {self.coluna}"
