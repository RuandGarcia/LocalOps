"""Aggregates the agent tools read: daily KPI per priority and daily trends per dimension
(daily so the agent can cut a month at the replay "today").

Usage: python -m localops_ml.agregados   (also called by localops_ml.run)
"""
from __future__ import annotations

import json

import pandas as pd

from localops_ml import config, dados

DIMENSOES = {"produto": "produto", "categoria": "categoria", "equipe": "equipe", "item": "item_config"}


def kpi_diario(df: pd.DataFrame) -> pd.DataFrame:
    """Per day and priority (P2, P3): incidents that entered the KPI and KPI violations."""
    d = df[(df["data"] >= config.INICIO_BASE) & df["prioridade"].isin(["P2", "P3"])]
    g = d.groupby(["data", "prioridade"]).agg(volume=("entrou_kpi", "sum"), violacoes=("kpi_violado", "sum"))
    dias = pd.date_range(config.INICIO_BASE, df["data"].max(), freq="D")
    idx = pd.MultiIndex.from_product([dias, ["P2", "P3"]], names=["data", "prioridade"])
    return g.reindex(idx, fill_value=0).astype(int).reset_index()


def tendencias_diarias(df: pd.DataFrame) -> pd.DataFrame:
    d = df[df["data"] >= config.INICIO_BASE].assign(dia=lambda x: x["data"].dt.strftime("%Y-%m-%d"))
    partes = []
    for nome, col in DIMENSOES.items():
        v = d[col].fillna("(não informado)")
        if nome == "item":  # 9 thousand configuration items: keep the 200 busiest of the year
            v = v.where(v.isin(v.value_counts().head(200).index), "(outros itens)")
        g = d.assign(valor=v).groupby(["dia", "valor"]).agg(
            total=("numero", "size"), humano=("humano", "sum"), violacoes=("kpi_violado", "sum"))
        partes.append(g.reset_index().assign(dimensao=nome))
    return pd.concat(partes, ignore_index=True)[["dimensao", "dia", "valor", "total", "humano", "violacoes"]]


def gravar(df: pd.DataFrame) -> None:
    config.ARTEFATOS.mkdir(parents=True, exist_ok=True)
    k = kpi_diario(df).assign(data=lambda x: x["data"].dt.strftime("%Y-%m-%d"))
    dados.escrever_atomico(config.ARTEFATOS / "kpi_diario.json", k.to_json(orient="records"))
    t = tendencias_diarias(df)
    dados.escrever_atomico(config.ARTEFATOS / "tendencias_diarias.json",
                           json.dumps(t.to_dict("records"), ensure_ascii=False, default=int))


if __name__ == "__main__":
    gravar(dados.carregar_incidentes())
