"""Páginas do dashboard LocalOps."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from localops import agent
from localops.config import FORECAST_HORIZON, REPORTS_DIR
from localops import store

C = {"fundo": "#0b0e26", "card": "#151a3d", "azul": "#5b8cff", "vermelho": "#ff4d6d", "verde": "#2ee6a6",
     "amarelo": "#ffc857", "roxo": "#7c6cff", "cinza": "#9aa3c7"}
DIAS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
NIVEL_CSS = {"CRÍTICO": "lo-crit", "ALTO": "lo-alto", "MÉDIO": "lo-medio", "BAIXO": "lo-baixo"}


def _layout(fig: go.Figure, titulo: str = "", altura: int = 360) -> go.Figure:
    fig.update_layout(title=titulo, template="plotly_dark", paper_bgcolor=C["fundo"], plot_bgcolor=C["fundo"],
                      margin=dict(l=30, r=20, t=48 if titulo else 20, b=30), height=altura,
                      legend=dict(orientation="h", y=-0.18), font=dict(size=12))
    fig.update_xaxes(gridcolor="#1f2447")
    fig.update_yaxes(gridcolor="#1f2447")
    return fig


def _tag(nivel: str) -> str:
    return f'<span class="lo-tag {NIVEL_CSS.get(nivel, "lo-medio")}">{nivel}</span>'


@st.cache_data(show_spinner=False)
def _dados():
    return store.incidentes(), store.serie_diaria()


@st.cache_data(show_spinner=False)
def _artefatos():
    # nomes qualificados: as páginas abaixo também se chamam previsoes/recomendacoes
    return (store.previsoes(), store.backtest(), store.metricas(),
            store.ler_json(REPORTS_DIR / "shap.json"), store.ler_json(REPORTS_DIR / "recomendacoes.json"))


# =============================================================================== 1. Visão geral
def visao_geral():
    df, s = _dados()
    st.title("Visão geral da operação")
    st.caption("Dataset ITSM Locaweb · base para previsão, explicabilidade e recomendação")

    kpi = df[df["entrou_kpi"]]
    c = st.columns(6)
    c[0].metric("Incidentes", f"{len(df):,}".replace(",", "."))
    c[1].metric("Período", f"{df['aberto'].min():%m/%Y} – {df['aberto'].max():%m/%Y}")
    c[2].metric("Equipes / Produtos", f"{df['equipe'].nunique()} / {df['produto'].nunique() - 1}")
    c[3].metric("Críticos (P1+P2)", f"{df['prioridade'].isin(['P1', 'P2']).mean():.1%}")
    c[4].metric("Medidos no KPI", f"{len(kpi):,}".replace(",", "."))
    c[5].metric("OLA violado", f"{int(kpi['kpi_violado'].sum())}", f"{kpi['kpi_violado'].mean():.2%} dos medidos", delta_color="inverse")

    s25 = s[s["ds"] >= "2025-01-01"]
    fig = go.Figure()
    fig.add_scatter(x=s25["ds"], y=s25["y"], name="Incidentes/dia", line=dict(color=C["azul"], width=1.2))
    fig.add_scatter(x=s25["ds"], y=s25["y"].rolling(7).mean(), name="Média móvel 7d", line=dict(color=C["vermelho"], width=2.5))
    st.plotly_chart(_layout(fig, "Volume diário de incidentes — 2025"), width="stretch")

    col1, col2 = st.columns([3, 2])
    with col1:
        m = df[df["ano"] == 2025].groupby(["ano_mes", "prioridade"]).size().unstack(fill_value=0)
        fig = go.Figure()
        cores = {"P1": C["vermelho"], "P2": C["amarelo"], "P3": C["azul"], "P4": C["roxo"], "P5": C["cinza"]}
        for p in m.columns:
            fig.add_bar(x=m.index, y=m[p], name=p, marker_color=cores.get(p))
        fig.update_layout(barmode="stack")
        st.plotly_chart(_layout(fig, "Incidentes por mês e prioridade (2025)"), width="stretch")
    with col2:
        eq = df["equipe"].value_counts(normalize=True).head(8)
        fig = go.Figure(go.Bar(x=eq.values * 100, y=eq.index, orientation="h",
                               marker_color=[C["vermelho"] if v > 0.5 else C["azul"] for v in eq.values]))
        fig.update_layout(yaxis=dict(autorange="reversed"), xaxis_title="% dos incidentes")
        st.plotly_chart(_layout(fig, "Concentração de carga por equipe"), width="stretch")

    col1, col2 = st.columns([3, 2])
    with col1:
        d25 = df[df["ano"] == 2025]
        hm = d25.groupby(["dia_semana_num", "hora"]).size().unstack(fill_value=0).reindex(range(7), fill_value=0)
        fig = go.Figure(go.Heatmap(z=hm.values, x=list(range(24)), y=DIAS, colorscale="Blues", showscale=False))
        st.plotly_chart(_layout(fig, "Sazonalidade: hora × dia da semana (2025)", 300), width="stretch")
    with col2:
        st.markdown("#### O que os dados mostram")
        ac1, ac7 = s25["y"].autocorr(1), s25["y"].autocorr(7)
        fds = d25.groupby(["fim_de_semana", "data"]).size().groupby(level=0).mean()
        queda = 1 - fds.get(True, 0) / fds.get(False, 1)
        st.markdown(f"""
<div class="lo-card">🧠 <b>A série tem memória</b>: autocorrelação de <b>{ac1:.2f}</b> em D+1 e <b>{ac7:.2f}</b> em D+7 — base para prever.</div>
<div class="lo-card">⏰ <b>Pico 9h–11h</b> em dias úteis; fim de semana tem <b>{queda:.0%}</b> menos incidentes por dia.</div>
<div class="lo-card">⚖️ <b>Team14</b> concentra <b>{eq.iloc[0]:.1%}</b> de toda a carga — risco estrutural de sobrecarga.</div>
<div class="lo-card">🏷️ <b>{df['categoria'].eq('(sem categoria)').mean():.0%}</b> dos registros sem categoria/produto — oportunidade de qualidade de dados.</div>
""", unsafe_allow_html=True)


# =============================================================================== 2. Previsões
def previsoes():
    df, s = _dados()
    prev, bt, met, shap, rec = _artefatos()
    st.title("Previsão de incidentes — D+1 e D+7")
    if prev.empty:
        st.warning("Execute `python run_pipeline.py` para gerar as previsões.")
        return

    rot = {"total": "Volume total", "P2": "Prioridade P2 (alta)", "P3": "Prioridade P3 (média)", "kpi": "Incidentes medidos no KPI"}
    c1, c2 = st.columns([2, 1])
    seg = c1.selectbox("Série", list(rot), format_func=rot.get)
    modelo = c2.selectbox("Modelo", ["ensemble", "prophet", "xgboost"], format_func=lambda m: {"ensemble": "Ensemble (Prophet + XGBoost)", "prophet": "Prophet", "xgboost": "XGBoost"}[m])
    col = "y" if seg == "total" else f"y_{seg}"

    p = prev[(prev["segmento"] == seg) & (prev["modelo"] == modelo)].sort_values("ds")
    band = prev[(prev["segmento"] == seg) & (prev["modelo"] == "prophet")].sort_values("ds")
    m30 = s[col].tail(30).mean()
    std30 = s[col].tail(30).std()
    d1 = p[p["horizonte"] == 1].iloc[0]
    d7 = p[p["horizonte"] == FORECAST_HORIZON].iloc[0] if (p["horizonte"] == FORECAST_HORIZON).any() else p.iloc[-1]

    def nivel(v):
        return "CRÍTICO" if v > m30 + 2 * std30 else "ALTO" if v > m30 + std30 else "MÉDIO" if v > m30 else "BAIXO"

    k = st.columns(4)
    k[0].metric(f"D+1 · {d1['ds']:%d/%m}", f"{d1['yhat']:.0f}", f"{(d1['yhat'] / m30 - 1) * 100:+.0f}% vs média 30d")
    k[1].metric(f"D+7 · {d7['ds']:%d/%m}", f"{d7['yhat']:.0f}", f"{(d7['yhat'] / m30 - 1) * 100:+.0f}% vs média 30d")
    b1 = band[band["horizonte"] == 1].iloc[0]
    k[2].metric("IC 95% (D+1)", f"{b1['yhat_lower']:.0f} – {b1['yhat_upper']:.0f}")
    k[3].markdown(f"<div class='lo-card'><span class='lo-muted'>NÍVEL DE RISCO D+1</span><br><br>{_tag(nivel(d1['yhat']))}</div>", unsafe_allow_html=True)

    hist = s.tail(60)
    fig = go.Figure()
    fig.add_scatter(x=hist["ds"], y=hist[col], name="Histórico", line=dict(color=C["azul"]))
    fig.add_scatter(x=band["ds"], y=band["yhat_upper"], line=dict(width=0), showlegend=False, hoverinfo="skip")
    fig.add_scatter(x=band["ds"], y=band["yhat_lower"], fill="tonexty", fillcolor="rgba(255,77,109,0.18)", line=dict(width=0), name="IC 95% (Prophet)")
    fig.add_scatter(x=p["ds"], y=p["yhat"], name=f"Previsão ({modelo})", line=dict(color=C["vermelho"], width=3), mode="lines+markers")
    fig.add_hline(y=m30, line_dash="dot", line_color=C["cinza"], annotation_text="média 30d")
    st.plotly_chart(_layout(fig, f"{rot[seg]} — últimos 60 dias + próximos {FORECAST_HORIZON}", 400), width="stretch")

    col1, col2 = st.columns([1, 1])
    with col1:
        st.markdown("#### Composição prevista para D+1")
        comp = {}
        for sg in ("P2", "P3"):
            q = prev[(prev["segmento"] == sg) & (prev["modelo"] == "ensemble") & (prev["horizonte"] == 1)]
            comp[sg] = float(q["yhat"].iloc[0]) if len(q) else 0
        tot = float(prev[(prev["segmento"] == "total") & (prev["modelo"] == "ensemble") & (prev["horizonte"] == 1)]["yhat"].iloc[0])
        comp["P4/P5/outros"] = max(tot - comp["P2"] - comp["P3"], 0)
        fig = go.Figure(go.Pie(labels=list(comp), values=list(comp.values()), hole=0.55,
                               marker_colors=[C["amarelo"], C["azul"], C["roxo"]]))
        fig.add_annotation(text=f"<b>{tot:.0f}</b><br>total", showarrow=False, font=dict(size=18))
        st.plotly_chart(_layout(fig, "", 300), width="stretch")
    with col2:
        st.markdown("#### Qualidade das previsões (backtest)")
        mseg = met.get("forecast", {}).get(seg, {})
        linhas = []
        for mod in ("prophet", "xgboost", "baseline"):
            for h in (1, FORECAST_HORIZON):
                r = mseg.get(f"{mod}_D+{h}", {})
                if r:
                    linhas.append({"Modelo": {"prophet": "Prophet", "xgboost": "XGBoost", "baseline": "Baseline (mesmo dia sem. anterior)"}[mod],
                                   "Horizonte": f"D+{h}", "WAPE": f"{r['wape']:.1%}", "MAE": f"{r['mae']:.1f}"})
        st.dataframe(pd.DataFrame(linhas), hide_index=True, width="stretch")
        meta = met.get("forecast", {}).get("_meta", {})
        st.caption(f"Backtest rolling-origin com {meta.get('cutoffs_backtest', 8)} cortes semanais (Prophet) e janela de "
                   f"{meta.get('janela_teste_xgb_dias', 56)} dias (XGBoost). WAPE = erro absoluto / volume real.")

    btp = bt[(bt["segmento"] == seg) & (bt["modelo"] == "prophet")].sort_values("ds")
    if len(btp):
        fig = go.Figure()
        fig.add_scatter(x=btp["ds"], y=btp["y"], name="Real", line=dict(color=C["azul"]))
        fig.add_scatter(x=btp["ds"], y=btp["yhat"], name="Previsto (Prophet, horizonte 1–7)", line=dict(color=C["vermelho"], dash="dot"))
        st.plotly_chart(_layout(fig, "Backtest — real vs. previsto nas últimas 8 semanas", 320), width="stretch")


# =============================================================================== 3. Explicabilidade
def explicabilidade():
    prev, bt, met, shap, rec = _artefatos()
    st.title("Explicabilidade — por que o modelo previu isso?")
    st.caption("SHAP (SHapley Additive exPlanations) decompõe cada previsão XGBoost em contribuições por variável.")
    if not shap:
        st.warning("Execute `python run_pipeline.py` para gerar as explicações SHAP.")
        return

    st.markdown("### 1 · Previsão de volume (XGBoost D+1 / D+7)")
    c1, c2 = st.columns(2)
    seg = c1.selectbox("Série", ["total", "P2", "P3"], format_func=lambda x: {"total": "Volume total", "P2": "P2", "P3": "P3"}[x])
    h = c2.selectbox("Horizonte", [1, 7], format_func=lambda x: f"D+{x}")
    info = shap.get("forecast", {}).get(f"{seg}_h{h}")
    if info:
        col1, col2 = st.columns([3, 2])
        with col1:
            contrib = pd.DataFrame(info["contribuicoes"])
            fig = go.Figure(go.Waterfall(
                orientation="h", measure=["relative"] * len(contrib) + ["total"],
                y=[f"{r.rotulo} = {r.valor}" for r in contrib.itertuples()][::-1] + ["previsto"],
                x=list(contrib["shap"][::-1]) + [info["previsto"]], base=info["base"],
                increasing=dict(marker_color=C["vermelho"]), decreasing=dict(marker_color=C["verde"]), totals=dict(marker_color=C["azul"]),
                connector=dict(line=dict(color="#2a2f5a")),
            ))
            st.plotly_chart(_layout(fig, f"Waterfall SHAP — {seg} D+{h} ({info['ds_previsto']})", 420), width="stretch")
        with col2:
            st.metric("Baseline do modelo", f"{info['base']:.0f}")
            st.metric("Valor previsto", f"{info['previsto']:.0f}", f"{info['previsto'] - info['base']:+.0f} explicados")
            top = contrib.iloc[0]
            st.markdown(f"""<div class="lo-card">🔎 <b>Maior driver:</b> {top.rotulo} = {top.valor} ({top.shap:+.0f} incidentes)<br>
<span class="lo-muted">Top-3 features explicam {contrib['shap'].abs().head(3).sum() / max(contrib['shap'].abs().sum() + abs(info['outras_features']), 1e-9):.0%} da variação.</span></div>""", unsafe_allow_html=True)

    st.markdown("### 2 · Classificadores de risco (XGBoost)")
    tab1, tab2 = st.tabs(["Risco de incidente crítico (P1/P2)", "Risco de violação de OLA"])
    for tab, nome in ((tab1, "risco_critico"), (tab2, "risco_ola")):
        with tab:
            m = met.get("classificacao", {}).get(nome, {})
            k = st.columns(5)
            k[0].metric("AUC-ROC", f"{m.get('auc_roc', 0):.3f}")
            k[1].metric("AUC-PR", f"{m.get('auc_pr', 0):.3f}")
            k[2].metric("Precisão", f"{m.get('precision', 0):.0%}")
            k[3].metric("Recall", f"{m.get('recall', 0):.0%}")
            k[4].metric("Positivos no teste", f"{m.get('positivos_teste', 0)} / {m.get('n_teste', 0):,}".replace(",", "."))
            st.caption(f"Split temporal: treino até {m.get('corte_temporal')} · teste = últimos 90 dias · limiar {m.get('limiar', 0):.2f} (melhor F1).")
            info = shap.get(nome, {})
            col1, col2 = st.columns([1, 1])
            with col1:
                imp = pd.DataFrame(info.get("importancia", [])).head(10)
                if len(imp):
                    fig = go.Figure(go.Bar(x=imp["valor"][::-1], y=imp["rotulo"][::-1], orientation="h", marker_color=C["roxo"]))
                    st.plotly_chart(_layout(fig, "Importância global (média |SHAP|)", 360), width="stretch")
            with col2:
                st.markdown("**Exemplos de maior risco previsto (teste)**")
                for ex in info.get("exemplos", [])[:3]:
                    drivers = ", ".join(f"{d['rotulo']}={d['valor']} ({d['shap']:+.2f})" for d in ex["drivers"][:3])
                    real = "✅ confirmado" if ex["real"] else "— não ocorreu"
                    st.markdown(f"""<div class="lo-card"><b>{ex['numero']}</b> · {ex['equipe']} · {ex['categoria']} · {ex['prioridade']}<br>
probabilidade <b>{ex['proba']:.0%}</b> {real}<br><span class="lo-muted">{drivers}</span></div>""", unsafe_allow_html=True)


# =============================================================================== 4. IncidentMap
def incident_map():
    df, s = _dados()
    prev, bt, met, shap, rec = _artefatos()
    st.title("IncidentMap NOC — onde agir")
    c1, c2, c3 = st.columns([1, 2, 1])
    janela = c1.selectbox("Janela", [30, 90, 365], format_func=lambda d: f"Últimos {d} dias")
    prios = c2.multiselect("Prioridades", ["P1", "P2", "P3", "P4", "P5"], default=["P1", "P2", "P3", "P4", "P5"])
    metrica = c3.selectbox("Cor do mapa", ["Volume", "% críticos (P1/P2)", "Violações de OLA"])
    rec_df = df[(df["aberto"] >= df["aberto"].max() - pd.Timedelta(days=janela)) & df["prioridade"].isin(prios)]

    esq, meio, dir_ = st.columns([1.1, 3, 1.2])
    with esq:
        st.markdown("#### 🔔 Alertas ativos")
        for a in [x for x in rec.get("alertas", []) if x["nivel"] in ("CRÍTICO", "ALTO", "MÉDIO")][:6]:
            st.markdown(f"""<div class="lo-card">{_tag(a['nivel'])}<b>{a['segmento']}</b> · D+{a['horizonte']} ({a['data'][5:]})<br>
<span class="lo-muted">previsto {a['previsto']:.0f} ({a['variacao_pct']:+.0f}% vs média 30d)</span></div>""", unsafe_allow_html=True)
        if not rec.get("alertas"):
            st.info("Sem alertas gerados.")
    with meio:
        cats = [c for c in rec_df["categoria"].value_counts().index if c != "(sem categoria)"][:16]
        sub = rec_df[rec_df["categoria"].isin(cats)]
        eqs = sub["equipe"].value_counts().index[:10]
        sub = sub[sub["equipe"].isin(eqs)]
        if metrica == "Volume":
            z = sub.groupby(["categoria", "equipe"]).size().unstack(fill_value=0)
            esc, fmt = "Reds", ".0f"
        elif metrica == "% críticos (P1/P2)":
            z = sub.groupby(["categoria", "equipe"])["prioridade"].apply(lambda x: x.isin(["P1", "P2"]).mean() * 100).unstack(fill_value=0)
            esc, fmt = "YlOrRd", ".0f"
        else:
            z = sub.groupby(["categoria", "equipe"])["kpi_violado"].sum().unstack(fill_value=0)
            esc, fmt = "Reds", ".0f"
        z = z.reindex(index=cats, columns=eqs).fillna(0)
        fig = go.Figure(go.Heatmap(z=z.values, x=z.columns, y=z.index, colorscale=esc, text=z.values, texttemplate="%{text:" + fmt + "}",
                                   textfont=dict(size=9), colorbar=dict(title=metrica)))
        st.plotly_chart(_layout(fig, f"Equipe × Categoria — {metrica} ({janela} dias)", 520), width="stretch")
    with dir_:
        st.markdown("#### 🏋️ Ranking de carga")
        carga = rec_df["equipe"].value_counts().head(8)
        for eq, n in carga.items():
            pct = n / len(rec_df)
            cor = C["vermelho"] if pct > 0.5 else C["amarelo"] if pct > 0.1 else C["verde"]
            st.markdown(f"""<div style="margin-bottom:6px"><span style="font-size:.85rem">{eq} · <b>{n:,}</b> ({pct:.1%})</span>
<div style="background:#1f2447;border-radius:4px;height:6px"><div style="width:{min(pct * 100, 100):.0f}%;background:{cor};height:6px;border-radius:4px"></div></div></div>""",
                        unsafe_allow_html=True)
        st.markdown("#### ⏰ Distribuição horária")
        hh = rec_df.groupby("hora").size().reindex(range(24), fill_value=0)
        fig = go.Figure(go.Bar(x=hh.index, y=hh.values, marker_color=[C["vermelho"] if 9 <= i <= 11 else C["azul"] for i in hh.index]))
        st.plotly_chart(_layout(fig, "", 180), width="stretch")

    st.markdown("#### Top categorias — volume e risco")
    top = rec_df[rec_df["categoria"] != "(sem categoria)"].groupby("categoria").agg(
        incidentes=("numero", "size"), pct_criticos=("prioridade", lambda x: x.isin(["P1", "P2"]).mean()),
        violacoes=("kpi_violado", "sum"), duracao_mediana_h=("duracao_horas", "median")).sort_values("incidentes", ascending=False).head(8)
    cols = st.columns(4)
    for i, (cat, r) in enumerate(top.iterrows()):
        with cols[i % 4]:
            st.markdown(f"""<div class="lo-card"><span class="lo-muted">{cat}</span><br><b style="font-size:1.4rem">{int(r.incidentes):,}</b> incidentes<br>
<span class="lo-muted">{r.pct_criticos:.0%} críticos · {int(r.violacoes)} violações · mediana {r.duracao_mediana_h:.1f}h</span></div>""", unsafe_allow_html=True)


# =============================================================================== 5. Agente IA
def agente():
    st.title("Agente IA — análise sob demanda")
    st.caption("Motor analítico offline: interpreta a pergunta, consulta os dados e modelos, e responde com gráfico, drivers e fontes.")
    if "chat" not in st.session_state:
        st.session_state.chat = []
    if "pendente" not in st.session_state:
        st.session_state.pendente = None

    sugestoes = ["Previsão para amanhã", "cat71 vai piorar?", "Quais equipes violam mais OLA?", "Compare cat71 e cat77", "Qual o horário de pico?"]
    cols = st.columns(len(sugestoes))
    for c, sug in zip(cols, sugestoes):
        if c.button(sug, width="stretch"):
            st.session_state.pendente = sug

    for msg in st.session_state.chat:
        with st.chat_message(msg["papel"], avatar="🧑‍💻" if msg["papel"] == "user" else "🤖"):
            st.markdown(msg["texto"])
            if msg.get("figura") is not None:
                st.plotly_chart(msg["figura"], width="stretch", key=f"fig_{id(msg)}")
            if msg.get("fontes"):
                st.caption("Fontes: " + " · ".join(msg["fontes"]))

    pergunta = st.chat_input("Pergunte sobre categorias, equipes, previsões, OLA...") or st.session_state.pendente
    if pergunta:
        st.session_state.pendente = None
        st.session_state.chat.append({"papel": "user", "texto": pergunta})
        with st.chat_message("user", avatar="🧑‍💻"):
            st.markdown(pergunta)
        with st.chat_message("assistant", avatar="🤖"):
            with st.spinner("Analisando..."):
                r = agent.responder(pergunta)
            st.markdown(r.texto)
            if r.figura is not None:
                st.plotly_chart(r.figura, width="stretch")
            if r.fontes:
                st.caption("Fontes: " + " · ".join(r.fontes) + f" · confiança {r.confianca:.0%}")
            if r.sugestoes:
                st.caption("Continue com: " + " | ".join(r.sugestoes))
        st.session_state.chat.append({"papel": "assistant", "texto": r.texto, "figura": r.figura, "fontes": r.fontes})


# =============================================================================== 6. Recomendações
def recomendacoes():
    prev, bt, met, shap, rec = _artefatos()
    st.title("Recomendações operacionais")
    st.caption("Geradas automaticamente a partir das previsões, da carga por equipe e do perfil de risco por categoria.")
    if not rec:
        st.warning("Execute `python run_pipeline.py`.")
        return
    cor = {1: "lo-crit", 2: "lo-alto", 3: "lo-medio"}
    for r in rec.get("recomendacoes", []):
        st.markdown(f"""<div class="lo-card"><span class="lo-tag {cor.get(r['prioridade'], 'lo-medio')}">Prioridade {r['prioridade']}</span>
<b>{r['acao']}</b><br><span class="lo-muted">Por quê: {r['motivo']}<br>Impacto esperado: {r['impacto']} · Público: {r['publico']}</span></div>""",
                    unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("#### Carga e violações por equipe (30 dias)")
        ce = pd.DataFrame(rec.get("carga_equipes", [])).head(8)
        if len(ce):
            ce["pct_carga"] = (ce["pct_carga"] * 100).round(1).astype(str) + "%"
            ce["pct_criticos"] = (ce["pct_criticos"] * 100).round(0).astype(str) + "%"
            st.dataframe(ce[["equipe", "incidentes_30d", "pct_carga", "kpi_30d", "violacoes_30d", "pct_criticos"]], hide_index=True, width="stretch")
    with col2:
        st.markdown("#### Categorias estruturalmente críticas")
        rc = pd.DataFrame(rec.get("risco_categorias", [])).head(8)
        if len(rc):
            fig = go.Figure(go.Bar(x=rc["pct_p2"] * 100, y=rc["categoria"], orientation="h", marker_color=C["amarelo"]))
            fig.update_layout(yaxis=dict(autorange="reversed"), xaxis_title="% de incidentes P2")
            st.plotly_chart(_layout(fig, "", 320), width="stretch")
