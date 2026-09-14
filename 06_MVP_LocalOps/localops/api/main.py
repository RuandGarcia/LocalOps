"""
api/main.py — API REST do LocalOps (FastAPI).

Endpoints:
  GET  /health                 — verificação de disponibilidade
  GET  /forecast                — previsões D+1/D+7 (prophet, xgboost, ensemble)
  GET  /alerts                  — picos de volume previstos, por nível (BAIXO/MÉDIO/ALTO)
  GET  /recommendations         — recomendações operacionais (reports/recomendacoes.json)
  GET  /explain                 — SHAP: waterfall da previsão + importância global
  GET  /risks/teams             — ranking de carga e violação de OLA por equipe
  POST /agent                   — agente conversacional offline

Documentação automática (OpenAPI) em /docs.

Uso:
    uvicorn localops.api.main:app --reload
"""

from __future__ import annotations

from typing import Optional

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from localops import agent as agent_mod
from localops import config, store
from localops.models.recommender import JANELA_DIAS, _nivel_alerta

app = FastAPI(
    title="LocalOps API",
    description="Previsão, explicabilidade e recomendação para a operação AIOps da Locaweb.",
    version="0.3.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class PerguntaAgente(BaseModel):
    pergunta: str


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/forecast")
def forecast(
    serie: Optional[str] = Query(None, description="total, p2, p3 ou kpi"),
    horizonte: Optional[int] = Query(None, description="1 (D+1) ou 7 (D+7)"),
    modelo: Optional[str] = Query(None, description="prophet, xgboost ou ensemble"),
) -> list[dict]:
    df = store.load_forecast()
    if serie:
        if serie not in config.SERIES_PREVISTAS:
            raise HTTPException(400, f"série inválida: {serie}. Use uma de {list(config.SERIES_PREVISTAS)}")
        df = df[df["serie"] == serie]
    if horizonte:
        df = df[df["horizonte"] == horizonte]
    if modelo:
        df = df[df["modelo"] == modelo]
    return df.to_dict(orient="records")


@app.get("/alerts")
def alerts() -> list[dict]:
    forecast_df = store.load_forecast()
    serie_diaria = store.load_serie_diaria()
    ensemble = forecast_df[forecast_df["modelo"] == "ensemble"]

    coluna_por_serie = {"total": "total", "p2": "p2", "p3": "p3", "kpi": "kpi_elegivel"}
    resultado = []
    for _, linha in ensemble.iterrows():
        hist = serie_diaria[coluna_por_serie[linha["serie"]]].tail(90)
        nivel = _nivel_alerta(linha["previsto"], hist.mean(), hist.std())
        if nivel == "BAIXO":
            continue
        resultado.append({
            "serie": linha["serie"],
            "rotulo": config.SERIES_PREVISTAS[linha["serie"]],
            "horizonte": int(linha["horizonte"]),
            "data_alvo": str(linha["data_alvo"].date()),
            "previsto": round(float(linha["previsto"]), 1),
            "variacao_pct_vs_media_30d": round(float(linha["variacao_pct_vs_media_30d"]), 1),
            "nivel": nivel,
        })
    return resultado


@app.get("/recommendations")
def recommendations() -> dict:
    """Dict com 4 chaves: recomendacoes, alertas, carga_equipes, risco_categorias
    (ver docstring de localops/models/recommender.py)."""
    return store.load_recomendacoes()


@app.get("/explain")
def explain(serie: str = Query("total", description="hoje só a série 'total' tem waterfall calculado")) -> dict:
    dados = store.load_shap()
    if not dados:
        raise HTTPException(404, "reports/shap.json ainda não foi gerado — rode o pipeline primeiro")
    return dados


@app.get("/risks/teams")
def risks_teams() -> list[dict]:
    incidentes = store.load_incidentes()
    ultima_data = incidentes["aberto"].max()
    janela = incidentes[incidentes["aberto"] >= ultima_data - pd.Timedelta(days=JANELA_DIAS)]

    resumo = janela.groupby("grupo_designado").agg(
        total=("numero", "count"),
        violacoes_ola=("ola_estourado", "sum"),
        criticos=("prioridade_cod", lambda s: s.isin(["P1", "P2"]).sum()),
    ).reset_index()
    resumo["pct_carga"] = (resumo["total"] / resumo["total"].sum() * 100).round(1)
    resumo = resumo.sort_values("total", ascending=False)

    return resumo.to_dict(orient="records")


@app.post("/agent")
def agent(payload: PerguntaAgente) -> dict:
    r = agent_mod.responder(payload.pergunta)
    return {
        "texto": r.texto,
        "fontes": r.fontes,
        "confianca": r.confianca,
        "sugestoes": r.sugestoes,
        "intencao": r.intencao,
        "dados": r.dados,
        # o gráfico (Plotly) não serializa em JSON puro; devolvemos como
        # figura.to_plotly_json() (dict), consumível por qualquer cliente
        # que saiba renderizar Plotly — None quando a intenção não gera gráfico.
        "figura": r.figura.to_plotly_json() if r.figura is not None else None,
    }
