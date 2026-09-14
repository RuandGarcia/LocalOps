"""
run_pipeline.py — orquestra o pipeline completo do LocalOps:

    1. ETL          (localops.etl.build_dataset)   xlsx -> SQLite/parquet
    2. Features     (localops.etl.features)        lags, médias móveis, calendário
    3. Forecast     (localops.models.forecast)      Prophet + XGBoost D+1/D+7 + backtest
    4. Classificadores (localops.models.classify)   risco crítico e risco de OLA
    5. SHAP         (localops.models.explain)       waterfall + importância global
    6. Recomendações (localops.models.recommender)  ações operacionais priorizadas

Ao final, os artefatos usados pelo dashboard/API estão em data/, models/ e
reports/. Tempo esperado: ~2-4 min (a maior parte é o backtest do Prophet).

Uso:
    python run_pipeline.py
"""

from __future__ import annotations

import time

from localops.models import classify, explain, forecast, recommender


def _etapa(nome: str, func) -> float:
    print(f"\n{'=' * 70}\n{nome}\n{'=' * 70}")
    t0 = time.time()
    func()
    dt = time.time() - t0
    print(f"[run_pipeline] '{nome}' concluída em {dt:.1f}s")
    return dt


def main() -> None:
    inicio = time.time()

    # forecast.run() já chama features.run(), que já chama build_dataset.run() —
    # rodamos aqui de novo isoladamente só para as mensagens/artefatos ficarem
    # explícitos passo a passo, o custo extra é pequeno (ETL é rápido).
    tempos = {
        "1/4 · Previsão (ETL + features + Prophet/XGBoost + backtest + ensemble)": _etapa(
            "1/4 · Previsão (ETL + features + Prophet/XGBoost + backtest + ensemble)", forecast.run
        ),
        "2/4 · Classificadores de risco (crítico / violação de OLA)": _etapa(
            "2/4 · Classificadores de risco (crítico / violação de OLA)", classify.run
        ),
        "3/4 · Explicabilidade (SHAP)": _etapa("3/4 · Explicabilidade (SHAP)", explain.run),
        "4/4 · Recomendações operacionais": _etapa("4/4 · Recomendações operacionais", recommender.run),
    }

    total = time.time() - inicio
    print(f"\n{'=' * 70}")
    print(f"[run_pipeline] pipeline completo em {total:.1f}s")
    print("[run_pipeline] artefatos gerados:")
    print("  data/localops.db, data/incidentes.parquet, data/features_serie_diaria.parquet")
    print("  models/forecast.parquet, models/backtest.parquet,")
    print("  models/classificador_critico.joblib, models/classificador_ola.joblib")
    print("  reports/metricas.json, reports/shap.json, reports/recomendacoes.json")
    print("[run_pipeline] próximo passo: streamlit run dashboard/app.py")
    print("=" * 70)


if __name__ == "__main__":
    main()
