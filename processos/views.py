"""
processos/views.py

Camada de apresentação. As views coordenam o fluxo e delegam o trabalho:

    pacotes.py      recebimento e extração segura dos arquivos enviados
    ai_processor.py leitura dos documentos (determinística ou por IA)
    persistencia.py gravação em banco
    relatorios.py   geração do .xlsx e do .odt
    services.py     normalização e montagem dos resumos de tela
"""

import json
import logging
import os
import tempfile
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .ai_processor import AIProcessor, parse_modelo_proposta
from .models import Processo
from .pacotes import (
    EXTENSOES_MODELO,
    EXTENSOES_RESPOSTA,
    PacoteInvalido,
    contar_emails,
    e_pacote,
    extrair_pacote,
    gravar_upload,
    validar_upload,
)
from .persistencia import MODO_BASE, MODO_COMPLETO, salvar_dados_ai
from .relatorios import (
    avisos_da_extracao,
    gerar_planilha_odt,
    preencher_mapa_comparativo,
    resumo_extracao,
)
from .services import linha_base, montar_resumo

logger = logging.getLogger(__name__)

ITENS_POR_PAGINA = 10
PROCESSOS_POR_PAGINA = 5

ORDENACOES = {
    'antigos': 'id',
    'recentes': '-id',
    'numero': 'numero',
    'maior_valor': '-valor_estimado',
    'menor_valor': 'valor_estimado',
}

MENSAGEM_ERRO_GENERICA = (
    'Não foi possível concluir o processamento. O erro foi registrado no log '
    'do servidor com o número do processo. Tente novamente ou acione o suporte.'
)


# ==================== LISTAGEM ====================

@login_required
def processos(request):
    """Lista os processos do usuário autenticado."""
    consulta = Processo.objects.filter(usuario=request.user)

    busca = request.GET.get('busca')
    data = request.GET.get('data')
    ordem = request.GET.get('ordem')

    if busca:
        for palavra in busca.split():
            consulta = consulta.filter(
                Q(numero__icontains=palavra) | Q(descricao__icontains=palavra)
            )

    hoje = timezone.now().date()
    if data == 'hoje':
        consulta = consulta.filter(data_abertura=hoje)
    elif data == 'mes':
        consulta = consulta.filter(data_abertura__month=hoje.month,
                                   data_abertura__year=hoje.year)
    elif data == 'ano':
        consulta = consulta.filter(data_abertura__year=hoje.year)

    if ordem in ORDENACOES:
        consulta = consulta.order_by(ORDENACOES[ordem])

    pagina = Paginator(consulta, ITENS_POR_PAGINA).get_page(request.GET.get('page'))

    return render(request, 'processos.html', {
        'processos': pagina,
        'busca': busca,
        'ordem': ordem,
        'data': data,
    })

@login_required
def documentos(request):
    """Lista os processos do usuário com os dados consolidados pela IA."""
    numero = (request.GET.get('numero') or '').strip()
    status = (request.GET.get('status') or '').strip()

    consulta = (Processo.objects
                .filter(usuario=request.user)
                .prefetch_related('fornecedores', 'itens__cotacoes__fornecedor'))

    if numero:
        consulta = consulta.filter(numero__icontains=numero)
    if status and status != 'todos':
        consulta = consulta.filter(status__iexact=status)

    paginador = Paginator(consulta, PROCESSOS_POR_PAGINA)
    pagina = paginador.get_page(request.GET.get('page'))

    filtros = request.GET.copy()
    filtros.pop('page', None)

    return render(request, 'documentos.html', {
        'resumos': [montar_resumo(processo) for processo in pagina],
        'pagina': pagina,
        'filtro_numero': numero,
        'filtro_status': status or 'todos',
        'status_choices': Processo.STATUS_CHOICES,
        'querystring': filtros.urlencode(),
        'total_encontrados': paginador.count,
    })


@login_required
def mapas_gerados(request):
    return render(request, 'mapasgerados.html')


# ==================== CRIAÇÃO DO PROCESSO ====================

@login_required
def novo_processo(request):
    """Cria ou complementa um processo, em duas etapas ligadas pelo NÚMERO.

    Etapa 1 - campo "modelo": o Modelo de Proposta (.xls/.xlsx) vira a LINHA
              DE BASE (itens e PI). Lido direto da planilha, sem IA.
    Etapa 2 - campo "file": pacote de respostas (.tgz/.zip) ou documento
              avulso. As cotações são casadas com a linha de base pelo PI.

    Os dois campos são opcionais, mas ao menos um precisa vir. Só o modelo
    deixa o processo 'pendente' aguardando as cotações; os dois juntos rodam
    as duas etapas na mesma requisição.
    """
    if request.method != 'POST':
        return render(request, 'novoprocesso.html')

    formulario = _ler_formulario(request)
    erros, dados = _validar_formulario(formulario)
    if erros:
        return _responder_com_erro(request, formulario, erros)

    try:
        processo, erros = _obter_ou_criar_processo(request, formulario, dados)
    except IntegrityError:
        logger.warning('Conflito ao gravar o processo %s', formulario['numero'])
        return _responder_com_erro(request, formulario, [
            'Não foi possível gravar o processo (número duplicado ou dado '
            'inconsistente). Confira o número e tente de novo.'
        ])

    if erros:
        return _responder_com_erro(request, formulario, erros)

    try:
        concluido, erros = _processar_arquivos(processo, formulario, dados)
    except PacoteInvalido as erro:
        _marcar_erro(processo)
        return _responder_com_erro(request, formulario, [str(erro)])
    except Exception:                                       # noqa: BLE001
        # A mensagem técnica fica no log. Devolver str(exc) à tela expõe
        # caminho de arquivo, resposta da API e configuração do servidor.
        logger.exception('Falha ao processar o processo %s', processo.numero)
        _marcar_erro(processo)
        return _responder_com_erro(request, formulario, [MENSAGEM_ERRO_GENERICA])

    if erros:
        return _responder_com_erro(request, formulario, erros)

    logger.info('Processo %s finalizado (concluido=%s)', processo.numero, concluido)
    return redirect('processos')


def _ler_formulario(request):
    return {
        'numero': (request.POST.get('numero') or '').strip(),
        'descricao': (request.POST.get('descricao') or '').strip(),
        'valor_estimado': (request.POST.get('valor_estimado') or '').strip(),
        'data_abertura': (request.POST.get('data_abertura') or '').strip(),
        'modelo': request.FILES.get('modelo'),
        'arquivo': request.FILES.get('file'),
    }


def _responder_com_erro(request, formulario, erros):
    """Redesenha o formulário preservando o que o usuário já digitou."""
    return render(request, 'novoprocesso.html', {
        'erros': erros,
        'form_numero': formulario['numero'],
        'form_descricao': formulario['descricao'],
        'form_valor_estimado': formulario['valor_estimado'],
        'form_data_abertura': formulario['data_abertura'],
    })


def _validar_formulario(formulario):
    """Valida os campos e converte os tipos. Devolve (erros, dados)."""
    erros = []
    dados = {}

    obrigatorios = ('numero', 'descricao', 'valor_estimado', 'data_abertura')
    if not all(formulario[campo] for campo in obrigatorios):
        erros.append('Todos os campos são obrigatórios!')

    # O formato do número é validado pelo próprio validador do modelo,
    # em _obter_ou_criar_processo, para não haver duas regras divergentes.

    dados['valor_estimado'] = _converter_valor(formulario['valor_estimado'], erros)
    dados['data_abertura'] = _converter_data(formulario['data_abertura'], erros)

    if not formulario['modelo'] and not formulario['arquivo']:
        erros.append('Envie o Modelo de Proposta, o pacote de respostas, ou os dois.')

    erros += validar_upload(formulario['modelo'], 'Modelo de Proposta',
                            EXTENSOES_MODELO)
    erros += validar_upload(formulario['arquivo'], 'Arquivo de respostas',
                            EXTENSOES_RESPOSTA)
    return erros, dados


def _converter_valor(texto, erros):
    """Dinheiro entra como Decimal: float perde centavo em valor de milhão."""
    if not texto:
        return None
    try:
        valor = Decimal(texto.replace('.', '').replace(',', '.')
                        if ',' in texto else texto)
    except (InvalidOperation, ValueError):
        erros.append('Valor estimado deve ser um número.')
        return None

    if valor <= 0:
        erros.append('Valor estimado deve ser maior que zero.')
        return None
    if valor >= Decimal('10') ** 13:
        erros.append('Valor estimado excede o limite do campo.')
        return None
    return valor


def _converter_data(texto, erros):
    if not texto:
        return None
    try:
        return datetime.strptime(texto, '%Y-%m-%d').date()
    except ValueError:
        erros.append('Data de abertura inválida. Use o seletor de data.')
        return None


def _obter_ou_criar_processo(request, formulario, dados):
    """Localiza o processo pelo número ou cria um novo. Devolve (processo, erros)."""
    numero = formulario['numero']
    modelo = formulario['modelo']

    processo = Processo.objects.filter(numero=numero).first()

    if processo is not None:
        erro = _conferir_reaproveitamento(processo, request.user, modelo)
        if erro:
            return processo, [erro]
        processo.status = Processo.STATUS_PROCESSANDO
    else:
        if not modelo:
            return None, [
                'Processo novo começa pelo Modelo de Proposta: é ele que define '
                'os itens e os PI da linha de base.'
            ]
        processo = Processo(
            usuario=request.user,
            numero=numero,
            descricao=formulario['descricao'],
            valor_estimado=dados['valor_estimado'],
            data_abertura=dados['data_abertura'] or date.today(),
            status=Processo.STATUS_PROCESSANDO,
        )
        try:
            # full_clean aplica o validador de formato do número declarado no
            # modelo. Sem esta chamada o validador nunca roda fora do admin.
            processo.full_clean(exclude=['arquivo_processo'])
        except ValidationError as erro:
            return None, [
                mensagem for lista in erro.message_dict.values() for mensagem in lista
            ]

    processo.arquivo_processo = formulario['arquivo'] or modelo
    processo.save()
    return processo, []


def _conferir_reaproveitamento(processo, usuario, modelo):
    """Regras de uso de um número de processo já existente."""
    if processo.usuario_id not in (None, usuario.id):
        return 'Esse número pertence a um processo de outro responsável.'

    if modelo and processo.itens.exists() and processo.fornecedores.exists():
        return ('Esse processo já tem linha de base e respostas processadas. '
                'Para trocar o Modelo de Proposta, exclua o processo antes.')

    if not modelo and not processo.itens.exists():
        return ('Esse processo ainda não tem linha de base. Envie primeiro o '
                'Modelo de Proposta com a coluna NÚMERO DE ESTOQUE (PI).')
    return None


def _marcar_erro(processo):
    """Evita processo preso em 'processando' quando algo falha no meio."""
    if processo is not None and processo.pk:
        processo.status = Processo.STATUS_ERRO
        processo.save(update_fields=['status'])


# ==================== PROCESSAMENTO DOS ARQUIVOS ====================

def _processar_arquivos(processo, formulario, dados):
    """Executa as duas etapas. Devolve (concluido, erros)."""
    contexto = {
        'numero': processo.numero,
        'descricao': processo.descricao,
        'valor_estimado': str(dados['valor_estimado']),
    }
    processador = AIProcessor()

    with tempfile.TemporaryDirectory() as pasta:
        if formulario['modelo']:
            erros = _gravar_linha_base(processo, formulario['modelo'], pasta)
            if erros:
                return False, erros

        if not formulario['arquivo']:
            processo.status = Processo.STATUS_PENDENTE
            processo.save(update_fields=['status'])
            return False, []

        resultados, emails_recebidos = _ler_respostas(
            processo, formulario['arquivo'], pasta, processador, contexto
        )
        dados_ai = processador.merge_results(resultados, linha_base(processo))

    _anexar_trilha_de_extracao(dados_ai, resultados)
    _gravar_json_bruto(processo, dados_ai)
    salvar_dados_ai(processo, dados_ai, emails_recebidos, modo=MODO_COMPLETO)
    _gerar_entregaveis(processo, dados_ai)

    processo.status = Processo.STATUS_CONCLUIDO
    processo.save(update_fields=['status', 'arquivo_gerado_xlsx',
                                 'arquivo_gerado_odt'])
    return True, []


def _gravar_linha_base(processo, modelo, pasta):
    """Etapa 1: lê o Modelo de Proposta e grava os itens/PI."""
    base = parse_modelo_proposta(gravar_upload(modelo, pasta))

    if not base or not any(item.get('pi') for item in base['itens']):
        with transaction.atomic():
            # Processo recém-criado sem linha de base só travaria o número.
            if not processo.itens.exists() and not processo.fornecedores.exists():
                processo.delete()
        return ['Não consegui ler o Modelo de Proposta. Confira se é a planilha '
                'enviada às empresas (com o cabeçalho ITEM / NÚMERO DE ESTOQUE / '
                'NOMENCLATURA) e se a coluna NÚMERO DE ESTOQUE (PI) está preenchida.']

    salvar_dados_ai(processo, base, modo=MODO_BASE)
    return []


def _ler_respostas(processo, arquivo, pasta, processador, contexto):
    """Etapa 2: lê o pacote ou o documento avulso. Devolve (resultados, e-mails)."""
    base = linha_base(processo)
    caminho = gravar_upload(arquivo, pasta)

    if e_pacote(arquivo.name):
        destino = os.path.join(pasta, 'extraido')
        extrair_pacote(caminho, destino)
        emails_recebidos = contar_emails(destino)
        resultados = processador.process_directory(destino, contexto, base)
        return resultados, emails_recebidos

    resultado = processador.process_file(caminho, contexto, base)
    emails_recebidos = 1 if arquivo.name.lower().endswith(('.eml', '.msg')) else 0
    return [{'filename': arquivo.name, 'ai_result': resultado}], emails_recebidos


def _anexar_trilha_de_extracao(dados_ai, resultados):
    """Registra de onde veio cada dado e os avisos que dependem da rota."""
    extracao = resumo_extracao(resultados)
    dados_ai['extracao'] = extracao
    dados_ai.setdefault('avisos_gerais', []).extend(avisos_da_extracao(extracao))


def _gravar_json_bruto(processo, dados_ai):
    """Mantém o JSON em disco como registro bruto e auditável da extração."""
    caminho = os.path.join(settings.MEDIA_ROOT, 'processos', 'gerados',
                           f'dados_ai_{processo.numero_slug}.json')
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, 'w', encoding='utf-8') as saida:
        json.dump(dados_ai, saida, ensure_ascii=False, indent=2)


def _gerar_entregaveis(processo, dados_ai):
    """Gera o mapa e o relatório. A falha de um não impede a gravação do outro."""
    try:
        caminho = preencher_mapa_comparativo(processo, dados_ai)
        processo.arquivo_gerado_xlsx = f'processos/gerados/{os.path.basename(caminho)}'
    except Exception:                                       # noqa: BLE001
        logger.exception('Falha ao gerar o XLSX do processo %s', processo.numero)

    try:
        caminho = gerar_planilha_odt(processo, dados_ai)
        processo.arquivo_gerado_odt = f'processos/gerados/{os.path.basename(caminho)}'
    except Exception:                                       # noqa: BLE001
        logger.exception('Falha ao gerar o ODT do processo %s', processo.numero)


# ==================== DOWNLOAD ====================

@login_required
def download_arquivo(request, tipo, processo_id):
    """Entrega um arquivo do processo ao responsável por ele.

    A conferência de dono é obrigatória: sem ela, trocar o id na URL dá acesso
    às cotações de qualquer processo do sistema, inclusive de outro setor.
    """
    processo = get_object_or_404(Processo, id=processo_id)
    if processo.usuario_id not in (None, request.user.id) and not request.user.is_staff:
        logger.warning('Usuário %s tentou baixar o processo %s de outro responsável',
                        request.user, processo.numero)
        raise Http404('Processo não encontrado')

    caminho = _caminho_do_arquivo(processo, tipo)
    if not caminho:
        raise Http404('Arquivo não disponível para este processo')

    return FileResponse(open(caminho, 'rb'), as_attachment=True,
                        filename=os.path.basename(caminho))


def _caminho_do_arquivo(processo, tipo):
    """Resolve o caminho e confirma que ele está dentro do MEDIA_ROOT."""
    relativos = {
        'xlsx': str(processo.arquivo_gerado_xlsx or ''),
        'odt': str(processo.arquivo_gerado_odt or ''),
        'json': os.path.join('processos', 'gerados',
                            f'dados_ai_{processo.numero_slug}.json'),
        'original': str(processo.arquivo_processo or ''),
    }

    relativo = relativos.get(tipo)
    if not relativo:
        return None

    raiz = os.path.realpath(settings.MEDIA_ROOT)
    caminho = os.path.realpath(os.path.join(raiz, relativo))

    # Barreira contra travessia de diretório: o nome do arquivo deriva de
    # campos gravados no banco, e nenhum deles pode apontar para fora da mídia.
    if os.path.commonpath([raiz, caminho]) != raiz:
        logger.error('Caminho fora do MEDIA_ROOT recusado: %s', caminho)
        return None

    return caminho if os.path.isfile(caminho) else None


# ==================== VISUALIZAR ====================


@login_required
def visualizar_processo(request, numero_slug):
    processo = get_object_or_404(Processo, numero_slug=numero_slug)
    # monte o contexto com os dados que deseja mostrar
    return render(request, 'visualizar_processo.html', {'processo': processo})

    
# ==================== EDITAR ====================


@login_required
def editar_processo(request, numero_slug):
    processo = get_object_or_404(Processo, numero_slug=numero_slug, usuario=request.user)

    if request.method == 'POST':
        # Processa o formulário de edição
        data_abertura = request.POST.get('data_abertura')
        descricao = request.POST.get('descricao', '').strip()
        valor_estimado = request.POST.get('valor_estimado', '').strip()

        erros = []
        if data_abertura:
            try:
                processo.data_abertura = datetime.strptime(data_abertura, '%Y-%m-%d').date()
            except ValueError:
                erros.append('Data de abertura inválida.')
        if descricao:
            processo.descricao = descricao
        if valor_estimado:
            try:
                processo.valor_estimado = Decimal(valor_estimado.replace(',', '.'))
            except (InvalidOperation, ValueError):
                erros.append('Valor estimado inválido.')

        # Se houver novo arquivo (substituição), processar novamente
        novo_arquivo = request.FILES.get('file')
        if novo_arquivo:
            # Código para reprocessar com o novo arquivo
            # (recomendo delegar para uma função separada, mas por simplicidade farei aqui)
            try:
                # Salva o arquivo, chama o processador, atualiza o processo
                # (pode aproveitar parte da lógica de novo_processo)
                pass
            except Exception as e:
                erros.append(f'Erro ao processar novo arquivo: {e}')

        if not erros:
            processo.save()
            return redirect('visualizar_processo', numero_slug=processo.numero_slug)

        # Se houve erros, renderiza o template com os erros
        return render(request, 'editar_processo.html', {
            'processo': processo,
            'erros': erros,
        })

    # GET: exibe o formulário preenchido
    return render(request, 'editar_processo.html', {'processo': processo})