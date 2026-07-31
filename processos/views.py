from django.shortcuts import render, redirect
from django.utils import timezone
from .models import Processo
from django.db.models import Q
from django.core.paginator import Paginator
from django.http import HttpResponse, FileResponse
from django.conf import settings
import re
import os
import zipfile
import tempfile
import json
from datetime import datetime
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter
from .ai_processor import AIProcessor
from django.db import IntegrityError
# >>> NOVO: dois imports
from .services import montar_resumo
from .persistencia import salvar_dados_ai
from django.contrib.auth.decorators import login_required

# ==================== VIEWS PRINCIPAIS ====================

@login_required
def processos(request):
    processos = Processo.objects.filter(usuario=request.user)
    ordem = request.GET.get("ordem")
    data = request.GET.get("data")
    busca = request.GET.get("busca")

    if busca:
        palavras = busca.split()
        for palavra in palavras:
            processos = processos.filter(Q(numero__icontains=palavra) | Q(descricao__icontains=palavra))

    hoje = timezone.now().date()
    if data == "hoje":
        processos = processos.filter(data_abertura=hoje)
    elif data == "mes":
        processos = processos.filter(data_abertura__month=hoje.month, data_abertura__year=hoje.year)
    elif data == "ano":
        processos = processos.filter(data_abertura__year=hoje.year)

    if ordem == "antigos":
        processos = processos.order_by("id")
    elif ordem == "numero":
        processos = processos.order_by("numero")
    elif ordem == "recentes":
        processos = processos.order_by("-id")
    elif ordem == "maior_valor":
        processos = processos.order_by("-valor_estimado")
    elif ordem == "menor_valor":
        processos = processos.order_by("valor_estimado")

    paginator = Paginator(processos, 10)
    page = request.GET.get("page")
    processos = paginator.get_page(page)

    return render(
        request,
        "processos.html",
        {
            "processos": processos,
            "busca": busca,
            "ordem": ordem,
            "data": data,
        }
    )

# ==================== FUNÇÕES DE PROCESSAMENTO ====================

def contar_emails(diretorio):
    """Conta os .eml/.msg extraídos do pacote (respostas dos fornecedores)."""
    total = 0
    for raiz, _, arquivos in os.walk(diretorio):
        total += sum(1 for nome in arquivos if nome.lower().endswith(('.eml', '.msg')))
    return total


def preencher_mapa_comparativo(processo, dados_ai):
    """Preenche o modelo Mapa_Comparativo_Base.xlsx com os dados extraídos pela IA"""
    try:
        template_path = os.path.join(settings.BASE_DIR, 'static-assets', 'modelos', 'Mapa_Comparativo_Base.xlsx')

        if os.path.exists(template_path):
            wb = openpyxl.load_workbook(template_path)
            ws = wb.active
        else:
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "MAPA COMPARATIVO DO PROCESSO"

        # Estilos
        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        header_font = Font(bold=True, color="FFFFFF", size=10)
        border = Border(left=Side(style='thin'), right=Side(style='thin'),
                        top=Side(style='thin'), bottom=Side(style='thin'))
        center = Alignment(horizontal='center', vertical='center', wrap_text=True)

        # Cabeçalhos (linha 3 do template)
        headers = ['ITEM', 'PI', 'NOME EM PORTUGUÊS', 'QTDE', 'UF', 'PAINEL DE PREÇO']
        empresas = dados_ai.get('empresas', [])
        for idx, empresa in enumerate(empresas[:20], 1):
            headers.append(f'EMPRESA{idx}')
        headers.extend(['VALOR UNITARIO ESTIMADO', 'VALOR TOTAL'])

        # Escreve cabeçalhos
        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=3, column=col, value=header)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = center
            cell.border = border

        # Preenche dados
        itens = dados_ai.get('itens', [])
        current_row = 4

        for item_idx, item in enumerate(itens, 1):
            row = current_row + item_idx - 1

            # Colunas A-F: dados básicos
            ws.cell(row=row, column=1, value=item.get('item', item_idx))
            ws.cell(row=row, column=2, value=item.get('pi', ''))
            ws.cell(row=row, column=3, value=item.get('nome_em_portugues', ''))
            ws.cell(row=row, column=4, value=item.get('qtde', ''))
            ws.cell(row=row, column=5, value=item.get('uf', ''))
            ws.cell(row=row, column=6, value=item.get('painel_preco', ''))

            # Colunas G-Z: empresas
            empresas_data = item.get('empresas', {})
            for emp_idx in range(1, 21):
                col = 6 + emp_idx
                key = f'empresa{emp_idx}'
                ws.cell(row=row, column=col, value=empresas_data.get(key, ''))
                ws.cell(row=row, column=col).alignment = center

            # Colunas AA-AB: valores
            ws.cell(row=row, column=27, value=item.get('valor_unitario_estimado', ''))
            ws.cell(row=row, column=28, value=item.get('valor_total', ''))

            # Aplica bordas
            for col in range(1, 29):
                ws.cell(row=row, column=col).border = border

        # Ajusta largura das colunas
        for col in range(1, 29):
            col_letter = get_column_letter(col)
            if col <= 6 or col >= 27:
                ws.column_dimensions[col_letter].width = 20
            else:
                ws.column_dimensions[col_letter].width = 12

        # Salva
        filename = f"mapa_comparativo_{processo.numero_slug}.xlsx"   # >>> ALTERADO: usa a property
        filepath = os.path.join(settings.MEDIA_ROOT, 'processos', 'gerados', filename)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        wb.save(filepath)
        return filepath

    except Exception as e:
        print(f"Erro ao preencher mapa: {e}")
        raise


def gerar_planilha_odt(processo, dados_ai):
    """Gera arquivo ODT"""
    try:
        from odf.opendocument import OpenDocumentText
        from odf.text import P, H

        doc = OpenDocumentText()

        # Título
        doc.text.addElement(H(outlinelevel=1, text=f"Mapa Comparativo - Processo {processo.numero}"))

        # Informações
        doc.text.addElement(H(outlinelevel=2, text="Informações do Processo"))
        doc.text.addElement(P(text=f"Número: {processo.numero}"))
        doc.text.addElement(P(text=f"Descrição: {processo.descricao}"))
        doc.text.addElement(P(text=f"Valor Estimado: R$ {processo.valor_estimado:.2f}"))
        doc.text.addElement(P(text=f"Data: {processo.data_abertura.strftime('%d/%m/%Y')}"))
        doc.text.addElement(P(text=""))

        # Empresas
        empresas = dados_ai.get('empresas', [])
        if empresas:
            doc.text.addElement(H(outlinelevel=2, text="Empresas Participantes"))
            for emp in empresas:
                doc.text.addElement(P(text=f"- {emp.get('nome', 'N/A')}"))
                if emp.get('cnpj'):
                    doc.text.addElement(P(text=f"  CNPJ: {emp.get('cnpj')}"))
                if emp.get('valor_global'):
                    doc.text.addElement(P(text=f"  Valor: {emp.get('valor_global')}"))
                doc.text.addElement(P(text=""))

        # Itens
        itens = dados_ai.get('itens', [])
        if itens:
            doc.text.addElement(H(outlinelevel=2, text="Itens do Processo"))
            for item in itens:
                doc.text.addElement(P(text=f"Item {item.get('item', '')}: {item.get('nome_em_portugues', '')}"))
                doc.text.addElement(P(text=f"  Quantidade: {item.get('qtde', '')} {item.get('uf', '')}"))
                if item.get('valor_unitario_estimado'):
                    doc.text.addElement(P(text=f"  Valor Unitário: {item.get('valor_unitario_estimado')}"))
                if item.get('valor_total'):
                    doc.text.addElement(P(text=f"  Valor Total: {item.get('valor_total')}"))
                # Empresas do item
                empresas_data = item.get('empresas', {})
                if empresas_data:
                    doc.text.addElement(P(text="  Cotações:"))
                    for key, value in empresas_data.items():
                        if value:
                            doc.text.addElement(P(text=f"    {key}: {value}"))
                doc.text.addElement(P(text=""))

        # Salva
        filename = f"mapa_comparativo_{processo.numero_slug}.odt"   # >>> ALTERADO: usa a property
        filepath = os.path.join(settings.MEDIA_ROOT, 'processos', 'gerados', filename)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        doc.save(filepath)
        return filepath

    except Exception as e:
        print(f"Erro ao gerar ODT: {e}")
        raise


# ==================== VIEWS DE CRIAÇÃO E DOWNLOAD ====================

def novo_processo(request):
    if request.method == 'POST':
        numero = request.POST.get("numero")
        descricao = request.POST.get("descricao")
        valor_estimado = request.POST.get("valor_estimado")
        data_abertura = request.POST.get("data_abertura")
        arquivo = request.FILES.get("file")

        erros = []

        # Validações
        if not numero or not descricao or not valor_estimado or not data_abertura:
            erros.append("Todos os campos são obrigatórios!")

        # >>> ALTERADO: sem o "if numero", campo vazio estourava TypeError no re.match
        if numero and not re.match(r'^[0-9./-]+$', numero):
            erros.append("Número deve conter apenas números, /, . e -")

        try:
            valor_estimado = float(valor_estimado)
            if valor_estimado < 0:
                erros.append("Valor estimado deve ser maior que zero.")
        except (TypeError, ValueError):   # >>> ALTERADO: float(None) levanta TypeError, não ValueError
            erros.append("Valor estimado deve ser um número.")

        if not arquivo:
            erros.append("É necessário enviar um arquivo!")

        if arquivo and arquivo.size > 50 * 1024 * 1024:
            erros.append("Arquivo muito grande. Máximo 50MB.")

        if erros:
            return render(request, "novoprocesso.html", {"erros": erros})

        try:
            # Cria o processo
            processo = Processo.objects.create(
                usuario=request.user,
                numero=numero,
                descricao=descricao,
                valor_estimado=valor_estimado,
                data_abertura=data_abertura,
                status='processando'
            )
            processo.arquivo_processo = arquivo
            processo.save()

            # Processa com IA
            contexto = {
                'numero': numero,
                'descricao': descricao,
                'valor_estimado': str(valor_estimado)
            }

            ai_processor = AIProcessor()
            emails_recebidos = 0   # >>> NOVO

            # Processa o arquivo
            with tempfile.TemporaryDirectory() as tmpdir:
                file_path = os.path.join(tmpdir, arquivo.name)
                with open(file_path, 'wb+') as f:
                    for chunk in arquivo.chunks():
                        f.write(chunk)

                # Verifica se é compactado
                if arquivo.name.lower().endswith(('.zip', '.tgz', '.tar.gz', '.tar')):
                    extract_dir = os.path.join(tmpdir, 'extracted')
                    os.makedirs(extract_dir, exist_ok=True)

                    if file_path.endswith('.zip'):
                        with zipfile.ZipFile(file_path, 'r') as zip_ref:
                            zip_ref.extractall(extract_dir)
                    else:
                        import tarfile
                        mode = 'r:gz' if file_path.endswith(('.tgz', '.tar.gz')) else 'r'
                        with tarfile.open(file_path, mode) as tar_ref:
                            tar_ref.extractall(extract_dir)

                    emails_recebidos = contar_emails(extract_dir)   # >>> NOVO
                    results = ai_processor.process_directory(extract_dir, contexto)
                    dados_ai = ai_processor.merge_results(results)
                else:
                    file_data = ai_processor.extract_text_from_file(file_path)
                    result = ai_processor.process_with_ai(file_data['content'], contexto)
                    dados_ai = result.get('data', {})
                    if isinstance(dados_ai, str):
                        try:
                            dados_ai = json.loads(dados_ai)
                        except:
                            dados_ai = {'conteudo': dados_ai}

            # Salva dados da IA (JSON bruto, para auditoria)
            json_path = os.path.join(settings.MEDIA_ROOT, 'processos', 'gerados',
                                     f'dados_ai_{processo.numero_slug}.json')
            os.makedirs(os.path.dirname(json_path), exist_ok=True)
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(dados_ai, f, ensure_ascii=False, indent=2)

            # >>> NOVO: grava os mesmos dados no SQLite (Fornecedor / Item / Cotacao)
            salvar_dados_ai(processo, dados_ai, emails_recebidos)

            # Gera arquivos
            xlsx_path = preencher_mapa_comparativo(processo, dados_ai)
            if xlsx_path:
                processo.arquivo_gerado_xlsx = f'processos/gerados/{os.path.basename(xlsx_path)}'

            odt_path = gerar_planilha_odt(processo, dados_ai)
            if odt_path:
                processo.arquivo_gerado_odt = f'processos/gerados/{os.path.basename(odt_path)}'

            processo.status = 'concluido'
            processo.save()

            return redirect("processos")

        except IntegrityError:
            return render(
                request,
                "novoprocesso.html",
                {
                    "erros": [
                        "Já existe um processo cadastrado com esse número."
                    ]
                }
            )

        except Exception as e:
            return render(
                request,
                "novoprocesso.html",
                {
                    "erros": [
                        f"Erro ao processar processo: {str(e)}"
                    ]
                }
            )

    return render(request, "novoprocesso.html")


# >>> SUBSTITUÍDA: era "return render(request, 'documentos.html')"
def documentos(request):
    """Lista os processos com os dados consolidados pela IA."""
    numero = (request.GET.get("numero") or "").strip()
    status = (request.GET.get("status") or "").strip()

    consulta = Processo.objects.all()

    if numero:
        consulta = consulta.filter(numero__icontains=numero)
    if status and status != "todos":
        consulta = consulta.filter(status__iexact=status)

    paginator = Paginator(consulta, 5)
    pagina = paginator.get_page(request.GET.get("page"))

    # mantém os filtros ao trocar de página
    filtros = request.GET.copy()
    filtros.pop("page", None)

    return render(
        request,
        "documentos.html",
        {
            "resumos": [montar_resumo(processo) for processo in pagina],
            "pagina": pagina,
            "filtro_numero": numero,
            "filtro_status": status or "todos",
            "status_choices": Processo.STATUS_CHOICES,
            "querystring": filtros.urlencode(),
            "total_encontrados": paginator.count,
        }
    )


def mapas_gerados(request):
    return render(request, "mapasgerados.html")


# >>> ALTERADA: aceita também 'original' (o pacote de e-mails enviado)
def download_arquivo(request, tipo, processo_id):
    try:
        processo = Processo.objects.get(id=processo_id)
    except Processo.DoesNotExist:
        return HttpResponse("Processo não encontrado", status=404)

    caminhos = {
        'xlsx': os.path.join(settings.MEDIA_ROOT, str(processo.arquivo_gerado_xlsx)) if processo.arquivo_gerado_xlsx else None,
        'odt': os.path.join(settings.MEDIA_ROOT, str(processo.arquivo_gerado_odt)) if processo.arquivo_gerado_odt else None,
        'json': os.path.join(settings.MEDIA_ROOT, 'processos', 'gerados', f'dados_ai_{processo.numero_slug}.json'),
        'original': os.path.join(settings.MEDIA_ROOT, str(processo.arquivo_processo)) if processo.arquivo_processo else None,
    }

    caminho = caminhos.get(tipo)
    if caminho and os.path.exists(caminho):
        return FileResponse(open(caminho, 'rb'),
                            as_attachment=True,
                            filename=os.path.basename(caminho))

    return HttpResponse("Arquivo não disponível para este processo", status=404)
