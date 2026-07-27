import os
import json
import re
import requests
from typing import Dict, List, Any
import magic
from PyPDF2 import PdfFileReader
from docx import Document
import pandas as pd
from odf.opendocument import load
from odf import text, teletype
from django.conf import settings

class AIProcessor:
    def __init__(self):
        self.api_key = settings.OPENROUTER_API_KEY
        self.base_url = settings.OPENROUTER_BASE_URL
        self.model = settings.OPENROUTER_MODEL
        self.timeout = settings.OPENROUTER_TIMEOUT
        
    def extract_text_from_file(self, file_path: str) -> Dict[str, Any]:
        """Extrai texto de diferentes tipos de arquivo"""
        try:
            mime = magic.from_file(file_path, mime=True)
            content = ""
            
            if 'pdf' in mime:
                with open(file_path, 'rb') as f:
                    reader = PdfReader(f)
                    for page in reader.pages:
                        content += page.extract_text() + "\n"
                        
            elif 'word' in mime or 'docx' in mime:
                doc = Document(file_path)
                for para in doc.paragraphs:
                    content += para.text + "\n"
                    
            elif 'excel' in mime or 'spreadsheet' in mime:
                df = pd.read_excel(file_path)
                content = df.to_string()
                
            elif 'opendocument' in mime:
                doc = load(file_path)
                for elem in doc.getElementsByType(text.P):
                    content += teletype.extractText(elem) + "\n"
                    
            elif 'text/plain' in mime:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
            else:
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                except:
                    content = f"Arquivo {os.path.basename(file_path)} não pôde ser lido"
            
            if len(content) > 50000:
                content = content[:50000] + "...\n[Conteúdo truncado]"
            
            return {
                'content': content,
                'mime_type': mime,
                'filename': os.path.basename(file_path),
                'size': os.path.getsize(file_path)
            }
            
        except Exception as e:
            return {
                'content': f"Erro ao extrair texto: {str(e)}",
                'mime_type': 'error',
                'filename': os.path.basename(file_path),
                'size': 0
            }

    def process_with_ai(self, content: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Processa o conteúdo usando a API do DeepSeek via OpenRouter"""
        
        system_prompt = """
        Você é um especialista em análise de documentos de licitação e compras públicas.
        Sua função é extrair informações estruturadas para preencher um mapa comparativo.
        
        Você deve identificar e estruturar:
        1. Itens: Descrição detalhada, quantidade, unidade, valor unitário estimado
        2. Empresas/Fornecedores: Nomes das empresas e seus valores
        3. Informações Gerais: Número do processo, modalidade, objeto, etc.
        
        Retorne em formato JSON estruturado.
        """
        
        user_prompt = f"""
        Analise o documento e extraia as informações para o Mapa Comparativo.
        
        Contexto:
        - Número: {context.get('numero', 'N/A')}
        - Descrição: {context.get('descricao', 'N/A')}
        - Valor Estimado: {context.get('valor_estimado', 'N/A')}
        
        Conteúdo:
        {content[:30000]}
        
        Extraia em JSON com esta estrutura:
        {{
            "informacoes_gerais": {{
                "numero_processo": "",
                "modalidade": "",
                "objeto": "",
                "data_abertura": "",
                "valor_estimado_total": ""
            }},
            "empresas": [
                {{"nome": "", "cnpj": "", "valor_global": ""}}
            ],
            "itens": [
                {{
                    "item": 1,
                    "pi": "",
                    "nome_em_portugues": "",
                    "qtde": "",
                    "uf": "",
                    "painel_preco": "",
                    "empresas": {{
                        "empresa1": "",
                        "empresa2": "",
                        "empresa3": "",
                        "empresa4": "",
                        "empresa5": "",
                        "empresa6": "",
                        "empresa7": "",
                        "empresa8": "",
                        "empresa9": "",
                        "empresa10": "",
                        "empresa11": "",
                        "empresa12": "",
                        "empresa13": "",
                        "empresa14": "",
                        "empresa15": "",
                        "empresa16": "",
                        "empresa17": "",
                        "empresa18": "",
                        "empresa19": "",
                        "empresa20": ""
                    }},
                    "valor_unitario_estimado": "",
                    "valor_total": ""
                }}
            ]
        }}
        """
        
        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "http://localhost:8000",
                    "X-Title": "Arsenal-Main"
                },
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "temperature": 0.2,
                    "max_tokens": 8000,
                    "response_format": {"type": "json_object"}
                },
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                result = response.json()
                ai_response = result['choices'][0]['message']['content']
                
                try:
                    parsed_data = json.loads(ai_response)
                    return {'status': 'success', 'data': parsed_data}
                except:
                    json_match = re.search(r'\{.*\}', ai_response, re.DOTALL)
                    if json_match:
                        try:
                            parsed_data = json.loads(json_match.group())
                            return {'status': 'success', 'data': parsed_data}
                        except:
                            pass
                    return {'status': 'partial', 'data': {'conteudo': ai_response}}
            else:
                return {'status': 'error', 'error': f"Erro: {response.status_code}"}
                
        except Exception as e:
            return {'status': 'error', 'error': str(e)}

    def process_directory(self, directory_path: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Processa todos os arquivos de um diretório"""
        results = []
        for root, dirs, files in os.walk(directory_path):
            for file in files:
                file_path = os.path.join(root, file)
                if os.path.getsize(file_path) > 10 * 1024 * 1024:
                    continue
                file_data = self.extract_text_from_file(file_path)
                if file_data['content']:
                    result = self.process_with_ai(file_data['content'], context)
                    results.append({
                        'filename': file_data['filename'],
                        'mime_type': file_data['mime_type'],
                        'ai_result': result
                    })
        return results

    def merge_results(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Mescla os resultados de múltiplos arquivos"""
        merged = {'informacoes_gerais': {}, 'empresas': [], 'itens': []}
        empresa_names = set()
        itens_map = {}
        
        for result in results:
            ai_data = result.get('ai_result', {}).get('data', {})
            if isinstance(ai_data, dict):
                for key, value in ai_data.get('informacoes_gerais', {}).items():
                    if value and not merged['informacoes_gerais'].get(key):
                        merged['informacoes_gerais'][key] = value
                
                for empresa in ai_data.get('empresas', []):
                    if empresa.get('nome') and empresa.get('nome') not in empresa_names:
                        empresa_names.add(empresa.get('nome'))
                        merged['empresas'].append(empresa)
                
                for item in ai_data.get('itens', []):
                    item_key = f"{item.get('nome_em_portugues', '')}_{item.get('item', '')}"
                    if item_key not in itens_map:
                        itens_map[item_key] = item
                        merged['itens'].append(item)
        
        merged['itens'] = sorted(merged['itens'], key=lambda x: int(x.get('item', 0)) if x.get('item') else 0)
        return merged