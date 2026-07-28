import pandas as pd
import os
from django.shortcuts import render
from django.http import JsonResponse, FileResponse, Http404
from django.views.decorators.csrf import csrf_exempt
from .models import Mapa
import numpy as np

def mapa(request):
    ultimo_mapa = Mapa.objects.order_by("-data_upload").first()
    
    return render(request, "mapa.html", {"mapa": ultimo_mapa})

@csrf_exempt
def processar_upload(request):
    """Endpoint para processar upload de arquivos via AJAX"""
    if request.method == 'POST' and request.FILES.get('arquivo'):
        arquivo = request.FILES['arquivo']
        nome_arquivo = arquivo.name

        # Remove o mapa antigo (caso exista)
        mapa_antigo = Mapa.objects.first()

        if mapa_antigo:
            # Apaga o arquivo físico
            if mapa_antigo.arquivo and os.path.exists(mapa_antigo.arquivo.path):
                os.remove(mapa_antigo.arquivo.path)

            # Remove o registro do banco
            mapa_antigo.delete()

        try:
            mapa = Mapa.objects.create(nome=arquivo.name, arquivo=arquivo)
            arquivo_path = mapa.arquivo.path
            extensao = os.path.splitext(nome_arquivo)[1].lower()

            if extensao == '.csv':
                df = pd.read_csv(arquivo_path, encoding='utf-8', on_bad_lines='skip')
            elif extensao in ['.xlsx', '.xls', '.ods']:
                # Ler todas as linhas sem especificar cabeçalho para processar manualmente
                df_temp = pd.read_excel(arquivo_path, header=None)
                
                # Encontrar a linha que contém "ITEM" (geralmente na linha 3, índice 2)
                header_row = None
                for idx, row in df_temp.iterrows():
                    if row.astype(str).str.contains('ITEM').any():
                        header_row = idx
                        break
                
                if header_row is not None:
                    # Usar essa linha como cabeçalho
                    df = pd.read_excel(arquivo_path, header=header_row)
                else:
                    # Fallback: usar a linha 3 (índice 2) como padrão
                    df = pd.read_excel(arquivo_path, header=2)
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
                            # Verificar se é um número inteiro ou decimalimport pandas as pd
import os
from django.shortcuts import render
from django.http import JsonResponse, FileResponse, Http404
from django.views.decorators.csrf import csrf_exempt
from .models import Mapa
import numpy as np

def mapa(request):
    ultimo_mapa = Mapa.objects.order_by("-data_upload").first()
    
    return render(request, "mapa.html", {"mapa": ultimo_mapa})

@csrf_exempt
def processar_upload(request):
    """Endpoint para processar upload de arquivos via AJAX"""
    if request.method == 'POST' and request.FILES.get('arquivo'):
        arquivo = request.FILES['arquivo']
        nome_arquivo = arquivo.name

        # Remove o mapa antigo (caso exista)
        mapa_antigo = Mapa.objects.first()

        if mapa_antigo:
            # Apaga o arquivo físico
            if mapa_antigo.arquivo and os.path.exists(mapa_antigo.arquivo.path):
                os.remove(mapa_antigo.arquivo.path)

            # Remove o registro do banco
            mapa_antigo.delete()

        try:
            mapa = Mapa.objects.create(nome=arquivo.name, arquivo=arquivo)
            arquivo_path = mapa.arquivo.path
            extensao = os.path.splitext(nome_arquivo)[1].lower()

            if extensao == '.csv':
                df = pd.read_csv(arquivo_path, encoding='utf-8', on_bad_lines='skip')
            elif extensao in ['.xlsx', '.xls', '.ods']:
                # Ler todas as linhas sem especificar cabeçalho para processar manualmente
                df_temp = pd.read_excel(arquivo_path, header=None)
                
                # Encontrar a linha que contém "ITEM" (geralmente na linha 3, índice 2)
                header_row = None
                for idx, row in df_temp.iterrows():
                    if row.astype(str).str.contains('ITEM').any():
                        header_row = idx
                        break
                
                if header_row is not None:
                    # Usar essa linha como cabeçalho
                    df = pd.read_excel(arquivo_path, header=header_row)
                else:
                    # Fallback: usar a linha 3 (índice 2) como padrão
                    df = pd.read_excel(arquivo_path, header=2)
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

            return JsonResponse({
                'success': True,
                'dados': dados
            })

        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            })

    return JsonResponse({'success': False, 'error': 'Método não permitido'})

def baixar_mapa(request):
    mapa = Mapa.objects.order_by("-data_upload").first()

    if not mapa or not mapa.arquivo:
        raise Http404("Nenhum mapa disponível.")

    return FileResponse(
        mapa.arquivo.open('rb'),
        as_attachment=True,
        filename=mapa.arquivo.name.split("/")[-1]
    )

def carregar_ultimo_mapa(request):
    mapa = Mapa.objects.first()

    if not mapa:
        return JsonResponse({"success": False, "error": "Nenhum mapa enviado."})

    arquivo_path = mapa.arquivo.path
    nome_arquivo = mapa.nome

    try:
        extensao = os.path.splitext(nome_arquivo)[1].lower()

        if extensao == ".csv":
            df = pd.read_csv(arquivo_path, encoding="utf-8", on_bad_lines="skip")

        elif extensao in [".xlsx", ".xls", ".ods"]:
            df_temp = pd.read_excel(arquivo_path,nheader=None)

            header_row = None

            for idx, row in df_temp.iterrows():
                if row.astype(str).str.contains("ITEM").any():
                    header_row = idx
                    break

            if header_row is not None:
                df = pd.read_excel(arquivo_path, header=header_row)
            else:
                df = pd.read_excel(arquivo_path, header=2)

        else:
            return JsonResponse({"success": False, "error": "Formato inválido."})

        df = df.dropna(axis=1, how="all")
        df = df.dropna(how="all")

        df.columns = df.columns.str.strip()
        df = df.loc[:, df.columns.notna()]
        df = df.replace({
            np.nan: None,
            np.inf: None,
            -np.inf: None
        })

        for col in df.columns:

            if pd.api.types.is_datetime64_any_dtype(df[col]):
                df[col] = df[col].dt.strftime("%Y-%m-%d")

            elif pd.api.types.is_numeric_dtype(df[col]):
                df[col] = df[col].apply(
                    lambda x: float(x)
                    if pd.notnull(x)
                    else None
                )

        dados = {
            "colunas": [str(c) for c in df.columns],
            "linhas": [],
            "nome_arquivo": nome_arquivo,
            "total_linhas": len(df),
            "total_colunas": len(df.columns)
        }

        for _, row in df.iterrows():
            linha = []

            for val in row:
                if pd.isna(val):
                    linha.append(None)
                elif isinstance(val, float) and val.is_integer():
                    linha.append(int(val))
                elif isinstance(val, (int, float)):
                    linha.append(float(val))
                elif isinstance(val, pd.Timestamp):
                    linha.append(
                        val.strftime("%Y-%m-%d %H:%M:%S")
                    )
                else:
                    linha.append(str(val) if val else None)

            dados["linhas"].append(linha)

        return JsonResponse({
            "success": True,
            "dados": dados
        })

    except Exception as e:

        return JsonResponse({
            "success": False,
            "error": str(e)
        })
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

            return JsonResponse({
                'success': True,
                'dados': dados
            })

        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            })

    return JsonResponse({'success': False, 'error': 'Método não permitido'})

def baixar_mapa(request):
    mapa = Mapa.objects.order_by("-data_upload").first()

    if not mapa or not mapa.arquivo:
        raise Http404("Nenhum mapa disponível.")

    return FileResponse(
        mapa.arquivo.open('rb'),
        as_attachment=True,
        filename=mapa.arquivo.name.split("/")[-1]
    )

def carregar_ultimo_mapa(request):
    mapa = Mapa.objects.first()

    if not mapa:
        return JsonResponse({"success": False, "error": "Nenhum mapa enviado."})

    arquivo_path = mapa.arquivo.path
    nome_arquivo = mapa.nome

    try:
        extensao = os.path.splitext(nome_arquivo)[1].lower()

        if extensao == ".csv":
            df = pd.read_csv(arquivo_path, encoding="utf-8", on_bad_lines="skip")

        elif extensao in [".xlsx", ".xls", ".ods"]:
            df_temp = pd.read_excel(arquivo_path,nheader=None)

            header_row = None

            for idx, row in df_temp.iterrows():
                if row.astype(str).str.contains("ITEM").any():
                    header_row = idx
                    break

            if header_row is not None:
                df = pd.read_excel(arquivo_path, header=header_row)
            else:
                df = pd.read_excel(arquivo_path, header=2)

        else:
            return JsonResponse({"success": False, "error": "Formato inválido."})

        df = df.dropna(axis=1, how="all")
        df = df.dropna(how="all")

        df.columns = df.columns.str.strip()
        df = df.loc[:, df.columns.notna()]
        df = df.replace({
            np.nan: None,
            np.inf: None,
            -np.inf: None
        })

        for col in df.columns:

            if pd.api.types.is_datetime64_any_dtype(df[col]):
                df[col] = df[col].dt.strftime("%Y-%m-%d")

            elif pd.api.types.is_numeric_dtype(df[col]):
                df[col] = df[col].apply(
                    lambda x: float(x)
                    if pd.notnull(x)
                    else None
                )

        dados = {
            "colunas": [str(c) for c in df.columns],
            "linhas": [],
            "nome_arquivo": nome_arquivo,
            "total_linhas": len(df),
            "total_colunas": len(df.columns)
        }

        for _, row in df.iterrows():
            linha = []

            for val in row:
                if pd.isna(val):
                    linha.append(None)
                elif isinstance(val, float) and val.is_integer():
                    linha.append(int(val))
                elif isinstance(val, (int, float)):
                    linha.append(float(val))
                elif isinstance(val, pd.Timestamp):
                    linha.append(
                        val.strftime("%Y-%m-%d %H:%M:%S")
                    )
                else:
                    linha.append(str(val) if val else None)

            dados["linhas"].append(linha)

        return JsonResponse({
            "success": True,
            "dados": dados
        })

    except Exception as e:

        return JsonResponse({
            "success": False,
            "error": str(e)
        })
