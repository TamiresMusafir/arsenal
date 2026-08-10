from django.conf import settings
from django.core.validators import RegexValidator
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

    # >>> NOVO (achado 2.8 / V15): aceita 00015/2026 e PE-90043/2026.
    # Validator só roda em full_clean()/ModelForm — não quebra linhas existentes.
    validador_numero = RegexValidator(
        r'^([A-Z]{2,4}-)?\d{4,6}/\d{4}$',
        'Use o formato 00015/2026 ou PE-90043/2026.'
    )

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='processos',
        null=True,
        blank=True,
        verbose_name='Responsável'
    )

    numero = models.CharField(max_length=20, unique=True,
                              validators=[validador_numero])
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

    # >>> NOVO (achado 1.9): qtd_cotacoes passa a contar CÉLULAS PREENCHIDAS.
    # O número de fornecedores que cotaram pelo menos um item vira campo próprio.
    qtd_fornecedores_com_preco = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['-data_criacao']
        verbose_name = 'Processo'
        verbose_name_plural = 'Processos'

    def __str__(self):
        return f"{self.numero} - {self.descricao[:50]}"

    @property
    def numero_slug(self):
        """00015/2026 -> 00015_2026"""
        return self.numero.replace('/', '_').replace('\\', '_')

    @property
    def status_label(self):
        return dict(self.STATUS_CHOICES).get(self.status, self.status.capitalize())

    @property
    def status_badge(self):
        return self.BADGES.get(self.status, 'bg-secondary')

    # >>> NOVO: atalhos para a aba de conferência
    @property
    def avisos_pendentes(self):
        return self.avisos.filter(resolvido=False).exclude(severidade='info')

    @property
    def precisa_conferencia(self):
        return self.avisos_pendentes.exists()


# ==================== DADOS EXTRAÍDOS PELA IA ====================
# Estas tabelas guardam no banco o que antes só existia no JSON.
# O JSON continua sendo gravado em disco como registro bruto/auditável.

class Fornecedor(models.Model):

    RESPOSTA_COTACAO = 'cotacao'
    RESPOSTA_DECLINIO = 'declinio'
    RESPOSTA_DUVIDA = 'duvida'
    RESPOSTA_SEM = 'sem_resposta'
    RESPOSTA_CHOICES = [
        (RESPOSTA_COTACAO, 'Cotação'),
        (RESPOSTA_DECLINIO, 'Declínio'),
        (RESPOSTA_DUVIDA, 'Dúvida/esclarecimento'),
        (RESPOSTA_SEM, 'Sem resposta'),
    ]

    processo = models.ForeignKey(Processo, on_delete=models.CASCADE, related_name='fornecedores')
    indice = models.PositiveIntegerField()
    nome = models.CharField(max_length=255)
    cnpj = models.CharField(max_length=20, blank=True, default='')
    email = models.EmailField(blank=True, default='')
    valor_global = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    tipo_resposta = models.CharField(max_length=20, choices=RESPOSTA_CHOICES, default=RESPOSTA_COTACAO)
    motivo_declinio = models.CharField(max_length=255, blank=True, default='')

    class Meta:
        ordering = ['indice']
        unique_together = [('processo', 'indice')]
        # >>> NOVO: cnpj é chave da 1ª passada do casamento (achados 1.7 / A3)
        indexes = [
            models.Index(fields=['processo', 'cnpj'], name='forn_processo_cnpj_idx'),
        ]

    def __str__(self):
        return f"{self.processo.numero} - {self.nome}"

    @property
    def cotou(self):
        return self.tipo_resposta == self.RESPOSTA_COTACAO


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

    # >>> NOVO (achado A12): a confiança já é calculada pelo ai_processor,
    # rebaixada para 70 quando houve OCR local, e morria no JSON.
    confianca = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text='0–100. Abaixo de 80, conferir contra o documento original.'
    )

    class Meta:
        ordering = ['posicao']
        unique_together = [('processo', 'posicao')]
        # >>> NOVO: pi é a chave primária de negócio do casamento base<->resposta
        indexes = [
            models.Index(fields=['processo', 'pi'], name='item_processo_pi_idx'),
        ]

    def __str__(self):
        return f"{self.processo.numero} - item {self.posicao}"

    @property
    def confianca_baixa(self):
        return self.confianca is not None and self.confianca < 80


class Cotacao(models.Model):
    """Uma célula do mapa: o preço de um fornecedor para um item."""

    # >>> NOVO: motivos padronizados para célula sem preço.
    # O campo observacao já existia e nunca era preenchido.
    SEM_PRECO_SOB_CONSULTA = 'sob_consulta'
    SEM_PRECO_NAO_COTADO = 'nao_cotado'
    SEM_PRECO_SEM_ESTOQUE = 'sem_estoque'
    SEM_PRECO_ILEGIVEL = 'ilegivel'

    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name='cotacoes')
    fornecedor = models.ForeignKey(Fornecedor, on_delete=models.CASCADE, related_name='cotacoes')
    valor_unitario = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    texto_original = models.CharField(max_length=100, blank=True, default='')   # o que veio na proposta
    observacao = models.CharField(max_length=255, blank=True, default='')       # "sob consulta", "não cotado"

    # >>> NOVO (achado A12)
    confianca = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        ordering = ['fornecedor__indice']
        unique_together = [('item', 'fornecedor')]

    def __str__(self):
        return f"{self.item} / {self.fornecedor.nome}: {self.valor_unitario}"

    @property
    def confianca_baixa(self):
        return self.confianca is not None and self.confianca < 80


# ==================== NOVO: TRILHA DE CONFERÊNCIA ====================
# Achado 3.2 / R1. Os avisos já são produzidos pelo merge_results e pelo
# resumo_extracao, e chegam ao ODT — mas não ao banco nem à tela. Sem isso,
# não há como filtrar processos pendentes nem marcar aviso como resolvido.

class AvisoProcessamento(models.Model):
    INFO = 'info'
    ATENCAO = 'atencao'
    ERRO = 'erro'
    SEVERIDADE_CHOICES = [
        (INFO, 'Informativo'),
        (ATENCAO, 'Requer conferência'),
        (ERRO, 'Erro'),
    ]

    BADGES = {
        INFO: 'bg-info',
        ATENCAO: 'bg-warning',
        ERRO: 'bg-danger',
    }

    processo = models.ForeignKey(Processo, on_delete=models.CASCADE, related_name='avisos')
    item = models.ForeignKey(Item, on_delete=models.SET_NULL, null=True, blank=True,
                             related_name='avisos')
    fornecedor = models.ForeignKey(Fornecedor, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='avisos')

    # pi_nao_encontrado, valor_ambiguo, nome_ambiguo, fornecedor_nao_casado,
    # preco_divergente, preco_zero, estimativa_ignorada, sem_linha_base,
    # item_sem_pi, costura_por_nome, geral, item
    tipo = models.CharField(max_length=50)
    severidade = models.CharField(max_length=10, choices=SEVERIDADE_CHOICES, default=ATENCAO)
    mensagem = models.CharField(max_length=500)
    valor_bruto = models.CharField(max_length=200, blank=True, default='',
                                   help_text='Texto original que gerou o aviso.')

    resolvido = models.BooleanField(default=False)
    resolvido_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                      on_delete=models.SET_NULL, related_name='avisos_resolvidos')
    resolvido_em = models.DateTimeField(null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['severidade', 'tipo', 'id']
        verbose_name = 'Aviso de processamento'
        verbose_name_plural = 'Avisos de processamento'
        indexes = [
            models.Index(fields=['processo', 'resolvido'], name='aviso_processo_resolv_idx'),
        ]

    def __str__(self):
        return f"[{self.severidade}] {self.tipo}: {self.mensagem[:60]}"

    @property
    def badge(self):
        return self.BADGES.get(self.severidade, 'bg-secondary')

    def marcar_resolvido(self, usuario=None):
        self.resolvido = True
        self.resolvido_por = usuario
        self.resolvido_em = timezone.now()
        self.save(update_fields=['resolvido', 'resolvido_por', 'resolvido_em'])
