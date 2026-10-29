"""Incident base: read the xlsx once, type it and cache it; build the daily series."""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

from localops_ml import config


def escrever_atomico(caminho: Path, texto: str) -> None:
    """Write next to the target and swap, so a reader (the API) never sees a half-written file."""
    tmp = caminho.with_name(caminho.name + ".tmp")
    tmp.write_text(texto, encoding="utf-8")
    os.replace(tmp, caminho)


def carregar_incidentes(recriar: bool = False) -> pd.DataFrame:
    if config.INCIDENTES.exists() and not recriar:
        return pd.read_parquet(config.INCIDENTES)

    df = tipar(pd.read_excel(config.XLSX, sheet_name="Dataset Geral", dtype=str))
    config.DADOS.mkdir(exist_ok=True)
    df.to_parquet(config.INCIDENTES, index=False)
    return df


def tipar(bruto: pd.DataFrame) -> pd.DataFrame:
    """Raw sheet (the 19 columns of the data dictionary, in order, as text) → typed incident table."""
    if len(bruto.columns) != len(config.COLUNAS):
        raise ValueError(f"esperava {len(config.COLUNAS)} colunas, vieram {len(bruto.columns)}")
    df = bruto.set_axis(config.COLUNAS, axis=1)

    for col in df.columns:
        df[col] = df[col].str.strip().replace({"": None})
    for col in ("aberto", "resolvido", "encerrado"):
        # format="mixed": the ITSM export mixes "…23:45:18" and "…23:45"; inferring from row 1 dropped the rest.
        df[col] = pd.to_datetime(df[col], errors="coerce", format="mixed")
    df["duracao_seg"] = pd.to_numeric(df["duracao_seg"], errors="coerce")

    df["prioridade"] = "P" + df["prioridade_txt"].str[0]
    df["humano"] = df["status"] != config.SEM_INTERVENCAO
    df["monitoramento"] = df["aberto_por"] == "Monitoramento"
    # Official result computed by Locaweb (the Duration column alone does not reproduce it).
    df["entrou_kpi"] = df["entrou_kpi_txt"].str.upper() == "SIM"
    df["kpi_violado"] = df["entrou_kpi"] & (df["kpi_violado_txt"].str.upper() == "SIM")
    df["data"] = df["aberto"].dt.normalize()
    return df


def serie_diaria(df: pd.DataFrame) -> pd.DataFrame:
    """Daily counts by opening date, from INICIO_BASE, with empty days filled as zero."""
    d = df[df["data"] >= config.INICIO_BASE]
    s = pd.DataFrame({
        "total": d.groupby("data").size(),
        "humano": d[d["humano"]].groupby("data").size(),
        "p2": d[d["prioridade"] == "P2"].groupby("data").size(),
        "p3": d[d["prioridade"] == "P3"].groupby("data").size(),
        "kpi": d[d["entrou_kpi"]].groupby("data").size(),
    })
    dias = pd.date_range(config.INICIO_BASE, d["data"].max(), freq="D")
    return s.reindex(dias).fillna(0).astype(float).rename_axis("data")
