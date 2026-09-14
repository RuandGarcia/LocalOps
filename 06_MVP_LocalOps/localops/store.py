"""
store.py — ponto único de acesso aos artefatos gerados pelo pipeline
(SQLite, parquet, joblib, json). Usado pelo dashboard, pela API e pelo
agente conversacional — nenhum desses componentes deve ler os arquivos
diretamente, para manter um único contrato de dados.
"""

from __future__ import annotations

import json
import sqlite3
from functools import lru_cache
from pathlib import Path

import joblib
import pandas as pd

from localops import config


def get_conn() -> sqlite3.Connection:
    return sqlite3.connect(config.DB_PATH)


@lru_cache(maxsize=1)
def load_incidentes() -> pd.DataFrame:
    df = pd.read_parquet(config.INCIDENTES_PARQUET_PATH)
    for col in ("aberto", "resolvido", "encerrado"):
        df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


@lru_cache(maxsize=1)
def load_serie_diaria() -> pd.DataFrame:
    conn = get_conn()
    try:
        df = pd.read_sql("SELECT * FROM serie_diaria", conn)
    finally:
        conn.close()
    df["data"] = pd.to_datetime(df["data"])
    return df


@lru_cache(maxsize=1)
def load_forecast() -> pd.DataFrame:
    df = pd.read_parquet(config.FORECAST_PARQUET_PATH)
    df["data_alvo"] = pd.to_datetime(df["data_alvo"])
    return df


@lru_cache(maxsize=1)
def load_backtest() -> pd.DataFrame:
    df = pd.read_parquet(config.BACKTEST_PARQUET_PATH)
    df["corte"] = pd.to_datetime(df["corte"])
    return df


def load_metricas() -> dict:
    if not config.METRICS_JSON_PATH.exists():
        return {}
    return json.loads(config.METRICS_JSON_PATH.read_text(encoding="utf-8"))


def load_shap() -> dict:
    if not config.SHAP_JSON_PATH.exists():
        return {}
    return json.loads(config.SHAP_JSON_PATH.read_text(encoding="utf-8"))


def load_recomendacoes() -> dict:
    """Dict com 4 chaves: recomendacoes, alertas, carga_equipes,
    risco_categorias (ver docstring de models/recommender.py)."""
    if not config.RECOMMENDATIONS_JSON_PATH.exists():
        return {}
    return json.loads(config.RECOMMENDATIONS_JSON_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_classificador_critico() -> dict:
    return joblib.load(config.MODELS_DIR / "classificador_critico.joblib")


@lru_cache(maxsize=1)
def load_classificador_ola() -> dict:
    return joblib.load(config.MODELS_DIR / "classificador_ola.joblib")


def limpar_cache() -> None:
    """Limpa os caches em memória — útil após rodar o pipeline de novo
    (ex.: dashboard/API de longa duração após um retreino)."""
    load_incidentes.cache_clear()
    load_serie_diaria.cache_clear()
    load_forecast.cache_clear()
    load_backtest.cache_clear()
    load_classificador_critico.cache_clear()
    load_classificador_ola.cache_clear()
    incidentes.cache_clear()
    serie_diaria.cache_clear()
    previsoes.cache_clear()
    backtest.cache_clear()


# ---------------------------------------------------------------------------
# Adapter para o dashboard (localops/dashboard/views.py)
#
# O dashboard foi escrito com nomes de função/coluna próprios (contrato
# combinado à parte da implementação dos módulos acima). As funções abaixo
# traduzem os artefatos "canônicos" (load_*, usados internamente por
# agent.py, api/main.py, classify.py e diagnostics.py) para esse contrato,
# sem alterar o formato canônico — assim nenhum consumidor existente quebra.
# shap.json e recomendacoes.json não precisam de adapter aqui porque o
# dashboard os lê via `ler_json()` direto do disco — explain.py e
# recommender.py já gravam esses dois arquivos no formato que o dashboard
# espera.
# ---------------------------------------------------------------------------

def ler_json(path) -> dict:
    """Leitor genérico de JSON (o dashboard usa isso pra shap.json e
    recomendacoes.json, que já são gravados no formato que ele espera)."""
    p = Path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def incidentes() -> pd.DataFrame:
    """`load_incidentes()` traduzido pro contrato do dashboard: nomes de
    coluna (`equipe`, `entrou_kpi`, `kpi_violado`, `prioridade` como "P1".."P5",
    `categoria` com "(sem categoria)" como marcador de nulo) + colunas de
    calendário derivadas (`ano`, `ano_mes`, `dia_semana_num`, `hora`,
    `fim_de_semana`, `data`)."""
    df = load_incidentes().copy()
    df = df.rename(columns={
        "grupo_designado": "equipe",
        "elegivel_kpi": "entrou_kpi",
        "ola_estourado": "kpi_violado",
    })
    df["prioridade"] = df["prioridade_cod"]
    df["categoria"] = df["categoria"].replace("Não informado", "(sem categoria)")
    df["ano"] = df["aberto"].dt.year
    df["ano_mes"] = df["aberto"].dt.strftime("%Y-%m")
    df["dia_semana_num"] = df["aberto"].dt.dayofweek
    df["hora"] = df["aberto"].dt.hour
    df["fim_de_semana"] = df["dia_semana_num"].isin([5, 6])
    df["data"] = df["aberto"].dt.date
    return df


@lru_cache(maxsize=1)
def serie_diaria() -> pd.DataFrame:
    """`load_serie_diaria()` traduzido: `data`->`ds`, `total`->`y`,
    `p2`/`p3`/`kpi_elegivel` -> `y_P2`/`y_P3`/`y_kpi` (mesmo mapeamento de
    `localops/etl/features.py::SERIE_PARA_COLUNA`)."""
    df = load_serie_diaria().copy()
    return df.rename(columns={
        "data": "ds", "total": "y", "p2": "y_P2", "p3": "y_P3", "kpi_elegivel": "y_kpi",
    })


_SEGMENTO_DASHBOARD = {"total": "total", "p2": "P2", "p3": "P3", "kpi": "kpi"}


@lru_cache(maxsize=1)
def previsoes() -> pd.DataFrame:
    """`load_forecast()` traduzido: `serie`->`segmento` (p2/p3 -> P2/P3, igual
    ao seletor do dashboard), `data_alvo`->`ds`, `previsto`->`yhat`,
    `ic_inferior`/`ic_superior` -> `yhat_lower`/`yhat_upper`."""
    df = load_forecast().copy()
    df["segmento"] = df["serie"].map(_SEGMENTO_DASHBOARD).fillna(df["serie"])
    return df.rename(columns={
        "data_alvo": "ds", "previsto": "yhat", "ic_inferior": "yhat_lower", "ic_superior": "yhat_upper",
    })


@lru_cache(maxsize=1)
def backtest() -> pd.DataFrame:
    """`load_backtest()` traduzido pro contrato do dashboard (`segmento`,
    `modelo`, `ds`, `y`, `yhat`). Mantém só o horizonte D+7: os cortes do
    backtest já são espaçados de 7 em 7 dias, então usar D+7 dá um ponto por
    semana (bate com a leitura "últimas 8 semanas" do gráfico) sem duplicar
    cada corte com duas datas-alvo diferentes (D+1 e D+7)."""
    df = load_backtest().copy()
    df = df[df["horizonte"] == 7].copy()
    df["ds"] = df["corte"] + pd.to_timedelta(df["horizonte"], unit="D")
    df["segmento"] = df["serie"].map(_SEGMENTO_DASHBOARD).fillna(df["serie"])
    return df.rename(columns={"previsto": "yhat", "real": "y"})


def metricas() -> dict:
    """`load_metricas()` traduzido pro contrato do dashboard:
    `met["forecast"][segmento]["{modelo}_D+{h}"] = {"wape":..,"mae":..}` e
    `met["classificacao"]["risco_critico"/"risco_ola"] = {auc_roc, auc_pr,
    precision, recall, positivos_teste, n_teste, corte_temporal, limiar}`."""
    brutos = load_metricas()
    resultado: dict = {"forecast": {}, "classificacao": {}}

    wape_backtest = brutos.get("forecast", {}).get("wape_backtest", [])
    bt_df = load_backtest()
    for linha in wape_backtest:
        serie = linha["serie"]
        segmento = _SEGMENTO_DASHBOARD.get(serie, serie)
        modelo = linha["modelo"]
        horizonte = int(linha["horizonte"])
        wape = linha["wape"]

        sub = bt_df[(bt_df["serie"] == serie) & (bt_df["modelo"] == modelo) & (bt_df["horizonte"] == horizonte)].dropna(subset=["previsto"])
        mae = float((sub["previsto"] - sub["real"]).abs().mean()) if len(sub) else None

        resultado["forecast"].setdefault(segmento, {})[f"{modelo}_D+{horizonte}"] = {
            "wape": wape, "mae": mae,
        }
    resultado["forecast"]["_meta"] = {"cortes_backtest": config.BACKTEST_N_CORTES}

    nomes = {"modelo_a_critico": "risco_critico", "modelo_b_ola": "risco_ola"}
    for chave_interna, chave_dashboard in nomes.items():
        m = brutos.get("classificadores", {}).get(chave_interna, {})
        if not m:
            continue
        resultado["classificacao"][chave_dashboard] = {
            "auc_roc": m.get("auc_roc_teste"),
            "auc_pr": m.get("auc_pr"),
            "precision": m.get("precisao"),
            "recall": m.get("recall"),
            "positivos_teste": m.get("positivos_teste"),
            "n_teste": m.get("n_teste"),
            "corte_temporal": config.CLASSIFICADORES_CORTE_TREINO,
            "limiar": m.get("limiar_decisao"),
            "gap_treino_teste": m.get("gap_treino_teste"),
        }

    return resultado
