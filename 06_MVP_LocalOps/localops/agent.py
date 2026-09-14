"""
agent.py — agente conversacional do LocalOps.

Dois motores, com fallback automático:

  1. IA online (Gemini, camada gratuita) — `_responder_llm()`. Monta um
     CONTEXTO textual com os dados/métricas/regras mais atuais do pipeline
     (RAG: nada de fine-tuning, o contexto é remontado do zero a cada
     pergunta a partir dos artefatos em reports/models) e manda pro Gemini
     junto com a pergunta em linguagem natural — por isso responde perguntas
     abertas, não só as intenções fixas abaixo.
  2. Motor de regras offline (determinístico, sem internet/sem chave de API)
     — `_responder_regras()`, o agente original: interpreta a pergunta por
     palavras-chave e monta um gráfico Plotly a partir dos dados.

`responder()` é o ponto de entrada público: tenta (1) se houver
GEMINI_API_KEY configurada, e cai pro (2) automaticamente se a chave não
estiver configurada ou a chamada falhar por qualquer motivo (sem internet,
cota excedida, etc.) — o dashboard nunca fica sem resposta.

`responder()` devolve um `RespostaAgente` (dataclass) — é o contrato que o
dashboard (`dashboard/views.py::agente()`) espera (`r.texto`, `r.figura`,
`r.fontes`, `r.confianca`, `r.sugestoes`). A API (`localops/api/main.py`,
endpoint POST /agent) converte esse dataclass pra um dict serializável antes
de devolver — um objeto Plotly Figure não serializa direto em JSON.

Intenções fixas do motor de regras (ver README): previsão, tendência,
comparativo, ranking, sazonalidade.

Uso:
    python -m localops.agent "previsão para amanhã"
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

import pandas as pd
import plotly.graph_objects as go

from localops import config, store

JANELA_TENDENCIA_DIAS = 30
COR_AZUL = "#5b8cff"
COR_VERMELHO = "#ff4d6d"

_PADRAO_ENTIDADE = re.compile(r"\b(cat\w*\d+|team\w*\d*\d)\b", re.IGNORECASE)

_SUGESTOES_PADRAO = [
    "Previsão para amanhã", "Qual o horário de pico?", "Quais equipes violam mais OLA?",
]


@dataclass
class RespostaAgente:
    texto: str
    fontes: list[str] = field(default_factory=list)
    confianca: float = 0.0
    sugestoes: list[str] = field(default_factory=list)
    figura: go.Figure | None = None
    intencao: str = "desconhecida"
    dados: dict = field(default_factory=dict)


def _localizar_entidade(termo: str, incidentes: pd.DataFrame) -> tuple[str, str] | None:
    """Tenta casar `termo` com uma categoria ou uma equipe conhecida."""
    termo_low = termo.lower()

    for categoria in incidentes["categoria"].unique():
        if isinstance(categoria, str) and categoria.lower() == termo_low:
            return "categoria", categoria
    for equipe in incidentes["grupo_designado"].unique():
        if isinstance(equipe, str) and equipe.lower() == termo_low:
            return "grupo_designado", equipe
    return None


def _serie_da_pergunta(pergunta: str) -> str:
    p = pergunta.lower()
    if "kpi" in p:
        return "kpi"
    if re.search(r"\bp ?2\b", p) or "alta" in p:
        return "p2"
    if re.search(r"\bp ?3\b", p) or "média" in p or "media" in p:
        return "p3"
    return "total"


def _horizonte_da_pergunta(pergunta: str) -> int:
    p = pergunta.lower()
    if "semana" in p or "d+7" in p or "d7" in p:
        return 7
    return 1  # "amanhã" é o padrão


def _fig_barras(x: list, y: list, titulo: str = "", cores: list[str] | None = None, horizontal: bool = False) -> go.Figure:
    fig = go.Figure(go.Bar(x=y if horizontal else x, y=x if horizontal else y,
                            orientation="h" if horizontal else "v",
                            marker_color=cores or COR_AZUL))
    fig.update_layout(title=titulo, template="plotly_dark", height=320,
                       margin=dict(l=30, r=20, t=48 if titulo else 20, b=30))
    if horizontal:
        fig.update_yaxes(autorange="reversed")
    return fig


# ---------------------------------------------------------------------------
# Intenções
# ---------------------------------------------------------------------------

def _intent_sazonalidade(pergunta: str) -> RespostaAgente:
    incidentes = store.load_incidentes()
    por_hora = incidentes.groupby(incidentes["aberto"].dt.hour).size().reindex(range(24), fill_value=0)
    pico_inicio = int(por_hora.idxmax())

    dias_uteis = incidentes[incidentes["aberto"].dt.dayofweek < 5]
    fim_de_semana = incidentes[incidentes["aberto"].dt.dayofweek >= 5]
    media_util = len(dias_uteis) / max(dias_uteis["aberto"].dt.date.nunique(), 1)
    media_fds = len(fim_de_semana) / max(fim_de_semana["aberto"].dt.date.nunique(), 1)
    variacao_fds = (media_fds - media_util) / media_util * 100 if media_util else 0

    resposta = (
        f"O horário de pico é por volta das {pico_inicio}h-{pico_inicio + 2}h. "
        f"Nos fins de semana o volume médio diário é {variacao_fds:+.0f}% em relação aos dias úteis."
    )
    cores = [COR_VERMELHO if 9 <= h <= 11 else COR_AZUL for h in por_hora.index]
    fig = _fig_barras(list(por_hora.index), list(por_hora.values), "Incidentes por hora do dia", cores)

    return RespostaAgente(
        texto=resposta, fontes=["incidentes"], confianca=0.95,
        sugestoes=["Previsão para amanhã", "Quais categorias são mais críticas?"],
        figura=fig, intencao="sazonalidade", dados={"incidentes_por_hora": por_hora.to_dict()},
    )


def _intent_comparativo(pergunta: str) -> RespostaAgente:
    incidentes = store.load_incidentes()
    termos = _PADRAO_ENTIDADE.findall(pergunta)
    entidades = [_localizar_entidade(t, incidentes) for t in termos]
    entidades = [e for e in entidades if e]

    if len(entidades) < 2:
        return _intent_desconhecida(pergunta)

    ultima_data = incidentes["aberto"].max()
    inicio = ultima_data - pd.Timedelta(days=JANELA_TENDENCIA_DIAS)
    janela = incidentes[incidentes["aberto"] >= inicio]

    resumo = {}
    for tipo_campo, valor in entidades:
        sub = janela[janela[tipo_campo] == valor]
        resumo[valor] = {
            "total": int(len(sub)),
            "pct_p2": round((sub["prioridade_cod"] == "P2").mean() * 100, 1) if len(sub) else 0.0,
            "violacoes_ola": int(sub["ola_estourado"].sum()),
        }

    partes = [f"{nome}: {dados['total']} incidentes, {dados['pct_p2']}% P2, {dados['violacoes_ola']} violações de OLA"
              for nome, dados in resumo.items()]
    resposta = f"Comparativo dos últimos {JANELA_TENDENCIA_DIAS} dias — " + "; ".join(partes)
    fig = _fig_barras(list(resumo.keys()), [d["total"] for d in resumo.values()], "Volume de incidentes (30d)")

    return RespostaAgente(
        texto=resposta, fontes=["incidentes"], confianca=0.9,
        sugestoes=[f"{list(resumo)[0]} vai piorar?", "Quais equipes violam mais OLA?"],
        figura=fig, intencao="comparativo", dados=resumo,
    )


def _intent_tendencia(pergunta: str) -> RespostaAgente:
    incidentes = store.load_incidentes()
    termos = _PADRAO_ENTIDADE.findall(pergunta)
    entidades = [_localizar_entidade(t, incidentes) for t in termos]
    entidades = [e for e in entidades if e]

    if not entidades:
        return _intent_desconhecida(pergunta)

    tipo_campo, valor = entidades[0]
    ultima_data = incidentes["aberto"].max()
    janela_atual = incidentes[
        (incidentes["aberto"] >= ultima_data - pd.Timedelta(days=JANELA_TENDENCIA_DIAS))
        & (incidentes[tipo_campo] == valor)
    ]
    janela_anterior = incidentes[
        (incidentes["aberto"] >= ultima_data - pd.Timedelta(days=2 * JANELA_TENDENCIA_DIAS))
        & (incidentes["aberto"] < ultima_data - pd.Timedelta(days=JANELA_TENDENCIA_DIAS))
        & (incidentes[tipo_campo] == valor)
    ]

    n_atual, n_anterior = len(janela_atual), len(janela_anterior)
    variacao = (n_atual - n_anterior) / n_anterior * 100 if n_anterior else float("inf")
    pct_p2_atual = (janela_atual["prioridade_cod"] == "P2").mean() * 100 if n_atual else 0.0

    if n_anterior == 0:
        tendencia_txt = "sem histórico suficiente no período anterior para comparar"
    elif variacao > 15:
        tendencia_txt = f"piorando ({variacao:+.0f}% de incidentes vs. os {JANELA_TENDENCIA_DIAS}d anteriores)"
    elif variacao < -15:
        tendencia_txt = f"melhorando ({variacao:+.0f}% de incidentes vs. os {JANELA_TENDENCIA_DIAS}d anteriores)"
    else:
        tendencia_txt = f"estável ({variacao:+.0f}% vs. os {JANELA_TENDENCIA_DIAS}d anteriores)"

    resposta = (
        f"{valor} está {tendencia_txt}. Nos últimos {JANELA_TENDENCIA_DIAS} dias: "
        f"{n_atual} incidentes, {pct_p2_atual:.0f}% classificados como P2."
    )
    fig = _fig_barras(
        [f"{JANELA_TENDENCIA_DIAS*2}-{JANELA_TENDENCIA_DIAS}d atrás", f"últimos {JANELA_TENDENCIA_DIAS}d"],
        [n_anterior, n_atual], f"Volume de {valor} — período anterior vs. atual",
        [COR_AZUL, COR_VERMELHO if variacao > 15 else COR_AZUL],
    )

    return RespostaAgente(
        texto=resposta, fontes=["incidentes"], confianca=0.9 if n_anterior else 0.5,
        sugestoes=["Quais equipes violam mais OLA?", "Previsão para amanhã"],
        figura=fig, intencao="tendencia",
        dados={"entidade": valor, "n_atual": n_atual, "n_anterior": n_anterior, "variacao_pct": variacao},
    )


def _intent_ranking(pergunta: str) -> RespostaAgente:
    incidentes = store.load_incidentes()
    ultima_data = incidentes["aberto"].max()
    janela = incidentes[incidentes["aberto"] >= ultima_data - pd.Timedelta(days=JANELA_TENDENCIA_DIAS)]

    p = pergunta.lower()
    if "equipe" in p or "time" in p:
        ranking = janela.groupby("grupo_designado")["ola_estourado"].sum().sort_values(ascending=False).head(5)
        resposta = "Equipes com mais violações de OLA nos últimos 30 dias: " + ", ".join(
            f"{k} ({int(v)})" for k, v in ranking.items()
        )
        dados = ranking.to_dict()
        sugestoes = ["Qual o horário de pico?", "Previsão de risco de OLA"]
    else:
        base = janela[janela["categoria"] != "Não informado"]
        resumo = base.groupby("categoria").agg(
            total=("numero", "count"), pct_p2=("prioridade_cod", lambda s: (s == "P2").mean() * 100)
        )
        resumo = resumo[resumo["total"] >= 20].sort_values("pct_p2", ascending=False).head(5)
        resposta = "Categorias mais críticas (maior % de P2) nos últimos 30 dias: " + ", ".join(
            f"{cat} ({row.pct_p2:.0f}% P2)" for cat, row in resumo.iterrows()
        )
        ranking = resumo["pct_p2"].round(1)
        dados = ranking.to_dict()
        sugestoes = ["Quais equipes violam mais OLA?", "Previsão para amanhã"]

    fig = _fig_barras(list(ranking.index), list(ranking.values), horizontal=True)

    return RespostaAgente(
        texto=resposta, fontes=["incidentes"], confianca=0.9,
        sugestoes=sugestoes, figura=fig, intencao="ranking", dados=dados,
    )


def _intent_previsao(pergunta: str) -> RespostaAgente:
    forecast_df = store.load_forecast()
    serie = _serie_da_pergunta(pergunta)
    horizonte = _horizonte_da_pergunta(pergunta)

    linha = forecast_df[
        (forecast_df["serie"] == serie)
        & (forecast_df["horizonte"] == horizonte)
        & (forecast_df["modelo"] == "ensemble")
    ]
    if linha.empty:
        return _intent_desconhecida(pergunta)

    linha = linha.iloc[0]
    rotulo_serie = config.SERIES_PREVISTAS[serie]
    resposta = (
        f"Previsão de {rotulo_serie.lower()} para D+{horizonte} "
        f"({linha['data_alvo'].strftime('%d/%m/%Y')}): {linha['previsto']:.0f} incidentes "
        f"({linha['variacao_pct_vs_media_30d']:+.0f}% vs. média 30d)."
    )
    fontes = ["forecast.parquet"]

    if "risco de ola" in pergunta.lower() or "risco de sla" in pergunta.lower():
        metricas = store.load_metricas().get("classificadores", {}).get("modelo_b_ola", {})
        if metricas:
            resposta += (
                f" O classificador de risco de violação de OLA tem AUC-ROC de "
                f"{metricas.get('auc_roc_teste', 0):.2f} no conjunto de teste."
            )
            fontes.append("metricas.json")

    fig = _fig_barras(
        ["média 30d", f"previsto D+{horizonte}"],
        [linha["media_30d"], linha["previsto"]], rotulo_serie,
        [COR_AZUL, COR_VERMELHO if linha["variacao_pct_vs_media_30d"] > 0 else COR_AZUL],
    )

    return RespostaAgente(
        texto=resposta, fontes=fontes, confianca=0.85,
        sugestoes=["Qual o horário de pico?", "Quais equipes violam mais OLA?"],
        figura=fig, intencao="previsao", dados=linha.to_dict(),
    )


def _intent_desconhecida(pergunta: str) -> RespostaAgente:
    return RespostaAgente(
        texto=(
            "Não entendi a pergunta. Posso ajudar com: previsão "
            "('previsão para amanhã', 'P2 na semana', 'risco de OLA'), tendência "
            "('cat71 vai piorar?'), comparativo ('compare cat71 e cat77'), ranking "
            "('quais equipes violam mais OLA?', 'categorias críticas') e sazonalidade "
            "('qual o horário de pico?')."
        ),
        fontes=[], confianca=0.0, sugestoes=list(_SUGESTOES_PADRAO), intencao="desconhecida",
    )


# ---------------------------------------------------------------------------
# Motor de regras — roteador por palavra-chave (offline, determinístico)
# ---------------------------------------------------------------------------

def _responder_regras(pergunta: str) -> RespostaAgente:
    p = pergunta.lower().strip()

    if any(k in p for k in ("horário de pico", "horario de pico", "sazonalidade", "pico operacional", "menos pico", "mais tranquilo", "mais calmo")):
        return _intent_sazonalidade(pergunta)

    if any(k in p for k in ("compare", "comparar", "comparativo")):
        return _intent_comparativo(pergunta)

    if any(k in p for k in ("ranking", "quais equipes", "quais categorias", "mais críticas", "mais criticas", "categorias críticas", "categorias criticas")):
        return _intent_ranking(pergunta)

    if any(k in p for k in ("piorar", "piorando", "melhorando", "tendência", "tendencia")):
        return _intent_tendencia(pergunta)

    if any(k in p for k in ("previsão", "previsao", "amanhã", "amanha", "semana", "risco de ola", "risco de sla")):
        return _intent_previsao(pergunta)

    return _intent_desconhecida(pergunta)


# ---------------------------------------------------------------------------
# IA online (Gemini) — RAG sobre os artefatos atuais do pipeline
# ---------------------------------------------------------------------------

_SISTEMA_GEMINI = """Você é o agente analítico do LocalOps, o painel AIOps da operação de \
incidentes da Locaweb. Responda SOMENTE com base no CONTEXTO abaixo, que traz os dados, \
métricas e regras de negócio mais atuais do pipeline (gerado automaticamente a cada execução \
— sempre reflete o estado mais recente da base). Nunca invente números que não estejam no \
contexto: se a pergunta pedir algo que não está lá, diga claramente que não tem esse dado \
disponível agora e sugira uma pergunta parecida que você consegue responder. Responda em \
português do Brasil, tom direto e profissional, no máximo 4-5 frases, citando números quando \
fizer sentido."""


def _ler_chave_gemini() -> str | None:
    """Lê GEMINI_API_KEY do ambiente ou de st.secrets (se rodando sob Streamlit).

    Fica bem verboso no console (prints) de propósito: a causa mais comum de
    'o agente não usa IA' é a chave não ser encontrada por algum detalhe de
    configuração, e sem um log claro fica impossível saber se caiu no motor
    de regras por falta de chave ou por erro na chamada."""
    chave = os.environ.get("GEMINI_API_KEY")
    if chave:
        print("[agent] GEMINI_API_KEY encontrada na variável de ambiente.")
        return chave
    try:
        import streamlit as st
    except Exception as erro:
        print(f"[agent] streamlit não disponível pra ler st.secrets: {erro}")
        return None
    try:
        chave = st.secrets.get("GEMINI_API_KEY")
    except Exception as erro:
        print(f"[agent] erro lendo st.secrets (verifique se .streamlit/secrets.toml existe e é TOML válido): {erro}")
        return None
    if chave:
        print(f"[agent] GEMINI_API_KEY encontrada em st.secrets (termina em ...{str(chave)[-4:]}).")
        return chave
    print("[agent] .streamlit/secrets.toml foi lido mas não tem a chave 'GEMINI_API_KEY' (ou está vazia).")
    return None


def _montar_contexto() -> str:
    """Monta um resumo textual compacto dos dados/métricas/regras atuais — o
    'RAG' do agente: remontado do zero a cada pergunta, sempre a partir dos
    artefatos mais recentes gerados por `run_pipeline.py` (nunca fine-tuning)."""
    incidentes = store.incidentes()
    met = store.metricas()
    rec = store.ler_json(config.RECOMMENDATIONS_JSON_PATH)

    ultima_data = incidentes["aberto"].max()
    janela30 = incidentes[incidentes["aberto"] >= ultima_data - pd.Timedelta(days=30)]

    partes = [
        "## Regras de negócio (Dicionário de Dados v2)",
        f"- Entram no KPI: prioridades {sorted(config.KPI_PRIORIDADES)}; status "
        f"'{config.STATUS_SEM_INTERVENCAO}' não conta.",
        f"- Limite de OLA por prioridade (horas): {config.OLA_HORAS}.",
        "",
        "## Base de incidentes",
        f"- Período: {incidentes['aberto'].min().date()} a {ultima_data.date()} · "
        f"{len(incidentes):,} incidentes no total.".replace(",", "."),
        f"- Últimos 30 dias: {len(janela30):,} incidentes.".replace(",", "."),
    ]

    horario = incidentes.groupby("hora").size().reindex(range(24), fill_value=0)
    pico = int(horario.idxmax())
    vale = int(horario.idxmin())
    partes += [
        f"- Horário de pico: {pico}h-{pico + 2}h ({int(horario.max())} incidentes nesse horário "
        f"em todo o histórico). Horário mais tranquilo: {vale}h ({int(horario.min())} incidentes).",
        "",
        "## Previsão de volume (ensemble Prophet+XGBoost)",
    ]
    prev = store.previsoes()
    prev_ens = prev[prev["modelo"] == "ensemble"]
    prev_prophet = prev[prev["modelo"] == "prophet"]  # IC95 só existe nas linhas do Prophet
    for seg, rotulo in (("total", "Volume total"), ("P2", "P2 (alta)"), ("P3", "P3 (média)"), ("kpi", "Perímetro KPI")):
        for h in (1, 7):
            linha = prev_ens[(prev_ens["segmento"] == seg) & (prev_ens["horizonte"] == h)]
            if len(linha):
                r = linha.iloc[0]
                ic = prev_prophet[(prev_prophet["segmento"] == seg) & (prev_prophet["horizonte"] == h)]
                ic_txt = f" (IC95: {ic.iloc[0]['yhat_lower']:.0f}-{ic.iloc[0]['yhat_upper']:.0f})" if len(ic) else ""
                partes.append(f"- {rotulo} D+{h} ({r['ds'].date()}): {r['yhat']:.0f}{ic_txt}")

    partes += ["", "## Classificadores de risco"]
    for chave, nome in (("risco_critico", "Risco de incidente crítico (P1/P2)"), ("risco_ola", "Risco de violação de OLA")):
        m = met.get("classificacao", {}).get(chave, {})
        if m:
            partes.append(
                f"- {nome}: AUC-ROC {m.get('auc_roc', 0):.2f}, AUC-PR {m.get('auc_pr', 0):.2f}, "
                f"precisão {m.get('precision', 0):.0%}, recall {m.get('recall', 0):.0%} "
                f"({m.get('positivos_teste', 0)} positivos em {m.get('n_teste', 0)} casos de teste)."
            )

    partes += ["", "## Carga e violações por equipe (30 dias, top 10)"]
    ranking_eq = janela30.groupby("equipe").agg(
        total=("numero", "count"), violacoes=("kpi_violado", "sum"),
        pct_criticos=("prioridade", lambda s: (s.isin(["P1", "P2"])).mean() * 100),
    ).sort_values("total", ascending=False).head(10)
    for eq, r in ranking_eq.iterrows():
        partes.append(f"- {eq}: {int(r.total)} incidentes, {r.pct_criticos:.0f}% críticos, {int(r.violacoes)} violações de OLA.")

    partes += ["", "## Categorias (30 dias, top 15 por volume)"]
    ranking_cat = janela30[janela30["categoria"] != "(sem categoria)"].groupby("categoria").agg(
        total=("numero", "count"), pct_p2=("prioridade", lambda s: (s == "P2").mean() * 100),
        violacoes=("kpi_violado", "sum"),
    ).sort_values("total", ascending=False).head(15)
    for cat, r in ranking_cat.iterrows():
        partes.append(f"- {cat}: {int(r.total)} incidentes, {r.pct_p2:.0f}% P2, {int(r.violacoes)} violações de OLA.")

    if rec.get("alertas"):
        partes += ["", "## Alertas ativos"]
        for a in rec["alertas"]:
            if a["nivel"] != "BAIXO":
                partes.append(f"- [{a['nivel']}] {a['segmento']} D+{a['horizonte']} ({a['data']}): previsto {a['previsto']:.0f} ({a['variacao_pct']:+.0f}% vs média 30d).")

    if rec.get("recomendacoes"):
        partes += ["", "## Recomendações operacionais vigentes"]
        for r in rec["recomendacoes"][:8]:
            partes.append(f"- [Prioridade {r['prioridade']}] {r['acao']} — {r['motivo']}")

    return "\n".join(partes)


# Número de tentativas em erros passageiros do lado do Google (503 "high
# demand", 429 rate limit momentâneo) — comuns na camada gratuita — antes de
# desistir e cair pro motor de regras offline. Pequeno de propósito: o
# objetivo é sobreviver a um pico rápido, não deixar quem pergunta esperando.
_GEMINI_TENTATIVAS = 3
_GEMINI_ESPERA_SEGUNDOS = 2


def _chamar_gemini(pergunta: str, contexto: str, chave: str) -> str:
    import time

    from google import genai

    cliente = genai.Client(api_key=chave)
    ultimo_erro: Exception | None = None

    for tentativa in range(1, _GEMINI_TENTATIVAS + 1):
        try:
            resposta = cliente.models.generate_content(
                model=config.GEMINI_MODEL,
                contents=f"CONTEXTO ATUAL DO LOCALOPS:\n{contexto}\n\nPERGUNTA: {pergunta}",
                config={
                    "system_instruction": _SISTEMA_GEMINI,
                    "max_output_tokens": 1024,
                    # gemini-2.5-flash "pensa" antes de responder por padrão, e em
                    # perguntas compostas (ex.: "quantos X? e qual Y?") pode gastar
                    # todo o orçamento de tokens só pensando, devolvendo texto vazio
                    # (finish_reason=MAX_TOKENS). Como as respostas aqui são curtas e
                    # bem ancoradas no CONTEXTO (não precisam de raciocínio longo),
                    # desligamos o "thinking" — mais rápido e evita esse problema.
                    "thinking_config": {"thinking_budget": 0},
                },
            )
            texto = (resposta.text or "").strip()
            if not texto:
                motivo = None
                try:
                    motivo = resposta.candidates[0].finish_reason
                except Exception:
                    pass
                raise RuntimeError(f"resposta vazia da API Gemini (finish_reason={motivo})")
            return texto
        except Exception as erro:
            ultimo_erro = erro
            transitorio = any(cod in str(erro) for cod in ("503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED"))
            if transitorio and tentativa < _GEMINI_TENTATIVAS:
                print(f"[agent] Gemini instável (tentativa {tentativa}/{_GEMINI_TENTATIVAS}: {erro}) — tentando de novo em {_GEMINI_ESPERA_SEGUNDOS}s...")
                time.sleep(_GEMINI_ESPERA_SEGUNDOS)
                continue
            raise

    raise ultimo_erro  # pragma: no cover — inatingível, loop sempre retorna ou levanta


def _responder_llm(pergunta: str, chave: str) -> RespostaAgente:
    contexto = _montar_contexto()
    texto = _chamar_gemini(pergunta, contexto, chave)
    return RespostaAgente(
        texto=texto,
        fontes=[f"IA online ({config.GEMINI_MODEL})", "dados atuais do pipeline (previsões, métricas, incidentes)"],
        confianca=0.8,
        sugestoes=list(_SUGESTOES_PADRAO),
        figura=None,
        intencao="llm_gemini",
    )


# ---------------------------------------------------------------------------
# Roteador público — tenta IA online, cai pro motor de regras se indisponível
# ---------------------------------------------------------------------------

def responder(pergunta: str) -> RespostaAgente:
    chave = _ler_chave_gemini()
    if chave:
        try:
            return _responder_llm(pergunta, chave)
        except Exception as erro:
            print(f"[agent] IA online indisponível ({erro}) — usando motor de regras offline.")
            resposta = _responder_regras(pergunta)
            resposta.texto += "\n\n_(IA online indisponível no momento — resposta gerada pelo motor de regras offline.)_"
            return resposta
    return _responder_regras(pergunta)


if __name__ == "__main__":
    import sys

    pergunta_cli = " ".join(sys.argv[1:]) or "previsão para amanhã"
    resultado = responder(pergunta_cli)
    print(resultado.texto)
