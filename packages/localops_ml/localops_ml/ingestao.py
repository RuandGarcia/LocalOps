"""Ingestion: a new export of incidents (the 19 columns of the "Dataset Geral" sheet, same order) joins
the base, and the pipeline reruns so the API and the agent answer with the new days.

The API only stages the file in config.ENTRADA (it carries no ML dependencies); this worker validates,
merges by incident number (a newer row replaces the older one) and reruns the pipeline.

Usage (repo root):
  python -m localops_ml.ingestao lote.csv            # one batch now (CSV or XLSX)
  python -m localops_ml.ingestao --vigiar 300        # worker: process ENTRADA every 300 s
"""
from __future__ import annotations

import json
import shutil
import sys
import time
import traceback
from pathlib import Path

import pandas as pd

from localops_ml import config, dados

ESTADO = "ingestao.json"  # read by GET /v1/ingestao
HISTORICO = 20
DATAS = ("aberto", "resolvido", "encerrado")


def ler_lote(caminho: Path) -> pd.DataFrame:
    if caminho.suffix.lower() in (".xlsx", ".xls"):
        bruto = pd.read_excel(caminho, sheet_name=0, dtype=str)
    else:
        try:
            bruto = pd.read_csv(caminho, dtype=str, sep=None, engine="python", encoding="utf-8-sig")
        except UnicodeDecodeError:  # exports from Windows tools come in latin-1
            bruto = pd.read_csv(caminho, dtype=str, sep=None, engine="python", encoding="latin-1")
    if len(bruto.columns) == len(config.COLUNAS):
        for i in (config.COLUNAS.index(c) for c in DATAS):
            col = bruto.iloc[:, i]
            # "31/12/2025 23:45" must not be read month-first.
            br = col.str.match(r"^\s*\d{2}/\d{2}/\d{4}", na=False)
            bruto.iloc[:, i] = col.where(~br, pd.to_datetime(col[br], dayfirst=True, errors="coerce").astype(str))
    return dados.tipar(bruto)


def validar(lote: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    """Rows the pipeline can use, and the rejected ones with the reason (line number as in the file)."""
    agora = pd.Timestamp.now() + pd.Timedelta(days=1)
    motivos = pd.Series("", index=lote.index)
    regras = (
        (lote["numero"].isna(), "sem número do incidente"),
        (lote["aberto"].isna(), "data de abertura vazia ou inválida"),
        (lote["aberto"] > agora, "abertura no futuro"),
        (~lote["prioridade_txt"].fillna("").str.match(r"^[1-5]"), "prioridade fora do dicionário (1 a 5)"),
        (lote["status"].isna(), "sem status"),
    )
    for falha, motivo in regras:
        motivos[falha & (motivos == "")] = motivo
    ruins = motivos != ""
    rejeitados = [{"linha": int(i) + 2, "numero": lote.at[i, "numero"], "motivo": motivos[i]} for i in lote.index[ruins]]
    validos = lote[~ruins].drop_duplicates("numero", keep="last")
    return validos, rejeitados


def incorporar(lote: pd.DataFrame) -> dict:
    """Merge a typed batch into the base; returns the counts shown to whoever sent it."""
    base = dados.carregar_incidentes()
    validos, rejeitados = validar(lote)
    ja_existia = validos["numero"].isin(base["numero"])
    # Updates stay in their row and new incidents go to the end: re-sending a batch that changes
    # nothing leaves the base, and every artefact, byte for byte the same.
    b = base.set_index("numero")
    v = validos.set_index("numero")[b.columns]
    atualiza = v.index[ja_existia.to_numpy()]
    b.loc[atualiza] = v.loc[atualiza]
    junto = pd.concat([b, v[~ja_existia.to_numpy()]]).reset_index()
    tmp = config.INCIDENTES.with_name(config.INCIDENTES.name + ".tmp")
    junto.to_parquet(tmp, index=False)
    tmp.replace(config.INCIDENTES)
    return {
        "recebidos": int(len(lote)),
        "novos": int((~ja_existia).sum()),
        "atualizados": int(ja_existia.sum()),
        "rejeitados": len(rejeitados),
        "exemplos_rejeitados": rejeitados[:10],
        "base_registros": int(len(junto)),
        "base_ate": f"{junto['aberto'].max():%Y-%m-%d %H:%M}",
    }


def _estado() -> dict:
    try:
        return json.loads((config.ARTEFATOS / ESTADO).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {"lotes": []}


def _gravar_estado(e: dict) -> None:
    config.ARTEFATOS.mkdir(parents=True, exist_ok=True)
    dados.escrever_atomico(config.ARTEFATOS / ESTADO, json.dumps(e, ensure_ascii=False, indent=1))


def _agora() -> str:
    return pd.Timestamp.now().isoformat(timespec="seconds")


def processar(arquivos: list[Path], rodar_pipeline=None) -> dict:
    """Merge each file, move it to processados/ or rejeitados/, then rerun the pipeline once if anything changed."""
    if rodar_pipeline is None:
        from localops_ml import run
        rodar_pipeline = run.main
    e = _estado()
    mudou = False
    for arq in arquivos:
        try:
            r = {"lote": arq.name, "em": _agora(), "estado": "incorporado", **incorporar(ler_lote(arq))}
            mudou |= r["novos"] + r["atualizados"] > 0
            destino = "processados"
        except Exception as ex:  # a bad file must not stop the worker or the other batches
            r = {"lote": arq.name, "em": _agora(), "estado": "recusado", "erro": str(ex)[:300]}
            destino = "rejeitados"
        (arq.parent / destino).mkdir(exist_ok=True)
        shutil.move(str(arq), arq.parent / destino / arq.name)
        e["lotes"] = [r, *e.get("lotes", [])][:HISTORICO]
        _gravar_estado(e)

    if mudou:
        e["pipeline"] = {"estado": "processando", "inicio": _agora()}
        _gravar_estado(e)
        t0 = time.time()
        try:
            rodar_pipeline()
            e["pipeline"] = {"estado": "ok", "inicio": e["pipeline"]["inicio"], "fim": _agora(), "duracao_min": round((time.time() - t0) / 60, 1)}
        except Exception:
            e["pipeline"] = {"estado": "falhou", "inicio": e["pipeline"]["inicio"], "fim": _agora(),
                             "erro": traceback.format_exc(limit=3)[-600:]}
        _gravar_estado(e)
    return e


def na_fila() -> list[Path]:
    if not config.ENTRADA.exists():
        return []
    return sorted(p for p in config.ENTRADA.iterdir() if p.is_file() and p.suffix.lower() in (".csv", ".xlsx", ".xls"))


def vigiar(intervalo_s: int) -> None:
    config.ENTRADA.mkdir(parents=True, exist_ok=True)
    print(f"ingestão: vigiando {config.ENTRADA} a cada {intervalo_s} s", flush=True)
    while True:
        arquivos = na_fila()
        if arquivos:
            print(f"ingestão: {len(arquivos)} lote(s)", flush=True)
            e = processar(arquivos)
            print(f"ingestão: pipeline {e.get('pipeline', {}).get('estado', 'sem mudança')}", flush=True)
        time.sleep(intervalo_s)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--vigiar":
        vigiar(int(sys.argv[2]))
    elif len(sys.argv) == 2:
        config.ENTRADA.mkdir(parents=True, exist_ok=True)
        alvo = config.ENTRADA / Path(sys.argv[1]).name
        shutil.copy(sys.argv[1], alvo)
        print(json.dumps(processar([alvo]), ensure_ascii=False, indent=1))
    else:
        sys.exit(__doc__)
