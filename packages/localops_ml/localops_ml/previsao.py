"""D+1 / D+7 forecast with a daily walk-forward.

Each origin trains only on days up to the origin (inclusive) and predicts origin + h. Candidates:
seasonal naive, 7-day mean, 4-week seasonal mean, direct XGBoost and Prophet. Per series and
horizon, the model with the lowest WAPE on SELECAO is chosen; its relative errors there give a split
conformal interval. Everything is then measured on TESTE, which played no part in any choice.
"""
from __future__ import annotations

import logging
import math
import warnings

import holidays
import numpy as np
import pandas as pd
from xgboost import XGBRegressor

from localops_ml import config

logging.getLogger("cmdstanpy").setLevel(logging.WARNING)
logging.getLogger("prophet").setLevel(logging.WARNING)
warnings.filterwarnings("ignore", category=FutureWarning)

UM_DIA = pd.Timedelta(days=1)
FERIADOS = holidays.Brazil(years=range(2024, 2027))
FERIADOS_TS = pd.to_datetime(list(FERIADOS.keys()))


def _feriado(datas: pd.DatetimeIndex) -> np.ndarray:
    return datas.isin(FERIADOS_TS).astype(int)


# --- candidates: each gets the history up to the origin and returns {h: forecast for origin + h} ---

def ingenuo_sazonal(hist: pd.Series, hs: list[int]) -> dict[int, float]:
    o = hist.index[-1]
    return {h: float(hist.get(o + (h - 7) * UM_DIA, np.nan)) for h in hs}


def media_7d(hist: pd.Series, hs: list[int]) -> dict[int, float]:
    m = float(hist.iloc[-7:].mean())
    return {h: m for h in hs}


def sazonal_4sem(hist: pd.Series, hs: list[int]) -> dict[int, float]:
    o = hist.index[-1]
    out = {}
    for h in hs:
        vals = [hist.get(o + (h - 7 * k) * UM_DIA) for k in range(1, 5)]
        vals = [v for v in vals if v is not None]
        out[h] = float(np.mean(vals)) if vals else np.nan
    return out


def _matriz_xgb(y: pd.Series, h: int) -> pd.DataFrame:
    """Features at day t to predict t + h. Uses only y up to t; the target is shifted inside `y`."""
    alvo = y.index + h * UM_DIA
    return pd.DataFrame({
        "y0": y,
        "y1": y.shift(1),
        "m7": y.rolling(7, min_periods=7).mean(),
        "m28": y.rolling(28, min_periods=7).mean(),
        "mesmo_dia_sem_passada": y.shift(7 - h),  # value at t + h − 7, already observed at t (h ≤ 7)
        "dow_alvo": alvo.dayofweek,
        "feriado_alvo": _feriado(alvo),
        "alvo": y.shift(-h),
    }, index=y.index)


def xgboost(hist: pd.Series, hs: list[int]) -> dict[int, float]:
    out = {}
    for h in hs:
        m = _matriz_xgb(hist, h)
        treino = m.dropna()
        if len(treino) < 14:
            out[h] = np.nan
            continue
        x_cols = [c for c in m.columns if c != "alvo"]
        modelo = XGBRegressor(n_estimators=200, max_depth=3, learning_rate=0.05, subsample=0.9,
                              random_state=config.RANDOM_STATE, n_jobs=1)
        modelo.fit(treino[x_cols], treino["alvo"])
        out[h] = float(modelo.predict(m[x_cols].iloc[[-1]])[0])
    return out


def prophet(hist: pd.Series, hs: list[int]) -> dict[int, float]:
    from prophet import Prophet

    feriados = pd.DataFrame({"holiday": "feriado_br", "ds": FERIADOS_TS})
    m = Prophet(weekly_seasonality=True, yearly_seasonality=False, daily_seasonality=False,
                holidays=feriados, uncertainty_samples=0)
    m.fit(pd.DataFrame({"ds": hist.index, "y": hist.values}))
    futuro = pd.DataFrame({"ds": [hist.index[-1] + h * UM_DIA for h in hs]})
    prev = m.predict(futuro)["yhat"].to_numpy()
    return {h: float(v) for h, v in zip(hs, prev)}


MODELOS = {
    "ingenuo_sazonal": ingenuo_sazonal,
    "media_7d": media_7d,
    "sazonal_4sem": sazonal_4sem,
    "xgboost": xgboost,
    "prophet": prophet,
}
BASELINE = "ingenuo_sazonal"
# Forecast combination: median of the candidates above at the same origin (each one leak-free).
COMBINACAO = "mediana"


def _com_mediana(linhas: list[dict]) -> list[dict]:
    df = pd.DataFrame(linhas)
    med = df.groupby(["serie", "origem", "h", "alvo", "treino_ate"], as_index=False)["previsto"].median()
    return linhas + med.assign(modelo=COMBINACAO).to_dict("records")


def prever_na_origem(y: pd.Series, serie: str, origem: pd.Timestamp, modelos=MODELOS) -> list[dict]:
    """All candidates at one origin. `y` may extend past the origin: it is cut here."""
    hist = y[config.INICIO_TREINO[serie]:origem]
    hs = list(config.HORIZONTES)
    linhas = []
    for nome, f in modelos.items():
        for h, v in f(hist, hs).items():
            linhas.append({"serie": serie, "modelo": nome, "origem": origem, "h": h,
                           "alvo": origem + h * UM_DIA, "previsto": max(v, 0.0) if not math.isnan(v) else v,
                           "treino_ate": hist.index[-1]})
    return _com_mediana(linhas) if len(modelos) > 1 else linhas


def walk_forward(serie_diaria: pd.DataFrame, modelos=MODELOS) -> pd.DataFrame:
    ini = pd.Timestamp(config.SELECAO[0]) - max(config.HORIZONTES) * UM_DIA
    fim = pd.Timestamp(config.TESTE[1]) - UM_DIA
    linhas = []
    for serie in config.SERIES:
        y = serie_diaria[serie]
        for origem in pd.date_range(ini, fim, freq="D"):
            linhas.extend(prever_na_origem(y, serie, origem, modelos))
        print(f"  walk-forward {serie}: ok", flush=True)
    wf = pd.DataFrame(linhas)
    wf = wf[(wf["alvo"] >= config.SELECAO[0]) & (wf["alvo"] <= config.TESTE[1])].copy()
    real = serie_diaria.stack().rename("real").reset_index().rename(columns={"level_1": "serie", "data": "alvo"})
    wf = wf.merge(real, on=["serie", "alvo"], how="left")
    wf["janela"] = np.where(wf["alvo"] <= pd.Timestamp(config.SELECAO[1]), "selecao", "teste")
    return wf


def wape(real, prev) -> float:
    real, prev = np.asarray(real, float), np.asarray(prev, float)
    ok = ~np.isnan(prev)
    return float(np.abs(real[ok] - prev[ok]).sum() / max(np.abs(real[ok]).sum(), 1e-9))


def quantil_conformal(erros_rel: np.ndarray, nivel: float = config.NIVEL_INTERVALO) -> float:
    e = np.sort(erros_rel[~np.isnan(erros_rel)])
    k = min(len(e), math.ceil((len(e) + 1) * nivel))
    return float(e[k - 1])


def escolher_e_calibrar(wf: pd.DataFrame) -> tuple[dict, pd.DataFrame]:
    """Choose per series × horizon on SELECAO, calibrate the interval there, report on TESTE."""
    metricas, replay = {}, []
    for (serie, h), g in wf.groupby(["serie", "h"]):
        sel, tes = g[g["janela"] == "selecao"], g[g["janela"] == "teste"]
        wape_sel = {m: wape(x["real"], x["previsto"]) for m, x in sel.groupby("modelo")}
        wape_tes = {m: wape(x["real"], x["previsto"]) for m, x in tes.groupby("modelo")}
        escolhido = min(wape_sel, key=wape_sel.get)

        s = sel[sel["modelo"] == escolhido]
        q = quantil_conformal((np.abs(s["real"] - s["previsto"]) / s["previsto"].clip(lower=1)).to_numpy())
        e = g[g["modelo"] == escolhido].copy()
        e["ic_inf"] = (e["previsto"] * (1 - q)).clip(lower=0)
        e["ic_sup"] = e["previsto"] * (1 + q)
        et = e[e["janela"] == "teste"]
        dentro = (et["real"] >= et["ic_inf"]) & (et["real"] <= et["ic_sup"])

        metricas.setdefault(serie, {})[f"D+{h}"] = {
            "modelo_escolhido": escolhido,
            "wape_selecao": {k: round(v, 4) for k, v in sorted(wape_sel.items(), key=lambda kv: kv[1])},
            "wape_teste": {k: round(v, 4) for k, v in sorted(wape_tes.items(), key=lambda kv: kv[1])},
            "wape_teste_escolhido": round(wape_tes[escolhido], 4),
            "wape_teste_baseline": round(wape_tes[BASELINE], 4),
            "bate_baseline_no_teste": bool(wape_tes[escolhido] < wape_tes[BASELINE]),
            "intervalo": {"nivel": config.NIVEL_INTERVALO, "erro_relativo_q": round(q, 4),
                          "cobertura_teste": round(float(dentro.mean()), 4), "n_teste": int(len(et))},
        }
        replay.append(e.assign(q=q))
    return metricas, pd.concat(replay, ignore_index=True)


def previsao_final(serie_diaria: pd.DataFrame, metricas: dict) -> pd.DataFrame:
    """Forecast from the last day of the base with the chosen model and calibrated interval."""
    origem = serie_diaria.index.max()
    linhas = []
    for serie in config.SERIES:
        for h in config.HORIZONTES:
            info = metricas[serie][f"D+{h}"]
            todas = pd.DataFrame(prever_na_origem(serie_diaria[serie], serie, origem))
            prev = float(todas[(todas["modelo"] == info["modelo_escolhido"]) & (todas["h"] == h)]["previsto"].iloc[0])
            q = info["intervalo"]["erro_relativo_q"]
            linhas.append({"serie": serie, "h": h, "origem": origem, "alvo": origem + h * UM_DIA,
                           "modelo": info["modelo_escolhido"], "previsto": prev,
                           "ic_inf": max(prev * (1 - q), 0.0), "ic_sup": prev * (1 + q)})
    return pd.DataFrame(linhas)
