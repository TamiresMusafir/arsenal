import base64
import email
import email.policy
import json
import mimetypes
import os
import random
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import requests
import xlrd
from django.conf import settings
from docx import Document
from odf import teletype, text as odftext
from odf.opendocument import load
from odf.table import Table, TableCell, TableRow
from openpyxl import load_workbook

def abrir_pdf(file_path):
    # pypdf moderno
    try:
        from pypdf import PdfReader

        leitor = PdfReader(file_path)

        paginas = []

        for pagina in leitor.pages:
            try:
                paginas.append(pagina.extract_text() or "")
            except Exception:
                paginas.append("")

        return paginas, len(paginas)

    except ImportError:
        pass

    # PyPDF2 moderno
    try:
        from PyPDF2 import PdfReader

        leitor = PdfReader(file_path)

        paginas = []

        for pagina in leitor.pages:
            try:
                paginas.append(pagina.extract_text() or "")
            except Exception:
                paginas.append("")

        return paginas, len(paginas)

    except ImportError:
        pass

    # PyPDF2 legado (ex.: 1.26)
    try:
        from PyPDF2 import PdfFileReader

        leitor = PdfFileReader(file_path, strict=False)
        total = leitor.getNumPages()
        paginas = []

        for i in range(total):
            try:
                paginas.append(
                    leitor.getPage(i).extractText() or ""
                )
            except Exception:
                paginas.append("")

        return paginas, total

    except ImportError as exc:
        raise RuntimeError(
            "Nenhuma biblioteca compatível para leitura de PDF "
            "(pypdf/PyPDF2) está instalada."
        ) from exc

EXTENSOES_IMAGEM = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"}

def ocr_pdf(file_path, idiomas=None, timeout=None):
    if not shutil.which("ocrmypdf"):
        return None

    pasta = tempfile.mkdtemp(prefix="ocr_")
    destino = os.path.join(
        pasta,
        os.path.basename(file_path),
    )

    idioma_ocr = idiomas or getattr(
        settings,
        "OCR_IDIOMAS",
        "por+eng",
    )

    timeout_total = timeout or getattr(
        settings,
        "OCR_TIMEOUT_TOTAL",
        900,
    )

    timeout_pagina = getattr(
        settings,
        "OCR_TIMEOUT_PAGINA",
        180,
    )

    comando = [
        "ocrmypdf",
        "-l", idioma_ocr,
        "--skip-text",
        "--rotate-pages",
        "--deskew",
        "--optimize", "0",
        "--tesseract-timeout", str(timeout_pagina),
        "--quiet",
        file_path,
        destino,
    ]

    try:
        subprocess.run(
            comando,
            check=True,
            timeout=timeout_total,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (subprocess.SubprocessError, OSError):
        shutil.rmtree(pasta, ignore_errors=True)
        return None

    if not os.path.isfile(destino):
        shutil.rmtree(pasta, ignore_errors=True)
        return None

    return destino

_CAB_MODELO = {
    "item": "item",
    "numero de estoque": "pi",
    "nr de estoque": "pi",
    "nomenclatura": "descricao",
    "u.f.": "uf",
    "uf": "uf",
    "qt.": "qtde",
    "qt": "qtde",
    "qtde": "qtde",
    "prazo entrega": "prazo_entrega",
    "preco unit. (r$)": "preco_unitario",
    "preco unitario": "preco_unitario",
    "preco total (r$)": "preco_total",
    "preco total": "preco_total",
}

_ROTULOS_EMPRESA = {
    "razao social": "nome",
    "cnpj": "cnpj",
    "codemp": "codemp",
    "e-mail": "email",
    "email": "email",
    "telefone": "telefone",
}

_RUIDO_MODELO = {
    "",
    "*",
    "mrc",
    "marca",
    "local de entrega",
    "referencia",
    "descricao caracteristica",
    "resposta decodificada",
    "--------------------",
}

_ACENTOS = str.maketrans(
    "áàâãäéèêëíìîïóòôõöúùûüç",
    "aaaaaeeeeiiiiooooouuuuc",
)


def _norm_modelo(valor):
    return re.sub(r"\s+", " ", str(valor or "").strip().lower().translate(_ACENTOS))

def _ler_grade(file_path):

    if file_path.lower().endswith(".xls"):
        wb = xlrd.open_workbook(file_path)

        try:
            for aba in wb.sheets():
                cabecalho = [
                    str(aba.cell(0, c).value or "").strip().lower()
                    for c in range(aba.ncols)
                ]

                # Procura uma aba que tenha algum cabeçalho conhecido.
                if any(coluna in _CAB_MODELO for coluna in cabecalho):
                    def celula(r, c):
                        cel = aba.cell(r, c)

                        if (
                            cel.ctype == xlrd.XL_CELL_NUMBER
                            and float(cel.value).is_integer()
                        ):
                            return str(int(cel.value))

                        return cel.value

                    return [
                        [celula(r, c) for c in range(aba.ncols)]
                        for r in range(aba.nrows)
                    ]

            return None

        finally:
            wb.release_resources()

    wb = load_workbook(file_path, data_only=True)

    try:
        for aba in wb.worksheets:
            grade = [
                list(linha)
                for linha in aba.iter_rows(values_only=True)
            ]

            # Procura uma aba que contenha algum cabeçalho conhecido.
            for linha in grade:
                cabecalho = [
                    _norm_modelo(celula)
                    for celula in linha
                ]

                if any(coluna in _CAB_MODELO for coluna in cabecalho):
                    return grade

        return None

    finally:
        wb.close()

def _numero_item(valor):
    texto = str(valor or "").strip()

    match = re.fullmatch(
        r"\s*(\d{1,4})\s*(?:[ºo°.)\-]+)?\s*",
        texto,
        re.IGNORECASE,
    )

    if not match:
        return None

    return int(match.group(1))


def parse_modelo_proposta(file_path, limite_descricao=500):
    from .services import para_float  # import tardio: evita ciclo

    if Path(file_path).suffix.lower() not in (".xls", ".xlsx", ".xlsm"):
        return None

    try:
        grade = _ler_grade(file_path)
    except Exception:
        return None

    # --- acha a linha de cabeçalho da tabela de itens ------------------
    colunas, linha_cab = {}, None

    for i, linha in enumerate(grade[:80]):
        achadas = {}

        for c, valor in enumerate(linha):
            campo = _CAB_MODELO.get(_norm_modelo(valor))

            if campo and campo not in achadas:
                achadas[campo] = c

        if {"item", "pi", "descricao"} <= set(achadas):
            colunas = achadas
            linha_cab = i
            break

    if linha_cab is None:
        return None

    def cel(linha, campo):
        c = colunas.get(campo)

        if c is None or c >= len(linha):
            return ""

        return str(linha[c] or "").strip()

    # --- identificação da empresa ------------------------------------
    identificacao = {}

    for linha in grade[:linha_cab]:
        for c, valor in enumerate(linha):

            campo = _ROTULOS_EMPRESA.get(_norm_modelo(valor))

            if not campo or identificacao.get(campo):
                continue

            for d in range(c + 1, min(c + 6, len(linha))):
                preenchido = str(linha[d] or "").strip()

                if preenchido and preenchido != "*":
                    identificacao[campo] = preenchido
                    break

    nome_empresa = identificacao.get("nome", "")

    # --- verifica se existem preços na planilha -----------------------
    # Se existem preços, mas não conseguimos identificar a empresa,
    # não podemos tratar essa planilha como uma proposta determinística.
    # Nesse caso, retorna None para que o arquivo siga para a IA.
    tem_preco = False

    for linha in grade[linha_cab + 1:]:
        primeiro = cel(linha, "item")
        numero_item = _numero_item(primeiro)

        if numero_item is not None:
            preco = para_float(cel(linha, "preco_unitario"))

            if preco is not None:
                tem_preco = True
                break

    if tem_preco and not nome_empresa:
        return None

    # --- blocos de item: a linha do item começa com o número ----------
    itens = []
    atual = None

    for linha in grade[linha_cab + 1:]:
        primeiro = cel(linha, "item")
        numero_item = _numero_item(primeiro)

        if numero_item is not None:

            preco = para_float(cel(linha, "preco_unitario"))

            atual = {
                "item": numero_item,
                "pi": cel(linha, "pi"),
                "nsn": "",
                "codigo": cel(linha, "pi"),
                "nome_em_portugues": cel(linha, "descricao"),
                "qtde": para_float(cel(linha, "qtde")),
                "uf": cel(linha, "uf"),
                "prazo_entrega": cel(linha, "prazo_entrega"),

                # O preço pertence à empresa identificada.
                "empresas": (
                    {nome_empresa: preco}
                    if nome_empresa and preco is not None
                    else {}
                ),

                # A proposta do fornecedor NÃO define a estimativa
                # da Administração.
                "valor_unitario_estimado": None,
                "valor_total": None,

                "confianca": 100,
                "avisos": [],
            }

            itens.append(atual)
            continue

        # --- linhas de continuação da descrição -----------------------
        if atual is None:
            continue

        if len(atual["nome_em_portugues"]) >= limite_descricao:
            continue

        extra = cel(linha, "descricao")

        if (
            extra
            and _norm_modelo(extra) not in _RUIDO_MODELO
            and not extra.startswith("<<")
        ):
            atual["nome_em_portugues"] = (
                atual["nome_em_portugues"] + " " + extra
            ).strip()[:limite_descricao]

    if not itens:
        return None

    # --- avisos -------------------------------------------------------
    avisos = []

    # Itens sem PI não entram no mapa.
    sem_pi = [
        i["item"]
        for i in itens
        if not i["pi"]
    ]

    if sem_pi:
        avisos.append(
            "itens sem PI no modelo (não entram no mapa): "
            + ", ".join(map(str, sem_pi))
        )

    # Verifica possíveis itens que desapareceram durante a leitura.
    numeros = [i["item"] for i in itens]

    if numeros:
        esperado = set(range(min(numeros), max(numeros) + 1))
        encontrados = set(numeros)
        faltando = sorted(esperado - encontrados)

        if faltando:
            avisos.append(
                "itens ausentes na leitura do modelo: "
                + ", ".join(map(str, faltando))
                + " — conferir"
            )

    # Empresa identificada, mas nenhum preço encontrado:
    # provavelmente é uma recusa/declínio.
    if nome_empresa and not any(i["empresas"] for i in itens):

        identificacao["tipo_resposta"] = "declinio"

        avisos.append(
            f"{nome_empresa} devolveu o modelo sem nenhum preço"
        )

    return {
        "informacoes_gerais": {},

        "empresas": (
            [
                dict(
                    identificacao,
                    tipo_resposta=identificacao.get(
                        "tipo_resposta",
                        "cotacao",
                    ),
                )
            ]
            if nome_empresa
            else []
        ),

        "itens": itens,

        "avisos_gerais": avisos,

        "origem": "modelo-deterministico",
    }

def extrair_json(texto):
    """
    Extrai um objeto JSON de uma resposta da IA.
    - Remove blocos Markdown ```json ... ```
    - Tenta interpretar a resposta inteira primeiro.
    - Caso exista texto antes/depois do JSON, localiza o primeiro objeto.
    - Faz a contagem de chaves ignorando chaves dentro de strings.
    - Caso a resposta esteja truncada, tenta fechar as chaves abertas.
    - Quando o JSON truncado possui uma lista 'itens', descarta o último
      item, pois ele pode estar incompleto.
    """

    if not texto:
        raise ValueError("resposta vazia")

    t = texto.strip()

    # ---------------------------------------------------------
    # Remove bloco Markdown ```json ... ```
    # ---------------------------------------------------------

    if t.startswith("```"):
        t = t.split("\n", 1)[-1]

        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]

    t = t.strip()

    # ---------------------------------------------------------
    # Primeiro: tenta interpretar a resposta inteira
    # ---------------------------------------------------------

    try:
        return json.loads(t)

    except json.JSONDecodeError:
        pass

    # ---------------------------------------------------------
    # Procura o início do objeto JSON
    # ---------------------------------------------------------

    inicio = t.find("{")

    if inicio == -1:
        raise ValueError("nenhum objeto JSON na resposta")

    # ---------------------------------------------------------
    # Varredura das chaves
    #
    # Ignora chaves que estejam dentro de strings.
    # Exemplo:
    #
    # "descricao": "Produto com {detalhes} adicionais"
    #
    # O {detalhes} não deve alterar a profundidade.
    # ---------------------------------------------------------

    profundidade = 0
    em_string = False
    escape = False

    for i in range(inicio, len(t)):
        c = t[i]

        # Trata caracteres escapados dentro de strings
        if escape:
            escape = False
            continue

        if c == "\\":
            escape = True
            continue

        # Abre/fecha string
        if c == '"':
            em_string = not em_string
            continue

        # Dentro de uma string, ignora tudo
        if em_string:
            continue

        # Conta abertura/fechamento de objetos
        if c == "{":
            profundidade += 1

        elif c == "}":
            profundidade -= 1

            # Encontrou o fechamento do objeto principal
            if profundidade == 0:
                return json.loads(t[inicio:i + 1])

    # ---------------------------------------------------------
    # JSON truncado
    #
    # A resposta terminou antes de fechar todas as chaves.
    # Tentamos fechar as chaves restantes.
    # ---------------------------------------------------------

    json_truncado = (
        t[inicio:]
        .rstrip()
        .rstrip(",")
        + "}" * profundidade
    )

    try:
        dados = json.loads(json_truncado)

    except json.JSONDecodeError as erro:
        raise ValueError(
            f"JSON inválido ou truncado e não pôde ser recuperado: {erro}"
        ) from erro

    # ---------------------------------------------------------
    # Remove o último item da lista quando a resposta foi
    # truncada.
    #
    # O último item é o candidato mais provável a estar
    # incompleto devido ao corte da resposta da IA.
    # ---------------------------------------------------------

    if isinstance(dados, dict) and dados.get("itens"):
        itens = dados["itens"]

        if isinstance(itens, list) and itens:
            perdido = itens.pop()

            if isinstance(perdido, dict):
                identificacao = perdido.get("pi", "?")
            else:
                identificacao = "?"

            dados.setdefault("avisos_gerais", []).append(
                f"resposta truncada: item '{identificacao}' "
                f"descartado por estar incompleto"
            )

    return dados

from django.core.exceptions import ImproperlyConfigured


# =====================================================================
# PROCESSAMENTO COM IA
# =====================================================================

class AIProcessor:

    SYSTEM_PROMPT = (
        "Você é um especialista em análise de documentos de licitação e compras "
        "públicas da Marinha do Brasil. Extraia informações estruturadas para "
        "preencher um Mapa Comparativo de Preços (Lei nº 14.133/2021, "
        "IN SEGES/ME nº 65/2021).\n"

        "REGRAS:\n"

        "1. NUNCA invente dados. Campo ausente no documento = string vazia "
        "ou null, conforme o tipo definido no esquema.\n"

        "2. NUNCA calcule preço que não esteja escrito no documento. "
        "Se só houver o valor total e a quantidade, preencha valor_total "
        "e deixe valor_unitario vazio/null.\n"

        "3. Preserve os números conforme aparecem no documento. Para valores "
        "monetários, converta para número JSON usando ponto decimal somente "
        "quando a interpretação estiver inequívoca. Nunca interprete "
        "automaticamente um ponto ou vírgula como separador de milhar se "
        "houver ambiguidade. Em caso de dúvida, mantenha o valor vazio/null, "
        "reduza a confiança e registre a dúvida em avisos.\n"

        "4. O PI (NÚMERO DE ESTOQUE) é a chave única do item. Copie-o "
        "exatamente como está no documento, sem reformatar, remover zeros "
        "à esquerda ou alterar caracteres.\n"

        "5. Quando houver LISTA DE PI abaixo, use SOMENTE esses PI. "
        "Item do documento que não casar com nenhum PI da lista não deve "
        "criar uma nova linha. Registre o item lido em avisos_gerais.\n"

        "6. Classifique cada empresa em tipo_resposta: 'cotacao' "
        "(há ao menos um preço), 'declinio' (recusa, não fornece, sem "
        "interesse, fora de linha ou sem estoque) ou 'duvida' "
        "(somente pergunta ou pedido de esclarecimento). Um mesmo e-mail "
        "pode cotar parte e declinar o restante: nesse caso é 'cotacao' "
        "e o motivo deve ser registrado em motivo_declinio.\n"

        "7. Perguntas do fornecedor vão em 'perguntas' e nunca devem "
        "ser transformadas em preço, quantidade ou qualquer outro dado "
        "inventado.\n"

        "8. Se a imagem, página, tabela ou trecho estiver ilegível, "
        "registre a dúvida em avisos e reduza a confiança do dado afetado. "
        "Não tente adivinhar o conteúdo.\n"

        "9. Se o texto vier de OCR e algum número estiver ambíguo "
        "(dígito borrado, separador decimal duvidoso, PI com caractere "
        "trocado ou valor parcialmente ilegível), reduza 'confianca' "
        "e descreva a dúvida em avisos. Não 'conserte' o número por "
        "conta própria.\n"

        "10. A confiança deve ser um número inteiro entre 0 e 100. "
        "Use 100 somente quando o dado estiver claramente legível e "
        "identificado. Reduza a confiança quando houver OCR, número "
        "ambíguo, texto ilegível, associação incerta ou qualquer dúvida "
        "na leitura. Nunca aumente a confiança para compensar uma dúvida.\n"

        "11. Não associe preço a uma empresa diferente daquela indicada "
        "no documento. Se não for possível determinar a empresa responsável "
        "pelo preço, deixe o preço sem associação e registre um aviso.\n"

        "12. Responda APENAS com o objeto JSON, sem markdown, sem ```json "
        "e sem qualquer texto antes ou depois do JSON."
    )

    ESQUEMA = """{
    "informacoes_gerais": {
        "numero_processo": "",
        "modalidade": "",
        "objeto": "",
        "data_documento": "",
        "valor_estimado_total": null
    },

    "empresas": [
        {
            "nome": "",
            "cnpj": "",
            "codemp": "",
            "email": "",
            "telefone": "",
            "tipo_resposta": "cotacao|declinio|duvida",
            "motivo_declinio": "",
            "validade_proposta": "",
            "prazo_entrega": "",
            "valor_global": null
        }
    ],

    "itens": [
        {
            "item": 1,
            "pi": "",
            "nsn": "",
            "codigo": "",
            "nome_em_portugues": "",
            "qtde": null,
            "uf": "",
            "empresas": {
                "NOME EXATO DA EMPRESA": 1234.56
            },
            "valor_unitario_estimado": null,
            "valor_total": null,
            "confianca": 90,
            "avisos": []
        }
    ],

    "perguntas": [
        {
            "empresa": "",
            "pergunta": ""
        }
    ],

    "avisos_gerais": []
}"""

    def __init__(self):
        self.api_key = settings.OPENROUTER_API_KEY
        self.base_url = settings.OPENROUTER_BASE_URL
        self.model = settings.OPENROUTER_MODEL

        # Conexão e leitura:
        # falha rapidamente se a rede estiver indisponível,
        # mas permite tempo suficiente para PDFs grandes.
        self.timeout = (
            getattr(
                settings,
                "OPENROUTER_CONNECT_TIMEOUT",
                15,
            ),
            getattr(
                settings,
                "OPENROUTER_TIMEOUT",
                300,
            ),
        )

        # Rede corporativa/militar:
        # None permite que requests utilize HTTP_PROXY/HTTPS_PROXY.
        self.proxies = getattr(
            settings,
            "OPENROUTER_PROXIES",
            None,
        )

        # Certificado da CA utilizado na conexão HTTPS.
        # False é explicitamente proibido para não desativar
        # a validação TLS.
        ca = getattr(
            settings,
            "OPENROUTER_CA_BUNDLE",
            True,
        )

        if ca is False:
            raise ImproperlyConfigured(
                "OPENROUTER_CA_BUNDLE=False desativa a verificação TLS. "
                "Configure corretamente a CA da rede."
            )

        self.verify = ca

        self.pdf_engine_scan = getattr(
            settings,
            "OPENROUTER_PDF_ENGINE_SCAN",
            "native",
        )

        # OCR local antes de recorrer ao motor pago.
        self.ocr_local = getattr(
            settings,
            "OCR_LOCAL",
            True,
        )

# -----------------------------------------------------------------
# Roteamento da entrada
# -----------------------------------------------------------------
def montar_conteudo(self, file_path):
    """
    Decide como o arquivo entra na requisição.

    Devolve:
        (blocos_de_conteudo, plugins, rota)
    """
    ext = Path(file_path).suffix.lower()

    # --- PDF -------------------------------------------------------
    # Primeiro verifica se o PDF já possui camada de texto.
    # Se não possuir, tenta OCR local antes de recorrer ao
    # processamento pago.
    if ext == ".pdf":
        caminho = file_path
        engine = "pdf-text"
        ocr_localizado = False

        if not self._pdf_tem_texto(file_path):
            if self.ocr_local:
                saida = ocr_pdf(file_path)

                if saida and self._pdf_tem_texto(saida):
                    caminho = saida
                    ocr_localizado = True
                else:
                    # OCR local ausente, falhou ou não produziu
                    # uma quantidade suficiente de texto.
                    if saida:
                        shutil.rmtree(
                            os.path.dirname(saida),
                            ignore_errors=True,
                        )

                    engine = self.pdf_engine_scan

            else:
                # OCR local desativado.
                engine = self.pdf_engine_scan

        blocos = [
            {
                "type": "file",
                "file": {
                    "filename": os.path.basename(file_path),
                    "file_data": (
                        "data:application/pdf;base64,"
                        + self._b64(caminho)
                    ),
                },
            }
        ]

        # O arquivo OCRizado já foi convertido para base64.
        # Portanto, o temporário pode ser removido.
        if ocr_localizado:
            shutil.rmtree(
                os.path.dirname(caminho),
                ignore_errors=True,
            )

        plugins = [
            {
                "id": "file-parser",
                "pdf": {
                    "engine": engine,
                },
            }
        ]

        rota = f"pdf/{engine}"

        if ocr_localizado:
            rota += "+ocr-local"

        return blocos, plugins, rota

    # --- Imagem ----------------------------------------------------
    # Imagens seguem diretamente para o modelo multimodal.
    if ext in EXTENSOES_IMAGEM:
        mime = mimetypes.guess_type(file_path)[0] or "image/png"

        blocos = [
            {
                "type": "image_url",
                "image_url": {
                    "url": (
                        f"data:{mime};base64,"
                        + self._b64(file_path)
                    ),
                },
            }
        ]

        return blocos, None, "imagem"

    # --- Demais formatos -------------------------------------------
    # Planilhas, DOCX, ODT, EML etc. são processados localmente.
    dados = self.extract_text_from_file(file_path)

    return (
        [{"type": "text", "text": dados["content"]}],
        None,
        f"texto/{ext.lstrip('.') or 'sem-extensao'}",
    )


@staticmethod
def _b64(file_path):
    """Lê um arquivo e devolve seu conteúdo em Base64."""
    with open(file_path, "rb") as f:
        return base64.b64encode(f.read()).decode()


# -----------------------------------------------------------------
# Detecção de camada de texto em PDF
# -----------------------------------------------------------------

@staticmethod
def _texto_das_paginas(file_path, amostra=5):
    """
    Extrai uma amostra do texto das primeiras páginas.

    Prioriza pdftotext, pois costuma ser mais confiável e rápido
    que versões antigas do PyPDF2/PyPDF.
    """
    if shutil.which("pdftotext"):
        try:
            saida = subprocess.run(
                [
                    "pdftotext",
                    "-f", "1",
                    "-l", str(amostra),
                    "-q",
                    file_path,
                    "-",
                ],
                check=True,
                timeout=120,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )

            paginas = (
                saida.stdout
                .decode("utf-8", "ignore")
                .split("\f")
            )

            # pdftotext costuma colocar \f também no final.
            if paginas and paginas[-1] == "":
                paginas.pop()

            if paginas:
                return paginas[:amostra]

        except (subprocess.SubprocessError, OSError):
            pass

    # Fallback para pypdf/PyPDF2.
    paginas, _total = abrir_pdf(file_path)

    return paginas[:amostra]


@classmethod
def _pdf_tem_texto(
    cls,
    file_path,
    minimo_por_pagina=40,
    amostra=5,
):
    """
    Verifica se o PDF possui uma camada de texto utilizável.

    Primeiro analisa apenas algumas páginas para evitar processamento
    desnecessário.

    Fluxo:
        PDF com texto -> pdf-text
        PDF sem texto -> OCR local
        OCR insuficiente -> motor configurado para PDF escaneado
    """
    try:
        paginas = cls._texto_das_paginas(
            file_path,
            amostra,
        )

        if not paginas:
            return False

        soma = sum(
            len(texto.strip())
            for texto in paginas
        )

        media = soma / len(paginas)

        return media >= minimo_por_pagina

    except Exception:
        # Se não conseguimos determinar com segurança,
        # tratamos como PDF escaneado.
        return False

# -----------------------------------------------------------------
# Parsing local (só para o que a API não lê)
# -----------------------------------------------------------------
def extract_text_from_file(self, file_path):
    nome = os.path.basename(file_path)
    ext = Path(file_path).suffix.lower()
    conteudo = ""

    try:
        # ---------------------------------------------------------
        # Excel moderno
        # ---------------------------------------------------------
        if ext in (".xlsx", ".xlsm", ".xltx"):
            wb = load_workbook(
                file_path,
                read_only=True,
                data_only=True,
            )

            partes = []

            for aba in wb.worksheets:
                partes.append(f"\n=== ABA: {aba.title} ===")

                vazias = 0

                for linha in aba.iter_rows(values_only=True):
                    celulas = [
                        "" if v is None else str(v).strip()
                        for v in linha
                    ]

                    if not any(celulas):
                        vazias += 1

                        # Evita percorrer grandes áreas vazias
                        if vazias > 25:
                            break

                        continue

                    vazias = 0

                    partes.append(
                        " | ".join(celulas).rstrip(" |")
                    )

            wb.close()

            conteudo = "\n".join(partes)

        # ---------------------------------------------------------
        # Word
        # ---------------------------------------------------------
        elif ext in (".docx", ".dotx"):
            d = Document(file_path)

            partes = [
                p.text
                for p in d.paragraphs
                if p.text.strip()
            ]

            for n, tab in enumerate(d.tables, 1):
                partes.append(f"\n--- tabela {n} ---")

                for linha in tab.rows:
                    partes.append(
                        " | ".join(
                            c.text.strip()
                            for c in linha.cells
                        )
                    )

            conteudo = "\n".join(partes)

        # ---------------------------------------------------------
        # OpenDocument
        # ---------------------------------------------------------
        elif ext in (".odt", ".ods"):
            d = load(file_path)

            partes = [
                teletype.extractText(p)
                for p in d.getElementsByType(odftext.P)
                if teletype.extractText(p).strip()
            ]

            for tab in d.getElementsByType(Table):
                for linha in tab.getElementsByType(TableRow):
                    celulas = [
                        teletype.extractText(c).strip()
                        for c in linha.getElementsByType(TableCell)
                    ]

                    if any(celulas):
                        partes.append(" | ".join(celulas))

            conteudo = "\n".join(partes)

        # ---------------------------------------------------------
        # E-mail
        # ---------------------------------------------------------
        elif ext == ".eml":
            with open(file_path, "rb") as f:
                msg = email.message_from_binary_file(
                    f,
                    policy=email.policy.default,
                )

            corpo = msg.get_body(
                preferencelist=("plain", "html")
            )

            texto = corpo.get_content() if corpo else ""

            if (
                corpo is not None
                and corpo.get_content_subtype() == "html"
            ):
                texto = re.sub(
                    r"<(script|style)[^>]*>.*?</\1>",
                    " ",
                    texto,
                    flags=re.S | re.I,
                )

                texto = re.sub(
                    r"<[^>]+>",
                    " ",
                    texto,
                )

            anexos = [
                p.get_filename() or "sem-nome"
                for p in msg.iter_attachments()
            ]

            conteudo = (
                f"De: {msg.get('From', '')}\n"
                f"Para: {msg.get('To', '')}\n"
                f"Assunto: {msg.get('Subject', '')}\n"
                f"Data: {msg.get('Date', '')}\n"
                f"Anexos: {', '.join(anexos) or 'nenhum'}\n\n"
                f"{texto}"
            )

        # ---------------------------------------------------------
        # Excel antigo
        # ---------------------------------------------------------
        elif ext == ".xls":
            aba = xlrd.open_workbook(
                file_path
            ).sheet_by_index(0)

            partes = [
                f"\n=== ABA: {aba.name} ==="
            ]

            for r in range(aba.nrows):
                celulas = []

                for c in range(aba.ncols):
                    celula = aba.cell(r, c)
                    valor = celula.value

                    # Evita transformar PI inteiro em "5330012345678.0"
                    if (
                        celula.ctype == xlrd.XL_CELL_NUMBER
                        and float(valor).is_integer()
                    ):
                        valor = int(valor)

                    celulas.append(
                        "" if valor in (None, "")
                        else str(valor).strip()
                    )

                if any(celulas):
                    partes.append(
                        " | ".join(celulas).rstrip(" |")
                    )

            conteudo = "\n".join(partes)

        # ---------------------------------------------------------
        # Outros arquivos de texto
        # ---------------------------------------------------------
        else:
            with open(
                file_path,
                "r",
                encoding="utf-8",
                errors="ignore",
            ) as f:
                conteudo = f.read()

    except Exception as exc:
        conteudo = (
            f"[erro ao ler {nome}: "
            f"{type(exc).__name__}: {exc}]"
        )

    # ---------------------------------------------------------
    # Limpeza
    # ---------------------------------------------------------
    conteudo = re.sub(
        r"\n{3,}",
        "\n\n",
        conteudo,
    ).strip()

    # Evita enviar conteúdo gigantesco para a IA
    if len(conteudo) > 300000:
        conteudo = (
            conteudo[:300000]
            + "\n[conteúdo truncado]"
        )

    return {
        "content": conteudo,
        "mime_type": (
            mimetypes.guess_type(file_path)[0]
            or "application/octet-stream"
        ),
        "filename": nome,
        "size": (
            os.path.getsize(file_path)
            if os.path.exists(file_path)
            else 0
        ),
    }

# -----------------------------------------------------------------
# Chamada à API
# -----------------------------------------------------------------
def montar_payload(self, file_path, context, base=None, limite_pi=200):
    blocos, plugins, rota = self.montar_conteudo(file_path)

    # -------------------------------------------------------------
    # Lista fechada de PI vinda do modelo de proposta
    # -------------------------------------------------------------
    lista_pi = ""

    itens_base = (base or {}).get("itens") or []

    if itens_base:
        linhas = []

        for item in itens_base[:limite_pi]:
            pi = item.get("pi")

            if not pi:
                continue

            linhas.append(
                f"{item.get('item')} | "
                f"{pi} | "
                f"{(item.get('nome_em_portugues') or '')[:80]} | "
                f"{item.get('qtde') or ''} "
                f"{item.get('uf') or ''}"
            )

        if linhas:
            lista_pi = (
                "\nLISTA DE PI DO MODELO DE PROPOSTA "
                "(item | PI | nomenclatura | qtde):\n"
                + "\n".join(linhas)
            )

        if len(itens_base) > limite_pi:
            lista_pi += (
                f"\n[... {len(itens_base) - limite_pi} "
                f"itens não listados]"
            )

    # -------------------------------------------------------------
    # Informa à IA quando houve OCR local
    # -------------------------------------------------------------
    origem_ocr = ""

    if rota.endswith("+ocr-local"):
        origem_ocr = (
            "\nATENÇÃO: este PDF não tinha camada de texto. "
            "Ela foi criada por OCR local (Tesseract). "
            "Trate números com desconfiança, conforme a regra 9."
        )

    # -------------------------------------------------------------
    # Contexto adicional enviado junto ao arquivo
    # -------------------------------------------------------------
    blocos.append({
        "type": "text",
        "text": (
            "PROCESSO\n"
            f"- Número: {context.get('numero', 'N/A')}\n"
            f"- Objeto: {context.get('descricao', 'N/A')}\n"
            f"- Valor estimado: {context.get('valor_estimado', 'N/A')}\n"
            f"{lista_pi}\n\n"
            f"ARQUIVO: {os.path.basename(file_path)}"
            f"{origem_ocr}\n\n"
            "Extraia os dados no schema abaixo.\n\n"
            f"SCHEMA:\n{self.ESQUEMA}"
        ),
    })

    # -------------------------------------------------------------
    # Payload da API
    # -------------------------------------------------------------
    payload = {
        "model": self.model,

        "messages": [
            {
                "role": "system",
                "content": self.SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": blocos,
            },
        ],

        "temperature": 0.0,

        "max_tokens": 32000,

        "response_format": {
            "type": "json_object",
        },

        # Para extração estruturada, raciocínio baixo é suficiente.
        "reasoning": {
            "effort": "low",
        },

        "usage": {
            "include": True,
        },
    }

    if plugins:
        payload["plugins"] = plugins

    return payload, rota

def process_file(self, file_path, context, base=None):
    # -----------------------------------------------------------------
    # Modelo de proposta em planilha:
    # tenta processar deterministicamente antes de chamar a IA.
    # -----------------------------------------------------------------
    if Path(file_path).suffix.lower() in (".xls", ".xlsx", ".xlsm"):
        direto = parse_modelo_proposta(file_path)

        if direto and direto.get("itens"):
            return {
                "status": "success",
                "data": direto,
                "uso": {
                    "entrada": 0,
                    "saida": 0,
                    "custo_usd": 0,
                },
                "rota": "modelo/deterministico",
            }

    # -----------------------------------------------------------------
    # Demais arquivos:
    # seguem para a IA.
    # -----------------------------------------------------------------
    payload, rota = self.montar_payload(
        file_path,
        context,
        base,
    )

    resultado = self._post(payload)
    resultado["rota"] = rota

    return resultado


def process_with_ai(self, content, context):
    """
    Compatibilidade:
    mantém a assinatura antiga para processamento de texto puro.
    """
    payload = {
        "model": self.model,

        "messages": [
            {
                "role": "system",
                "content": self.SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": (
                    "PROCESSO\n"
                    f"- Número: {context.get('numero', 'N/A')}\n"
                    f"- Objeto: {context.get('descricao', 'N/A')}\n\n"
                    f"SCHEMA:\n{self.ESQUEMA}\n\n"
                    f"CONTEÚDO:\n{content}"
                ),
            },
        ],

        "temperature": 0.0,

        "max_tokens": 32000,

        "response_format": {
            "type": "json_object",
        },

        "reasoning": {
            "effort": "low",
        },

        "usage": {
            "include": True,
        },
    }

    return self._post(payload)


# -----------------------------------------------------------------
# Chamada à API
# -----------------------------------------------------------------
def _post(self, payload):
    headers = {
        "Authorization": f"Bearer {self.api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": getattr(
            settings,
            "OPENROUTER_SITE_URL",
            "http://localhost:8000",
        ),
        "X-Title": "Arsenal-Main",
    }

    for tentativa in range(4):
        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=self.timeout,
                proxies=self.proxies,
                verify=self.verify,
            )

        except requests.exceptions.SSLError as exc:
            return {
                "status": "error",
                "error": (
                    f"TLS rejeitado (CA da rede?): {exc}. "
                    "Configure OPENROUTER_CA_BUNDLE."
                ),
            }

        except (
            requests.exceptions.ConnectTimeout,
            requests.exceptions.ProxyError,
        ) as exc:
            return {
                "status": "error",
                "error": (
                    f"sem rota ate openrouter.ai: {exc}. "
                    "Verifique proxy/firewall (HTTPS_PROXY)."
                ),
            }

        except requests.RequestException as exc:
            if tentativa == 3:
                return {
                    "status": "error",
                    "error": f"rede: {exc}",
                }

            time.sleep(
                2 ** tentativa + random.random()
            )
            continue

        # ---------------------------------------------------------
        # Erros HTTP
        # ---------------------------------------------------------
        if response.status_code == 401:
            return {
                "status": "error",
                "error": "chave OpenRouter inválida (401)",
            }

        if response.status_code == 402:
            return {
                "status": "error",
                "error": "sem créditos na OpenRouter (402)",
            }

        if response.status_code in (
            408,
            429,
            500,
            502,
            503,
            504,
        ):
            if tentativa == 3:
                return {
                    "status": "error",
                    "error": (
                        f"HTTP {response.status_code} "
                        "após 4 tentativas"
                    ),
                }

            espera = float(
                response.headers.get("Retry-After")
                or 2 ** tentativa
            )

            time.sleep(
                min(espera, 30) + random.random()
            )

            continue

        if response.status_code >= 400:
            return {
                "status": "error",
                "error": (
                    f"HTTP {response.status_code}: "
                    f"{response.text[:400]}"
                ),
            }

        # ---------------------------------------------------------
        # Resposta da API
        # ---------------------------------------------------------
        try:
            dados = response.json()

        except ValueError as exc:
            return {
                "status": "error",
                "error": f"resposta inválida da API: {exc}",
            }

        if "error" in dados and not dados.get("choices"):
            erro = dados["error"]

            if isinstance(erro, dict):
                mensagem = erro.get(
                    "message",
                    "erro da API",
                )
            else:
                mensagem = str(erro)

            return {
                "status": "error",
                "error": mensagem,
            }

        choices = dados.get("choices") or []

        if not choices:
            return {
                "status": "error",
                "error": "API não retornou nenhuma escolha",
            }

        escolha = choices[0]

        mensagem = escolha.get("message") or {}

        texto = mensagem.get("content") or ""

        if isinstance(texto, list):
            texto = "".join(
                bloco.get("text", "")
                for bloco in texto
                if isinstance(bloco, dict)
            )

        # ---------------------------------------------------------
        # Uso / custo
        # ---------------------------------------------------------
        uso = dados.get("usage", {}) or {}

        # ---------------------------------------------------------
        # Extrai JSON retornado pela IA
        # ---------------------------------------------------------
        try:
            data = extrair_json(texto)

            return {
                "status": "success",
                "data": data,
                "uso": {
                    "entrada": uso.get(
                        "prompt_tokens",
                        0,
                    ),
                    "saida": uso.get(
                        "completion_tokens",
                        0,
                    ),
                    "custo_usd": uso.get(
                        "cost",
                        0,
                    ),
                },
                "truncado": (
                    escolha.get("finish_reason")
                    == "length"
                ),
                "modelo": dados.get(
                    "model",
                    self.model,
                ),
            }

        except (
            ValueError,
            json.JSONDecodeError,
        ) as exc:
            return {
                "status": "partial",
                "data": {
                    "conteudo": texto,
                },
                "error": f"JSON inválido: {exc}",
            }

    return {
        "status": "error",
        "error": "tentativas esgotadas",
    }

# -----------------------------------------------------------------
def process_directory(self, directory_path, context, base=None):
    resultados = []

    extensoes_ignoradas = {
        ".zip",
        ".tgz",
        ".tar",
        ".gz",
        ".exe",
        ".dll",
        ".db",
    }

    tamanho_maximo = 40 * 1024 * 1024

    for raiz, _dirs, arquivos in os.walk(directory_path):
        for nome in sorted(arquivos):
            caminho = os.path.join(raiz, nome)

            try:
                if os.path.getsize(caminho) > tamanho_maximo:
                    continue
            except OSError:
                continue

            if Path(nome).suffix.lower() in extensoes_ignoradas:
                continue

            resultado = self.process_file(
                caminho,
                context,
                base,
            )

            resultados.append({
                "filename": nome,
                "rota": resultado.get("rota", ""),
                "ai_result": resultado,
            })

    return resultados


# -----------------------------------------------------------------
def merge_results(self, results, base=None):
    merged = {
        "informacoes_gerais": {},
        "empresas": [],
        "itens": [],
        "perguntas": [],
        "avisos_gerais": [],
    }

    empresas_vistas = {}
    itens_por_pi = {}
    ordem = []

    def chave(texto):
        """
        Normaliza uma chave para comparação.

        Exemplo:
            '53.300.123/4567-89'
            '53300123456789'

        viram a mesma chave.
        """
        return re.sub(
            r"[^a-z0-9]",
            "",
            str(texto or "").lower(),
        )

    # -------------------------------------------------------------
    # 1. A base define as linhas válidas do mapa
    # -------------------------------------------------------------
    for item in (base or {}).get("itens") or []:
        k = chave(item.get("pi"))

        if not k:
            merged["avisos_gerais"].append(
                f"item {item.get('item')} do modelo sem PI: "
                "fora do mapa"
            )
            continue

        itens_por_pi[k] = dict(
            item,
            empresas=dict(item.get("empresas") or {}),
        )

        ordem.append(k)

    tem_base = bool(ordem)

    # -------------------------------------------------------------
    # 2. Processa as respostas dos fornecedores
    # -------------------------------------------------------------
    for resultado in results:
        dados = (
            resultado.get("ai_result") or {}
        ).get("data") or {}

        if not isinstance(dados, dict):
            continue

        origem = resultado.get("filename", "")

        rota = (
            resultado.get("rota")
            or (resultado.get("ai_result") or {}).get("rota")
            or ""
        )

        veio_de_ocr = "ocr-local" in rota

        # ---------------------------------------------------------
        # Informações gerais
        # ---------------------------------------------------------
        informacoes = (
            dados.get("informacoes_gerais") or {}
        )

        for campo, valor in informacoes.items():
            if (
                valor not in (None, "", [])
                and not merged["informacoes_gerais"].get(campo)
            ):
                merged["informacoes_gerais"][campo] = valor

        # ---------------------------------------------------------
        # Empresas
        # ---------------------------------------------------------
        for empresa in dados.get("empresas") or []:
            nome = (
                empresa.get("nome") or ""
            ).strip()

            if not nome:
                continue

            chave_empresa = (
                chave(empresa.get("cnpj"))
                or chave(nome)
            )

            if not chave_empresa:
                continue

            if chave_empresa in empresas_vistas:
                existente = empresas_vistas[chave_empresa]

                for campo, valor in empresa.items():
                    if (
                        valor
                        and not existente.get(campo)
                    ):
                        existente[campo] = valor

                # Uma cotação prevalece sobre
                # declínio ou dúvida.
                if (
                    empresa.get("tipo_resposta")
                    == "cotacao"
                ):
                    existente["tipo_resposta"] = "cotacao"

            else:
                empresas_vistas[chave_empresa] = dict(
                    empresa,
                    nome=nome,
                )

        # ---------------------------------------------------------
        # Itens
        # ---------------------------------------------------------
        for item in dados.get("itens") or []:

            chave_item = (
                chave(item.get("pi"))
                or chave(item.get("codigo"))
                or chave(item.get("nsn"))
            )

            precos = {
                nome: valor
                for nome, valor
                in (item.get("empresas") or {}).items()
                if nome
            }

            # -----------------------------------------------------
            # Confiança
            # -----------------------------------------------------
            try:
                confianca = float(
                    item.get("confianca", 100)
                )
            except (TypeError, ValueError):
                confianca = 100

            confianca = max(
                0,
                min(100, confianca),
            )

            avisos_item = list(
                item.get("avisos") or []
            )

            # OCR reduz a confiança máxima.
            if veio_de_ocr:
                confianca = min(
                    confianca,
                    70,
                )

                aviso_ocr = (
                    f"valores lidos por OCR local em "
                    f"{origem}: conferir"
                )

                if aviso_ocr not in avisos_item:
                    avisos_item.append(aviso_ocr)

            # -----------------------------------------------------
            # Item já existente na base
            # -----------------------------------------------------
            if chave_item in itens_por_pi:
                alvo = itens_por_pi[chave_item]

                # Preços encontrados no documento
                # são associados ao item existente.
                alvo.setdefault(
                    "empresas",
                    {},
                ).update(precos)

                # Completa campos que a base não possuía.
                for campo in (
                    "nsn",
                    "codigo",
                    "nome_em_portugues",
                    "qtde",
                    "uf",
                ):
                    if (
                        not alvo.get(campo)
                        and item.get(campo)
                    ):
                        alvo[campo] = item[campo]

                # Mantém a menor confiança.
                try:
                    confianca_anterior = float(
                        alvo.get("confianca", 100)
                    )
                except (TypeError, ValueError):
                    confianca_anterior = 100

                alvo["confianca"] = min(
                    confianca_anterior,
                    confianca,
                )

                alvo.setdefault(
                    "avisos",
                    [],
                )

                for aviso in avisos_item:
                    if aviso not in alvo["avisos"]:
                        alvo["avisos"].append(aviso)

            # -----------------------------------------------------
            # PI não existente na base
            # -----------------------------------------------------
            elif tem_base:
                merged["avisos_gerais"].append(
                    f"{origem}: PI "
                    f"'{item.get('pi') or '(vazio)'}' "
                    f"({(item.get('nome_em_portugues') or '')[:60]}) "
                    "não consta do modelo de proposta — "
                    "conferir manualmente"
                )

            # -----------------------------------------------------
            # Não existe base:
            # permite criar o item.
            # -----------------------------------------------------
            elif chave_item:
                novo_item = dict(
                    item,
                    empresas=precos,
                    confianca=confianca,
                    avisos=avisos_item,
                )

                itens_por_pi[chave_item] = novo_item
                ordem.append(chave_item)

        # ---------------------------------------------------------
        # Perguntas
        # ---------------------------------------------------------
        for pergunta in dados.get("perguntas") or []:
            merged["perguntas"].append(
                dict(
                    pergunta,
                    arquivo=origem,
                )
            )

        # ---------------------------------------------------------
        # Avisos gerais
        # ---------------------------------------------------------
        avisos_gerais = (
            dados.get("avisos_gerais") or []
        )

        merged["avisos_gerais"].extend(
            avisos_gerais
        )

    # -------------------------------------------------------------
    # Monta resultado final
    # -------------------------------------------------------------
    merged["empresas"] = list(
        empresas_vistas.values()
    )

    merged["itens"] = [
        itens_por_pi[k]
        for k in ordem
    ]

    # Garante número sequencial para itens
    # que não possuíam número.
    for i, item in enumerate(
        merged["itens"],
        1,
    ):
        if not item.get("item"):
            item["item"] = i

    return merged
