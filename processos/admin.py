from django.contrib import admin
from .models import Processo

# Register your models here.

@admin.register(Processo)
class ProcessoAdmin(admin.ModelAdmin):
  # Colunas que aparecem na tabela
    list_display = (
        "numero",
        "descricao",
        "data_abertura",
        "valor_estimado_formatado",
        "status",
    )

    # Barra de pesquisa
    search_fields = (
        "numero",
        "descricao",
    )

    # Filtros laterais
    list_filter = (
        "status",
        "data_abertura",
    )

    # Ordenação padrão do admin
    ordering = (
        "-data_criacao",
    )

    # Quantidade de itens por página
    list_per_page = 20

    def valor_estimado_formatado(self, obj):
      return f"R$ {obj.valor_estimado:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
