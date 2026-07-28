"""
processos/ai_processor.py

Substituto direto do seu arquivo atual. Mantém os mesmos nomes públicos
(AIProcessor, extract_text_from_file, process_with_ai, process_directory,
merge_results), então nada mais no projeto precisa mudar.

O que muda por dentro:
  * PDF e imagem vão INTEIROS para a API (plugin file-parser da OpenRouter).
    Não há mais pré-extração de texto para esses formatos — é justamente a
    pré-extração que perdia tabela e devolvia vazio em PDF escaneado.
  * XLSX/DOCX/ODT/EML continuam sendo lidos localmente: nenhuma API de IA
    lê esses formatos: o parsing é responsabilidade sua.
  * O motor de PDF é escolhido por documento: `pdf-text` (grátis) quando há
    camada de texto, `native`/`mistral-ocr` quando é escaneado.
"""
import base64
import email
import email.policy
import json
import mimetypes
import os
import random
import re
import time
from pathlib import Path

import requests
from django.conf import settings




# =====================================================================
# Compatibilidade de PDF entre três gerações da biblioteca
# ---------------------------------------------------------------------
# Ubuntu 22.04 (apt install python3-pypdf2) entrega PyPDF2 1.26.0, onde a
# classe é PdfFileReader e os métodos são getNumPages()/extractText().
# A classe PdfReader NÃO existe nessa versão — era exatamente esse o erro
# do código anterior: o import trazia PdfFileReader e o corpo usava PdfReader.
#
# Ordem de preferência: pypdf (moderno) > PyPDF2 2.x/3.x > PyPDF2 1.26.
# =====================================================================
def abrir_pdf(file_path):
    """Devolve (lista_de_textos_por_pagina, total_de_paginas)."""
    leitor = None
    api_legada = False

    try:                                   # pypdf 3.x / 5.x (pip)
        from pypdf import PdfReader
        leitor = PdfReader(file_path)
    except ImportError:
        try:                               # PyPDF2 2.x / 3.x (apt noble 24.04)
            from PyPDF2 import PdfReader
            leitor = PdfReader(file_path)
        except ImportError:                # PyPDF2 1.26 (apt jammy 22.04)
            from PyPDF2 import PdfFileReader
            leitor = PdfFileReader(file_path, strict=False)
            api_legada = True

    if api_legada:
        total = leitor.getNumPages()
        paginas = []
        for i in range(total):
            try:
                paginas.append(leitor.getPage(i).extractText() or "")
            except Exception:
                paginas.append("")
        return paginas, total

    paginas = []
    for p in leitor.pages:
        try:
            paginas.append(p.extract_text() or "")
        except Exception:
            paginas.append("")
    return paginas, len(paginas)


EXTENSOES_IMAGEM = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"}


# =====================================================================
# Extração do JSON da resposta
# =====================================================================
def extrair_json(texto):
    """
    Varredura com contagem de chaves, ignorando o que está dentro de aspas.
    O `re.search(r'\\{.*\\}')` da versão anterior quebrava quando havia
    chave dentro de uma string JSON (acontece em descrição de item).
    """
    if not texto:
        raise ValueError("resposta vazia")

    t = texto.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[-1]
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    t = t.strip()

    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass

    inicio = t.find("{")
    if inicio == -1:
        raise ValueError("nenhum objeto JSON na resposta")

    profundidade = em_string = escape = 0
    em_string = False
    escape = False
    for i in range(inicio, len(t)):
        c = t[i]
        if escape:
            escape = False
            continue
        if c == "\\":
            escape = True
            continue
        if c == '"':
            em_string = not em_string
            continue
        if em_string:
            continue
        if c == "{":
            profundidade += 1
        elif c == "}":
            profundidade -= 1
            if profundidade == 0:
                return json.loads(t[inicio:i + 1])

    # resposta truncada por max_tokens: fecha as chaves que ficaram abertas
    return json.loads(t[inicio:].rstrip().rstrip(",") + "}" * profundidade)


# =====================================================================
class AIProcessor:

    SYSTEM_PROMPT = (
        "Você é um especialista em análise de documentos de licitação e compras "
        "públicas da Marinha do Brasil. Extraia informações estruturadas para "
        "preencher um Mapa Comparativo de Preços (Lei nº 14.133/2021, "
        "IN SEGES/ME nº 65/2021).\n"
        "REGRAS:\n"
        "1. NUNCA invente dados. Campo ausente no documento = string vazia.\n"
        "2. NUNCA calcule preço que não esteja escrito. Se só houver o total e "
        "a quantidade, preencha valor_total e deixe valor_unitario vazio.\n"
        "3. Números em formato brasileiro (1.234,56) viram float (1234.56).\n"
        "4. Preserve o código do item exatamente como está (PI, NSN, part number).\n"
        "5. Se a imagem/página estiver ilegível, registre em avisos.\n"
        "6. Responda APENAS com o objeto JSON, sem markdown e sem preâmbulo."
    )

    ESQUEMA = """{
  "informacoes_gerais": {"numero_processo":"","modalidade":"","objeto":"",
                         "data_documento":"","valor_estimado_total":null},
  "empresas": [{"nome":"","cnpj":"","email":"","telefone":"",
                "validade_proposta":"","prazo_entrega":"","valor_global":null}],
  "itens": [{
     "item": 1, "pi": "", "nsn": "", "codigo": "",
     "nome_em_portugues": "", "qtde": null, "uf": "",
     "empresas": {"NOME EXATO DA EMPRESA": 1234.56},
     "valor_unitario_estimado": null, "valor_total": null,
     "confianca": 90, "avisos": []
  }],
  "avisos_gerais": []
}"""

    def __init__(self):
        self.api_key = settings.OPENROUTER_API_KEY
        self.base_url = settings.OPENROUTER_BASE_URL
        self.model = settings.OPENROUTER_MODEL
        # (conexao, leitura): falha rapido se a rede bloqueia, mas espera
        # o tempo necessario quando o PDF grande esta sendo processado.
        self.timeout = (
            getattr(settings, "OPENROUTER_CONNECT_TIMEOUT", 15),
            getattr(settings, "OPENROUTER_TIMEOUT", 300),
        )
        # Rede corporativa/militar: proxy explicito e CA propria.
        # None faz o requests cair nas variaveis HTTP_PROXY/HTTPS_PROXY.
        self.proxies = getattr(settings, "OPENROUTER_PROXIES", None)
        self.verify = getattr(settings, "OPENROUTER_CA_BUNDLE", True)
        self.pdf_engine_scan = getattr(settings, "OPENROUTER_PDF_ENGINE_SCAN", "native")

    # -----------------------------------------------------------------
    # Roteamento da entrada
    # -----------------------------------------------------------------
    def montar_conteudo(self, file_path):
        """
        Decide como o arquivo entra na requisição.
        Devolve (blocos_de_conteudo, plugins, rota).
        """
        ext = Path(file_path).suffix.lower()

        # --- PDF: vai inteiro, o file-parser cuida ---------------------
        if ext == ".pdf":
            engine = "pdf-text" if self._pdf_tem_texto(file_path) else self.pdf_engine_scan
            blocos = [{
                "type": "file",
                "file": {
                    "filename": os.path.basename(file_path),
                    "file_data": "data:application/pdf;base64," + self._b64(file_path),
                },
            }]
            plugins = [{"id": "file-parser", "pdf": {"engine": engine}}]
            return blocos, plugins, f"pdf/{engine}"

        # --- imagem: direto para o modelo multimodal -------------------
        if ext in EXTENSOES_IMAGEM:
            mime = mimetypes.guess_type(file_path)[0] or "image/png"
            blocos = [{
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64," + self._b64(file_path)},
            }]
            return blocos, None, "imagem"

        # --- demais formatos: parsing local ----------------------------
        dados = self.extract_text_from_file(file_path)
        return ([{"type": "text", "text": dados["content"]}], None,
                f"texto/{ext.lstrip('.') or 'sem-extensao'}")

    @staticmethod
    def _b64(file_path):
        with open(file_path, "rb") as f:
            return base64.b64encode(f.read()).decode()

    @staticmethod
    def _pdf_tem_texto(file_path, minimo_por_pagina=40, amostra=5):
        """
        Amostra as primeiras páginas. Com camada de texto usa o motor grátis;
        sem camada, paga OCR/visão. Evita gastar OCR em PDF digital.

        Atenção: o extractText() da PyPDF2 1.26 é bem pior que o das versões
        modernas. Ele serve para ESTA decisão (tem texto ou não), mas se você
        ficar nessa versão, prefira o motor de OCR quando houver dúvida.
        """
        try:
            paginas, _total = abrir_pdf(file_path)
            paginas = paginas[:amostra]
            if not paginas:
                return False
            soma = sum(len(t.strip()) for t in paginas)
            return (soma / len(paginas)) >= minimo_por_pagina
        except Exception:
            return False   # na dúvida, trata como escaneado

    # -----------------------------------------------------------------
    # Parsing local (só para o que a API não lê)
    # -----------------------------------------------------------------
    def extract_text_from_file(self, file_path):
        nome = os.path.basename(file_path)
        ext = Path(file_path).suffix.lower()
        conteudo = ""

        try:
            if ext in (".xlsx", ".xlsm", ".xltx"):
                from openpyxl import load_workbook
                wb = load_workbook(file_path, read_only=True, data_only=True)
                partes = []
                for aba in wb.worksheets:          # TODAS as abas
                    partes.append(f"\n=== ABA: {aba.title} ===")
                    vazias = 0
                    for linha in aba.iter_rows(values_only=True):
                        celulas = ["" if v is None else str(v).strip() for v in linha]
                        if not any(celulas):
                            vazias += 1
                            if vazias > 25:
                                break
                            continue
                        vazias = 0
                        partes.append(" | ".join(celulas).rstrip(" |"))
                wb.close()
                conteudo = "\n".join(partes)

            elif ext in (".docx", ".dotx"):
                from docx import Document
                d = Document(file_path)
                partes = [p.text for p in d.paragraphs if p.text.strip()]
                for n, tab in enumerate(d.tables, 1):
                    partes.append(f"\n--- tabela {n} ---")
                    for linha in tab.rows:
                        partes.append(" | ".join(c.text.strip() for c in linha.cells))
                conteudo = "\n".join(partes)

            elif ext in (".odt", ".ods"):
                from odf import teletype, text as odftext
                from odf.opendocument import load
                from odf.table import Table, TableCell, TableRow
                d = load(file_path)
                partes = [teletype.extractText(p) for p in d.getElementsByType(odftext.P)]
                for tab in d.getElementsByType(Table):
                    for linha in tab.getElementsByType(TableRow):
                        cel = [teletype.extractText(c) for c in linha.getElementsByType(TableCell)]
                        if any(cel):
                            partes.append(" | ".join(cel))
                conteudo = "\n".join(partes)

            elif ext == ".eml":
                with open(file_path, "rb") as f:
                    msg = email.message_from_binary_file(f, policy=email.policy.default)
                corpo = msg.get_body(preferencelist=("plain", "html"))
                texto = corpo.get_content() if corpo else ""
                if corpo is not None and corpo.get_content_subtype() == "html":
                    texto = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", texto, flags=re.S | re.I)
                    texto = re.sub(r"<[^>]+>", " ", texto)
                anexos = [p.get_filename() or "sem-nome" for p in msg.iter_attachments()]
                conteudo = (f"De: {msg.get('From','')}\nPara: {msg.get('To','')}\n"
                            f"Assunto: {msg.get('Subject','')}\nData: {msg.get('Date','')}\n"
                            f"Anexos: {', '.join(anexos) or 'nenhum'}\n\n{texto}")

            else:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    conteudo = f.read()

        except Exception as exc:
            conteudo = f"[erro ao ler {nome}: {type(exc).__name__}: {exc}]"

        conteudo = re.sub(r"\n{3,}", "\n\n", conteudo).strip()
        if len(conteudo) > 300000:
            conteudo = conteudo[:300000] + "\n[conteúdo truncado]"

        return {
            "content": conteudo,
            "mime_type": mimetypes.guess_type(file_path)[0] or "application/octet-stream",
            "filename": nome,
            "size": os.path.getsize(file_path) if os.path.exists(file_path) else 0,
        }

    # -----------------------------------------------------------------
    # Chamada à API
    # -----------------------------------------------------------------
    def montar_payload(self, file_path, context):
        """Separado da chamada HTTP para permitir teste sem gastar crédito."""
        blocos, plugins, rota = self.montar_conteudo(file_path)

        blocos.append({"type": "text", "text": (
            f"PROCESSO\n"
            f"- Número: {context.get('numero', 'N/A')}\n"
            f"- Objeto: {context.get('descricao', 'N/A')}\n"
            f"- Valor estimado: {context.get('valor_estimado', 'N/A')}\n\n"
            f"ARQUIVO: {os.path.basename(file_path)}\n\n"
            f"Extraia os dados no schema abaixo.\n\nSCHEMA:\n{self.ESQUEMA}"
        )})

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": blocos},
            ],
            "temperature": 0.0,
            "max_tokens": 32000,
            "response_format": {"type": "json_object"},
            # Gemini 3 Flash tem níveis de raciocínio. "low" basta para
            # extração; "minimal" degrada em documento sujo.
            "reasoning": {"effort": "low"},
            "usage": {"include": True},
        }
        if plugins:
            payload["plugins"] = plugins
        return payload, rota

    def process_file(self, file_path, context):
        """Rota nova: recebe o CAMINHO do arquivo, não o texto."""
        payload, rota = self.montar_payload(file_path, context)
        resultado = self._post(payload)
        resultado["rota"] = rota
        return resultado

    def process_with_ai(self, content, context):
        """Compatibilidade: mantém a assinatura antiga (texto puro)."""
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": (
                    f"PROCESSO\n- Número: {context.get('numero','N/A')}\n"
                    f"- Objeto: {context.get('descricao','N/A')}\n\n"
                    f"SCHEMA:\n{self.ESQUEMA}\n\nCONTEÚDO:\n{content}"
                )},
            ],
            "temperature": 0.0,
            "max_tokens": 32000,
            "response_format": {"type": "json_object"},
            "reasoning": {"effort": "low"},
            "usage": {"include": True},
        }
        return self._post(payload)

    # -----------------------------------------------------------------
    def _post(self, payload):
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": getattr(settings, "OPENROUTER_SITE_URL", "http://localhost:8000"),
            "X-Title": "Arsenal-Main",
        }

        for tentativa in range(4):
            try:
                r = requests.post(f"{self.base_url}/chat/completions",
                                  headers=headers, json=payload,
                                  timeout=self.timeout,
                                  proxies=self.proxies, verify=self.verify)
            except requests.exceptions.SSLError as exc:
                return {"status": "error", "error":
                        f"TLS rejeitado (CA da rede?): {exc}. "
                        "Configure OPENROUTER_CA_BUNDLE."}
            except (requests.exceptions.ConnectTimeout,
                    requests.exceptions.ProxyError) as exc:
                return {"status": "error", "error":
                        f"sem rota ate openrouter.ai: {exc}. "
                        "Verifique proxy/firewall (HTTPS_PROXY)."}
            except requests.RequestException as exc:
                if tentativa == 3:
                    return {"status": "error", "error": f"rede: {exc}"}
                time.sleep(2 ** tentativa + random.random())
                continue

            if r.status_code == 401:
                return {"status": "error", "error": "chave OpenRouter inválida (401)"}
            if r.status_code == 402:
                return {"status": "error", "error": "sem créditos na OpenRouter (402)"}
            if r.status_code in (408, 429, 500, 502, 503, 504):
                if tentativa == 3:
                    return {"status": "error", "error": f"HTTP {r.status_code} após 4 tentativas"}
                espera = float(r.headers.get("Retry-After") or 2 ** tentativa)
                time.sleep(min(espera, 30) + random.random())
                continue
            if r.status_code >= 400:
                return {"status": "error", "error": f"HTTP {r.status_code}: {r.text[:400]}"}

            dados = r.json()
            if "error" in dados and not dados.get("choices"):
                return {"status": "error",
                        "error": dados["error"].get("message", "erro da API")}

            escolha = dados["choices"][0]
            texto = escolha["message"].get("content") or ""
            if isinstance(texto, list):
                texto = "".join(b.get("text", "") for b in texto if isinstance(b, dict))

            uso = dados.get("usage", {}) or {}
            try:
                return {
                    "status": "success",
                    "data": extrair_json(texto),
                    "uso": {"entrada": uso.get("prompt_tokens", 0),
                            "saida": uso.get("completion_tokens", 0),
                            "custo_usd": uso.get("cost", 0)},
                    "truncado": escolha.get("finish_reason") == "length",
                    "modelo": dados.get("model", self.model),
                }
            except (ValueError, json.JSONDecodeError) as exc:
                return {"status": "partial", "data": {"conteudo": texto},
                        "error": f"JSON inválido: {exc}"}

        return {"status": "error", "error": "tentativas esgotadas"}

    # -----------------------------------------------------------------
    def process_directory(self, directory_path, context):
        resultados = []
        for raiz, _dirs, arquivos in os.walk(directory_path):
            for nome in sorted(arquivos):
                caminho = os.path.join(raiz, nome)
                if os.path.getsize(caminho) > 40 * 1024 * 1024:
                    continue
                if Path(nome).suffix.lower() in (".zip", ".tgz", ".tar", ".gz",
                                                 ".exe", ".dll", ".db"):
                    continue
                resultado = self.process_file(caminho, context)
                resultados.append({
                    "filename": nome,
                    "rota": resultado.get("rota", ""),
                    "ai_result": resultado,
                })
        return resultados

    # -----------------------------------------------------------------
    def merge_results(self, results):
        merged = {"informacoes_gerais": {}, "empresas": [], "itens": [],
                  "avisos_gerais": []}
        empresas_vistas = {}
        itens_por_chave = {}

        def chave(texto):
            return re.sub(r"[^a-z0-9]", "", str(texto or "").lower())

        for r in results:
            dados = (r.get("ai_result") or {}).get("data") or {}
            if not isinstance(dados, dict):
                continue

            for k, v in (dados.get("informacoes_gerais") or {}).items():
                if v not in (None, "", []) and not merged["informacoes_gerais"].get(k):
                    merged["informacoes_gerais"][k] = v

            for emp in (dados.get("empresas") or []):
                nome = (emp.get("nome") or "").strip()
                if not nome:
                    continue
                k = chave(emp.get("cnpj")) or chave(nome)
                if k in empresas_vistas:
                    for campo, valor in emp.items():
                        if valor and not empresas_vistas[k].get(campo):
                            empresas_vistas[k][campo] = valor
                else:
                    empresas_vistas[k] = dict(emp, nome=nome)

            for item in (dados.get("itens") or []):
                # chave forte: código/PI/NSN. Só cai na descrição se não houver.
                k = (chave(item.get("codigo")) or chave(item.get("pi"))
                     or chave(item.get("nsn")))
                if not k or len(k) < 4:
                    k = "desc:" + chave(item.get("nome_em_portugues"))[:60]

                if k in itens_por_chave:
                    alvo = itens_por_chave[k]
                    alvo.setdefault("empresas", {}).update(item.get("empresas") or {})
                    for campo in ("pi", "nsn", "codigo", "nome_em_portugues", "qtde", "uf"):
                        if not alvo.get(campo) and item.get(campo):
                            alvo[campo] = item[campo]
                    alvo["confianca"] = min(alvo.get("confianca", 100),
                                            item.get("confianca", 100))
                else:
                    itens_por_chave[k] = dict(item)

            merged["avisos_gerais"].extend(dados.get("avisos_gerais") or [])

        merged["empresas"] = list(empresas_vistas.values())
        merged["itens"] = list(itens_por_chave.values())
        for i, item in enumerate(merged["itens"], 1):
            if not item.get("item"):
                item["item"] = i
        return merged
