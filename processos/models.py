from django.db import models
from django.utils import timezone
 
 
class Processo(models.Model):
    STATUS_PENDENTE = 'pendente'
    STATUS_PROCESSANDO = 'processando'
    STATUS_CONCLUIDO = 'concluido'
    STATUS_ERRO = 'erro'
 
    STATUS_CHOICES = [
        (STATUS_PENDENTE, 'Pendente'),
        (STATUS_PROCESSANDO, 'Em andamento'),
        (STATUS_CONCLUIDO, 'Concluído'),
        (STATUS_ERRO, 'Erro no processamento'),
    ]
 
    BADGES = {
        STATUS_PENDENTE: 'bg-secondary',
        STATUS_PROCESSANDO: 'bg-warning',
        STATUS_CONCLUIDO: 'bg-success',
        STATUS_ERRO: 'bg-danger',
    }
 
    numero = models.CharField(max_length=20, unique=True)
    descricao = models.CharField(max_length=255)
    data_abertura = models.DateField(default=timezone.now)
    valor_estimado = models.DecimalField(max_digits=15, decimal_places=2)
    arquivo_processo = models.FileField(upload_to='processos/', null=True, blank=True)
    data_criacao = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default=STATUS_PENDENTE)
    arquivo_gerado_xlsx = models.FileField(upload_to='processos/gerados/', null=True, blank=True)
    arquivo_gerado_odt = models.FileField(upload_to='processos/gerados/', null=True, blank=True)
 
    emails_enviados = models.PositiveIntegerField(default=0)
    emails_recebidos = models.PositiveIntegerField(default=0)
    qtd_fornecedores = models.PositiveIntegerField(default=0)
    qtd_cotacoes = models.PositiveIntegerField(default=0)
    qtd_itens = models.PositiveIntegerField(default=0)
 
    class Meta:
        ordering = ['-data_criacao']
        verbose_name = 'Processo'
        verbose_name_plural = 'Processos'
 
    def __str__(self):
        return f"{self.numero} - {self.descricao[:50]}"
 
    # >>> NOVO: atalhos usados no template e nos nomes de arquivo
    @property
    def numero_slug(self):
        """00015/2026 -> 00015_2026"""
        return self.numero.replace('/', '_')
 
    @property
    def status_label(self):
        return dict(self.STATUS_CHOICES).get(self.status, self.status.capitalize())
 
    @property
    def status_badge(self):
        return self.BADGES.get(self.status, 'bg-secondary')
 
 
# ==================== NOVO: DADOS EXTRAÍDOS PELA IA ====================
# Estas três tabelas guardam no SQLite o que hoje só existe no JSON.
# O JSON continua sendo gravado em disco como registro bruto/auditável.
 
class Fornecedor(models.Model):
    processo = models.ForeignKey(Processo, on_delete=models.CASCADE, related_name='fornecedores')
    indice = models.PositiveIntegerField()
    nome = models.CharField(max_length=255)
    cnpj = models.CharField(max_length=20, blank=True, default='')
    email = models.EmailField(blank=True, default='')
    valor_global = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
 
    class Meta:
        ordering = ['indice']
        unique_together = [('processo', 'indice')]
 
    def __str__(self):
        return f"{self.processo.numero} - {self.nome}"
 
 
class Item(models.Model):
    processo = models.ForeignKey(Processo, on_delete=models.CASCADE, related_name='itens')
    posicao = models.PositiveIntegerField()
    pi = models.CharField(max_length=50, blank=True, default='')
    descricao = models.CharField(max_length=500, blank=True, default='')
    qtde = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)
    uf = models.CharField(max_length=20, blank=True, default='')
    painel_preco = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    valor_unitario_estimado = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    valor_total = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
 
    class Meta:
        ordering = ['posicao']
        unique_together = [('processo', 'posicao')]
 
    def __str__(self):
        return f"{self.processo.numero} - item {self.posicao}"
 
 
class Cotacao(models.Model):
    """Uma célula do mapa: o preço de um fornecedor para um item."""
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name='cotacoes')
    fornecedor = models.ForeignKey(Fornecedor, on_delete=models.CASCADE, related_name='cotacoes')
    valor_unitario = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    texto_original = models.CharField(max_length=100, blank=True, default='')   # o que veio na proposta
    observacao = models.CharField(max_length=255, blank=True, default='')       # "sob consulta", "não cotado"
 
    class Meta:
        ordering = ['fornecedor__indice']
        unique_together = [('item', 'fornecedor')]
 
    def __str__(self):
        return f"{self.item} / {self.fornecedor.nome}: {self.valor_unitario}"
