"""
models/explain.py — explicabilidade SHAP para os modelos de previsão e de
classificação de risco.

Gera reports/shap.json no formato que o dashboard (`dashboard/views.py`) lê
direto do disco via `localops.store.ler_json` — duas seções:

  * "forecast": um waterfall por série × horizonte (`total`/`P2`/`P3` × D+1/D+7)
    — decompõe a previsão do XGBoost feature a feature.
  * "risco_critico" / "risco_ola": para cada classificador, a importância
    global (mean |SHAP|, top 10 features transformadas) e os 5 incidentes de
    maior risco previsto no conjunto de teste, com os drivers (SHAP) de cada
    um — os cartões "exemplos de maior risco previsto" do dashboard.

Uso:
    python -m localops.models.explain
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import shap

from localops import config, store
from localops.etl import build_dataset, features as features_mod
from localops.models import classify as classify_mod
from localops.models import forecast

# ---------------------------------------------------------------------------
# 1. Waterfall da previsão de volume (Prophet/XGBoost ensemble — parte XGBoost)
# ---------------------------------------------------------------------------

ROTULOS_FORECAST = {
    "lag_1": "valor de ontem",
    "lag_7": "valor há 7 dias",
    "lag_14": "valor há 14 dias",
    "media_movel_7": "média móvel 7 dias",
    "media_movel_30": "média móvel 30 dias",
    "dia_semana": "dia da semana",
    "fim_de_semana": "fim de semana?",
    "mes": "mês",
    "dia_do_mes": "dia do mês",
    "feriado": "feriado nacional?",
}

# series internas (config.SERIES_PREVISTAS) -> chave usada pelo dashboard
_SEGMENTO_DASHBOARD = {"total": "total", "p2": "P2", "p3": "P3"}


def _waterfall_previsao(nome_serie: str, df_serie: pd.DataFrame) -> dict[str, dict]:
    resultado = {}
    ultima_data = df_serie["data"].max()
    primeiro_dia_futuro = ultima_data + pd.Timedelta(days=1)
    linha_virtual = forecast._linha_features_virtual(df_serie, primeiro_dia_futuro)

    for horizonte, coluna_alvo in ((1, "y"), (7, "y_d7")):
        modelo = forecast._xgb_fit(df_serie, coluna_alvo)
        explainer = shap.TreeExplainer(modelo)
        shap_values = explainer(linha_virtual)

        base_value = float(shap_values.base_values[0])
        contribuicoes = [
            {
                "rotulo": ROTULOS_FORECAST.get(feat, feat),
                "valor": float(linha_virtual.iloc[0][feat]),
                "shap": float(shap_values.values[0][i]),
            }
            for i, feat in enumerate(forecast.FEATURE_COLS)
        ]
        contribuicoes.sort(key=lambda c: abs(c["shap"]), reverse=True)
        previsto = base_value + sum(c["shap"] for c in contribuicoes)
        data_alvo = ultima_data + pd.Timedelta(days=horizonte)

        chave = f"{_SEGMENTO_DASHBOARD.get(nome_serie, nome_serie)}_h{horizonte}"
        resultado[chave] = {
            "ds_previsto": str(data_alvo.date()),
            "base": round(base_value, 1),
            "previsto": round(max(previsto, 0.0), 1),
            "outras_features": 0.0,  # todas as features já entram em "contribuicoes"
            "contribuicoes": [
                {**c, "valor": round(c["valor"], 2), "shap": round(c["shap"], 1)}
                for c in contribuicoes
            ],
        }

    return resultado


# ---------------------------------------------------------------------------
# 2. Importância global (SHAP) para os modelos de previsão — usado só pra
#    conferência/relatório interno, o dashboard não lê esta chave hoje.
# ---------------------------------------------------------------------------

def _importancia_global_forecast(series: dict[str, pd.DataFrame]) -> dict:
    resultado = {}
    for nome, df_serie in series.items():
        modelo = forecast._xgb_fit(df_serie, "y")
        treino = df_serie.dropna(subset=forecast.FEATURE_COLS + ["y"])
        explainer = shap.TreeExplainer(modelo)
        shap_values = explainer(treino[forecast.FEATURE_COLS])
        importancia = np.abs(shap_values.values).mean(axis=0)
        ranking = sorted(
            zip(forecast.FEATURE_COLS, importancia.tolist()), key=lambda x: x[1], reverse=True
        )
        resultado[nome] = [{"feature": f, "importancia_media_abs": round(v, 2)} for f, v in ranking]
    return resultado


# ---------------------------------------------------------------------------
# 3. SHAP dos classificadores de risco — importância global + exemplos
# ---------------------------------------------------------------------------

ROTULOS_NUMERICAS = {
    "hora_abertura": "hora de abertura",
    "dia_semana_abertura": "dia da semana (abertura)",
    "fim_de_semana_abertura": "aberto no fim de semana?",
    "mes_abertura": "mês de abertura",
}

AMOSTRA_MAX_IMPORTANCIA = 3000
N_EXEMPLOS = 5


def _rotulo_feature_transformada(nome: str) -> str:
    if nome.startswith("texto__"):
        token = nome[len("texto__"):]
        return f'descrição contém "{token}"'
    if nome.startswith("categoricas__"):
        resto = nome[len("categoricas__"):]
        for c in classify_mod.CATEGORICAS:
            if resto.startswith(c + "_"):
                return f"{c} = {resto[len(c) + 1:]}"
        return resto
    if nome.startswith("remainder__"):
        col = nome[len("remainder__"):]
        return ROTULOS_NUMERICAS.get(col, col)
    return nome


def _valor_feature_original(nome: str, linha: pd.Series):
    if nome.startswith("texto__"):
        token = nome[len("texto__"):]
        texto = str(linha.get(classify_mod.TEXTO_COL, "") or "")
        return "presente" if token.lower() in texto.lower() else "ausente"
    if nome.startswith("categoricas__"):
        resto = nome[len("categoricas__"):]
        for c in classify_mod.CATEGORICAS:
            if resto.startswith(c + "_"):
                return linha.get(c)
        return "-"
    if nome.startswith("remainder__"):
        col = nome[len("remainder__"):]
        return linha.get(col)
    return "-"


def _shap_classificador(pacote: dict, incidentes: pd.DataFrame, y_col: str, apenas_elegiveis: bool) -> dict:
    pipeline = pacote["pipeline"]
    df = classify_mod._preparar_features(incidentes)
    _, teste = classify_mod._split_temporal(df)
    if apenas_elegiveis:
        teste = teste[teste["elegivel_kpi"]]
    teste = teste.reset_index(drop=True)

    x_teste = teste[classify_mod.FEATURE_COLS]
    proba = pipeline.predict_proba(x_teste)[:, 1]

    pre = pipeline.named_steps["preprocessador"]
    clf = pipeline.named_steps["classificador"]
    x_transformado = pre.transform(x_teste)
    if hasattr(x_transformado, "toarray"):
        x_transformado = x_transformado.toarray()
    nomes = pre.get_feature_names_out()

    explainer = shap.TreeExplainer(clf)

    # Importância global: amostra (SHAP em toda a base de teste seria caro à
    # toa — a média já estabiliza bem com alguns milhares de linhas).
    rng = np.random.default_rng(config.RANDOM_STATE)
    tamanho_amostra = min(AMOSTRA_MAX_IMPORTANCIA, len(x_teste))
    idx_amostra = rng.choice(len(x_teste), size=tamanho_amostra, replace=False)
    shap_amostra = np.asarray(explainer(x_transformado[idx_amostra]).values)
    if shap_amostra.ndim == 3:
        shap_amostra = shap_amostra[:, :, -1]
    importancia_media = np.abs(shap_amostra).mean(axis=0)
    ranking = sorted(zip(nomes, importancia_media), key=lambda x: x[1], reverse=True)[:10]
    importancia = [{"rotulo": _rotulo_feature_transformada(n), "valor": round(float(v), 4)} for n, v in ranking]

    # Exemplos: os incidentes de maior probabilidade prevista no teste,
    # com os 3 principais drivers (SHAP) de cada um.
    top_idx = np.argsort(-proba)[:N_EXEMPLOS]
    shap_exemplos = np.asarray(explainer(x_transformado[top_idx]).values)
    if shap_exemplos.ndim == 3:
        shap_exemplos = shap_exemplos[:, :, -1]

    exemplos = []
    for pos, i in enumerate(top_idx):
        linha = teste.iloc[int(i)]
        shap_linha = shap_exemplos[pos]
        top3 = np.argsort(-np.abs(shap_linha))[:3]
        drivers = [
            {
                "rotulo": _rotulo_feature_transformada(nomes[j]),
                "valor": _valor_feature_original(nomes[j], linha),
                "shap": round(float(shap_linha[j]), 3),
            }
            for j in top3
        ]
        exemplos.append({
            "numero": str(linha["numero"]),
            "equipe": linha["grupo_designado"],
            "categoria": linha["categoria"],
            "prioridade": linha["prioridade_cod"],
            "proba": round(float(proba[int(i)]), 3),
            "real": bool(linha[y_col]),
            "drivers": drivers,
        })

    return {"importancia": importancia, "exemplos": exemplos}


# ---------------------------------------------------------------------------
# Orquestração
# ---------------------------------------------------------------------------

def run() -> dict:
    incidentes, serie_diaria = build_dataset.run()
    feature_store = features_mod.construir_feature_store(serie_diaria)
    series = forecast._preparar_series(feature_store)

    print("[explain] calculando waterfall da previsão (total, P2, P3)...")
    waterfall = {}
    for nome_serie in ("total", "p2", "p3"):
        waterfall.update(_waterfall_previsao(nome_serie, series[nome_serie]))

    print("[explain] calculando importância global dos modelos de previsão...")
    importancia_forecast = _importancia_global_forecast(series)

    print("[explain] calculando SHAP do classificador de risco crítico (Modelo A)...")
    pacote_a = store.load_classificador_critico()
    shap_a = _shap_classificador(pacote_a, incidentes, "y_critico", apenas_elegiveis=False)

    print("[explain] calculando SHAP do classificador de violação de OLA (Modelo B)...")
    pacote_b = store.load_classificador_ola()
    shap_b = _shap_classificador(pacote_b, incidentes, "ola_estourado", apenas_elegiveis=True)

    resultado = {
        "forecast": waterfall,
        "importancia_global_forecast": importancia_forecast,
        "risco_critico": shap_a,
        "risco_ola": shap_b,
    }

    config.SHAP_JSON_PATH.write_text(
        json.dumps(resultado, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    print(f"[explain] gravado em {config.SHAP_JSON_PATH}")

    return resultado


if __name__ == "__main__":
    run()
