"""
ARQUIVO NOVO - crie como <app>/persistencia.py

Grava no SQLite o dicionário devolvido pelo ai_processor.merge_results().
Chame no novo_processo, logo depois do json.dump:

    from .persistencia import salvar_dados_ai
    salvar_dados_ai(processo, dados_ai, emails_recebidos)
"""
import re       
from decimal import Decimal, InvalidOperation

from django.db import transaction

from .models import Cotacao, Fornecedor, Item
from .services import para_float

def _chave(texto):                                    # >>> NOVO
    return re.sub(r'[^a-z0-9]', '', str(texto or '').lower())

def para_decimal(valor):
    numero = para_float(valor)
    if numero is None:
        return None
    try:
        return Decimal(str(round(numero, 2)))
    except (InvalidOperation, ValueError):
        return None


@transaction.atomic
def salvar_dados_ai(processo, dados_ai, emails_recebidos=0, modo='completo'):
    """
    modo='base'     -> grava a LINHA DE BASE do modelo de proposta (itens/PI),
                       sem fornecedores. Apaga o que houver antes.
    modo='completo' -> grava as respostas. PRESERVA os itens da linha de base e
                       casa as cotações pelo PI.
    Pode rodar de novo sem duplicar.
    """

    fornecedor, _ = Fornecedor.objects.update_or_create(
    processo=processo,
    cnpj=cnpj or None,
    defaults={'nome': nome, 'email': ..., ...},
)
    processo.fornecedores.all().delete()          # a cascata apaga as cotações

    if modo == 'base':
        processo.itens.all().delete()

    # --- itens: linha de base (cria) ou respostas (localiza pelo PI) ---
    itens_por_pi = {_chave(i.pi): i for i in processo.itens.all() if i.pi}
    proxima_posicao = (max([i.posicao for i in processo.itens.all()], default=0)) + 1

    # --- fornecedores ---------------------------------------------------
    fornecedores = {}
    for indice, bruto in enumerate(dados_ai.get('empresas') or [], start=1):
        if isinstance(bruto, str):
            bruto = {'nome': bruto}
        if not isinstance(bruto, dict):
            continue
        nome = (bruto.get('nome') or f'Empresa {indice}')[:255]
        fornecedor = Fornecedor.objects.create(
            processo=processo,
            indice=indice,
            nome=nome,
            cnpj=(bruto.get('cnpj') or '')[:20],
            email=(bruto.get('email') or '')[:254],
            tipo_resposta=(bruto.get('tipo_resposta') or 'cotacao'),      # >>> NOVO
            motivo_declinio=(bruto.get('motivo_declinio') or '')[:255],   # >>> NOVO
            valor_global=para_decimal(bruto.get('valor_global')),
        )
        # >>> ALTERADO: indexa pelo NOME (o que a IA usa) e pelo empresaN (JSON antigo)
        fornecedores[_chave(nome)] = fornecedor
        fornecedores[f'empresa{indice}'] = fornecedor

    # --- itens e cotações ------------------------------------------------
    cotacoes = []
    for posicao, bruto in enumerate(dados_ai.get('itens') or [], start=1):
        if not isinstance(bruto, dict):
            continue

        pi = str(bruto.get('pi') or '')[:50]
        item = itens_por_pi.get(_chave(pi))

        if item is None:
            item = Item.objects.create(
                processo=processo,
                posicao=int(para_float(bruto.get('item')) or proxima_posicao),
                pi=pi,
                descricao=str(bruto.get('nome_em_portugues') or bruto.get('descricao') or '')[:500],
                qtde=para_decimal(bruto.get('qtde')),
                uf=str(bruto.get('uf') or '')[:20],
                painel_preco=para_decimal(bruto.get('painel_preco')),
                valor_unitario_estimado=para_decimal(bruto.get('valor_unitario_estimado')),
                valor_total=para_decimal(bruto.get('valor_total')),
            )
            proxima_posicao = max(proxima_posicao, item.posicao) + 1
            if pi:
                itens_por_pi[_chave(pi)] = item
        else:
            # >>> NOVO: item da linha de base — só completa o que faltar
            mudou = []
            for campo, valor in (('descricao', str(bruto.get('nome_em_portugues') or '')[:500]),
                                 ('uf', str(bruto.get('uf') or '')[:20])):
                if valor and not getattr(item, campo):
                    setattr(item, campo, valor)
                    mudou.append(campo)
            for campo in ('valor_unitario_estimado', 'valor_total'):
                valor = para_decimal(bruto.get(campo))
                if valor is not None:
                    setattr(item, campo, valor)
                    mudou.append(campo)
            if mudou:
                item.save(update_fields=mudou)

        for chave_empresa, valor in (bruto.get('empresas') or {}).items():
            fornecedor = (fornecedores.get(_chave(chave_empresa))
                          or fornecedores.get(str(chave_empresa).lower()))
            if not fornecedor:
                continue
            cotacoes.append(Cotacao(
                item=item,
                fornecedor=fornecedor,
                valor_unitario=para_decimal(valor),
                texto_original=str(valor if valor not in (None, '') else '')[:100],
            ))

    Cotacao.objects.bulk_create(cotacoes, batch_size=500)

    # --- contadores da tela de Documentos ---------------------------------
    processo.qtd_fornecedores = processo.fornecedores.count()
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
