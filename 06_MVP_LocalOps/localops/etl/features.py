"""
etl/features.py — feature engineering sobre a série diária de incidentes.

Gera, para cada série prevista (total, p2, p3, kpi — ver config.SERIES_PREVISTAS),
um "feature store" em formato longo (uma linha por data x série) com:

  * y                 — valor observado naquele dia
  * lag_1/7/14        — memória da série (mesmo dia da semana anterior = lag_7)
  * media_movel_7/30  — médias móveis (calculadas sobre valores passados, sem leakage)
  * calendário         — dia da semana, fim de semana, mês, feriado nacional (BR)

Uso:
    python -m localops.etl.features
"""

from __future__ import annotations

import holidays
import pandas as pd

from localops import config
from localops.etl.build_dataset import run as build_dataset_run

SERIE_PARA_COLUNA = {
    "total": "total",
    "p2": "p2",
    "p3": "p3",
    "kpi": "kpi_elegivel",
}


def _features_calendario(datas: pd.Series) -> pd.DataFrame:
    br_feriados = holidays.Brazil(years=config.ANOS_FERIADOS)

    cal = pd.DataFrame({"ds": datas})
    cal["dia_semana"] = cal["ds"].dt.dayofweek  # 0 = segunda
    cal["fim_de_semana"] = cal["dia_semana"].isin([5, 6]).astype(int)
    cal["mes"] = cal["ds"].dt.month
    cal["dia_do_mes"] = cal["ds"].dt.day
    cal["feriado"] = cal["ds"].dt.date.isin(br_feriados).astype(int)
    return cal


def _lags_e_medias_moveis(y: pd.Series) -> pd.DataFrame:
    out = pd.DataFrame(index=y.index)
    for lag in config.LAGS_DIAS:
        out[f"lag_{lag}"] = y.shift(lag)
    for janela in config.MEDIAS_MOVEIS_DIAS:
        # shift(1) garante que a média móvel só usa dias estritamente anteriores.
        out[f"media_movel_{janela}"] = y.shift(1).rolling(janela).mean()
    return out


def construir_feature_store(serie_diaria: pd.DataFrame) -> pd.DataFrame:
    serie_diaria = serie_diaria.sort_values("data").reset_index(drop=True)
    cal = _features_calendario(serie_diaria["data"])

    partes = []
    for serie_nome, coluna in SERIE_PARA_COLUNA.items():
        y = serie_diaria[coluna].astype(float)
        bloco = pd.DataFrame({
            "data": serie_diaria["data"],
            "serie": serie_nome,
            "y": y,
        })
        bloco = pd.concat([bloco.reset_index(drop=True), _lags_e_medias_moveis(y).reset_index(drop=True)], axis=1)
        bloco = bloco.merge(cal, left_on="data", right_on="ds").drop(columns="ds")

        # Contexto adicional (não usado como alvo, mas útil como feature exógena
        # para o volume total: fração de abertura manual x monitoramento).
        bloco["manual"] = serie_diaria["manual"].values
        bloco["monitoramento"] = serie_diaria["monitoramento"].values

        partes.append(bloco)

    feature_store = pd.concat(partes, ignore_index=True)
    return feature_store


def run() -> pd.DataFrame:
    _, serie_diaria = build_dataset_run()
    feature_store = construir_feature_store(serie_diaria)
    feature_store.to_parquet(config.FEATURES_PARQUET_PATH, index=False)

    n_series = feature_store["serie"].nunique()
    print(f"[features] feature store com {len(feature_store):,} linhas "
          f"({n_series} séries x {feature_store['data'].nunique():,} dias)")
    print(f"[features] gravado em {config.FEATURES_PARQUET_PATH}")

    return feature_store


if __name__ == "__main__":
    run()
