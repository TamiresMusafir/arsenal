"""
ARQUIVO NOVO - crie como <app>/persistencia.py

Grava no SQLite o dicionário devolvido pelo ai_processor.merge_results().
Chame no novo_processo, logo depois do json.dump:

    from .persistencia import salvar_dados_ai
    salvar_dados_ai(processo, dados_ai, emails_recebidos)
"""

from decimal import Decimal, InvalidOperation

from django.db import transaction

from .models import Cotacao, Fornecedor, Item
from .services import para_float


def para_decimal(valor):
    numero = para_float(valor)
    if numero is None:
        return None
    try:
        return Decimal(str(round(numero, 2)))
    except (InvalidOperation, ValueError):
        return None


@transaction.atomic
def salvar_dados_ai(processo, dados_ai, emails_recebidos=0):
    """Regrava fornecedores, itens e cotações do processo. Pode rodar de novo sem duplicar."""
    processo.fornecedores.all().delete()   # a cascata apaga as cotações
    processo.itens.all().delete()

    # --- fornecedores ---
    fornecedores = {}
    for indice, bruto in enumerate(dados_ai.get('empresas') or [], start=1):
        if isinstance(bruto, str):
            bruto = {'nome': bruto}
        if not isinstance(bruto, dict):
            continue
        fornecedores[f'empresa{indice}'] = Fornecedor.objects.create(
            processo=processo,
            indice=indice,
            nome=(bruto.get('nome') or f'Empresa {indice}')[:255],
            cnpj=(bruto.get('cnpj') or '')[:20],
            email=(bruto.get('email') or '')[:254],
            valor_global=para_decimal(bruto.get('valor_global')),
        )

    # --- itens e cotações ---
    cotacoes = []
    for posicao, bruto in enumerate(dados_ai.get('itens') or [], start=1):
        if not isinstance(bruto, dict):
            continue

        item = Item.objects.create(
            processo=processo,
            posicao=int(para_float(bruto.get('item')) or posicao),
            pi=str(bruto.get('pi') or '')[:50],
            descricao=str(bruto.get('nome_em_portugues') or bruto.get('descricao') or '')[:500],
            qtde=para_decimal(bruto.get('qtde')),
            uf=str(bruto.get('uf') or '')[:20],
            painel_preco=para_decimal(bruto.get('painel_preco')),
            valor_unitario_estimado=para_decimal(bruto.get('valor_unitario_estimado')),
            valor_total=para_decimal(bruto.get('valor_total')),
        )

        for chave, valor in (bruto.get('empresas') or {}).items():
            fornecedor = fornecedores.get(chave)
            if not fornecedor:
                continue
            cotacoes.append(Cotacao(
                item=item,
                fornecedor=fornecedor,
                valor_unitario=para_decimal(valor),
                texto_original=str(valor or '')[:100],
            ))

    Cotacao.objects.bulk_create(cotacoes, batch_size=500)

    # --- contadores mostrados na tela de Documentos ---
    processo.qtd_fornecedores = len(fornecedores)
    processo.qtd_itens = processo.itens.count()
    processo.qtd_cotacoes = (
        Cotacao.objects
        .filter(item__processo=processo, valor_unitario__isnull=False)
        .values('fornecedor').distinct().count()
    )
    processo.emails_recebidos = emails_recebidos
    processo.save(update_fields=[
        'qtd_fornecedores', 'qtd_itens', 'qtd_cotacoes', 'emails_recebidos'
    ])

    return processo