import pandas as pd
import json
import os
from django.conf import settings
from django.shortcuts import render
from django.http import JsonResponse, FileResponse
from django.views.decorators.csrf import csrf_exempt
import numpy as np

def mapa(request):
    return render(request, "mapa.html")

@csrf_exempt
def processar_upload(request):
    """Endpoint para processar upload de arquivos via AJAX"""
    if request.method == 'POST' and request.FILES.get('arquivo'):
        arquivo = request.FILES['arquivo']
        nome_arquivo = arquivo.name

        try:
            # Salvar arquivo temporariamente
            temp_path = os.path.join(settings.MEDIA_ROOT, 'temp', nome_arquivo)
            os.makedirs(os.path.dirname(temp_path), exist_ok=True)

            with open(temp_path, 'wb+') as destination:
                for chunk in arquivo.chunks():
                    destination.write(chunk)

            extensao = os.path.splitext(nome_arquivo)[1].lower()

            if extensao == '.csv':
                df = pd.read_csv(temp_path, encoding='utf-8', on_bad_lines='skip')
            elif extensao in ['.xlsx', '.xls', '.ods']:
                # Ler todas as linhas sem especificar cabeçalho para processar manualmente
                df_temp = pd.read_excel(temp_path, header=None)
                
                # Encontrar a linha que contém "ITEM" (geralmente na linha 3, índice 2)
                header_row = None
                for idx, row in df_temp.iterrows():
                    if row.astype(str).str.contains('ITEM').any():
                        header_row = idx
                        break
                
                if header_row is not None:
                    # Usar essa linha como cabeçalho
                    df = pd.read_excel(temp_path, header=header_row)
                else:
                    # Fallback: usar a linha 3 (índice 2) como padrão
                    df = pd.read_excel(temp_path, header=2)
            else:
                return JsonResponse({
                    'success': False,
                    'error': 'Formato de arquivo não suportado'
                })

            # Remover colunas totalmente vazias
            df = df.dropna(axis=1, how='all')
            
            # Remover linhas totalmente vazias
            df = df.dropna(how='all')

            # Limpar nomes das colunas (remover espaços extras, caracteres especiais)
            df.columns = df.columns.str.strip()
            
            # Remover colunas sem nome (NaN)
            df = df.loc[:, df.columns.notna()]
            
            # Substituir NaN, None e outros valores não serializáveis
            df = df.replace({np.nan: None, np.inf: None, -np.inf: None})
            
            # Converter colunas de data para string, se existirem
            for col in df.columns:
                if pd.api.types.is_datetime64_any_dtype(df[col]):
                    df[col] = df[col].dt.strftime('%Y-%m-%d')
                elif pd.api.types.is_numeric_dtype(df[col]):
                    # Formatar números para evitar problemas de precisão no JSON
                    df[col] = df[col].apply(lambda x: float(x) if pd.notnull(x) else None)

            # Converter DataFrame para dicionário com tratamento adequado
            dados = {
                'colunas': [str(col) for col in df.columns.tolist() if str(col) != 'nan'],
                'linhas': [],
                'nome_arquivo': nome_arquivo,
                'total_linhas': len(df),
                'total_colunas': len(df.columns)
            }

            # Processar cada linha garantindo que todos os valores sejam serializáveis
            for _, row in df.iterrows():
                linha = []
                for val in row:
                    if pd.isna(val):
                        linha.append(None)
                    elif isinstance(val, (int, float)):
                        # Tratar valores numéricos
                        if pd.isna(val) or np.isinf(val):
                            linha.append(None)
                        else:
                            # Verificar se é um número inteiro ou decimal
                            if isinstance(val, float) and val.is_integer():
                                linha.append(int(val))
                            else:
                                linha.append(float(val))
                    elif isinstance(val, pd.Timestamp):
                        linha.append(val.strftime('%Y-%m-%d %H:%M:%S'))
                    elif isinstance(val, (pd.Timedelta, pd.Period)):
                        linha.append(str(val))
                    else:
                        linha.append(str(val) if val is not None else None)
                dados['linhas'].append(linha)

            # Remover arquivo temporário
            if os.path.exists(temp_path):
                os.remove(temp_path)

            return JsonResponse({
                'success': True,
                'dados': dados
            })

        except Exception as e:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            
            return JsonResponse({
                'success': False,
                'error': str(e)
            })

    return JsonResponse({'success': False, 'error': 'Método não permitido'})

def baixar_modelo_base(request):
    """Faz o download do modelo base oficial"""
    caminho_modelo = os.path.join(
        settings.BASE_DIR,
        'static-assets',
        'modelos',
        'Mapa_Comparativo_Base.xlsx'
    )

    if not os.path.exists(caminho_modelo):
        return JsonResponse({
            'success': False,
            'error': 'Modelo base não encontrado.'
        })

    return FileResponse(
        open(caminho_modelo, 'rb'),
        as_attachment=True,
        filename='Mapa_Comparativo_Base.xlsx'
    )
