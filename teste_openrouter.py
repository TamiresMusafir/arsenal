#!/usr/bin/env python3
"""
teste_openrouter.py — coloque na raiz do projeto (ao lado do manage.py).

Valida a conexão ANTES de mexer no Django. Roda em três etapas, da mais
barata para a mais cara, para você não descobrir problema de chave depois
de já ter gasto OCR.

    export OPENROUTER_API_KEY="sk-or-v1-..."

    python teste_openrouter.py                        # etapa 1: só a chave
    python teste_openrouter.py --dry caminho/arq.pdf  # etapa 2: monta o payload, não envia
    python teste_openrouter.py caminho/arq.pdf        # etapa 3: envia de verdade
"""
import argparse
import json
import os
import sys

import django

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1/chat/completions"
from django.conf import settings

# --- configura o Django mínimo, sem carregar o projeto inteiro -----------
if not settings.configured:
    settings.configure(
        OPENROUTER_API_KEY=os.environ.get("OPENROUTER_API_KEY", ""),
        OPENROUTER_BASE_URL="https://openrouter.ai/api/v1",
        OPENROUTER_MODEL=os.environ.get("OPENROUTER_MODEL", "google/gemini-3-flash-preview"),
        OPENROUTER_PDF_ENGINE_SCAN=os.environ.get("OPENROUTER_PDF_ENGINE_SCAN", "native"),
        OPENROUTER_TIMEOUT=300,
        INSTALLED_APPS=[], DATABASES={},
    )
    django.setup()

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "processos"))
from ai_processor import AIProcessor  # noqa: E402

VERDE, VERMELHO, AMARELO, FIM = "\033[92m", "\033[91m", "\033[93m", "\033[0m"
CTX = {"numero": "TESTE-001/2026", "descricao": "Validação da API",
       "valor_estimado": "0.00"}


def etapa_1_chave():
    """Ping barato: confere chave, crédito e se o modelo existe."""
    import requests
    chave = settings.OPENROUTER_API_KEY
    if not chave:
        print(f"{VERMELHO}✗ OPENROUTER_API_KEY não está no ambiente.{FIM}")
        print('  export OPENROUTER_API_KEY="sk-or-v1-..."')
        return False
    print(f"  chave  : {chave[:12]}…{chave[-4:]}")

    r = requests.get("https://openrouter.ai/api/v1/auth/key",
                     headers={"Authorization": f"Bearer {chave}"}, timeout=30)
    if r.status_code != 200:
        print(f"{VERMELHO}✗ chave rejeitada (HTTP {r.status_code}): {r.text[:200]}{FIM}")
        return False

    info = r.json().get("data", {})
    limite = info.get("limit")
    print(f"{VERDE}✓ chave válida{FIM}   uso: US$ {info.get('usage', 0):.4f}"
          f"   limite: {'sem limite' if limite is None else f'US$ {limite}'}")

    r = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {chave}", "Content-Type": "application/json"},
        json={"model": settings.OPENROUTER_MODEL, "max_tokens": 20,
              "messages": [{"role": "user", "content": "Responda apenas: OK"}]},
        timeout=60,
    )
    if r.status_code != 200:
        print(f"{VERMELHO}✗ modelo '{settings.OPENROUTER_MODEL}' recusado "
              f"(HTTP {r.status_code}): {r.text[:250]}{FIM}")
        return False
    print(f"{VERDE}✓ modelo responde{FIM}  → "
          f"{r.json()['choices'][0]['message']['content'].strip()[:40]}")
    return True


def etapa_2_dry(caminho):
    """Mostra o JSON que SERIA enviado. Não gasta nada."""
    p = AIProcessor()
    payload, rota = p.montar_payload(caminho, CTX)
    blocos = payload["messages"][1]["content"]

    print(f"  arquivo : {os.path.basename(caminho)}")
    print(f"  rota    : {AMARELO}{rota}{FIM}")
    print(f"  modelo  : {payload['model']}")
    print(f"  plugins : {json.dumps(payload.get('plugins', '(nenhum)'))}")
    print(f"  blocos  : {[b['type'] for b in blocos]}")

    b0 = blocos[0]
    if b0["type"] == "file":
        n = len(b0["file"]["file_data"])
        print(f"  base64  : {n:,} chars  (~{n * 3 // 4 // 1024} KB de PDF)")
    elif b0["type"] == "image_url":
        n = len(b0["image_url"]["url"])
        print(f"  base64  : {n:,} chars  (~{n * 3 // 4 // 1024} KB de imagem)")
    else:
        print(f"  texto   : {len(b0['text']):,} caracteres extraídos localmente")
        print("  ---- primeiras linhas ----")
        for linha in b0["text"].splitlines()[:8]:
            print(f"    {linha[:100]}")

    if rota == "pdf/pdf-text":
        print(f"{VERDE}  → PDF com camada de texto: parsing gratuito.{FIM}")
    elif rota.startswith("pdf/"):
        print(f"{AMARELO}  → PDF sem camada de texto: vai pagar OCR/visão.{FIM}")
    return True


def etapa_3_real(caminho):
    """Envia de verdade e mostra o que voltou."""
    p = AIProcessor()
    print(f"  enviando {os.path.basename(caminho)} …")
    r = p.process_file(caminho, CTX)

    if r["status"] != "success":
        print(f"{VERMELHO}✗ {r['status']}: {r.get('error')}{FIM}")
        if r.get("data", {}).get("conteudo"):
            print("  resposta bruta (200 primeiros chars):")
            print("  " + r["data"]["conteudo"][:200])
        return False

    uso = r.get("uso", {})
    print(f"{VERDE}✓ sucesso{FIM}  rota={r.get('rota')}  modelo={r.get('modelo')}")
    print(f"  tokens: {uso.get('entrada', 0):,} entrada / "
          f"{uso.get('saida', 0):,} saída   custo: US$ {uso.get('custo_usd', 0):.6f}")
    if r.get("truncado"):
        print(f"{AMARELO}  ⚠ resposta truncada por max_tokens — fatie o documento.{FIM}")

    d = r["data"]
    itens = d.get("itens", [])
    print(f"\n  empresas: {[e.get('nome') for e in d.get('empresas', [])]}")
    print(f"  itens   : {len(itens)}")
    for it in itens[:10]:
        print(f"    {str(it.get('item')):>3} | "
              f"{(it.get('pi') or it.get('codigo') or '-'):10} | "
              f"{(it.get('nome_em_portugues') or '-')[:38]:38} | "
              f"conf={it.get('confianca', '?')} | {it.get('empresas', {})}")
    if len(itens) > 10:
        print(f"    … mais {len(itens) - 10} item(ns)")
    for aviso in d.get("avisos_gerais", [])[:5]:
        print(f"{AMARELO}  ⚠ {aviso}{FIM}")

    with open("resposta_teste.json", "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    print("\n  JSON completo salvo em resposta_teste.json")
    return True


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("arquivo", nargs="?", help="documento para testar")
    ap.add_argument("--dry", action="store_true", help="monta o payload sem enviar")
    ap.add_argument("--sem-ping", action="store_true", dest="sem_ping",
                    help="pula a etapa 1 (útil offline / atrás de proxy)")
    args = ap.parse_args()

    if not args.sem_ping:
        print(f"\n{'=' * 62}\nETAPA 1 — chave e modelo\n{'=' * 62}")
        if not etapa_1_chave():
            sys.exit(1)

    if not args.arquivo:
        print("\nPara testar um documento:  python teste_openrouter.py arquivo.pdf")
        sys.exit(0)
    if not os.path.exists(args.arquivo):
        print(f"{VERMELHO}arquivo não encontrado: {args.arquivo}{FIM}")
        sys.exit(1)

    print(f"\n{'=' * 62}\nETAPA 2 — roteamento (dry-run)\n{'=' * 62}")
    etapa_2_dry(args.arquivo)

    if args.dry:
        print(f"\n{AMARELO}--dry ativo: nada foi enviado.{FIM}")
        sys.exit(0)

    print(f"\n{'=' * 62}\nETAPA 3 — chamada real\n{'=' * 62}")
    sys.exit(0 if etapa_3_real(args.arquivo) else 1)