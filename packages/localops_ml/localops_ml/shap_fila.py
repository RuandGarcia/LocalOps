"""Writes the noise-filter SHAP artefacts without rerunning the forecast.

Usage (repo root): .venv/Scripts/python.exe -m localops_ml.shap_fila
"""
from __future__ import annotations

import json

from localops_ml import config, dados, fila


def gravar(r: dict) -> None:
    resumo, por = fila.explicar(r)
    dados.escrever_atomico(config.ARTEFATOS / "fila_shap.json", json.dumps(resumo, ensure_ascii=False, indent=1))
    dados.escrever_atomico(config.ARTEFATOS / "fila_shap_alarmes.json",
                           json.dumps(por, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    r = fila.treinar(fila.montar_alarmes(dados.carregar_incidentes()))
    atual = json.loads((config.ARTEFATOS / "metricas.json").read_text(encoding="utf-8"))["fila"]
    # The SHAP must explain the published filter, not a retrain on a different base.
    assert r["metricas"]["limiar"] == atual["limiar"], "o filtro retreinado difere do publicado: rode o pipeline completo"
    gravar(r)
    print(f"SHAP gravado: {len(r['teste']):,} alarmes")
