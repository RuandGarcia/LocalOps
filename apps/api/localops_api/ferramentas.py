"""Read-only tools over the pipeline artefacts. The same functions back the REST API, the MCP server
the OpenClaw agent calls, and the deterministic fallback. Every answer carries its source.

"dia" is the replay "today" (YYYY-MM-DD, 2025): nothing after that day is used, except the `real`
field, which shows what actually happened and is labeled as such.
"""
from __future__ import annotations

import json
import math
import os
from functools import lru_cache
from pathlib import Path

import pandas as pd

ARTEFATOS = Path(os.environ.get("LOCALOPS_ARTEFATOS", Path(__file__).resolve().parents[3] / "artefatos"))
SERIES = {"total": "volume total de registros", "humano": "registros que exigiram uma pessoa",
          "p2": "registros P2", "p3": "registros P3", "kpi": "registros que entraram no KPI"}
DIMENSOES = ("produto", "categoria", "equipe", "item")
DIAS_SEMANA = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]


class ErroFerramenta(ValueError):
    """Bad argument; the message is safe to show to the model and the user."""


_carimbo = {"mtime": 0.0}


def _recarregar_se_mudou() -> None:
    """The pipeline worker rewrites the artefacts after an ingestion, metricas.json last: drop the cache then."""
    try:
        m = (ARTEFATOS / "metricas.json").stat().st_mtime
    except FileNotFoundError:
        return
    if m != _carimbo["mtime"]:
        _carimbo["mtime"] = m
        _ler_cache.cache_clear()
        _df_cache.cache_clear()


@lru_cache
def _ler_cache(nome: str):
    return json.loads((ARTEFATOS / nome).read_text(encoding="utf-8"))


@lru_cache
def _df_cache(nome: str) -> pd.DataFrame:
    return pd.DataFrame(_ler_cache(nome))


def _ler(nome: str):
    _recarregar_se_mudou()
    return _ler_cache(nome)


def _df(nome: str) -> pd.DataFrame:
    _recarregar_se_mudou()
    return _df_cache(nome)


def _dia(dia: str | None, minimo: str = "2025-01-01") -> pd.Timestamp:
    serie = _df("serie_diaria.json")
    ultimo = pd.Timestamp(serie["data"].max())
    if not dia:
        return ultimo
    try:
        d = pd.Timestamp(dia).normalize()
    except ValueError as e:
        raise ErroFerramenta(f"data inválida: {dia!r}; use AAAA-MM-DD") from e
    if not pd.Timestamp(minimo) <= d <= ultimo:
        raise ErroFerramenta(f"a base vai de {minimo} a {ultimo:%Y-%m-%d}; {dia} está fora")
    return d


def _r(x: float, casas: int = 1) -> float:
    return round(float(x), casas)


# --- 1. forecast --------------------------------------------------------------------------------

def prever(serie: str = "humano", dia: str | None = None) -> dict:
    """D+1 and D+7 forecast made on `dia`, with the 80% interval, the model's December error and the
    context that explains the number (recent level, same weekday last week, holiday)."""
    if serie not in SERIES:
        raise ErroFerramenta(f"série {serie!r} não existe; use uma de {list(SERIES)}")
    d = _dia(dia, minimo="2025-09-30")
    metricas = _ler("metricas.json")["previsao"]["series"][serie]
    rep = _df("previsao_replay.json")
    fin = _df("previsao_final.json")
    s = _df("serie_diaria.json").set_index("data")[serie]
    s.index = pd.to_datetime(s.index)
    hist = s[:d]

    saida = []
    for h in (1, 7):
        alvo = d + pd.Timedelta(days=h)
        linha = rep[(rep["serie"] == serie) & (rep["h"] == h) & (rep["origem"] == f"{d:%Y-%m-%d}")]
        if linha.empty:
            linha = fin[(fin["serie"] == serie) & (fin["h"] == h) & (fin["origem"] == f"{d:%Y-%m-%d}")]
        if linha.empty:
            continue
        l = linha.iloc[0]
        m = metricas[f"D+{h}"]
        saida.append({
            "horizonte": f"D+{h}", "dia_alvo": f"{alvo:%Y-%m-%d}", "dia_semana_alvo": DIAS_SEMANA[alvo.dayofweek],
            "previsto": _r(l["previsto"]), "faixa_80": [_r(l["ic_inf"]), _r(l["ic_sup"])],
            "real": None if pd.isna(l.get("real")) else int(l["real"]),
            "modelo": m["modelo_escolhido"], "erro_wape_dez25": m["wape_teste_escolhido"],
            "erro_baseline_dez25": m["wape_teste_baseline"], "bate_baseline": m["bate_baseline_no_teste"],
            "contexto": {
                "mesmo_dia_semana_passada": int(hist.get(alvo - pd.Timedelta(days=7), float("nan")))
                if (alvo - pd.Timedelta(days=7)) in hist.index else None,
                "media_7d": _r(hist.iloc[-7:].mean()),
                "media_28d": _r(hist.iloc[-28:].mean()),
                "tendencia_7d_vs_28d_pct": _r((hist.iloc[-7:].mean() / max(hist.iloc[-28:].mean(), 1) - 1) * 100),
            },
        })
    return {"serie": serie, "descricao": SERIES[serie], "hoje": f"{d:%Y-%m-%d}", "previsoes": saida,
            "fonte": "walk-forward diário; modelo escolhido em out–nov/2025, erro medido em dez/2025"}


# --- 2. noise filter -----------------------------------------------------------------------------

_NOMES_FILA = {
    "tpl": "o tipo de alarme (texto sem números)",
    "n24h_ci": "quantos alarmes o mesmo item teve nas 24 h anteriores",
    "n24h_tpl": "quantos alarmes do mesmo tipo nas 24 h anteriores",
    "n1h_tpl": "rajada do mesmo tipo na última hora",
    "hora": "a hora do dia",
    "dow": "o dia da semana",
}


def fila_ruido(dia: str | None = None) -> dict:
    """What the noise filter does to the monitoring alarm queue: a December day, or the whole month."""
    met = _ler("metricas.json")["fila"]
    diaria = _df("fila_diaria.json")
    imp = met["importancia_shap_media"]
    total = sum(imp.values()) or 1
    resumo = {
        "auc_roc": met["auc_roc_teste"], "recall_alvo": met["recall_alvo"], "recall_obtido": met["recall_teste"],
        "fila_por_dia_antes": met["fila_por_dia_antes"], "fila_por_dia_depois": met["fila_por_dia_depois"],
        "reducao_fila_pct": _r(met["reducao_fila"] * 100), "exigiram_pessoa_e_ficaram_fora": met["humanos_perdidos_teste"],
        # Share of the mean |SHAP|: the alarm type alone is about 73%, so the agent must not list factors as equals.
        "o_que_mais_pesa": [{"fator": _NOMES_FILA.get(k, k), "peso_pct": _r(v / total * 100)} for k, v in imp.items()],
    }
    out = {"mes_de_teste": "2025-12", "resumo_dez25": resumo,
           "maiores_templates": _ler("fila_templates.json")[:8],
           "fonte": "filtro de ruído; treino set–out, limiar escolhido em nov, teste em dez/2025"}
    if dia:
        d = _dia(dia)
        linha = diaria[diaria["data"] == f"{d:%Y-%m-%d}"]
        if linha.empty:
            out["observacao_dia"] = (f"o filtro só foi testado em dezembro/2025 (antes disso o modelo estava em treino); "
                                     f"não há resultado para {d:%Y-%m-%d}, use o resumo de dezembro")
        else:
            out["dia"] = linha.iloc[0].to_dict()
    return out


# --- 3. annual KPI target ------------------------------------------------------------------------

# Official yearly goals (Dicionário de Dados v2, "Metas Anuais de KPI"); same table as apps/web/src/data/meta.ts.
_LIMITES = {
    ("violacoes", "P2"): (31, 35, 39, 45, 53), ("violacoes", "P3"): (201, 230, 263, 290, 320),
    ("volume", "P2"): (4585, 5388, 6168, 6252, 6336), ("volume", "P3"): (19489, 22116, 22524, 23892, 24276),
}


def _faixas(a, b, c, d, e):
    return [("150%", 0, a - 1), ("125%", a, b), ("100%", b + 1, c), ("75%", c + 1, d), ("50%", d + 1, e), ("0%", e + 1, math.inf)]


def _phi(z: float) -> float:
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def meta_kpi(dia: str | None = None) -> dict:
    """Year-end projection of both annual KPIs (violations and handled volume) for P2 and P3, as of `dia`:
    observed so far plus the remaining days at the last 90 days' pace, with the probability per band."""
    d = _dia(dia)
    k = _df("kpi_diario.json")
    k["data"] = pd.to_datetime(k["data"])
    fim_ano = pd.Timestamp(f"{d.year}-12-31")
    restantes = (fim_ano - d).days
    out = []
    for kpi in ("violacoes", "volume"):
        for pri in ("P2", "P3"):
            s = k[k["prioridade"] == pri].set_index("data")[kpi]
            ate = s[:d]
            recorte = ate.iloc[-90:]
            # With one day of history (1st of January) the sample variance is NaN: treat it as Poisson (var = mean).
            m, v = recorte.mean(), (recorte.var(ddof=1) if len(recorte) > 1 else 0.0)
            media = ate.sum() + m * restantes
            dp = math.sqrt(max(v, m) * restantes)
            probs = []
            for rot, lo, hi in _faixas(*_LIMITES[(kpi, pri)]):
                sup = 1.0 if hi == math.inf else _phi((hi + 0.5 - media) / dp) if dp else float(media <= hi)
                inf = 0.0 if lo == 0 else _phi((lo - 0.5 - media) / dp) if dp else float(media < lo)
                probs.append({"faixa": rot, "de": lo, "ate": None if hi == math.inf else hi, "prob": _r(max(0, sup - inf), 3)})
            teto100 = _faixas(*_LIMITES[(kpi, pri)])[2][2]
            out.append({
                "kpi": kpi, "prioridade": pri, "ate_hoje": int(ate.sum()), "dias_restantes": restantes,
                "ritmo_semanal": _r(m * 7), "projecao_31_12": _r(media, 0),
                "faixa_80": [max(int(ate.sum()), round(media - 1.2816 * dp)), round(media + 1.2816 * dp)],
                "faixa_mais_provavel": max(probs, key=lambda p: p["prob"])["faixa"],
                "teto_para_100pct": teto100, "folga_ate_teto_100pct": int(teto100 - ate.sum()),
                "probabilidades": probs,
            })
    return {"hoje": f"{d:%Y-%m-%d}", "kpis": out,
            "regra": "menos é melhor nas duas metas; as faixas vêm do dicionário de dados (150% a 0%)",
            "fonte": "projeção da meta: acumulado + ritmo dos últimos 90 dias"}


# --- 4. trends -----------------------------------------------------------------------------------

def tendencias(dimensao: str = "produto", inicio: str = "2025-12", fim: str | None = None,
               metrica: str = "humano", top: int = 10, dia: str | None = None) -> dict:
    """Ranking of products, categories, teams or configuration items in a month range (AAAA-MM), cut at
    `dia`, with the change against the same stretch of the months just before. metrica: total, humano or violacoes."""
    if dimensao not in DIMENSOES:
        raise ErroFerramenta(f"dimensão {dimensao!r} não existe; use uma de {list(DIMENSOES)}")
    if metrica not in ("total", "humano", "violacoes"):
        raise ErroFerramenta("métrica deve ser total, humano ou violacoes")
    hoje = _dia(dia)
    fim = fim or inicio
    try:
        ini, fim_mes = pd.Period(inicio, "M"), pd.Period(fim, "M")
    except ValueError as e:
        raise ErroFerramenta("use meses no formato AAAA-MM") from e
    primeiro = pd.Period("2025-01", "M")
    if not primeiro <= ini <= fim_mes or fim_mes > hoje.to_period("M"):
        raise ErroFerramenta(f"use meses entre {primeiro} e {hoje:%Y-%m} (hoje no replay é {hoje:%Y-%m-%d})")
    corte = min(fim_mes.end_time.normalize(), hoje)
    k = fim_mes.ordinal - ini.ordinal + 1
    a_ini, a_fim = ini.start_time - pd.DateOffset(months=k), corte - pd.DateOffset(months=k)
    t = _df("tendencias_diarias.json")
    t = t[t["dimensao"] == dimensao]
    datas = pd.to_datetime(t["dia"])
    atual = t[(datas >= ini.start_time) & (datas <= corte)].groupby("valor")[metrica].sum()
    tem_anterior = a_ini >= primeiro.start_time
    ant = t[(datas >= a_ini) & (datas <= a_fim)].groupby("valor")[metrica].sum() if tem_anterior else pd.Series(dtype=int)
    rank = atual.sort_values(ascending=False).head(max(1, min(int(top), 30)))
    linhas = [{"valor": v, metrica: int(x), "periodo_anterior": int(ant.get(v, 0)),
               "variacao_pct": None if ant.get(v, 0) == 0 else _r((x / ant[v] - 1) * 100)} for v, x in rank.items()]
    return {"dimensao": dimensao, "metrica": metrica, "hoje": f"{hoje:%Y-%m-%d}",
            "periodo": [f"{ini.start_time:%Y-%m-%d}", f"{corte:%Y-%m-%d}"],
            "periodo_anterior": [f"{a_ini:%Y-%m-%d}", f"{a_fim:%Y-%m-%d}"] if tem_anterior else None,
            "total_periodo": int(atual.sum()), "ranking": linhas,
            "observacao": "produtos, categorias, equipes e itens vêm anonimizados na base da Locaweb; "
                          "o período para no hoje do replay e o anterior cobre o mesmo trecho dos meses de antes",
            "fonte": "base real 2025, agregada por dia"}


# --- 5. model confidence -------------------------------------------------------------------------

def confianca() -> dict:
    """How good the models really are, including where they lose to the simple baseline."""
    m = _ler("metricas.json")
    prev = {s: {h: {k: v[k] for k in ("modelo_escolhido", "wape_teste_escolhido", "wape_teste_baseline", "bate_baseline_no_teste")}
                | {"cobertura_faixa_80": v["intervalo"]["cobertura_teste"]} for h, v in hs.items()}
            for s, hs in m["previsao"]["series"].items()}
    return {"previsao": prev, "fila": {k: m["fila"][k] for k in ("auc_roc_teste", "auc_pr_teste", "recall_alvo", "recall_teste",
                                                                  "fila_por_dia_antes", "fila_por_dia_depois")},
            "descontinuados": m["descontinuados"], "gerado_em": m["gerado_em"],
            "fonte": "artefatos/metricas.json; teste em dez/2025, mês que não entrou em nenhuma escolha"}


# --- 6. explainability (SHAP of the noise filter) -------------------------------------------------

_DIAS = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
_FONTE_SHAP = "SHAP do filtro de ruído (XGBoost), teste em dez/2025"


def _ler_shap(nome: str):
    try:
        return _ler(nome)
    except FileNotFoundError as e:
        raise ErroFerramenta("a explicabilidade (SHAP) ainda não foi gerada neste servidor") from e


def explicabilidade() -> dict:
    """What drives the noise filter (SHAP on Dec/2025): each factor's weight, the alarm types that push the
    chance of needing a person up or down, and 3 example alarms. Also says why the forecast has no SHAP."""
    s = _ler_shap("fila_shap.json")
    return {**{k: s[k] for k in ("mes", "n_alarmes", "base_prob", "taxa_humano", "limiar", "exemplos", "previsao")},
            "importancia": [{"fator": _NOMES_FILA[i["feature"]], "peso_pct": i["peso_pct"]} for i in s["importancia"]],
            "tipos_que_sobem": s["tipos"]["sobem"][:5], "tipos_que_descem": s["tipos"]["descem"][:5],
            "fonte": _FONTE_SHAP}


def explicar_alarme(numero: str) -> dict:
    """Why one December monitoring alarm got its chance of needing a person: each factor's SHAP push
    (log-odds; positive raises the chance), biggest first."""
    s = _ler_shap("fila_shap_alarmes.json")
    chave = numero.strip().upper()
    v = s["alarmes"].get(chave)
    if v is None:
        raise ErroFerramenta(f"não achei {numero!r}: só explico alarmes de monitoramento de dez/2025 (o mês de teste)")
    valores = [s["templates"][v[0]], f"{v[1]}h", _DIAS[v[2]], *v[3:6]]
    fatores = [{"fator": _NOMES_FILA[f], "valor": x, "shap": sh, "efeito": "sobe" if sh > 0 else "desce"}
               for f, x, sh in zip(s["features"], valores, v[6:12])]
    return {"numero": chave, "prob_humano": v[12], "na_fila": v[12] >= _ler("metricas.json")["fila"]["limiar"],
            "base_prob": round(1 / (1 + math.exp(-s["base"])), 4),
            "fatores": sorted(fatores, key=lambda x: -abs(x["shap"])), "fonte": _FONTE_SHAP}


def historico(serie: str, dia: str, dias: int = 28) -> list[tuple[str, float]]:
    """The last `dias` days of a series up to `dia`, never after it: the report's chart."""
    if serie not in SERIES:
        raise ErroFerramenta(f"série desconhecida: {serie}")
    s = _df("serie_diaria.json")
    s = s[pd.to_datetime(s["data"]) <= _dia(dia)].tail(dias)
    return [(str(x)[:10], float(v)) for x, v in zip(s["data"], s[serie])]


FERRAMENTAS = {f.__name__: f for f in (prever, fila_ruido, meta_kpi, tendencias, confianca, explicabilidade, explicar_alarme)}
