"""
processos/persistencia.py

Grava no banco o dicionário devolvido por ai_processor.merge_results().


    from .persistencia import salvar_dados_ai
    salvar_dados_ai(processo, dados_ai, emails_recebidos, modo='completo')

Regras da gravação:
    * É idempotente. Rodar duas vezes o mesmo pacote não duplica nada.
    * Por padrão faz UPSERT e nunca apaga. Substituição destrutiva só pela função substituir_dados_ai(), que exige decisão explícita.
    * O casamento de fornecedor é em duas passadas: primeiro por CNPJ
        (identificador legal, estável), depois por nome normalizado.
    * O casamento de item é pelo PI (número de estoque), que é a chave do negócio da linha do mapa comparativo.
"""

import logging
import re

from django.db import transaction

from .models import AvisoProcessamento, Cotacao, Fornecedor, Item, Processo
from .services import para_decimal, para_float

logger = logging.getLogger(__name__)

MODO_BASE = 'base'
MODO_COMPLETO = 'completo'

TAMANHO_LOTE = 500
LIMITE_AVISOS_ORFAOS = 100

def _chave(texto):
    """Normalização única usada em todas as comparações de nome/CNPJ/PI."""
    return re.sub(r'[^a-z0-9]', '', str(texto or '').lower())

# ==================== GRAVAÇÃO PRINCIPAL ====================

@transaction.atomic
def salvar_dados_ai(processo, dados_ai, emails_recebidos=0,
                    modo=MODO_COMPLETO, substituir=False):
    """Persiste fornecedores, itens, cotações e avisos de um processo.

    Args:
        processo: instância de Processo já gravada.
        dados_ai: dicionário no formato do merge_results.
        emails_recebidos: contagem de .eml/.msg do pacote de respostas.
        modo: MODO_BASE grava só a linha de base (itens/PI, sem fornecedores);
            MODO_COMPLETO grava as respostas preservando a linha de base.
        substituir: True apaga fornecedores e cotações antes de gravar.
            Use apenas por substituir_dados_ai().

    Returns:
        O processo atualizado.
    """
    # Trava a linha do processo até o fim da transação. Sem isso, dois uploads
    # simultâneos do mesmo número duplicam fornecedores e cotações.
    processo = Processo.objects.select_for_update().get(pk=processo.pk)

    if substituir:
        logger.warning('Substituindo dados do processo %s', processo.numero)
        processo.fornecedores.all().delete()          # cascata apaga cotações
        if modo == MODO_BASE:
            processo.itens.all().delete()
    else:
        logger.info('Atualizando processo %s (modo=%s)', processo.numero, modo)
    
    fornecedores = _gravar_fornecedores(processo, dados_ai)
    _gravar_itens_e_cotacoes(processo, dados_ai, fornecedores)
    _avisar_cotacoes_orfas(processo, fornecedores)
    _gravar_avisos_gerais(processo, dados_ai)
    _atualizar_contadores(processo, emails_recebidos)

    logger.info(
        'Processo %s salvo. Fornecedores: %s, itens: %s, células cotadas: %s',
        processo.numero, processo.qtd_fornecedores,
        processo.qtd_itens, processo.qtd_cotacoes,
    )
    return processo

    # ==================== FORNECEDORES ====================

def _gravar_fornecedores(processo, dados_ai):
    """Cria ou atualiza os fornecedores e devolve o índice de lookup.

    O índice mapeia todas as formas pelas quais uma cotação pode referenciar
    o fornecedor: nome normalizado, CNPJ normalizado e a chave legada empresaN.
    """
    existentes = list(processo.fornecedores.all())
    por_cnpj = {_chave(f.cnpj): f for f in existentes if f.cnpj}
    por_nome = {_chave(f.nome): f for f in existentes}
    indice_lookup = {}

    for indice, bruto in enumerate(dados_ai.get('empresas') or [], start=1):
        if isinstance(bruto, str):
            bruto = {'nome': bruto}
        if not isinstance(bruto, dict):
            continue

        campos = {
            'nome': (bruto.get('nome') or f'Empresa {indice}')[:255],
            'cnpj': (bruto.get('cnpj') or '').strip()[:20],
            'email': (bruto.get('email') or '')[:254],
            'tipo_resposta': bruto.get('tipo_resposta') or Fornecedor.RESPOSTA_COTACAO,
            'motivo_declinio': (bruto.get('motivo_declinio') or '')[:255],
            'valor_global': para_decimal(bruto.get('valor_global')),
        }

        chave_cnpj = _chave(campos['cnpj'])
        chave_nome = _chave(campos['nome'])
        fornecedor = por_cnpj.get(chave_cnpj) if chave_cnpj else None
        if fornecedor is None:
            fornecedor = por_nome.get(chave_nome)

        if fornecedor is None:
            fornecedor = Fornecedor.objects.create(
                processo=processo, indice=indice, **campos
            )
        else:
            _atualizar_fornecedor(fornecedor, campos, indice)

        if chave_cnpj:
            por_cnpj[chave_cnpj] = fornecedor
        por_nome[chave_nome] = fornecedor

        indice_lookup[chave_nome] = fornecedor
        indice_lookup[f'empresa{indice}'] = fornecedor
        if chave_cnpj:
            indice_lookup[chave_cnpj] = fornecedor

    return indice_lookup

def _atualizar_fornecedor(fornecedor, campos, indice):
    """Grava só o que mudou, para não sujar o log de auditoria do banco.  """
    alterados = [nome for nome, valor in campos.items()
                if valor and getattr(fornecedor, nome) != valor]
    if fornecedor.indice != indice:
        logger.info('Fornecedor %s mudou do índice %s para %s',
                    fornecedor.nome, fornecedor.indice, indice)
        fornecedor.indice = indice
        alterados.append('indice')

    if alterados:
        for nome in alterados:
            if nome != 'indice':
                setattr(fornecedor, nome, campos[nome])
        fornecedor.save(update_fields=alterados)

# ==================== ITENS E COTAÇÕES ====================

def _gravar_itens_e_cotacoes(processo, dados_ai, fornecedores):
    """Casa cada item pelo PI e grava as cotações em lote."""
    itens_por_pi = {_chave(i.pi): i for i in processo.itens.all() if i.pi}
    proxima_posicao = max((i.posicao for i in processo.itens.all()), default=0) + 1

    cotacoes_existentes = {
        (c.item_id, c.fornecedor_id): c
        for c in Cotacao.objects.filter(item__processo=processo)
    }
    a_criar = []
    a_atualizar = []

    for bruto in dados_ai.get('itens') or []:
        if not isinstance(bruto, dict):
            continue

        item, proxima_posicao = _obter_ou_criar_item(
            processo, bruto, itens_por_pi, proxima_posicao
        )
        _acumular_cotacoes(
            item, bruto, fornecedores, cotacoes_existentes, a_criar, a_atualizar
        )

    if a_atualizar:
        Cotacao.objects.bulk_update(
            a_atualizar,
            ['valor_unitario', 'texto_original', 'confianca'],
            batch_size=TAMANHO_LOTE,
        )
        logger.info('Atualizadas %s cotações', len(a_atualizar))

    if a_criar:
        Cotacao.objects.bulk_create(a_criar, batch_size=TAMANHO_LOTE)
        logger.info('Criadas %s cotações', len(a_criar))

def _obter_ou_criar_item(processo, bruto, itens_por_pi, proxima_posicao):
    """Devolve (item, proxima_posicao). Cria a linha só se o PI for novo."""
    pi = str(bruto.get('pi') or '')[:50]
    chave_pi = _chave(pi)
    item = itens_por_pi.get(chave_pi) if chave_pi else None

    if item is None:
        posicao = int(para_float(bruto.get('item')) or proxima_posicao)
        item = Item.objects.create(
            processo=processo,
            posicao=posicao,
            pi=pi,
            descricao=str(bruto.get('nome_em_portugues')
                        or bruto.get('descricao') or '')[:500],
            qtde=para_decimal(bruto.get('qtde'), casas=3),
            uf=str(bruto.get('uf') or '')[:20],
            painel_preco=para_decimal(bruto.get('painel_preco')),
            valor_unitario_estimado=para_decimal(bruto.get('valor_unitario_estimado')),
            valor_total=para_decimal(bruto.get('valor_total')),
            confianca=bruto.get('confianca'),
        )
        if chave_pi:
            itens_por_pi[chave_pi] = item
        return item, max(proxima_posicao, posicao) + 1

    _completar_item(item, bruto)
    return item, proxima_posicao


def _completar_item(item, bruto):
    """Preenche apenas os campos ainda vazios da linha de base.
    
    A linha de base veio do Modelo de Proposta e é a fonte da verdade. O que
    a IA leu da resposta do fornecedor só entra onde há lacuna.
    """
    alterados = []

    textos = (
        ('descricao', str(bruto.get('nome_em_portugues') or '')[:500]),
        ('uf', str(bruto.get('uf') or '')[:20]),
    )
    for campo, valor in textos:
        if valor and not getattr(item, campo):
            setattr(item, campo, valor)
            alterados.append(campo)

    for campo in ('valor_unitario_estimado', 'valor_total', 'painel_preco'):
        valor = para_decimal(bruto.get(campo))
        if valor is not None and getattr(item, campo) is None:
            setattr(item, campo, valor)
            alterados.append(campo)

    # Confiaça é sempre a pior observada: uma leitura ruim contamina a linha
    confianca = bruto.get('confianca')
    if isinstance(confianca, int):
        if item.confianca is None or confianca < item.confianca:
            item.confianca = confianca
            alterados.append('confianca')

    if alterados:
        item.save(update_fields=alterados)

def _acumular_cotacoes(item, bruto, fornecedores, existentes, a_criar, a_atualizar):
    """Prepara as células deste item para gravação em lote."""
    confianca =  bruto.get('confianca')
    
    for referencia, valor in (bruto.get('empresas') or {}).items():
        fornecedor = _resolver_fornecedor(referencia, fornecedores)
        if fornecedor is None:
            logger.warning('Fornecedor não encontrado para chave %r', referencia)
            continue
        
        valor_decimal = para_decimal(valor, item=item, fornecedor=fornecedor)
        texto_original = str(valor if valor not in (None, '') else '')[:100]
        chave = (item.id, fornecedor.id)
        cotacao = existentes.get(chave)

        if cotacao is None:
            nova = Cotacao(
                item=item,
                fornecedor=fornecedor,
                valor_unitario=valor_decimal,
                texto_original=texto_original,
                confianca=confianca,
            )
            existentes[chave] = nova
            a_criar.append(nova)
        elif cotacao.valor_unitario != valor_decimal:
            cotacao.valor_unitario = valor_decimal
            cotacao.texto_original = texto_original
            cotacao.confianca = confianca
            a_atualizar.append(cotacao)

def _resolver_fornecedor(referencia, fornecedores):
    """Resolve a chave da cotação: nome, CNPJ ou a forma legada empresaN.

    Todas as três formas foram indexadas com a mesma normalização em
    _gravar_fornecedores, então uma única consulta ao dicionário basta.
    """
    return fornecedores.get(_chave(referencia))

# ==================== AVISOS ====================
def _avisar_cotacoes_orfas(processo, fornecedores):
    """Registra fornecedores que sumiram do JSON mas ainda têm cotações.

    Nada é apagado: numa pesquisa de preços, apagar preço já coletado sem
    decisão humana destrói prova do processo administrativo.
    """
    ids_atuais = {f.id for f in fornecedores.values()}
    if not ids_atuais:
        return

    orfas = (Cotacao.objects
            .filter(item__processo=processo)
            .exclude(fornecedor_id__in=ids_atuais)
            .select_related('fornecedor'))

    contagem = {}
    for cotacao in orfas[:LIMITE_AVISOS_ORFAOS]:
        registro = contagem.setdefault(
            cotacao.fornecedor_id,
            {'fornecedor': cotacao.fornecedor, 'total': 0},
        )
        registro['total'] += 1

    for dados in contagem.values():
        fornecedor = dados['fornecedor']
        AvisoProcessamento.objects.get_or_create(
            processo=processo,
            fornecedor=fornecedor,
            tipo='fornecedor_removido',
            resolvido=False,
            defaults={
                'severidade': AvisoProcessamento.ATENCAO,
                'mensagem': (
                    f'{fornecedor.nome} não veio no último processamento. '
                    f'{dados["total"]} cotações foram preservadas e podem '
                    f'estar desatualizadas.'
                )[:500],
            },
        )

def _gravar_avisos_gerais(processo, dados_ai):
    """Leva os avisos do merge_results para o banco, e não só para o ODT."""
    for mensagem in dados_ai.get('avisos_gerais') or []:
        texto = str(mensagem)[:500]
        if not texto.strip():
            continue
        AvisoProcessamento.objects.get_or_create(
            processo=processo,
            tipo='geral',
            mensagem=texto,
            resolvido=False,
            defaults={'severidade': AvisoProcessamento.ATENCAO},
        )

# ==================== CONTADORES ====================

def _atualizar_contadores(processo, emails_recebidos):
    """Recalcula os números exibidos na tela de Documentos.

    qtd_cotacoes conta CÉLULAS preenchidas do mapa.
    qtd_fornecedores_com_preco conta fornecedores que cotaram ao menos um item.
    """

    celulas = Cotacao.objects.filter(
        item__processo=processo, valor_unitario__isnull=False
    )

    processo.qtd_fornecedores = processo.fornecedores.count()
    processo.qtd_itens = processo.itens.count()
    processo.qtd_cotacoes = celulas.count()
    processo.qtd_fornecedores_com_preco = celulas.values('fornecedor').distinct().count()
    processo.emails_recebidos = emails_recebidos
    processo.save(update_fields=[
        'qtd_fornecedores', 'qtd_itens', 'qtd_cotacoes',
        'qtd_fornecedores_com_preco', 'emails_recebidos',
    ])

# ==================== SUBSTITUIÇÃO DESTRUTIVA ====================

def substituir_dados_ai(processo, dados_ai, emails_recebidos=0):
    """Apaga os dados existenes e regrava do zero.
    
    Só deve ser chamada depois de confirmação explícita do usuário na tela:
    o histórico de cotações é peça do processo administrativo.
    """
    logger.warning(
        'Substituição completa do processo %s: %s fornecedores e %s itens serão apagados',
        processo.numero, processo.fornecedores.count(), processo.itens.count(),
    )
    return salvar_dados_ai(
        processo=processo,
        dados_ai=dados_ai,
        emails_recebidos=emails_recebidos,
        modo=MODO_COMPLETO,
        substituir=True,
    )
