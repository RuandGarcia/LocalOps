"""S2 pipeline: base → walk-forward forecast → noise filter → artefacts for the API and the agent.

Usage (repo root):  .venv/Scripts/python.exe -m localops_ml.run [--recriar-base]
"""
from __future__ import annotations

import json
import sys
import time

import pandas as pd

from localops_ml import agregados, config, dados, fila, previsao, shap_fila


def _json(nome: str, obj) -> None:
    config.ARTEFATOS.mkdir(parents=True, exist_ok=True)
    dados.escrever_atomico(config.ARTEFATOS / nome, json.dumps(obj, ensure_ascii=False, indent=1, default=str))


def _registros(df: pd.DataFrame) -> list[dict]:
    out = df.copy()
    for c in out.select_dtypes("datetime").columns:
        out[c] = out[c].dt.strftime("%Y-%m-%d")
    return json.loads(out.round(3).to_json(orient="records", force_ascii=False))


def main() -> None:
    t0 = time.time()
    df = dados.carregar_incidentes(recriar="--recriar-base" in sys.argv)
    s = dados.serie_diaria(df)
    print(f"base: {len(df):,} registros · série {s.index.min():%d/%m/%Y} → {s.index.max():%d/%m/%Y}", flush=True)

    print("previsão (walk-forward diário)...", flush=True)
    wf = previsao.walk_forward(s)
    wf.to_parquet(config.DADOS / "walk_forward.parquet", index=False)
    metricas_prev, replay = previsao.escolher_e_calibrar(wf)
    final = previsao.previsao_final(s, metricas_prev)

    print("fila (filtro de ruído)...", flush=True)
    a = fila.montar_alarmes(df)
    r = fila.treinar(a)
    r["teste"].drop(columns=["descricao"]).to_parquet(config.FILA_ALARMES, index=False)

    _json("previsao_replay.json", _registros(replay[["serie", "h", "origem", "alvo", "previsto", "ic_inf", "ic_sup", "real", "janela"]]))
    _json("previsao_final.json", _registros(final))
    _json("serie_diaria.json", _registros(s.reset_index()))
    _json("fila_diaria.json", _registros(fila.resumo_diario(r["teste"])))
    _json("fila_templates.json", _registros(fila.resumo_templates(r["teste"])))
    # Compact on purpose: the panel loads it on the queue page (about 1.5 MB).
    dados.escrever_atomico(config.ARTEFATOS / "fila_alarmes_dez.json",
                           json.dumps(fila.alarmes_painel(r["teste"]), ensure_ascii=False, separators=(",", ":")))
    shap_fila.gravar(r)
    agregados.gravar(df)
    # Last on purpose: the API reloads its cache when this file changes, so everything else is already in place.
    _json("metricas.json", {
        "gerado_em": pd.Timestamp.now().isoformat(timespec="seconds"),
        "base": {"registros": int(len(df)), "inicio_serie": s.index.min(), "fim_serie": s.index.max()},
        "previsao": {"janelas": {"selecao": config.SELECAO, "teste": config.TESTE},
                     "inicio_treino": config.INICIO_TREINO, "series": metricas_prev},
        "fila": r["metricas"],
        "descontinuados": {
            "classificador_risco_critico": "usava categoria/produto/subcategoria, preenchidos durante o atendimento (vazamento M6)",
            "classificador_risco_ola": "mesmo vazamento (M6) e limiar escolhido no teste (M7)",
            "ensemble_prophet_xgboost": "pesos de 8 pontos de backtest com vazamento no D+7 (M1–M3)",
        },
    })
    print(f"pronto em {(time.time() - t0) / 60:.1f} min · artefatos em {config.ARTEFATOS}")


if __name__ == "__main__":
    main()
