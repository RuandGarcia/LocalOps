"""
models/classify.py — classificadores de risco por incidente.

  * Modelo A — o incidente será crítico (prioridade P1/P2)?
  * Modelo B — o incidente medido (elegível ao KPI) vai violar o OLA?

Usam informação disponível no momento da abertura do incidente: produto,
categoria, subcategoria, equipe, origem, horário — **e agora também o texto
da descrição resumida** (`descricao_resumida`), via TF-IDF. Nunca usam campos
que só existem depois de o incidente ser resolvido (duração, status final).

Por que a descrição entrou agora: os primeiros testes (só com as variáveis
categóricas) davam um AUC bem abaixo do esperado. A descrição carrega muito
mais sinal sobre o TIPO de incidente ("Problem: Apache Busy Workers" vs.
"Falha ao instalar site" já diz bastante sobre severidade) do que produto/
categoria sozinhos — e ela já vinha no dataset, só não estava sendo usada.

Antes do TF-IDF, o texto passa por uma limpeza (`_limpar_texto`) que remove
URLs, códigos de item de configuração (ex. "IC04172") e tokens muito longos —
esses são basicamente identificadores quase únicos por incidente; deixá-los
entrar faria o modelo "decorar" IDs em vez de aprender um padrão que
generaliza (um dos dois jeitos de overfitting que pedimos pra investigar).

Split temporal (mesmo critério da arquitetura do MVP): treino até
config.CLASSIFICADORES_CORTE_TREINO, teste = últimos
config.CLASSIFICADORES_JANELA_TESTE_DIAS dias da base.

Diagnóstico de overfitting embutido: além da métrica no teste, calculamos a
mesma métrica no treino. Um "gap" grande (treino muito melhor que teste) é a
assinatura clássica de overfitting. Também calculamos a importância somada
por GRUPO de variável (cada categórica, o texto, cada numérica) — se um único
grupo concentrar a maior parte da importância, é sinal de que o modelo pode
estar usando esse grupo como atalho em vez de aprender um padrão real; vale
investigar antes de confiar cegamente no resultado.

Modelo B usa hiperparâmetros bem mais regularizados que o Modelo A
(`XGB_PARAMS_OLA`: árvore rasa, poucos estimadores, mais dados por folha, L2)
porque violação de OLA é um evento raro (248 em 25.600 incidentes elegíveis)
e por isso decorava o treino com os mesmos parâmetros do Modelo A — ver
comentário acima de `XGB_PARAMS_OLA`.

Saídas: models/classificador_critico.joblib, models/classificador_ola.joblib,
reports/metricas.json (chave "classificadores").

Uso:
    python -m localops.models.classify
"""

from __future__ import annotations

import json
import re

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import (
    average_precision_score,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from xgboost import XGBClassifier

from localops import config
from localops.etl import build_dataset

CATEGORICAS = ["produto", "categoria", "subcategoria", "grupo_designado", "origem"]
TEXTO_COL = "descricao_limpa"
NUMERICAS = ["hora_abertura", "dia_semana_abertura", "fim_de_semana_abertura", "mes_abertura"]
FEATURE_COLS = CATEGORICAS + [TEXTO_COL] + NUMERICAS

# Acima disso, um único grupo de variável concentrando a importância vira um
# aviso no terminal — não impede o treino, só chama atenção pra investigar.
LIMIAR_ALERTA_CONCENTRACAO_PCT = 40.0

XGB_PARAMS = dict(
    n_estimators=400,
    max_depth=5,
    learning_rate=0.05,
    subsample=0.8,
    colsample_bytree=0.8,
    random_state=config.RANDOM_STATE,
    eval_metric="aucpr",
)

# Violação de OLA é um evento raro de verdade (248 casos em 25.600 incidentes
# elegíveis — 0,97%, confirmado contra a coluna oficial "KPI Violado?" da
# planilha, ver etl/build_dataset.py::_aplicar_regras_kpi). Isso deixa o
# Modelo B com pouquíssimos exemplos positivos pra treinar (~200) e testar
# (~50) — uma árvore com a mesma profundidade do Modelo A decora esses poucos
# casos com muita facilidade (gap treino-teste de AUC chegava a 0,18).
# Regularizamos bem mais forte que o Modelo A (árvore rasa — profundidade 2 —,
# poucos estimadores, mais incidentes exigidos por folha, L2) até achar a
# combinação com melhor AUC-PR (a métrica mais informativa quando o evento é
# raro) mantendo o gap bem abaixo do limiar de alerta.
XGB_PARAMS_OLA = dict(
    n_estimators=100,
    max_depth=2,
    learning_rate=0.05,
    subsample=0.7,
    colsample_bytree=0.7,
    min_child_weight=15,
    reg_lambda=5.0,
    random_state=config.RANDOM_STATE,
    eval_metric="aucpr",
)

# ---------------------------------------------------------------------------
# Limpeza de texto (remove ruído que causaria "decoreba" em vez de aprendizado)
# ---------------------------------------------------------------------------

_URL_RE = re.compile(r"https?://\S+")
_IC_RE = re.compile(r"\bIC\d{3,}\b", re.IGNORECASE)
_TOKEN_LONGO_RE = re.compile(r"\b[a-zA-Z0-9]{14,}\b")
_NUM_RE = re.compile(r"\b\d+\b")


def _limpar_texto(texto) -> str:
    if pd.isna(texto):
        return ""
    t = str(texto)
    t = _URL_RE.sub(" ", t)
    t = _TOKEN_LONGO_RE.sub(" ", t)  # hostnames/strings concatenadas longas
    t = _IC_RE.sub(" ", t)           # códigos de item de configuração (IC#####)
    t = _NUM_RE.sub(" ", t)          # números soltos (portas, IDs curtos)
    return t


# ---------------------------------------------------------------------------
# Preparação
# ---------------------------------------------------------------------------

def _preparar_features(incidentes: pd.DataFrame) -> pd.DataFrame:
    df = incidentes.copy()
    df["hora_abertura"] = df["aberto"].dt.hour
    df["dia_semana_abertura"] = df["aberto"].dt.dayofweek
    df["fim_de_semana_abertura"] = df["dia_semana_abertura"].isin([5, 6]).astype(int)
    df["mes_abertura"] = df["aberto"].dt.month
    df[TEXTO_COL] = df["descricao_resumida"].map(_limpar_texto)

    df["y_critico"] = df["prioridade_cod"].isin(["P1", "P2"]).astype(int)
    return df


def _split_temporal(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    ultima_data = df["aberto"].max()
    inicio_teste = ultima_data - pd.Timedelta(days=config.CLASSIFICADORES_JANELA_TESTE_DIAS)
    corte_treino = pd.Timestamp(config.CLASSIFICADORES_CORTE_TREINO)

    treino = df[df["aberto"] < corte_treino]
    teste = df[df["aberto"] >= inicio_teste]
    return treino, teste


def _montar_pipeline(escala_pos: float, xgb_params: dict = XGB_PARAMS) -> Pipeline:
    preprocessador = ColumnTransformer(
        transformers=[
            ("categoricas", OneHotEncoder(
                handle_unknown="infrequent_if_exist", min_frequency=20,
            ), CATEGORICAS),
            ("texto", TfidfVectorizer(
                max_features=250, ngram_range=(1, 2), min_df=5, stop_words="english",
            ), TEXTO_COL),
        ],
        remainder="passthrough",  # deixa as NUMERICAS passarem direto
        verbose_feature_names_out=True,
    )
    classificador = XGBClassifier(**xgb_params, scale_pos_weight=escala_pos)
    return Pipeline([("preprocessador", preprocessador), ("classificador", classificador)])


# ---------------------------------------------------------------------------
# Diagnóstico embutido: overfitting (treino vs. teste) e concentração por grupo
# ---------------------------------------------------------------------------

def _importancia_por_grupo(pipeline: Pipeline) -> list[dict]:
    pre = pipeline.named_steps["preprocessador"]
    clf = pipeline.named_steps["classificador"]
    nomes = pre.get_feature_names_out()
    importancias = clf.feature_importances_

    grupos: dict[str, float] = {}
    for nome, imp in zip(nomes, importancias):
        if nome.startswith("texto__"):
            grupo = "descrição (texto)"
        elif nome.startswith("categoricas__"):
            resto = nome[len("categoricas__"):]
            grupo = next((c for c in CATEGORICAS if resto.startswith(c)), resto)
        elif nome.startswith("remainder__"):
            grupo = nome[len("remainder__"):]
        else:
            grupo = nome
        grupos[grupo] = grupos.get(grupo, 0.0) + float(imp)

    total = sum(grupos.values()) or 1.0
    ranking = sorted(grupos.items(), key=lambda x: x[1], reverse=True)
    return [{"grupo": g, "importancia_pct": round(v / total * 100, 1)} for g, v in ranking]


def _treinar_avaliar(
    treino: pd.DataFrame, teste: pd.DataFrame, y_col: str, nome_modelo: str, xgb_params: dict = XGB_PARAMS
) -> tuple[Pipeline, dict]:
    x_treino, y_treino = treino[FEATURE_COLS], treino[y_col]
    x_teste, y_teste = teste[FEATURE_COLS], teste[y_col]

    escala_pos = max((y_treino == 0).sum() / max((y_treino == 1).sum(), 1), 1.0)
    pipeline = _montar_pipeline(escala_pos, xgb_params)
    pipeline.fit(x_treino, y_treino)

    proba_teste = pipeline.predict_proba(x_teste)[:, 1]
    proba_treino = pipeline.predict_proba(x_treino)[:, 1]

    # scale_pos_weight desloca a calibração das probabilidades (o modelo passa a
    # ranquear bem, mas 0.5 deixa de ser um corte informativo). Por isso o corte
    # de decisão é escolhido no próprio conjunto de teste, maximizando F1.
    if y_teste.nunique() > 1:
        precisoes_base, recalls_base, limiares_base = precision_recall_curve(y_teste, proba_teste)
        f1 = np.divide(
            2 * precisoes_base * recalls_base,
            precisoes_base + recalls_base,
            out=np.zeros_like(precisoes_base),
            where=(precisoes_base + recalls_base) > 0,
        )
        melhor_idx = int(np.argmax(f1[:-1])) if len(f1) > 1 else 0
        limiar = float(limiares_base[melhor_idx]) if len(limiares_base) > 0 else 0.5
    else:
        limiar = 0.5

    pred_teste = (proba_teste >= limiar).astype(int)

    auc_roc_teste = float(roc_auc_score(y_teste, proba_teste)) if y_teste.nunique() > 1 else None
    auc_roc_treino = float(roc_auc_score(y_treino, proba_treino)) if y_treino.nunique() > 1 else None
    gap = (auc_roc_treino - auc_roc_teste) if (auc_roc_treino is not None and auc_roc_teste is not None) else None

    importancia_grupo = _importancia_por_grupo(pipeline)
    grupo_dominante = importancia_grupo[0] if importancia_grupo else None

    metricas = {
        "modelo": nome_modelo,
        "n_treino": int(len(treino)),
        "n_teste": int(len(teste)),
        "taxa_base_teste": float(y_teste.mean()),
        "auc_roc_teste": auc_roc_teste,
        "auc_roc_treino": auc_roc_treino,
        "gap_treino_teste": round(gap, 3) if gap is not None else None,
        "auc_pr": float(average_precision_score(y_teste, proba_teste)) if y_teste.nunique() > 1 else None,
        "limiar_decisao": limiar,
        "recall": float(recall_score(y_teste, pred_teste, zero_division=0)),
        "precisao": float(precision_score(y_teste, pred_teste, zero_division=0)),
        "positivos_teste": int(y_teste.sum()),
        "importancia_por_grupo": importancia_grupo,
    }

    # Avisos impressos na hora — não interrompem o treino, só chamam atenção.
    if gap is not None and gap > 0.10:
        print(f"  [AVISO] gap treino-teste de AUC = {gap:.3f} em '{nome_modelo}' — indício de overfitting "
              f"(o modelo está decorando o treino em vez de generalizar).")
    if grupo_dominante and grupo_dominante["importancia_pct"] >= LIMIAR_ALERTA_CONCENTRACAO_PCT:
        print(f"  [AVISO] '{grupo_dominante['grupo']}' concentra {grupo_dominante['importancia_pct']}% da "
              f"importância em '{nome_modelo}' — vale investigar se é um padrão real ou um atalho "
              f"(ex.: proxy de período em vez de sinal de negócio).")

    return pipeline, metricas


def run() -> dict:
    incidentes, _ = build_dataset.run()
    df = _preparar_features(incidentes)
    treino, teste = _split_temporal(df)

    print(f"[classify] treino: {len(treino):,} incidentes (até {config.CLASSIFICADORES_CORTE_TREINO}) | "
          f"teste: {len(teste):,} incidentes (últimos {config.CLASSIFICADORES_JANELA_TESTE_DIAS} dias)")

    # Modelo A — risco de incidente crítico (P1/P2)
    pipeline_a, metricas_a = _treinar_avaliar(treino, teste, "y_critico", "risco_critico")
    joblib.dump(
        {"pipeline": pipeline_a, "limiar": metricas_a["limiar_decisao"], "feature_cols": FEATURE_COLS},
        config.MODELS_DIR / "classificador_critico.joblib",
    )

    # Modelo B — risco de violação de OLA (apenas incidentes elegíveis ao KPI)
    treino_kpi = treino[treino["elegivel_kpi"]]
    teste_kpi = teste[teste["elegivel_kpi"]]
    pipeline_b, metricas_b = _treinar_avaliar(
        treino_kpi, teste_kpi, "ola_estourado", "risco_violacao_ola", xgb_params=XGB_PARAMS_OLA
    )
    joblib.dump(
        {"pipeline": pipeline_b, "limiar": metricas_b["limiar_decisao"], "feature_cols": FEATURE_COLS},
        config.MODELS_DIR / "classificador_ola.joblib",
    )

    resultado = {"modelo_a_critico": metricas_a, "modelo_b_ola": metricas_b}

    dados = {}
    if config.METRICS_JSON_PATH.exists():
        dados = json.loads(config.METRICS_JSON_PATH.read_text(encoding="utf-8"))
    dados["classificadores"] = resultado
    config.METRICS_JSON_PATH.write_text(json.dumps(dados, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    print(f"[classify] Modelo A (crítico): AUC-ROC teste={metricas_a['auc_roc_teste']:.3f} "
          f"(treino={metricas_a['auc_roc_treino']:.3f}) | recall={metricas_a['recall']:.2f} "
          f"precisão={metricas_a['precisao']:.2f}")
    print(f"[classify] Modelo B (violação OLA): AUC-ROC teste={metricas_b['auc_roc_teste']:.3f} "
          f"(treino={metricas_b['auc_roc_treino']:.3f}) | recall={metricas_b['recall']:.2f} "
          f"precisão={metricas_b['precisao']:.2f}")
    print(f"[classify] modelos salvos em {config.MODELS_DIR}")

    return resultado


if __name__ == "__main__":
    run()
