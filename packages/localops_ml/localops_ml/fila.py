"""Noise filter: at the moment a monitoring alarm opens, how likely is it to need a person?

Features come only from fields that exist at opening (config.CAMPOS_NA_ABERTURA) and from earlier
alarms. Trained on FILA_TREINO, threshold picked on FILA_VALIDACAO for the target recall, measured on
FILA_TESTE.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import average_precision_score, roc_auc_score

from localops_ml import config

FEATURES = ["tpl", "hora", "dow", "n1h_tpl", "n24h_tpl", "n24h_ci"]
# Which opening fields each feature is derived from (checked by the anti-leak test).
ORIGEM_DAS_FEATURES = {
    "tpl": {"descricao"},
    "hora": {"aberto"},
    "dow": {"aberto"},
    "n1h_tpl": {"descricao", "aberto"},
    "n24h_tpl": {"descricao", "aberto"},
    "n24h_ci": {"item_config", "aberto"},
}


def template(descricao: pd.Series) -> pd.Series:
    """Alarm text without numbers: 'Disk I/O is overloaded on IC00152' → '... on IC#'."""
    return descricao.fillna("").str.replace(r"\d+", "#", regex=True).str.slice(0, 60)


def montar_alarmes(df: pd.DataFrame) -> pd.DataFrame:
    a = df[df["monitoramento"] & (df["aberto"] >= config.FILA_TREINO[0])][
        ["numero", "aberto", "descricao", "item_config", "humano"]
    ].sort_values("aberto").reset_index(drop=True)
    a["tpl"] = template(a["descricao"])
    a["ci"] = a["item_config"].fillna("(sem ci)")
    a["hora"] = a["aberto"].dt.hour
    a["dow"] = a["aberto"].dt.dayofweek
    # Counts of the same template / CI in the window before this alarm (closed="left": past only).
    a = a.set_index("aberto")
    um = pd.Series(1.0, index=a.index)
    for chave, janela, nome in (("tpl", "1h", "n1h_tpl"), ("tpl", "24h", "n24h_tpl"), ("ci", "24h", "n24h_ci")):
        a[nome] = um.groupby(a[chave].to_numpy()).transform(
            lambda s: s.rolling(janela, closed="left").count()
        ).fillna(0).to_numpy()
    return a.reset_index()


def _janela(a: pd.DataFrame, jan: tuple[str, str]) -> pd.DataFrame:
    return a[(a["aberto"] >= jan[0]) & (a["aberto"] < pd.Timestamp(jan[1]) + pd.Timedelta(days=1))]


def _x(d: pd.DataFrame, categorias: pd.Index) -> pd.DataFrame:
    x = d[FEATURES].copy()
    x["tpl"] = pd.Categorical(x["tpl"], categories=categorias)
    return x


def treinar(a: pd.DataFrame) -> dict:
    treino, valid, teste = (_janela(a, j) for j in (config.FILA_TREINO, config.FILA_VALIDACAO, config.FILA_TESTE))
    cats = pd.Index(sorted(treino["tpl"].unique()))
    modelo = xgb.XGBClassifier(n_estimators=300, max_depth=6, learning_rate=0.08, enable_categorical=True,
                               tree_method="hist", random_state=config.RANDOM_STATE)
    modelo.fit(_x(treino, cats), treino["humano"].astype(int))

    p_val = modelo.predict_proba(_x(valid, cats))[:, 1]
    y_val = valid["humano"].to_numpy()
    # Highest threshold that still keeps FILA_RECALL_ALVO of the human alarms in validation.
    pos = np.sort(p_val[y_val])
    corte = lambda alvo: float(pos[int(np.floor((1 - alvo) * len(pos)))])
    limiar = corte(config.FILA_RECALL_ALVO)

    p_te = modelo.predict_proba(_x(teste, cats))[:, 1]
    y_te = teste["humano"].to_numpy()
    mantidos = p_te >= limiar
    dias = teste["aberto"].dt.normalize().nunique()
    # The same model at other recall targets, each threshold also picked on validation only.
    por_recall = {}
    for alvo in config.FILA_RECALLS:
        m = p_te >= corte(alvo)
        por_recall[f"{round(alvo * 100)}"] = {"limiar": round(corte(alvo), 6), "recall_teste": round(float(m[y_te].mean()), 4),
                                             "fila_por_dia_depois": round(float(m.sum()) / dias, 1), "reducao_fila": round(1 - float(m.mean()), 4)}

    contrib = modelo.get_booster().predict(xgb.DMatrix(_x(teste, cats), enable_categorical=True), pred_contribs=True)
    importancia = dict(zip(FEATURES, np.abs(contrib[:, :-1]).mean(axis=0).round(4).tolist()))

    teste = teste.assign(prob_humano=p_te, mantido=mantidos)
    metricas = {
        "janelas": {"treino": config.FILA_TREINO, "limiar_escolhido_em": config.FILA_VALIDACAO, "teste": config.FILA_TESTE},
        "features": FEATURES,
        "n": {"treino": int(len(treino)), "validacao": int(len(valid)), "teste": int(len(teste))},
        "taxa_humano_teste": round(float(y_te.mean()), 4),
        "auc_roc_teste": round(float(roc_auc_score(y_te, p_te)), 4),
        "auc_pr_teste": round(float(average_precision_score(y_te, p_te)), 4),
        "recall_alvo": config.FILA_RECALL_ALVO,
        "limiar": round(limiar, 6),
        "recall_teste": round(float(mantidos[y_te].mean()), 4),
        "humanos_perdidos_teste": int((~mantidos & y_te).sum()),
        "fila_por_dia_antes": round(len(teste) / dias, 1),
        "fila_por_dia_depois": round(float(mantidos.sum()) / dias, 1),
        "reducao_fila": round(1 - float(mantidos.mean()), 4),
        "por_recall": por_recall,
        "importancia_shap_media": dict(sorted(importancia.items(), key=lambda kv: -kv[1])),
    }
    return {"modelo": modelo, "categorias": cats, "metricas": metricas, "teste": teste, "contrib": contrib}


def resumo_diario(teste: pd.DataFrame) -> pd.DataFrame:
    t = teste.assign(data=teste["aberto"].dt.normalize())
    return t.groupby("data").agg(
        alarmes=("numero", "size"),
        exigiram_pessoa=("humano", "sum"),
        fila_filtrada=("mantido", "sum"),
        pessoa_fora_da_fila=("humano", lambda s: int((s & ~t.loc[s.index, "mantido"]).sum())),
    ).reset_index()


def resumo_templates(teste: pd.DataFrame, n: int = 15) -> pd.DataFrame:
    g = teste.groupby("tpl").agg(alarmes=("numero", "size"), exigiram_pessoa=("humano", "sum"),
                                 prob_media=("prob_humano", "mean"), mantidos=("mantido", "sum"))
    return g.sort_values("alarmes", ascending=False).head(n).reset_index()


def alarmes_painel(teste: pd.DataFrame) -> dict:
    """Every test-month alarm for the panel's queue table, compact: templates once, then one row per alarm
    [number, opened at, template index, CI, same template in the last hour, same CI in 24 h, P(person), needed a person]."""
    tpls = sorted(teste["tpl"].unique())
    idx = {t: i for i, t in enumerate(tpls)}
    linhas = [[r.numero, r.aberto.strftime("%Y-%m-%d %H:%M"), idx[r.tpl], r.ci, int(r.n1h_tpl), int(r.n24h_ci),
               round(float(r.prob_humano), 4), int(r.humano)] for r in teste.itertuples()]
    return {"templates": tpls, "alarmes": linhas}


FAIXAS_CONTAGEM = [(0, 0, "0"), (1, 1, "1"), (2, 3, "2–3"), (4, 7, "4–7"), (8, 15, "8–15"), (16, 10**9, "16+")]
PREVISAO_SEM_SHAP = ("A previsão usa a mediana de modelos simples (no P3 em 7 dias, a média sazonal de 4 semanas); "
                     "SHAP não se aplica. O porquê dela é o contexto (médias de 7 e 28 dias, mesmo dia da semana passada).")


def _dependencia(teste: pd.DataFrame, phi: np.ndarray) -> dict:
    """Mean SHAP per value band of each numeric feature: which way it pushes, and how hard."""
    out = {}
    for j, f in enumerate(FEATURES):
        if f == "tpl":
            continue
        v = teste[f].to_numpy()
        faixas = [(x, x, str(x)) for x in range(24 if f == "hora" else 7)] if f in ("hora", "dow") else FAIXAS_CONTAGEM
        out[f] = [{"faixa": rot, "n": int(m.sum()), "shap_medio": round(float(phi[m, j].mean()), 3)}
                  for lo, hi, rot in faixas if (m := (v >= lo) & (v <= hi)).any()]
    return out


def explicar(r: dict) -> tuple[dict, dict]:
    """Per-alarm SHAP of the noise filter (log-odds) and a panel-sized summary of it."""
    teste, contrib, met = r["teste"].reset_index(drop=True), r["contrib"], r["metricas"]
    phi, base = contrib[:, :-1], float(contrib[0, -1])
    imp = met["importancia_shap_media"]
    total = sum(imp.values()) or 1
    por_tpl = teste.assign(s=phi[:, FEATURES.index("tpl")].astype(float)).groupby("tpl").agg(
        n=("numero", "size"), shap_medio=("s", "mean"), taxa_humano=("humano", "mean"))
    por_tpl = por_tpl[por_tpl["n"] >= 30].round(3).reset_index()
    p = teste["prob_humano"].to_numpy()
    exemplos = [teste.loc[int(np.argmax(np.where(teste["humano"], p, -1))), "numero"],
                teste.loc[int(np.argmin(np.abs(p - met["limiar"]))), "numero"],
                teste.loc[int(np.argmin(p)), "numero"]]
    resumo = {
        "mes": config.FILA_TESTE[0][:7], "n_alarmes": int(len(teste)),
        # base_prob is the SHAP base value (the model's starting point, from training); taxa_humano is what happened.
        "base_prob": round(1 / (1 + math.exp(-base)), 4), "taxa_humano": met["taxa_humano_teste"], "limiar": met["limiar"],
        "importancia": [{"feature": k, "media_abs": v, "peso_pct": round(v / total * 100, 1)} for k, v in imp.items()],
        "dependencia": _dependencia(teste, phi),
        "tipos": {"sobem": por_tpl.nlargest(8, "shap_medio").to_dict("records"),
                  "descem": por_tpl.nsmallest(8, "shap_medio").to_dict("records")},
        "exemplos": [str(n) for n in exemplos],
        "previsao": PREVISAO_SEM_SHAP,
    }
    tpls = sorted(teste["tpl"].unique())
    idx = {t: i for i, t in enumerate(tpls)}
    por = {"features": FEATURES, "templates": tpls, "base": round(base, 4), "alarmes": {
        str(a.numero): [idx[a.tpl], int(a.hora), int(a.dow), int(a.n1h_tpl), int(a.n24h_tpl), int(a.n24h_ci),
                        *[round(float(x), 3) for x in phi[i]], round(float(a.prob_humano), 7)]  # 7 places: near the threshold 4 flipped the queue
        for i, a in enumerate(teste.itertuples())}}
    return resumo, por
