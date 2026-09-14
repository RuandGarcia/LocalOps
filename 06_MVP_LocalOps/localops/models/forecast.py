"""
models/forecast.py — previsão de volume de incidentes D+1 e D+7.

Para cada série (total, p2, p3, kpi — config.SERIES_PREVISTAS):
  1. Treina Prophet (sazonalidade semanal/anual + feriados BR + IC 95%).
  2. Treina XGBoost em modo "direto" (um modelo por horizonte), usando as
     features de localops/etl/features.py (sem vazamento: cada linha só usa
     informação disponível até o dia anterior ao alvo).
  3. Faz backtest rolling-origin (config.BACKTEST_N_CORTES cortes, um por
     semana) para medir o WAPE de cada modelo e de um baseline sazonal
     ingênuo (mesmo dia da semana anterior).
  4. Monta um ensemble ponderado pelo inverso do WAPE de cada modelo.
  5. Gera a previsão de produção para D+1 e D+7 a partir do último dia
     disponível na base.

Saídas: models/forecast.parquet, models/backtest.parquet, reports/metricas.json
(chave "forecast").

Uso:
    python -m localops.models.forecast
"""

from __future__ import annotations

import json
import warnings
from dataclasses import dataclass

import holidays
import numpy as np
import pandas as pd
from prophet import Prophet
from xgboost import XGBRegressor

from localops import config
from localops.etl import features as features_mod

warnings.filterwarnings("ignore", module="prophet")
warnings.filterwarnings("ignore", module="cmdstanpy")

FEATURE_COLS = [
    "lag_1", "lag_7", "lag_14", "media_movel_7", "media_movel_30",
    "dia_semana", "fim_de_semana", "mes", "dia_do_mes", "feriado",
]

XGB_PARAMS = dict(
    n_estimators=300,
    max_depth=4,
    learning_rate=0.05,
    subsample=0.8,
    colsample_bytree=0.8,
    random_state=config.RANDOM_STATE,
    objective="reg:squarederror",
)


# ---------------------------------------------------------------------------
# Preparação
# ---------------------------------------------------------------------------

def _preparar_series(feature_store: pd.DataFrame) -> dict[str, pd.DataFrame]:
    series = {}
    for nome in config.SERIES_PREVISTAS:
        df = feature_store[feature_store["serie"] == nome].sort_values("data").reset_index(drop=True)
        df["y_d7"] = df["y"].shift(-6)  # alvo D+7 (ver docstring do módulo)
        series[nome] = df
    return series


def _wape(y_real: np.ndarray, y_previsto: np.ndarray) -> float:
    y_real = np.asarray(y_real, dtype=float)
    y_previsto = np.asarray(y_previsto, dtype=float)
    denom = np.sum(np.abs(y_real))
    if denom == 0:
        return float("nan")
    return float(np.sum(np.abs(y_real - y_previsto)) / denom)


# ---------------------------------------------------------------------------
# Modelos individuais
# ---------------------------------------------------------------------------

def _prophet_fit(df_treino: pd.DataFrame) -> Prophet:
    br_feriados = holidays.Brazil(years=config.ANOS_FERIADOS)
    feriados_df = pd.DataFrame({
        "holiday": "feriado_nacional",
        "ds": pd.to_datetime(list(br_feriados.keys())),
    })

    modelo = Prophet(
        weekly_seasonality=True,
        yearly_seasonality=True,
        daily_seasonality=False,
        holidays=feriados_df,
        interval_width=0.95,
        seasonality_mode="additive",
    )
    ds_treino = df_treino.rename(columns={"data": "ds", "y": "y"})[["ds", "y"]]
    modelo.fit(ds_treino)
    return modelo


def _prophet_previsao(modelo: Prophet, ultima_data: pd.Timestamp, horizonte: int) -> tuple[float, float, float]:
    futuro = modelo.make_future_dataframe(periods=7, include_history=False)
    pred = modelo.predict(futuro)
    pred = pred.set_index("ds")
    alvo = ultima_data + pd.Timedelta(days=horizonte)
    linha = pred.loc[alvo]
    return float(linha["yhat"]), float(linha["yhat_lower"]), float(linha["yhat_upper"])


def _xgb_fit(df_treino: pd.DataFrame, coluna_alvo: str) -> XGBRegressor:
    treino = df_treino.dropna(subset=FEATURE_COLS + [coluna_alvo])
    modelo = XGBRegressor(**XGB_PARAMS)
    modelo.fit(treino[FEATURE_COLS], treino[coluna_alvo])
    return modelo


def _linha_features(df_serie: pd.DataFrame, data: pd.Timestamp) -> pd.DataFrame | None:
    linha = df_serie[df_serie["data"] == data]
    if linha.empty or linha[FEATURE_COLS].isna().any(axis=1).iloc[0]:
        return None
    return linha[FEATURE_COLS]


def _linha_features_virtual(df_serie: pd.DataFrame, data_alvo: pd.Timestamp) -> pd.DataFrame:
    """Constrói a linha de features para um dia além do fim da base (produção),
    usando o mesmo cálculo de lags/médias móveis/calendário de features.py."""
    y = df_serie.set_index("data")["y"]
    br_feriados = holidays.Brazil(years=config.ANOS_FERIADOS)

    linha = {
        "lag_1": y.loc[data_alvo - pd.Timedelta(days=1)],
        "lag_7": y.loc[data_alvo - pd.Timedelta(days=7)],
        "lag_14": y.loc[data_alvo - pd.Timedelta(days=14)],
        "media_movel_7": y.loc[data_alvo - pd.Timedelta(days=7):data_alvo - pd.Timedelta(days=1)].mean(),
        "media_movel_30": y.loc[data_alvo - pd.Timedelta(days=30):data_alvo - pd.Timedelta(days=1)].mean(),
        "dia_semana": data_alvo.dayofweek,
        "fim_de_semana": int(data_alvo.dayofweek in (5, 6)),
        "mes": data_alvo.month,
        "dia_do_mes": data_alvo.day,
        "feriado": int(data_alvo.date() in br_feriados),
    }
    return pd.DataFrame([linha])


def _baseline_sazonal(df_serie: pd.DataFrame, data_alvo: pd.Timestamp, horizonte: int) -> float:
    """Baseline ingênuo: repete o valor do mesmo dia da semana no período anterior
    (lag_7 para D+1 medido a partir do dia anterior, lag_7 também serve de proxy
    para D+7 pois é exatamente o valor observado 7 dias antes)."""
    y = df_serie.set_index("data")["y"]
    ref = data_alvo - pd.Timedelta(days=7)
    return float(y.loc[ref]) if ref in y.index else float("nan")


# ---------------------------------------------------------------------------
# Backtest rolling-origin
# ---------------------------------------------------------------------------

@dataclass
class ResultadoBacktest:
    serie: str
    corte: pd.Timestamp
    horizonte: int
    modelo: str
    previsto: float
    real: float
    ic_inferior: float | None = None
    ic_superior: float | None = None


def _backtest_serie(nome_serie: str, df_serie: pd.DataFrame) -> list[ResultadoBacktest]:
    ultima_data = df_serie["data"].max()
    cortes = [ultima_data - pd.Timedelta(days=7 * (k + 1)) for k in range(config.BACKTEST_N_CORTES)]
    cortes = sorted(cortes)

    resultados: list[ResultadoBacktest] = []

    for corte in cortes:
        treino = df_serie[df_serie["data"] <= corte]
        if len(treino) < 120:
            continue

        prophet_modelo = _prophet_fit(treino)
        xgb_d1 = _xgb_fit(treino, "y")
        xgb_d7 = _xgb_fit(treino, "y_d7")

        for horizonte in config.HORIZONTES_PREVISAO:
            data_alvo = corte + pd.Timedelta(days=horizonte)
            linha_real = df_serie[df_serie["data"] == data_alvo]
            if linha_real.empty:
                continue
            real = float(linha_real["y"].iloc[0])

            # Prophet (guarda também o IC 95%, usado depois para checar cobertura)
            try:
                previsto_p, ic_lo, ic_hi = _prophet_previsao(prophet_modelo, corte, horizonte)
            except KeyError:
                previsto_p, ic_lo, ic_hi = float("nan"), None, None
            resultados.append(
                ResultadoBacktest(nome_serie, corte, horizonte, "prophet", previsto_p, real, ic_lo, ic_hi)
            )

            # XGBoost (linha de referência para previsão é sempre corte+1;
            # o modelo D+7 já foi treinado para prever 6 dias além dessa linha)
            linha_feat = _linha_features(df_serie, corte + pd.Timedelta(days=1))
            if linha_feat is not None:
                modelo_xgb = xgb_d1 if horizonte == 1 else xgb_d7
                previsto_x = float(modelo_xgb.predict(linha_feat)[0])
            else:
                previsto_x = float("nan")
            resultados.append(ResultadoBacktest(nome_serie, corte, horizonte, "xgboost", previsto_x, real))

            # Baseline sazonal
            previsto_b = _baseline_sazonal(df_serie, data_alvo, horizonte)
            resultados.append(ResultadoBacktest(nome_serie, corte, horizonte, "baseline", previsto_b, real))

    return resultados


# ---------------------------------------------------------------------------
# Orquestração
# ---------------------------------------------------------------------------

def run() -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    feature_store = features_mod.run()
    series = _preparar_series(feature_store)

    # --- Backtest ---
    todos_resultados: list[ResultadoBacktest] = []
    for nome, df_serie in series.items():
        print(f"[forecast] backtest da série '{nome}'...")
        todos_resultados.extend(_backtest_serie(nome, df_serie))

    backtest_df = pd.DataFrame([r.__dict__ for r in todos_resultados])
    backtest_df.to_parquet(config.BACKTEST_PARQUET_PATH, index=False)

    wape_tabela = (
        backtest_df.dropna(subset=["previsto"])
        .groupby(["serie", "horizonte", "modelo"])
        .apply(lambda g: _wape(g["real"], g["previsto"]), include_groups=False)
        .rename("wape")
        .reset_index()
    )

    # --- Pesos do ensemble (inverso do WAPE de prophet/xgboost) ---
    pesos: dict[str, dict[int, dict[str, float]]] = {}
    for (serie, horizonte), grupo in wape_tabela[wape_tabela["modelo"].isin(["prophet", "xgboost"])].groupby(["serie", "horizonte"]):
        inv = {row["modelo"]: 1.0 / max(row["wape"], 1e-6) for _, row in grupo.iterrows()}
        soma = sum(inv.values())
        pesos.setdefault(serie, {})[horizonte] = {m: v / soma for m, v in inv.items()}

    # --- Previsão de produção (D+1 e D+7 a partir do último dia da base) ---
    linhas_forecast = []
    for nome, df_serie in series.items():
        ultima_data = df_serie["data"].max()
        prophet_modelo = _prophet_fit(df_serie)
        xgb_d1 = _xgb_fit(df_serie, "y")
        xgb_d7 = _xgb_fit(df_serie, "y_d7")

        primeiro_dia_futuro = ultima_data + pd.Timedelta(days=1)
        linha_virtual = _linha_features_virtual(df_serie, primeiro_dia_futuro)

        for horizonte in config.HORIZONTES_PREVISAO:
            data_alvo = ultima_data + pd.Timedelta(days=horizonte)

            p_yhat, p_lo, p_hi = _prophet_previsao(prophet_modelo, ultima_data, horizonte)
            modelo_xgb = xgb_d1 if horizonte == 1 else xgb_d7
            x_yhat = float(modelo_xgb.predict(linha_virtual)[0])

            peso = pesos.get(nome, {}).get(horizonte, {"prophet": 0.5, "xgboost": 0.5})
            ensemble = peso.get("prophet", 0.5) * p_yhat + peso.get("xgboost", 0.5) * x_yhat

            media_30d = df_serie["y"].tail(30).mean()
            variacao_pct = (ensemble - media_30d) / media_30d * 100 if media_30d else float("nan")

            for modelo_nome, valor, lo, hi in (
                ("prophet", p_yhat, p_lo, p_hi),
                ("xgboost", x_yhat, None, None),
                ("ensemble", ensemble, None, None),
            ):
                linhas_forecast.append({
                    "serie": nome,
                    "horizonte": horizonte,
                    "data_alvo": data_alvo,
                    "modelo": modelo_nome,
                    "previsto": max(valor, 0.0),
                    "ic_inferior": lo,
                    "ic_superior": hi,
                    "media_30d": media_30d,
                    "variacao_pct_vs_media_30d": variacao_pct if modelo_nome == "ensemble" else None,
                    "peso_prophet": peso.get("prophet"),
                    "peso_xgboost": peso.get("xgboost"),
                })

    forecast_df = pd.DataFrame(linhas_forecast)
    forecast_df.to_parquet(config.FORECAST_PARQUET_PATH, index=False)

    metricas = {
        "wape_backtest": wape_tabela.to_dict(orient="records"),
        "pesos_ensemble": pesos,
        "gerado_em": pd.Timestamp.utcnow().isoformat(),
    }
    _salvar_metricas("forecast", metricas)

    print("[forecast] WAPE por série/horizonte/modelo:")
    print(wape_tabela.pivot_table(index=["serie", "horizonte"], columns="modelo", values="wape").round(3))
    print(f"[forecast] previsões de produção gravadas em {config.FORECAST_PARQUET_PATH}")

    return forecast_df, backtest_df, metricas


def _salvar_metricas(chave: str, valor: dict) -> None:
    dados = {}
    if config.METRICS_JSON_PATH.exists():
        dados = json.loads(config.METRICS_JSON_PATH.read_text(encoding="utf-8"))
    dados[chave] = valor
    config.METRICS_JSON_PATH.write_text(
        json.dumps(dados, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )


if __name__ == "__main__":
    run()
