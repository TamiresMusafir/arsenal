import os
import shutil
import sqlite3
import tempfile
from datetime import datetime

from django.conf import settings
from django.contrib import messages
from django.db import connections
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required

from usuarios.models import Perfil

MAGIC_SQLITE = b"SQLite format 3\x00"


# Create your views here.

def configuracoes(request):
    return render(request, "configuracoes.html")


def conta(request):
    return render(request, "conta.html")

@login_required
def preferencias(request):
    return render(request, "preferencias.html")


def _caminho_banco():
    return str(settings.DATABASES["default"]["NAME"])

@login_required
def editar_conta(request):
    usuario = request.user
    perfil, created = Perfil.objects.get_or_create(usuario=usuario)

    if request.method == "POST":
        usuario.first_name = request.POST.get("nome")
        usuario.last_name = request.POST.get("sobrenome")
        usuario.email = request.POST.get("email")
        usuario.save()

        if request.FILES.get("foto"):
            if perfil.foto and os.path.exists(perfil.foto.path):
                os.remove(perfil.foto.path)

            perfil.foto = request.FILES["foto"]
            perfil.save()

        return redirect("conta")

    return render(request, "editarconta.html", {
        "usuario": usuario,
        "perfil": perfil
    })



def backup_download(request):
    """Gera cópia consistente do db.sqlite3 e devolve como download."""
    origem = _caminho_banco()
    if not os.path.exists(origem):
        raise Http404("Banco de dados não localizado.")

    tmp = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
    tmp.close()
    try:
        # API de backup do SQLite: seguro mesmo com escritas em andamento (WAL)
        src = sqlite3.connect(f"file:{origem}?mode=ro", uri=True)
        dst = sqlite3.connect(tmp.name)
        with dst:
            src.backup(dst)
        dst.close()
        src.close()

        with open(tmp.name, "rb") as fh:
            conteudo = fh.read()
    finally:
        os.unlink(tmp.name)

    nome = f"arsenal_backup_{datetime.now():%Y%m%d_%H%M%S}.sqlite3"
    resposta = HttpResponse(conteudo, content_type="application/vnd.sqlite3")
    resposta["Content-Disposition"] = f'attachment; filename="{nome}"'
    resposta["Content-Length"] = len(conteudo)
    return resposta


@require_POST
def backup_restore(request):
    """Valida e substitui o db.sqlite3 pelo arquivo enviado."""
    enviado = request.FILES.get("arquivo")
    if not enviado:
        messages.error(request, "Selecione um arquivo de backup.")
        return redirect("configuracoes")

    tmp = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
    try:
        for pedaco in enviado.chunks():
            tmp.write(pedaco)
        tmp.close()

        # 1) assinatura do formato
        with open(tmp.name, "rb") as fh:
            if fh.read(16) != MAGIC_SQLITE:
                messages.error(request, "O arquivo enviado não é um banco SQLite válido.")
                return redirect("configuracoes")

        # 2) integridade e aderência ao schema do Django
        con = sqlite3.connect(f"file:{tmp.name}?mode=ro", uri=True)
        try:
            if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                messages.error(request, "O backup está corrompido (falha na verificação de integridade).")
                return redirect("configuracoes")
            if not con.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='django_migrations'"
            ).fetchone():
                messages.error(request, "O arquivo não corresponde a um banco do Arsenal.")
                return redirect("configuracoes")
        finally:
            con.close()

        # 3) substituição, preservando o banco atual
        destino = _caminho_banco()
        marca = datetime.now().strftime("%Y%m%d_%H%M%S")
        connections.close_all()

        if os.path.exists(destino):
            shutil.copy2(destino, f"{destino}.pre_restauracao_{marca}")
        shutil.copy2(tmp.name, destino)

        # descarta journal/WAL remanescente do banco anterior
        for sufixo in ("-wal", "-shm", "-journal"):
            residuo = destino + sufixo
            if os.path.exists(residuo):
                os.remove(residuo)
    finally:
        if os.path.exists(tmp.name):
            os.unlink(tmp.name)

    messages.success(
        request,
        f"Backup restaurado com sucesso. O banco anterior foi preservado como "
        f"db.sqlite3.pre_restauracao_{marca}.",
    )
    return redirect("configuracoes")
