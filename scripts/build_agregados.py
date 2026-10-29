"""Build the web app's aggregate file from the incident base.

Usage: python scripts/build_agregados.py <incidentes.parquet> [saida.json]

Output is anonymized counts only (product, category and team are already coded in the base).
Default output: apps/web/src/data/agregados.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
TOP_PRODUTOS = 12
TOP_CATEGORIAS = 15
TOP_CIS = 10


def main(origem: str, destino: str) -> None:
    df = pd.read_parquet(origem)
    d = df[df["ano"] == 2025].copy()
    d["humano"] = ~d["sem_intervencao"].astype(bool)
    # KPI violation as Locaweb counts it (eligible P1-P3, not a child, human intervention): 42 P2 / 196 P3 in 2025.
    d["ola"] = d["kpi_violado"].fillna(False).astype(bool)
    # Second annual KPI: volume of incidents handled (entered the KPI), per priority.
    d["kpi"] = d["entrou_kpi"].fillna(False).astype(bool)

    top_p = d["produto"].value_counts().head(TOP_PRODUTOS).index
    top_c = d["categoria"].value_counts().head(TOP_CATEGORIAS).index
    d["prod"] = d["produto"].where(d["produto"].isin(top_p), "outros").astype(str)
    d["cat"] = d["categoria"].where(d["categoria"].isin(top_c), "outras").astype(str)
    d["eq"] = d["equipe"].astype(str)
    d["pri"] = d["prioridade"].astype(str)

    dims = {
        "produtos": sorted(d["prod"].unique()),
        "categorias": sorted(d["cat"].unique()),
        "equipes": sorted(d["eq"].unique()),
        "prioridades": sorted(d["pri"].unique()),
    }
    idx = {k: {v: i for i, v in enumerate(vals)} for k, vals in dims.items()}
    dias = sorted(d["data"].dt.strftime("%Y-%m-%d").unique())
    idx_dia = {v: i for i, v in enumerate(dias)}
    d["dia"] = d["data"].dt.strftime("%Y-%m-%d")

    g = (
        d.groupby(["dia", "prod", "cat", "eq", "pri"])
        .agg(n=("numero", "size"), h=("humano", "sum"), o=("ola", "sum"), e=("kpi", "sum"))
        .reset_index()
    )
    # Fact rows: [day, product, category, team, priority, total, human, kpi_violations, kpi_handled]
    fatos = [
        [idx_dia[r.dia], idx["produtos"][r.prod], idx["categorias"][r.cat], idx["equipes"][r.eq], idx["prioridades"][r.pri], int(r.n), int(r.h), int(r.o), int(r.e)]
        for r in g.itertuples(index=False)
    ]

    # Hour x weekday for human alarms, per month (heatmap; does not split by product/team).
    hm = d[d["humano"]].groupby([d["mes"], d["dia_semana_num"], d["hora"]]).size().reset_index(name="n")
    calor = [[int(r.mes), int(r.dia_semana_num), int(r.hora), int(r.n)] for r in hm.itertuples(index=False)]

    # Recurring configuration items that needed a person.
    cis = (
        d[d["humano"] & d["item_config"].notna()]
        .groupby(["mes", "item_config"])
        .size()
        .reset_index(name="n")
    )
    top_ci = cis.groupby("item_config")["n"].sum().nlargest(TOP_CIS).index
    reincidentes = [[int(r.mes), str(r.item_config), int(r.n)] for r in cis[cis["item_config"].isin(top_ci)].itertuples(index=False)]

    # Weekly series of the configuration items that most needed a person (trend by CI).
    d["semana"] = (d["data"] - pd.to_timedelta(d["data"].dt.dayofweek, unit="D")).dt.strftime("%Y-%m-%d")
    semanas = sorted(d["semana"].unique())
    idx_sem = {v: i for i, v in enumerate(semanas)}
    top_ci_h = d[d["humano"] & d["item_config"].notna()]["item_config"].value_counts().head(30).index
    ci_sem = d[d["item_config"].isin(top_ci_h)].groupby(["item_config", "semana"]).agg(h=("humano", "sum"), o=("ola", "sum")).reset_index()
    tendencia_ci = {}
    for r in ci_sem.itertuples(index=False):
        serie = tendencia_ci.setdefault(str(r.item_config), {"h": [0] * len(semanas), "o": [0] * len(semanas)})
        serie["h"][idx_sem[r.semana]] = int(r.h)
        serie["o"][idx_sem[r.semana]] = int(r.o)

    # Every KPI violation with its configuration item, to measure recurrence as of any day.
    v = d[d["ola"]].sort_values("aberto")
    violacoes = [[idx_dia[r.dia], idx["prioridades"][r.pri], str(r.item_config), idx["categorias"][r.cat], idx["produtos"][r.prod]] for r in v.itertuples(index=False)]

    saida = {
        "fonte": "incidentes.parquet, ano 2025",
        "dias": dias,
        **dims,
        "fatos": fatos,
        "calor": calor,
        "reincidentes": reincidentes,
        "semanas": semanas,
        "tendenciaCi": tendencia_ci,
        "violacoes": violacoes,
    }
    Path(destino).write_text(json.dumps(saida, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{len(fatos)} fatos, {len(dias)} dias -> {destino} ({Path(destino).stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else str(ROOT / "apps/web/src/data/agregados.json"))
