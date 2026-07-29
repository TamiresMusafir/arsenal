"""
ARQUIVO NOVO - crie como <app>/services.py

Monta o resumo de cada processo para a tela de Documentos.
Lê primeiro do banco (tabelas Fornecedor/Item/Cotacao) e, se o processo
for antigo e ainda não tiver dados lá, cai para o JSON em
MEDIA_ROOT/processos/gerados/dados_ai_<numero>.json
"""

import json
import os
import re

from django.conf import settings


# ==================== LEITURA DO JSON ====================

def caminho_json(processo):
    return os.path.join(
        settings.MEDIA_ROOT, 'processos', 'gerados',
        f'dados_ai_{processo.numero_slug}.json'
    )


def carregar_dados_ai(processo):
    """Lê o JSON do processo. Devolve {} se não existir ou estiver inválido."""
    caminho = caminho_json(processo)
    if not os.path.exists(caminho):
        return {}
    try:
        with open(caminho, encoding='utf-8') as arquivo:
            dados = json.load(arquivo)
        return dados if isinstance(dados, dict) else {}
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return {}


def para_float(valor):
    """Converte 'R$ 1.234,56', '1234.56' ou 1234.56 em float. Devolve None se não der."""
    if valor is None or isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float)):
        return float(valor)

    texto = re.sub(r'[^\d,.\-]', '', str(valor).strip())
    if not texto:
        return None

    if ',' in texto and '.' in texto:
        # o separador decimal é o que aparece por último
        if texto.rfind(',') > texto.rfind('.'):
            texto = texto.replace('.', '').replace(',', '.')
        else:
            texto = texto.replace(',', '')
    elif ',' in texto:
        texto = texto.replace(',', '.')

    try:
        return float(texto)
    except ValueError:
        return None


# ==================== RESUMO A PARTIR DO BANCO ====================

def montar_resumo_do_banco(processo, limite_itens=10):
    empresas = [{
        'indice': f.indice,
        'chave': f'empresa{f.indice}',
        'nome': f.nome,
        'cnpj': f.cnpj,
        'email': f.email,
        'valor_global': f.valor_global or '',
    } for f in processo.fornecedores.all()]

    itens = []
    itens_cotados = 0
    fornecedores_com_preco = set()

    for registro in processo.itens.prefetch_related('cotacoes__fornecedor'):
        por_indice = {c.fornecedor.indice: c for c in registro.cotacoes.all()}
        cotacoes = []
        for empresa in empresas:
            cotacao = por_indice.get(empresa['indice'])
            valor = float(cotacao.valor_unitario) if cotacao and cotacao.valor_unitario is not None else None
            if valor is not None:
                fornecedores_com_preco.add(empresa['indice'])
            cotacoes.append({
                'empresa': empresa['nome'],
                'texto': (cotacao.texto_original if cotacao else '') or '—',
                'valor': valor,
                'melhor': False,
            })

        validas = [c for c in cotacoes if c['valor'] is not None]
        menor = min(validas, key=lambda c: c['valor']) if validas else None
        if menor:
            menor['melhor'] = True
            itens_cotados += 1

        itens.append({
            'posicao': registro.posicao,
            'pi': registro.pi,
            'descricao': registro.descricao,
            'qtde': registro.qtde or '',
            'uf': registro.uf,
            'valor_unitario_estimado': registro.valor_unitario_estimado or '',
            'valor_total': registro.valor_total or '',
            'cotacoes': cotacoes,
            'qtd_cotacoes': len(validas),
            'menor_preco': menor['valor'] if menor else None,
            'menor_fornecedor': menor['empresa'] if menor else '',
        })

    total_itens = len(itens)
    return {
        'processo': processo,
        'empresas': empresas,
        'itens': itens[:limite_itens],
        'itens_ocultos': max(total_itens - limite_itens, 0),
        'total_itens': total_itens,
        'itens_cotados': itens_cotados,
        'cobertura': round(itens_cotados / total_itens * 100) if total_itens else 0,
        'total_fornecedores': len(empresas),
        'total_cotacoes': len(fornecedores_com_preco),
        'emails_enviados': processo.emails_enviados,
        'emails_recebidos': processo.emails_recebidos,
        'tem_json': os.path.exists(caminho_json(processo)),
        'tem_xlsx': bool(processo.arquivo_gerado_xlsx),
        'tem_odt': bool(processo.arquivo_gerado_odt),
        'tem_pacote': bool(processo.arquivo_processo),
    }


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
            'valor_global': bruto.get('valor_global') or '',
        })
    return empresas


def montar_resumo_do_json(processo, limite_itens=10):
    dados = carregar_dados_ai(processo)
    empresas = _empresas_do_json(dados)

    itens = []
    itens_cotados = 0
    chaves_com_preco = set()

    for posicao, bruto in enumerate(dados.get('itens') or [], start=1):
        if not isinstance(bruto, dict):
            continue

        precos = bruto.get('empresas') or {}
        cotacoes = []
        for empresa in empresas:
            original = precos.get(empresa['chave'])
            valor = para_float(original)
            if valor is not None:
                chaves_com_preco.add(empresa['chave'])
            cotacoes.append({
                'empresa': empresa['nome'],
                'texto': original if original not in (None, '') else '—',
                'valor': valor,
                'melhor': False,
            })

        validas = [c for c in cotacoes if c['valor'] is not None]
        menor = min(validas, key=lambda c: c['valor']) if validas else None
        if menor:
            menor['melhor'] = True
            itens_cotados += 1

        itens.append({
            'posicao': bruto.get('item') or posicao,
            'pi': bruto.get('pi') or '',
            'descricao': bruto.get('nome_em_portugues') or bruto.get('descricao') or '',
            'qtde': bruto.get('qtde') or '',
            'uf': bruto.get('uf') or '',
            'valor_unitario_estimado': bruto.get('valor_unitario_estimado') or '',
            'valor_total': bruto.get('valor_total') or '',
            'cotacoes': cotacoes,
            'qtd_cotacoes': len(validas),
            'menor_preco': menor['valor'] if menor else None,
            'menor_fornecedor': menor['empresa'] if menor else '',
        })

    total_itens = len(itens) or processo.qtd_itens
    emails = dados.get('emails') or {}

    return {
        'processo': processo,
        'empresas': empresas,
        'itens': itens[:limite_itens],
        'itens_ocultos': max(len(itens) - limite_itens, 0),
        'total_itens': total_itens,
        'itens_cotados': itens_cotados,
        'cobertura': round(itens_cotados / total_itens * 100) if total_itens else 0,
        'total_fornecedores': len(empresas) or processo.qtd_fornecedores,
        'total_cotacoes': len(chaves_com_preco) or processo.qtd_cotacoes,
        'emails_enviados': emails.get('enviados', processo.emails_enviados),
        'emails_recebidos': emails.get('recebidos', processo.emails_recebidos),
        'tem_json': bool(dados),
        'tem_xlsx': bool(processo.arquivo_gerado_xlsx),
        'tem_odt': bool(processo.arquivo_gerado_odt),
        'tem_pacote': bool(processo.arquivo_processo),
    }


def montar_resumo(processo, limite_itens=10):
    """Entrada usada pela view documentos()."""
    if processo.fornecedores.exists() or processo.itens.exists():
        return montar_resumo_do_banco(processo, limite_itens)
    return montar_resumo_do_json(processo, limite_itens)