"""
models/recommender.py — recomendações operacionais automáticas.

Combina três sinais:
  1. Previsão (models/forecast.parquet) — picos de volume D+1/D+7 vs. a
     média móvel de 30 dias (nível de alerta por desvio-padrão, "média + 2σ").
  2. Carga por equipe — % dos incidentes dos últimos 30 dias por
     `grupo_designado`, e violações de OLA por equipe no mesmo período.
  3. Perfil de risco por categoria — % de incidentes P1/P2 por categoria,
     comparado à média geral, para categorias com volume relevante.

Saída: reports/recomendacoes.json — um dict com 4 chaves (contrato usado
pelo dashboard, lido direto do disco via `localops.store.ler_json`):

  - "recomendacoes": lista de recomendações em texto (prioridade/ação/motivo/
    impacto/público), a mesma ideia de antes.
  - "alertas": picos de volume previstos (nível/segmento/horizonte/data/
    previsto/variação), a versão "crua" (sem texto) do sinal 1 acima —
    usada no IncidentMap.
  - "carga_equipes": tabela por equipe (incidentes/% carga/medidos no KPI/
    violações/% críticos nos últimos 30 dias) — a versão "crua" do sinal 2.
  - "risco_categorias": tabela por categoria (% de incidentes P2) — a versão
    "crua" do sinal 3.

Uso:
    python -m localops.models.recommender
"""

from __future__ import annotations

import json

import pandas as pd

from localops import config
from localops.etl import build_dataset

JANELA_DIAS = 30
VOLUME_MINIMO_CATEGORIA = 30  # incidentes na janela, para a categoria ser considerada


def _nivel_alerta(previsto: float, media: float, desvio: float) -> str:
    if desvio == 0 or pd.isna(desvio):
        return "BAIXO"
    z = (previsto - media) / desvio
    if z >= 2:
        return "ALTO"
    if z >= 1:
        return "MÉDIO"
    return "BAIXO"


def _alertas_e_recomendacoes_previsao(
    forecast_df: pd.DataFrame, serie_diaria_por_serie: dict[str, pd.Series]
) -> tuple[list[dict], list[dict]]:
    alertas: list[dict] = []
    recs: list[dict] = []
    ensemble = forecast_df[forecast_df["modelo"] == "ensemble"]

    for _, linha in ensemble.iterrows():
        serie = linha["serie"]
        y_hist = serie_diaria_por_serie[serie].tail(90)
        media, desvio = y_hist.mean(), y_hist.std()
        nivel = _nivel_alerta(linha["previsto"], media, desvio)

        variacao = linha["variacao_pct_vs_media_30d"]
        data_alvo_str = pd.to_datetime(linha["data_alvo"]).strftime("%Y-%m-%d")

        alertas.append({
            "nivel": nivel,
            "segmento": serie,
            "horizonte": int(linha["horizonte"]),
            "data": data_alvo_str,
            "previsto": round(float(linha["previsto"]), 1),
            "variacao_pct": round(float(variacao), 1) if pd.notna(variacao) else None,
        })

        if nivel == "BAIXO":
            continue

        rotulo_serie = config.SERIES_PREVISTAS[serie]
        data_alvo_br = pd.to_datetime(linha["data_alvo"]).strftime("%d/%m/%Y")
        recs.append({
            "prioridade": 1 if nivel == "ALTO" else 2,
            "acao": (
                f"Reforçar plantão para {rotulo_serie.lower()} em {data_alvo_br} "
                f"(D+{int(linha['horizonte'])})"
            ),
            "motivo": (
                f"Previsão de {linha['previsto']:.0f} incidentes "
                f"({variacao:+.0f}% vs. média 30d), nível {nivel}"
            ),
            "impacto": "Reduz fila no horário de pico e protege o OLA de P1/P2/P3",
            "publico": "Gestor de Operações · Analista de NOC",
            "fonte": "previsao",
        })

    return alertas, recs


def _carga_equipes(incidentes: pd.DataFrame) -> pd.DataFrame:
    ultima_data = incidentes["aberto"].max()
    inicio = ultima_data - pd.Timedelta(days=JANELA_DIAS)
    janela = incidentes[incidentes["aberto"] >= inicio]

    total_janela = len(janela)
    carga_equipe = janela.groupby("grupo_designado").size().sort_values(ascending=False)
    medidos_equipe = (
        janela[janela["elegivel_kpi"]].groupby("grupo_designado").size().reindex(carga_equipe.index, fill_value=0)
    )
    violacoes_equipe = (
        janela[janela["ola_estourado"]].groupby("grupo_designado").size().reindex(carga_equipe.index, fill_value=0)
    )
    criticos_equipe = (
        janela[janela["prioridade_cod"].isin(["P1", "P2"])]
        .groupby("grupo_designado").size().reindex(carga_equipe.index, fill_value=0)
    )

    tabela = pd.DataFrame({
        "equipe": carga_equipe.index,
        "incidentes_30d": carga_equipe.values,
        "pct_carga": (carga_equipe.values / total_janela) if total_janela else 0.0,
        "kpi_30d": medidos_equipe.reindex(carga_equipe.index).values,
        "violacoes_30d": violacoes_equipe.reindex(carga_equipe.index).values,
        "pct_criticos": (criticos_equipe.reindex(carga_equipe.index).values / carga_equipe.values.clip(min=1)),
    })
    return tabela


def _recomendacoes_equipe(tabela_carga: pd.DataFrame) -> list[dict]:
    recs = []
    if len(tabela_carga):
        top = tabela_carga.iloc[0]
        if top["pct_carga"] * 100 >= 50:
            recs.append({
                "prioridade": 1,
                "acao": f"Redistribuir triagem automática de {top['equipe']} (concentra {top['pct_carga'] * 100:.0f}% dos incidentes em {JANELA_DIAS}d)",
                "motivo": f"{int(top['incidentes_30d']):,} incidentes em {JANELA_DIAS} dias; {top['pct_criticos'] * 100:.0f}% críticos".replace(",", "."),
                "impacto": "Equilibra carga entre equipes e reduz risco de sobrecarga",
                "publico": "Gestor de Operações",
                "fonte": "carga_equipe",
            })

    for _, linha in tabela_carga.iterrows():
        if linha["violacoes_30d"] >= 5:
            pct_violacoes = linha["violacoes_30d"] / max(linha["kpi_30d"], 1) * 100
            recs.append({
                "prioridade": 2,
                "acao": f"Revisar escalonamento e runbooks de {linha['equipe']}",
                "motivo": f"{int(linha['violacoes_30d'])} violações de OLA em {JANELA_DIAS} dias ({pct_violacoes:.0f}% dos incidentes medidos)",
                "impacto": "Reduz violações de OLA e risco de perda de KPI mensal",
                "publico": "Engenheiro de SRE",
                "fonte": "violacao_ola_equipe",
            })

    return recs


def _risco_categorias(incidentes: pd.DataFrame) -> pd.DataFrame:
    ultima_data = incidentes["aberto"].max()
    inicio = ultima_data - pd.Timedelta(days=JANELA_DIAS)
    janela = incidentes[
        (incidentes["aberto"] >= inicio) & (incidentes["categoria"] != "Não informado")
    ]
    if janela.empty:
        return pd.DataFrame(columns=["categoria", "total", "pct_p2"])

    resumo = janela.groupby("categoria").agg(
        total=("numero", "count"),
        pct_p2=("prioridade_cod", lambda s: (s == "P2").mean()),
    ).reset_index()
    resumo = resumo[resumo["total"] >= VOLUME_MINIMO_CATEGORIA].sort_values("pct_p2", ascending=False)
    return resumo


def _recomendacoes_categoria(tabela_risco: pd.DataFrame, media_geral_p2: float) -> list[dict]:
    recs = []
    alvo = tabela_risco[tabela_risco["pct_p2"] >= media_geral_p2 * 2]
    for _, linha in alvo.head(5).iterrows():
        recs.append({
            "prioridade": 2,
            "acao": f"Monitoramento priorizado e runbook para '{linha['categoria']}'",
            "motivo": (
                f"{linha['pct_p2'] * 100:.0f}% dos {int(linha['total'])} incidentes são P2 "
                f"(média geral {media_geral_p2 * 100:.0f}%)"
            ),
            "impacto": "Antecipação de incidentes críticos recorrentes",
            "publico": "Engenheiro de SRE · Analista de NOC",
            "fonte": "risco_categoria",
        })
    return recs


def run() -> dict:
    incidentes, serie_diaria = build_dataset.run()
    forecast_df = pd.read_parquet(config.FORECAST_PARQUET_PATH)

    serie_diaria_por_serie = {
        "total": serie_diaria.set_index("data")["total"],
        "p2": serie_diaria.set_index("data")["p2"],
        "p3": serie_diaria.set_index("data")["p3"],
        "kpi": serie_diaria.set_index("data")["kpi_elegivel"],
    }

    alertas, recs_previsao = _alertas_e_recomendacoes_previsao(forecast_df, serie_diaria_por_serie)

    tabela_carga = _carga_equipes(incidentes)
    recs_equipe = _recomendacoes_equipe(tabela_carga)

    tabela_risco = _risco_categorias(incidentes)
    janela_p2 = incidentes[incidentes["aberto"] >= incidentes["aberto"].max() - pd.Timedelta(days=JANELA_DIAS)]
    media_geral_p2 = (janela_p2["prioridade_cod"] == "P2").mean() if len(janela_p2) else 0.0
    recs_categoria = _recomendacoes_categoria(tabela_risco, media_geral_p2)

    recomendacoes = sorted(recs_previsao + recs_equipe + recs_categoria, key=lambda r: r["prioridade"])

    resultado = {
        "recomendacoes": recomendacoes,
        "alertas": alertas,
        "carga_equipes": tabela_carga.round(4).to_dict(orient="records"),
        "risco_categorias": tabela_risco.round(4).to_dict(orient="records"),
    }

    config.RECOMMENDATIONS_JSON_PATH.write_text(
        json.dumps(resultado, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )

    print(f"[recommender] {len(recomendacoes)} recomendações, {len(alertas)} alertas, "
          f"{len(tabela_carga)} equipes, {len(tabela_risco)} categorias avaliadas")
    print(f"[recommender] gravado em {config.RECOMMENDATIONS_JSON_PATH}")

    return resultado


if __name__ == "__main__":
    run()
