"""
processos/services.py

Camada de leitura e normalização. Não escreve nada no banco.

Responsabilidades:
    1. Converter texto monetário heterogêneo em número (para_float / para_decimal).
    2. Normalizar nomes de empresa para casamento de chaves (chave_empresa).
    3. Montar o resumo de cada processo para a tela de Documentos,
       lendo do banco (Fornecedor/Item/Cotacao) e caindo para o JSON
       em MEDIA_ROOT/processos/gerados/dados_ai_<numero>.json nos
       processos antigos.
    4. Reconstruir a linha de base (itens/PI do Modelo de Proposta)
       para alimentar o prompt da IA e o merge_results.
"""


import json
import logging
import os
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.conf import settings

logger = logging.getLogger(__name__)

# Confiança abaixo deste valor exige conferência manual contra o original.
LIMITE_CONFIANCA = 80

# Primeiro grupo numérico de um texto: "1 234.567,89", "1.500", "-15", "3,14".
_PADRAO_NUMERO = re.compile(r'-?\d[\d.,\s\u00a0]*\d|-?\d')

# "1.500" e "1,500" são ambíguos: podem ser milhar (1500) ou decimal (1,5).
_PADRAO_AMBIGUO = re.compile(r'^-?\d{1,3}[.,]\d{3}$')

_SIMBOLOS_MOEDA = re.compile(r'([A-Z]{2,3}\$)|[R$€£¥]', re.IGNORECASE)


# ==================== NORMALIZAÇÃO ====================

def chave_empresa(texto):
    """Normaliza nome ou CNPJ de empresa para casar chaves de cotação."""
    return re.sub(r'[^a-z0-9]', '', str(texto or '').lower())


# ==================== PARSE DE VALORES MONETÁRIOS ====================

def para_float(valor, item=None, fornecedor=None, criar_aviso=None):
    """Converte valor monetário heterogêneo em float.

    Args:
        valor: str, int, float, Decimal ou None.
        item: Item opcional, usado apenas para contextualizar o aviso.
        fornecedor: Fornecedor opcional, mesma finalidade.
        criar_aviso: callable(processo, item, fornecedor, tipo, severidade,
            mensagem, valor_bruto) chamado quando o valor é ilegível ou ambíguo.

    Returns:
        float ou None quando não há número reconhecível.

    Exemplos:
        "R$ 1.500"          -> 1500.0
        "R$ 1.234,56"       -> 1234.56
        "1,234.56"          -> 1234.56
        "R$ 1.234,56 - 15%" -> 1234.56
        "1 500,00"          -> 1500.0
        "sob consulta"      -> None
    """
    if valor is None or isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    if isinstance(valor, Decimal):
        return float(valor)

    original = str(valor).strip()
    if not original:
        return None

    texto = _limpar_texto_monetario(original)
    encontrado = _PADRAO_NUMERO.search(texto)
    if not encontrado:
        return _registrar_aviso(original, item, fornecedor, criar_aviso,
                                'nenhum número encontrado')

    token = re.sub(r'[\s\u00a0]', '', encontrado.group(0))
    _validar_ambiguidade(token, original, item, fornecedor, criar_aviso)

    numero = _parse_numero_br(token)
    if numero is None:
        return _registrar_aviso(original, item, fornecedor, criar_aviso,
                                'não foi possível interpretar o número')
    return numero


def para_decimal(valor, item=None, fornecedor=None, criar_aviso=None, casas=2):
    """Mesma conversão de para_float, devolvendo Decimal arredondado.

    Dinheiro nunca deve trafegar como float até o banco: o arredondamento
    do float é o de banqueiro, e a Receita/TCU esperam ROUND_HALF_UP.
    """
    numero = para_float(valor, item, fornecedor, criar_aviso)
    if numero is None:
        return None
    try:
        quantum = Decimal(1).scaleb(-casas)
        return Decimal(repr(numero)).quantize(quantum, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        logger.warning('Valor fora da faixa suportada por Decimal: %r', valor)
        return None


def _limpar_texto_monetario(texto):
    """Remove símbolos monetários e separadores invisíveis."""
    texto = texto.replace('\u00a0', ' ')
    texto = _SIMBOLOS_MOEDA.sub('', texto)
    return texto.strip()


def _parse_numero_br(texto):
    """Interpreta um token numérico em formato brasileiro ou americano.

    Regras, nesta ordem:
        1. Vírgula e ponto presentes: o separador mais à direita é o decimal.
        2. Só vírgula: decimal, exceto no padrão de milhar "1,500".
        3. Só ponto: decimal, exceto no padrão de milhar "1.500" / "1.234.567".
        4. Sem separador: inteiro.
    """
    if not texto:
        return None

    tem_virgula = ',' in texto
    tem_ponto = '.' in texto

    if tem_virgula and tem_ponto:
        if texto.rfind(',') > texto.rfind('.'):
            texto = texto.replace('.', '').replace(',', '.')   # BR: 1.234,56
        else:
            texto = texto.replace(',', '')                     # US: 1,234.56

    elif tem_virgula:
        partes = texto.split(',')
        if _e_grupo_de_milhar(partes):
            texto = texto.replace(',', '')
        else:
            texto = texto.replace(',', '.')

    elif tem_ponto:
        partes = texto.split('.')
        if _e_grupo_de_milhar(partes):
            texto = texto.replace('.', '')

    try:
        return float(texto)
    except ValueError:
        return None


def _e_grupo_de_milhar(partes):
    """Decide se os grupos separados representam milhar e não decimal.

    "1.500"     -> ['1', '500']            -> milhar
    "1.234.567" -> ['1', '234', '567']     -> milhar
    "1.5"       -> ['1', '5']              -> decimal
    "10.50"     -> ['10', '50']            -> decimal
    """
    if len(partes) > 2:
        return all(len(p) == 3 for p in partes[1:])
    return len(partes) == 2 and len(partes[1]) == 3 and 1 <= len(partes[0].lstrip('-')) <= 3


def _validar_ambiguidade(token, original, item, fornecedor, criar_aviso):
    """Registra aviso quando o token admite duas leituras legítimas.

    "1.500" pode ser mil e quinhentos ou um vírgula cinco. O sistema adota
    milhar, que é o uso corrente em proposta comercial brasileira, mas a
    decisão fica registrada para conferência.
    """
    if not _PADRAO_AMBIGUO.match(token):
        return
    _registrar_aviso(
        original, item, fornecedor, criar_aviso,
        f"valor ambíguo: '{token}' foi lido como milhar; "
        f"confira se não era {token.replace(',', '.').replace('.', ',')} decimal",
        tipo='valor_ambiguo',
    )


def _registrar_aviso(original, item, fornecedor, criar_aviso, motivo,
                     tipo='preco_ilegivel'):
    """Encaminha o problema ao callback de avisos e devolve None.

    O retorno None permite usar esta função diretamente no `return` de
    para_float, sem duplicar o caminho de saída.
    """
    logger.warning("Valor não convertido: %r (%s)", original, motivo)

    if not criar_aviso:
        return None
    

    processo = None
    if item is not None:
        processo = item.processo
    elif fornecedor is not None:
        processo = fornecedor.processo
    if processo is None:
        return None

    try:
        criar_aviso(
            processo=processo,
            item=item,
            fornecedor=fornecedor,
            tipo=tipo,
            severidade='atencao',
            mensagem=f'Valor "{original[:120]}": {motivo}',
            valor_bruto=original[:200],
        )
    except Exception:                                   # noqa: BLE001
        # Um aviso que falha não pode derrubar a gravação do processo.
        logger.exception('Falha ao registrar aviso de processamento')
    return None


# ==================== LEITURA DO JSON ====================

def caminho_json(processo):
    return os.path.join(
        settings.MEDIA_ROOT, 'processos', 'gerados',
        f'dados_ai_{processo.numero_slug}.json',
    )


def carregar_dados_ai(processo):
    """Lê o JSON bruto do processo. Devolve {} se não existir ou for inválido."""
    caminho = caminho_json(processo)
    if not os.path.exists(caminho):
        return {}
    try:
        with open(caminho, encoding='utf-8') as arquivo:
            dados = json.load(arquivo)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        logger.exception('JSON ilegível para o processo %s', processo.numero)
        return {}
    return dados if isinstance(dados, dict) else {}


# ==================== RESUMO A PARTIR DO BANCO ====================

def _linha_de_item(posicao, pi, descricao, qtde, uf, estimado, total, cotacoes):
    """Monta uma linha do mapa já com o menor preço marcado."""
    validas = [c for c in cotacoes if c['valor'] is not None]
    menor = min(validas, key=lambda c: c['valor']) if validas else None
    if menor:
        menor['melhor'] = True

    return {
        'posicao': posicao,
        'pi': pi,
        'descricao': descricao,
        'qtde': qtde,
        'uf': uf,
        'valor_unitario_estimado': estimado,
        'valor_total': total,
        'cotacoes': cotacoes,
        'qtd_cotacoes': len(validas),
        'menor_preco': menor['valor'] if menor else None,
        'menor_fornecedor': menor['empresa'] if menor else '',
    }


def montar_resumo_do_banco(processo, limite_itens=10):
    """Resumo lido das tabelas normalizadas.

    Depende do prefetch feito na view (`fornecedores`, `itens__cotacoes__fornecedor`).
    Nenhuma consulta nova é disparada dentro do laço.
    """
    empresas = [{
        'indice': fornecedor.indice,
        'chave': f'empresa{fornecedor.indice}',
        'nome': fornecedor.nome,
        'cnpj': fornecedor.cnpj,
        'email': fornecedor.email,
        'tipo_resposta': fornecedor.tipo_resposta,
        'motivo': fornecedor.motivo_declinio,
        'valor_global': fornecedor.valor_global or '',
    } for fornecedor in processo.fornecedores.all()]

    itens = []
    itens_cotados = 0
    celulas_cotadas = 0
    fornecedores_com_preco = set()

    for registro in processo.itens.all():
        por_indice = {c.fornecedor.indice: c for c in registro.cotacoes.all()}

        cotacoes = []
        for empresa in empresas:
            cotacao = por_indice.get(empresa['indice'])
            valor = None
            if cotacao is not None and cotacao.valor_unitario is not None:
                valor = float(cotacao.valor_unitario)
                fornecedores_com_preco.add(empresa['indice'])
                celulas_cotadas += 1
            cotacoes.append({
                'empresa': empresa['nome'],
                'texto': (cotacao.texto_original if cotacao else '') or '—',
                'valor': valor,
                'melhor': False,
                'confianca': cotacao.confianca if cotacao else None,
                'confianca_baixa': bool(
                    cotacao and cotacao.confianca is not None
                    and cotacao.confianca < LIMITE_CONFIANCA
                ),
            })

        linha = _linha_de_item(
            registro.posicao, registro.pi, registro.descricao,
            registro.qtde or '', registro.uf,
            registro.valor_unitario_estimado or '', registro.valor_total or '',
            cotacoes,
        )
        linha['confianca'] = registro.confianca
        linha['confianca_baixa'] = (
            registro.confianca is not None and registro.confianca < LIMITE_CONFIANCA
        )
        if linha['qtd_cotacoes']:
            itens_cotados += 1
        itens.append(linha)

    return _fechar_resumo(
        processo, empresas, itens, itens_cotados,
        celulas_cotadas=celulas_cotadas,
        fornecedores_com_preco=len(fornecedores_com_preco),
        limite_itens=limite_itens,
        emails_enviados=processo.emails_enviados,
        emails_recebidos=processo.emails_recebidos,
        tem_json=os.path.exists(caminho_json(processo)),
    )


# ==================== RESUMO A PARTIR DO JSON (fallback) ====================

def _empresas_do_json(dados):
    empresas = []
    for indice, bruto in enumerate(dados.get('empresas') or [], start=1):
        if isinstance(bruto, str):
            bruto = {'nome': bruto}
        if not isinstance(bruto, dict):
            continue
        empresas.append({
            'indice': indice,
            'chave': f'empresa{indice}',
            'nome': bruto.get('nome') or f'Empresa {indice}',
            'cnpj': bruto.get('cnpj') or '',
            'email': bruto.get('email') or '',
            'tipo_resposta': bruto.get('tipo_resposta') or 'cotacao',
            'motivo': bruto.get('motivo_declinio') or '',
            'valor_global': bruto.get('valor_global') or '',
        })
    return empresas


def montar_resumo_do_json(processo, limite_itens=10):
    """Resumo dos processos anteriores à normalização em tabelas."""
    dados = carregar_dados_ai(processo)
    empresas = _empresas_do_json(dados)

    itens = []
    itens_cotados = 0
    celulas_cotadas = 0
    chaves_com_preco = set()

    for posicao, bruto in enumerate(dados.get('itens') or [], start=1):
        if not isinstance(bruto, dict):
            continue

        precos = bruto.get('empresas') or {}
        # A IA devolve o NOME da empresa como chave; o JSON antigo, empresaN.
        precos_por_nome = {chave_empresa(k): v for k, v in precos.items()}

        cotacoes = []
        for empresa in empresas:
            texto = precos.get(empresa['chave'])
            if texto in (None, ''):
                texto = precos_por_nome.get(chave_empresa(empresa['nome']))
            valor = para_float(texto)
            if valor is not None:
                chaves_com_preco.add(empresa['chave'])
                celulas_cotadas += 1
            cotacoes.append({
                'empresa': empresa['nome'],
                'texto': texto if texto not in (None, '') else '—',
                'valor': valor,
                'melhor': False,
                'confianca': bruto.get('confianca'),
                'confianca_baixa': False,
            })

        linha = _linha_de_item(
            bruto.get('item') or posicao,
            bruto.get('pi') or '',
            bruto.get('nome_em_portugues') or bruto.get('descricao') or '',
            bruto.get('qtde') or '',
            bruto.get('uf') or '',
            bruto.get('valor_unitario_estimado') or '',
            bruto.get('valor_total') or '',
            cotacoes,
        )
        linha['confianca'] = bruto.get('confianca')
        linha['confianca_baixa'] = (
            isinstance(bruto.get('confianca'), int)
            and bruto['confianca'] < LIMITE_CONFIANCA
        )
        if linha['qtd_cotacoes']:
            itens_cotados += 1
        itens.append(linha)

    emails = dados.get('emails') or {}

    return _fechar_resumo(
        processo, empresas, itens, itens_cotados,
        celulas_cotadas=celulas_cotadas,
        fornecedores_com_preco=len(chaves_com_preco),
        limite_itens=limite_itens,
        emails_enviados=emails.get('enviados', processo.emails_enviados),
        emails_recebidos=emails.get('recebidos', processo.emails_recebidos),
        tem_json=bool(dados),
        total_itens_fallback=processo.qtd_itens,
        total_fornecedores_fallback=processo.qtd_fornecedores,
    )


# ==================== MONTAGEM COMUM ====================

def _fechar_resumo(processo, empresas, itens, itens_cotados, *,
                   celulas_cotadas, fornecedores_com_preco, limite_itens,
                   emails_enviados, emails_recebidos, tem_json,
                   total_itens_fallback=0, total_fornecedores_fallback=0):
    """Consolida os contadores comuns às duas origens de dados."""
    total_itens = len(itens) or total_itens_fallback
    total_fornecedores = len(empresas) or total_fornecedores_fallback

    return {
        'processo': processo,
        'empresas': empresas,
        'itens': itens[:limite_itens],
        'itens_ocultos': max(len(itens) - limite_itens, 0),
        'total_itens': total_itens,
        'itens_cotados': itens_cotados,
        'itens_sem_cotacao': max(total_itens - itens_cotados, 0),
        'cobertura': round(itens_cotados / total_itens * 100) if total_itens else 0,
        'total_fornecedores': total_fornecedores,
        # Mantido com o nome antigo: o template documentos.html já usa esta chave
        # como "respostas recebidas", ou seja, fornecedores que cotaram.
        'total_cotacoes': fornecedores_com_preco,
        'total_celulas_cotadas': celulas_cotadas,
        'total_declinios': sum(1 for e in empresas if e['tipo_resposta'] == 'declinio'),
        'total_duvidas': sum(1 for e in empresas if e['tipo_resposta'] == 'duvida'),
        'emails_enviados': emails_enviados,
        'emails_recebidos': emails_recebidos,
        'avisos_pendentes': processo.avisos_pendentes.count(),
        'tem_json': tem_json,
        'tem_xlsx': bool(processo.arquivo_gerado_xlsx),
        'tem_odt': bool(processo.arquivo_gerado_odt),
        'tem_pacote': bool(processo.arquivo_processo),
    }


def montar_resumo(processo, limite_itens=10):
    """Entrada usada pela view documentos().

    Usa os objetos já trazidos pelo prefetch para decidir a origem, em vez de
    dois `.exists()`, que custavam duas consultas por processo listado.
    """
    if processo.fornecedores.all() or processo.itens.all():
        return montar_resumo_do_banco(processo, limite_itens)
    return montar_resumo_do_json(processo, limite_itens)


# ==================== LINHA DE BASE (MODELO DE PROPOSTA) ====================

def linha_base(processo):
    """Reconstrói a linha de base para alimentar o prompt e o merge_results."""
    return {
        'informacoes_gerais': {},
        'empresas': [],
        'itens': [{
            'item': item.posicao,
            'pi': item.pi,
            'nsn': '',
            'codigo': item.pi,
            'nome_em_portugues': item.descricao,
            'qtde': float(item.qtde) if item.qtde is not None else None,
            'uf': item.uf,
            'empresas': {},
            'valor_unitario_estimado': None,
            'valor_total': None,
            'confianca': 100,
            'avisos': [],
        } for item in processo.itens.all()],
        'avisos_gerais': [],
    }
