"""
processos/pacotes.py

Recebimento de arquivos enviados pelo usuário: validação do upload e
extração de pacotes compactados.

Este módulo existe por um motivo específico. `ZipFile.extractall()` e
`TarFile.extractall()` gravam onde o pacote mandar, inclusive fora do
diretório de destino, quando o pacote contém entradas com `..` ou caminho
absoluto — é o ataque conhecido como Zip Slip. Um .tgz de fornecedor é um
arquivo de origem externa: chega por e-mail, ninguém audita o conteúdo.
Aqui todas as entradas são validadas antes de qualquer escrita em disco.
"""

import logging
import os
import tarfile
import zipfile
from pathlib import Path

logger = logging.getLogger(__name__)

# Formatos aceitos em cada campo do formulário.
EXTENSOES_MODELO = frozenset({'.xls', '.xlsx', '.xlsm'})
EXTENSOES_PACOTE = frozenset({'.zip', '.tgz', '.tar', '.tar.gz'})
EXTENSOES_DOCUMENTO = frozenset({
    '.pdf', '.eml', '.msg', '.docx', '.doc', '.odt', '.ods',
    '.xls', '.xlsx', '.xlsm', '.txt', '.csv',
    '.png', '.jpg', '.jpeg', '.webp', '.tif', '.tiff', '.bmp', '.gif',
})
EXTENSOES_RESPOSTA = EXTENSOES_PACOTE | EXTENSOES_DOCUMENTO

TAMANHO_MAXIMO_UPLOAD = 50 * 1024 * 1024        # 50 MB por arquivo enviado
TAMANHO_MAXIMO_EXTRAIDO = 500 * 1024 * 1024     # 500 MB somados após descompactar
RAZAO_MAXIMA_COMPRESSAO = 200                   # trava de zip bomb
MAXIMO_DE_ENTRADAS = 5000


class PacoteInvalido(Exception):
    """Erro de conteúdo do pacote, seguro para exibir ao usuário."""


# ==================== VALIDAÇÃO DO UPLOAD ====================

def extensao_de(nome):
    """Extensão em minúsculas, tratando o duplo sufixo .tar.gz."""
    nome = (nome or '').lower()
    if nome.endswith('.tar.gz'):
        return '.tar.gz'
    return os.path.splitext(nome)[1]


def validar_upload(arquivo, rotulo, extensoes_aceitas):
    """Valida um arquivo enviado. Devolve a lista de erros encontrados."""
    if arquivo is None:
        return []

    erros = []
    if arquivo.size > TAMANHO_MAXIMO_UPLOAD:
        limite = TAMANHO_MAXIMO_UPLOAD // (1024 * 1024)
        erros.append(f'{rotulo}: arquivo muito grande. Máximo {limite} MB.')

    extensao = extensao_de(arquivo.name)
    if extensao not in extensoes_aceitas:
        aceitas = ', '.join(sorted(extensoes_aceitas))
        erros.append(f'{rotulo}: formato {extensao or "desconhecido"} não aceito. '
                     f'Use um destes: {aceitas}.')
    return erros


def e_pacote(nome):
    return extensao_de(nome) in EXTENSOES_PACOTE


def gravar_upload(arquivo, destino):
    """Grava o upload em `destino` usando apenas o nome-base do arquivo.

    O Django já reduz `name` ao nome-base, mas a garantia é repetida aqui
    porque esta função também é usada com nomes vindos de outras origens.
    """
    nome_seguro = os.path.basename(arquivo.name) or 'upload.bin'
    caminho = os.path.join(destino, nome_seguro)

    with open(caminho, 'wb+') as saida:
        for pedaco in arquivo.chunks():
            saida.write(pedaco)
    return caminho


# ==================== EXTRAÇÃO SEGURA ====================

def extrair_pacote(caminho_pacote, destino):
    """Extrai .zip/.tar/.tgz validando cada entrada antes de gravar.

    Raises:
        PacoteInvalido: pacote corrompido, grande demais ou com entrada
            que tenta escapar do diretório de destino.
    """
    os.makedirs(destino, exist_ok=True)
    extensao = extensao_de(caminho_pacote)

    try:
        if extensao == '.zip':
            _extrair_zip(caminho_pacote, destino)
        else:
            _extrair_tar(caminho_pacote, destino, extensao)
    except (zipfile.BadZipFile, tarfile.TarError, EOFError) as erro:
        logger.warning('Pacote ilegível %s: %s', caminho_pacote, erro)
        raise PacoteInvalido(
            'O pacote enviado está corrompido ou não é um arquivo compactado válido.'
        ) from erro


def _extrair_zip(caminho_pacote, destino):
    with zipfile.ZipFile(caminho_pacote) as pacote:
        entradas = pacote.infolist()
        _conferir_quantidade(len(entradas))

        total = 0
        for entrada in entradas:
            if entrada.is_dir():
                continue

            _conferir_caminho(entrada.filename, destino)
            total += entrada.file_size
            _conferir_tamanho(total)
            _conferir_razao_compressao(entrada.file_size, entrada.compress_size,
                                       entrada.filename)

            alvo = _caminho_final(entrada.filename, destino)
            os.makedirs(os.path.dirname(alvo), exist_ok=True)
            with pacote.open(entrada) as origem, open(alvo, 'wb') as saida:
                saida.write(origem.read())


def _extrair_tar(caminho_pacote, destino, extensao):
    modo = 'r:gz' if extensao in ('.tgz', '.tar.gz') else 'r:*'

    with tarfile.open(caminho_pacote, modo) as pacote:
        total = 0
        quantidade = 0

        for entrada in pacote:
            quantidade += 1
            _conferir_quantidade(quantidade)

            if entrada.isdir():
                continue
            if not entrada.isfile():
                # Link simbólico, hard link, FIFO ou dispositivo. Um symlink
                # apontando para /etc/passwd faria o processador de IA ler e
                # enviar o arquivo do servidor para fora.
                logger.warning('Entrada não regular ignorada: %s', entrada.name)
                continue

            _conferir_caminho(entrada.name, destino)
            total += entrada.size
            _conferir_tamanho(total)

            origem = pacote.extractfile(entrada)
            if origem is None:
                continue

            alvo = _caminho_final(entrada.name, destino)
            os.makedirs(os.path.dirname(alvo), exist_ok=True)
            with origem, open(alvo, 'wb') as saida:
                saida.write(origem.read())


def _caminho_final(nome, destino):
    return os.path.join(destino, os.path.normpath(nome).lstrip(os.sep))


def _conferir_caminho(nome, destino):
    """Garante que a entrada permanece dentro do diretório de destino."""
    if os.path.isabs(nome) or nome.startswith(('/', '\\')):
        raise PacoteInvalido(f'O pacote contém caminho absoluto: {nome!r}.')

    alvo = Path(_caminho_final(nome, destino)).resolve()
    raiz = Path(destino).resolve()
    if raiz not in alvo.parents and alvo != raiz:
        raise PacoteInvalido(
            f'O pacote tenta gravar fora da pasta de trabalho: {nome!r}.'
        )


def _conferir_quantidade(quantidade):
    if quantidade > MAXIMO_DE_ENTRADAS:
        raise PacoteInvalido(
            f'O pacote tem mais de {MAXIMO_DE_ENTRADAS} arquivos. '
            f'Divida o envio em pacotes menores.'
        )


def _conferir_tamanho(total):
    if total > TAMANHO_MAXIMO_EXTRAIDO:
        limite = TAMANHO_MAXIMO_EXTRAIDO // (1024 * 1024)
        raise PacoteInvalido(
            f'O conteúdo descompactado passa de {limite} MB. '
            f'Divida o envio em pacotes menores.'
        )


def _conferir_razao_compressao(tamanho_final, tamanho_comprimido, nome):
    """Detecta zip bomb: arquivo pequeno que estoura o disco ao abrir."""
    if tamanho_comprimido <= 0:
        return
    if tamanho_final / tamanho_comprimido > RAZAO_MAXIMA_COMPRESSAO:
        raise PacoteInvalido(
            f'A entrada {nome!r} tem taxa de compressão anormal e foi recusada.'
        )


# ==================== INSPEÇÃO DO CONTEÚDO ====================

def contar_emails(diretorio):
    """Conta os .eml/.msg extraídos (respostas dos fornecedores)."""
    total = 0
    for _raiz, _dirs, arquivos in os.walk(diretorio):
        total += sum(1 for nome in arquivos
                     if nome.lower().endswith(('.eml', '.msg')))
    return total
