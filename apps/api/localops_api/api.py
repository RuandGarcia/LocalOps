"""LocalOps API /v1: the tools as REST and the copilot chat the web panel calls.

Usage: uvicorn localops_api.api:app --port 8000
Env: LOCALOPS_CORS (allowed origins, comma separated), LOCALOPS_LIMITE_DIA (LLM answers per day, all
visitors together, to protect the subscription quota), LOCALOPS_ENTRADA (folder the pipeline worker
watches for new batches), LOCALOPS_INGESTAO_TOKEN_FILE (secret that authorizes POST /v1/ingestao; without
it ingestion is off), plus the OPENCLAW_* settings in cerebro.py.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import io
import json
import logging
import os
import time
from collections import defaultdict, deque
from pathlib import Path

import pandas as pd

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from localops_api import cerebro
from localops_api import ferramentas as f
from localops_api import formatos

app = FastAPI(title="LocalOps API", version="0.2.0", docs_url="/v1/docs", openapi_url="/v1/openapi.json")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.environ.get("LOCALOPS_CORS", "http://localhost:5173,http://localhost:5174").split(",") if o.strip()],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],  # no Authorization: ingestion is server to server, never from the panel
)

_log = logging.getLogger("uvicorn.error")
POR_MINUTO = 6
LIMITE_DIA = int(os.environ.get("LOCALOPS_LIMITE_DIA", "400"))
_janelas: dict[str, deque] = defaultdict(deque)
_uso_dia = {"dia": "", "n": 0}
_cache: dict[tuple, tuple[float, dict]] = {}
CACHE_S = 6 * 3600


def _visitante(req: Request) -> str:
    ip = req.headers.get("x-forwarded-for", req.client.host if req.client else "?").split(",")[0].strip()
    return hashlib.sha256(ip.encode()).hexdigest()[:16]


def _limitar(quem: str) -> None:
    agora, j = time.time(), _janelas[quem]
    while j and agora - j[0] > 60:
        j.popleft()
    if len(j) >= POR_MINUTO:
        raise HTTPException(429, "Muitas perguntas seguidas. Espere um minuto.")
    j.append(agora)


def _cota_llm() -> bool:
    hoje = time.strftime("%Y-%m-%d")
    if _uso_dia["dia"] != hoje:
        _uso_dia.update(dia=hoje, n=0)
    if _uso_dia["n"] >= LIMITE_DIA:
        return False
    _uso_dia["n"] += 1
    return True


@app.get("/v1/saude")
def saude() -> dict:
    return {"ok": True, "llm_configurado": cerebro.llm_configurado(), "ferramentas": list(f.FERRAMENTAS),
            "dados_ate": f._ler("metricas.json")["base"]["fim_serie"][:10]}


@app.get("/v1/ferramentas/{nome}")
def ferramenta(nome: str, req: Request) -> dict:
    if nome not in f.FERRAMENTAS:
        raise HTTPException(404, f"ferramenta {nome!r} não existe")
    try:
        return f.FERRAMENTAS[nome](**dict(req.query_params))
    except (f.ErroFerramenta, TypeError) as e:
        raise HTTPException(400, str(e)) from e


class AnexoIn(BaseModel):
    nome: str = Field(min_length=1, max_length=120)
    texto: str = Field(default="", max_length=cerebro.MAX_ANEXO)  # text files, read in the browser
    base64: str = Field(default="", max_length=7_000_000)  # PDF, XLSX or HTML (≤ 5 MB), read here


def _ler_anexos(anexos: list[dict]) -> list[dict]:
    """PDF, Excel and HTML become text for the model; a file that cannot be read says why."""
    lidos = []
    for a in anexos:
        texto = a["texto"]
        if a["base64"]:
            try:
                texto = formatos.ler_anexo(a["nome"], a["base64"])
            except Exception as e:  # corrupt, encrypted or scanned files: tell the agent, never fail the chat
                texto = f"(não consegui ler este arquivo: {e if isinstance(e, formatos.ErroFormato) else 'formato inválido'})"
            if len(texto) > cerebro.MAX_ANEXO:
                texto = texto[:cerebro.MAX_ANEXO] + f"\n[cortado em {cerebro.MAX_ANEXO:,} caracteres]".replace(",", ".")
        lidos.append({"nome": a["nome"], "texto": texto})
    return lidos


class Pergunta(BaseModel):
    pergunta: str = Field(min_length=1, max_length=1000)
    hoje: str = Field(default="2025-12-31", pattern=r"^\d{4}-\d{2}-\d{2}$")
    conversa: str = Field(default="", max_length=64)
    filtro: str = Field(default="", max_length=200)  # the panel's period filter, e.g. "dezembro de 2025"
    anexos: list[AnexoIn] = Field(default_factory=list, max_length=3)


@app.post("/v1/copilot")
async def copilot(p: Pergunta, req: Request) -> dict:
    quem = _visitante(req)
    _limitar(quem)
    anexos = await asyncio.to_thread(_ler_anexos, [a.model_dump() for a in p.anexos])
    # Per visitor conversation: the agent answers from that conversation's history and attachments.
    chave = (quem, p.conversa, p.pergunta.strip().lower(), p.hoje, p.filtro)
    if not anexos and chave in _cache and time.time() - _cache[chave][0] < CACHE_S:
        return _cache[chave][1] | {"cache": True}

    if cerebro.llm_configurado() and _cota_llm():
        try:
            t0 = time.perf_counter()
            bruto = await cerebro.perguntar_agente(p.pergunta, p.hoje, f"web:{quem}:{p.conversa}", p.filtro, anexos)
            _log.info("copilot llm %.1fs anexos=%d", time.perf_counter() - t0, len(anexos))
            # An empty model turn comes back as this placeholder (seen in production on 20/10): answer offline.
            if bruto.strip() in ("", "No response from OpenClaw."):
                raise RuntimeError("resposta vazia do agente")
            # Rendering PDF/XLSX is CPU work: off the event loop, so one report never freezes the other visitors.
            texto, arquivos = await asyncio.to_thread(cerebro.extrair_arquivos, bruto, p.hoje)
            texto, fonte = cerebro.separar_fonte(texto)
            resp = {"de": "agente", "texto": texto, "arquivos": arquivos, "modo": "llm",
                    "fonte": f"{fonte} · agente localops (IA)" if fonte else "agente localops (IA) com as ferramentas do LocalOps"}
            if not anexos:
                _cache[chave] = (time.time(), resp)
            return resp
        except Exception:  # gateway down, timeout, quota: never break the panel
            pass
    try:
        r = await asyncio.to_thread(cerebro.responder_offline, p.pergunta, p.hoje, anexos)
    except f.ErroFerramenta as e:
        r = {"texto": str(e), "fonte": None}
    return {"de": "agente", "modo": "offline", **r}


# --- ingestion ------------------------------------------------------------------------------------
# The API only checks and stages the batch; the pipeline worker (localops_ml.ingestao) validates each
# row, merges it into the base and reruns the models. Progress is read back from GET /v1/ingestao.

ENTRADA = Path(os.environ.get("LOCALOPS_ENTRADA", f.ARTEFATOS.parent / "dados" / "entrada"))
MAX_LOTE = 25 * 1024 * 1024
N_COLUNAS = 19  # "Dataset Geral" sheet of the data dictionary
TIPOS = {"text/csv": ".csv", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx"}


def _token_ingestao() -> str:
    arq = os.environ.get("LOCALOPS_INGESTAO_TOKEN_FILE", "")
    try:
        return Path(arq).read_text(encoding="utf-8").strip() if arq else ""
    except OSError:
        return ""


def _autorizar(req: Request) -> None:
    esperado = _token_ingestao()
    if not esperado:
        raise HTTPException(503, "ingestão desligada neste ambiente")
    dado = req.headers.get("authorization", "").removeprefix("Bearer ").strip()
    if not hmac.compare_digest(dado.encode(), esperado.encode()):
        raise HTTPException(401, "token de ingestão inválido")


@app.post("/v1/ingestao", status_code=202)
async def ingestao(req: Request) -> dict:
    _autorizar(req)
    ext = TIPOS.get(req.headers.get("content-type", "").split(";")[0].strip())
    if not ext:
        raise HTTPException(415, f"envie CSV ou XLSX; content-type aceitos: {list(TIPOS)}")
    corpo = await req.body()
    if not corpo:
        raise HTTPException(400, "lote vazio")
    if len(corpo) > MAX_LOTE:
        raise HTTPException(413, f"lote acima de {MAX_LOTE // 2**20} MB; divida em partes")
    try:
        if ext == ".csv":
            tabela = pd.read_csv(io.BytesIO(corpo), dtype=str, sep=None, engine="python", encoding="latin-1")
        else:
            tabela = pd.read_excel(io.BytesIO(corpo), sheet_name=0, dtype=str)
    except Exception as e:
        raise HTTPException(422, f"não consegui ler o arquivo: {str(e)[:200]}") from e
    if len(tabela.columns) != N_COLUNAS:
        raise HTTPException(422, f"esperava as {N_COLUNAS} colunas do dicionário de dados, vieram {len(tabela.columns)}")

    ENTRADA.mkdir(parents=True, exist_ok=True)
    nome = f"{time.strftime('%Y%m%dT%H%M%S')}-{hashlib.sha256(corpo).hexdigest()[:8]}{ext}"
    tmp = ENTRADA / f".{nome}.parcial"  # the worker ignores it until the rename
    tmp.write_bytes(corpo)
    os.replace(tmp, ENTRADA / nome)
    return {"lote": nome, "linhas": int(len(tabela)), "estado": "na_fila",
            "proximo_passo": "o pipeline valida, incorpora e recalcula; acompanhe em GET /v1/ingestao"}


@app.get("/v1/ingestao")
def ingestao_estado() -> dict:
    try:
        e = json.loads((f.ARTEFATOS / "ingestao.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        e = {"lotes": []}
    fila = sorted(p.name for p in ENTRADA.glob("*") if p.is_file() and not p.name.startswith(".")) if ENTRADA.exists() else []
    return {"ligada": bool(_token_ingestao()), "na_fila": fila, "dados_ate": f._ler("metricas.json")["base"]["fim_serie"][:10], **e}
