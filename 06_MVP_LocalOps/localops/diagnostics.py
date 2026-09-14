"""
diagnostics.py — diagnóstico dos modelos, para orientar onde investir esforço
de melhoria.

  * Classificadores (Modelo A — crítico, Modelo B — violação de OLA):
    matriz de confusão (TP/TN/FP/FN), tabela de precisão/recall por limiar de
    decisão, e as categorias/equipes onde o modelo mais erra.

  * Previsão (Prophet/XGBoost/ensemble, por série e horizonte): análise de
    resíduo — MAE, RMSE, WAPE, viés (erro sistemático pra cima ou pra baixo),
    erro por dia da semana, e cobertura do intervalo de confiança de 95% do
    Prophet (idealmente perto de 95%).

Saídas:
  reports/diagnostico_classificadores.json
  reports/diagnostico_previsao.json
  reports/plots/*.png (matrizes de confusão + gráficos de resíduo)

Pré-requisito: rodar `python run_pipeline.py` pelo menos uma vez antes (este
script só lê os artefatos já gerados, não treina nada de novo).

Uso:
    python -m localops.diagnostics
"""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import matplotlib

matplotlib.use("Agg")  # sem interface gráfica — só salva os arquivos .png
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import confusion_matrix, f1_score, precision_score, recall_score

from localops import config, store
from localops.models import classify

PLOTS_DIR = config.REPORTS_DIR / "plots"
DIAG_CLASSIFICADORES_PATH = config.REPORTS_DIR / "diagnostico_classificadores.json"
DIAG_PREVISAO_PATH = config.REPORTS_DIR / "diagnostico_previsao.json"


# ---------------------------------------------------------------------------
# Classificadores — matriz de confusão
# ---------------------------------------------------------------------------

def _matriz_confusao(y_real, y_pred) -> dict:
    tn, fp, fn, tp = confusion_matrix(y_real, y_pred, labels=[0, 1]).ravel()
    return {
        "verdadeiro_positivo": int(tp), "falso_positivo": int(fp),
        "falso_negativo": int(fn), "verdadeiro_negativo": int(tn),
    }


def _tabela_limiares(y_real, proba) -> list[dict]:
    linhas = []
    for lim in np.arange(0.1, 1.0, 0.1):
        pred = (proba >= lim).astype(int)
        cm = _matriz_confusao(y_real, pred)
        linhas.append({
            "limiar": round(float(lim), 2),
            **cm,
            "precisao": round(float(precision_score(y_real, pred, zero_division=0)), 3),
            "recall": round(float(recall_score(y_real, pred, zero_division=0)), 3),
            "f1": round(float(f1_score(y_real, pred, zero_division=0)), 3),
        })
    return linhas


def _plot_matriz_confusao(cm: dict, titulo: str, arquivo: Path) -> None:
    matriz = np.array([
        [cm["verdadeiro_negativo"], cm["falso_positivo"]],
        [cm["falso_negativo"], cm["verdadeiro_positivo"]],
    ])
    fig, ax = plt.subplots(figsize=(4.2, 4.2))
    ax.imshow(matriz, cmap="Blues")
    for i in range(2):
        for j in range(2):
            cor = "white" if matriz[i, j] > matriz.max() / 2 else "black"
            ax.text(j, i, f"{matriz[i, j]:,}".replace(",", "."), ha="center", va="center", color=cor, fontsize=12)
    ax.set_xticks([0, 1]); ax.set_xticklabels(["Previsto: Não", "Previsto: Sim"])
    ax.set_yticks([0, 1]); ax.set_yticklabels(["Real: Não", "Real: Sim"])
    ax.set_title(titulo, fontsize=10)
    fig.tight_layout()
    fig.savefig(arquivo, dpi=130)
    plt.close(fig)


def _piores_grupos(teste: pd.DataFrame, coluna: str, min_n: int = 30) -> list[dict]:
    agr = teste.groupby(coluna).agg(
        n=("_erro", "size"),
        taxa_erro=("_erro", "mean"),
        falsos_negativos=("_fn", "sum"),
        falsos_positivos=("_fp", "sum"),
    )
    agr = agr[agr["n"] >= min_n].sort_values("taxa_erro", ascending=False)
    agr["taxa_erro"] = agr["taxa_erro"].round(3)
    return agr.head(5).reset_index().to_dict(orient="records")


def _diagnostico_classificador(nome_chave: str, arquivo_joblib: str, y_col: str, incidentes: pd.DataFrame) -> dict:
    pacote = joblib.load(config.MODELS_DIR / arquivo_joblib)
    pipeline, limiar, feature_cols = pacote["pipeline"], pacote["limiar"], pacote["feature_cols"]

    df = classify._preparar_features(incidentes)
    _, teste = classify._split_temporal(df)
    if nome_chave == "risco_violacao_ola":
        teste = teste[teste["elegivel_kpi"]].copy()
    else:
        teste = teste.copy()

    proba = pipeline.predict_proba(teste[feature_cols])[:, 1]
    y_real = teste[y_col].values
    pred = (proba >= limiar).astype(int)

    teste["_pred"] = pred
    teste["_erro"] = pred != y_real
    teste["_fn"] = (y_real == 1) & (pred == 0)
    teste["_fp"] = (y_real == 0) & (pred == 1)

    cm = _matriz_confusao(y_real, pred)
    _plot_matriz_confusao(cm, f"{nome_chave} (limiar={limiar:.2f})", PLOTS_DIR / f"confusao_{nome_chave}.png")

    return {
        "limiar_usado": round(float(limiar), 3),
        "n_teste": int(len(teste)),
        "taxa_base": round(float(np.mean(y_real)), 3),
        "matriz_confusao": cm,
        "tabela_por_limiar": _tabela_limiares(y_real, proba),
        "piores_categorias": _piores_grupos(teste, "categoria"),
        "piores_equipes": _piores_grupos(teste, "grupo_designado"),
    }


def diagnostico_classificadores() -> dict:
    incidentes = store.load_incidentes()
    resultado = {
        "risco_critico": _diagnostico_classificador(
            "risco_critico", "classificador_critico.joblib", "y_critico", incidentes
        ),
        "risco_violacao_ola": _diagnostico_classificador(
            "risco_violacao_ola", "classificador_ola.joblib", "ola_estourado", incidentes
        ),
    }
    DIAG_CLASSIFICADORES_PATH.write_text(
        json.dumps(resultado, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    return resultado


# ---------------------------------------------------------------------------
# Previsão — análise de resíduo
# ---------------------------------------------------------------------------

def _reconstruir_ensemble(sub: pd.DataFrame, peso: dict) -> pd.DataFrame:
    """A partir das previsões de prophet/xgboost por corte, reconstrói o que
    o ensemble teria previsto (mesmo peso usado na previsão de produção)."""
    pivot = sub.pivot_table(index="corte", columns="modelo", values="previsto")
    real = sub.groupby("corte")["real"].first()

    p_peso = peso.get("prophet", 0.5)
    x_peso = peso.get("xgboost", 0.5)
    ensemble = p_peso * pivot.get("prophet") + x_peso * pivot.get("xgboost")

    return pd.DataFrame({"corte": ensemble.index, "previsto": ensemble.values, "real": real.values})


def _metricas_residuo(real: np.ndarray, previsto: np.ndarray) -> dict:
    residuo = real - previsto
    mae = float(np.mean(np.abs(residuo)))
    rmse = float(np.sqrt(np.mean(residuo ** 2)))
    wape = float(np.sum(np.abs(residuo)) / np.sum(np.abs(real))) if np.sum(np.abs(real)) else float("nan")
    vies = float(np.mean(residuo))  # >0: modelo subestima em média; <0: superestima
    return {"mae": round(mae, 2), "rmse": round(rmse, 2), "wape": round(wape, 3), "vies_medio": round(vies, 2)}


def _erro_por_dia_semana(cortes: pd.Series, horizonte: int, real: np.ndarray, previsto: np.ndarray) -> dict:
    datas_alvo = pd.to_datetime(cortes) + pd.Timedelta(days=horizonte)
    df = pd.DataFrame({"dia_semana": datas_alvo.dt.dayofweek, "erro_abs": np.abs(real - previsto)})
    nomes = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
    resumo = df.groupby("dia_semana")["erro_abs"].mean().reindex(range(7))
    return {nomes[i]: (round(float(v), 1) if pd.notna(v) else None) for i, v in resumo.items()}


def _cobertura_ic(sub_prophet: pd.DataFrame) -> float | None:
    if "ic_inferior" not in sub_prophet.columns or sub_prophet["ic_inferior"].isna().all():
        return None
    dentro = (sub_prophet["real"] >= sub_prophet["ic_inferior"]) & (sub_prophet["real"] <= sub_prophet["ic_superior"])
    return round(float(dentro.mean()), 3)


def _plot_residuo(serie: str, horizonte: int, sub: pd.DataFrame, arquivo: Path) -> None:
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))

    for modelo, cor in (("prophet", "tab:blue"), ("xgboost", "tab:orange")):
        linha = sub[sub["modelo"] == modelo].sort_values("corte")
        if linha.empty:
            continue
        ax1.plot(linha["corte"], linha["previsto"], marker="o", label=f"previsto ({modelo})", color=cor)
    real_unico = sub.groupby("corte")["real"].first().sort_index()
    ax1.plot(real_unico.index, real_unico.values, marker="o", label="real", color="black", linewidth=2)
    ax1.set_title(f"Real vs. previsto — {serie} D+{horizonte}", fontsize=10)
    ax1.legend(fontsize=8)
    ax1.tick_params(axis="x", rotation=45)

    prophet_res = sub[sub["modelo"] == "prophet"]
    if not prophet_res.empty:
        residuo = prophet_res["real"] - prophet_res["previsto"]
        ax2.hist(residuo, bins=8, color="tab:blue", alpha=0.7)
        ax2.axvline(0, color="black", linestyle="--")
        ax2.set_title("Distribuição do resíduo (Prophet)\nreal - previsto", fontsize=10)

    fig.tight_layout()
    fig.savefig(arquivo, dpi=130)
    plt.close(fig)


def diagnostico_previsao() -> dict:
    backtest_df = store.load_backtest()
    metricas = store.load_metricas()
    pesos = metricas.get("forecast", {}).get("pesos_ensemble", {})

    resultado = {}
    for serie in sorted(backtest_df["serie"].unique()):
        resultado[serie] = {}
        for horizonte in sorted(backtest_df["horizonte"].unique()):
            sub = backtest_df[(backtest_df["serie"] == serie) & (backtest_df["horizonte"] == horizonte)].dropna(subset=["previsto"])
            if sub.empty:
                continue

            peso = pesos.get(serie, {}).get(str(horizonte), {"prophet": 0.5, "xgboost": 0.5})
            ensemble_df = _reconstruir_ensemble(sub, peso)

            bloco = {}
            for modelo_nome in ("baseline", "prophet", "xgboost"):
                linha = sub[sub["modelo"] == modelo_nome]
                if linha.empty:
                    continue
                metr = _metricas_residuo(linha["real"].values, linha["previsto"].values)
                metr["erro_por_dia_semana"] = _erro_por_dia_semana(
                    linha["corte"], horizonte, linha["real"].values, linha["previsto"].values
                )
                if modelo_nome == "prophet":
                    metr["cobertura_ic95"] = _cobertura_ic(linha)
                bloco[modelo_nome] = metr

            if not ensemble_df.empty and ensemble_df["previsto"].notna().any():
                bloco["ensemble"] = _metricas_residuo(
                    ensemble_df.dropna(subset=["previsto"])["real"].values,
                    ensemble_df.dropna(subset=["previsto"])["previsto"].values,
                )

            resultado[serie][f"d{horizonte}"] = bloco

            _plot_residuo(serie, horizonte, sub, PLOTS_DIR / f"residuo_{serie}_d{horizonte}.png")

    DIAG_PREVISAO_PATH.write_text(json.dumps(resultado, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return resultado


# ---------------------------------------------------------------------------
# Orquestração + impressão amigável no terminal
# ---------------------------------------------------------------------------

def _imprimir_classificadores(resultado: dict) -> None:
    metricas_chave = {"risco_critico": "modelo_a_critico", "risco_violacao_ola": "modelo_b_ola"}
    metricas = store.load_metricas().get("classificadores", {})

    for nome, dados in resultado.items():
        print(f"\n--- {nome} (limiar={dados['limiar_usado']}, taxa base={dados['taxa_base']:.1%}) ---")
        cm = dados["matriz_confusao"]
        print(f"  TP={cm['verdadeiro_positivo']}  FP={cm['falso_positivo']}  "
              f"FN={cm['falso_negativo']}  TN={cm['verdadeiro_negativo']}")
        print("  Categorias onde mais erra:", [g["categoria"] for g in dados["piores_categorias"]])
        print("  Equipes onde mais erra:", [g["grupo_designado"] for g in dados["piores_equipes"]])

        m = metricas.get(metricas_chave.get(nome, ""), {})
        if m.get("auc_roc_treino") is not None:
            print(f"  Overfitting: AUC treino={m['auc_roc_treino']:.3f}  AUC teste={m['auc_roc_teste']:.3f}  "
                  f"gap={m.get('gap_treino_teste')}")
        if m.get("importancia_por_grupo"):
            top3 = m["importancia_por_grupo"][:3]
            print("  Importância por grupo (top 3):", [f"{g['grupo']} ({g['importancia_pct']}%)" for g in top3])


def _imprimir_previsao(resultado: dict) -> None:
    for serie, horizontes in resultado.items():
        for horizonte, modelos in horizontes.items():
            print(f"\n--- {serie} {horizonte} ---")
            for modelo, metr in modelos.items():
                extra = f" | cobertura IC95={metr['cobertura_ic95']:.0%}" if metr.get("cobertura_ic95") is not None else ""
                print(f"  {modelo:9s} MAE={metr['mae']:>8.1f}  RMSE={metr['rmse']:>8.1f}  "
                      f"WAPE={metr['wape']:.1%}  viés={metr['vies_medio']:+.1f}{extra}")


def run() -> None:
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("Diagnóstico dos classificadores (matriz de confusão)")
    print("=" * 70)
    diag_class = diagnostico_classificadores()
    _imprimir_classificadores(diag_class)

    print("\n" + "=" * 70)
    print("Diagnóstico da previsão (análise de resíduo)")
    print("=" * 70)
    diag_prev = diagnostico_previsao()
    _imprimir_previsao(diag_prev)

    print(f"\n[diagnostics] detalhado em {DIAG_CLASSIFICADORES_PATH} e {DIAG_PREVISAO_PATH}")
    print(f"[diagnostics] gráficos (.png) em {PLOTS_DIR}")


if __name__ == "__main__":
    run()
