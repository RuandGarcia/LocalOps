"""LocalOps — dashboard Streamlit (MVP preliminar, Sprint 3).

Execução:  streamlit run dashboard/app.py   (a partir da pasta 06_MVP_LocalOps)
"""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dashboard import views  # noqa: E402
from localops import __version__  # noqa: E402

st.set_page_config(page_title="LocalOps · AIOps Locaweb", page_icon="📡", layout="wide", initial_sidebar_state="expanded")

st.markdown(
    """
<style>
.block-container {padding-top: 1.2rem; padding-bottom: 2rem;}
[data-testid="stMetric"] {background: #151a3d; border: 1px solid #2a2f5a; border-radius: 12px; padding: 12px 16px;}
[data-testid="stMetricLabel"] {color: #9aa3c7; font-size: 0.8rem; text-transform: uppercase; letter-spacing: .04em;}
[data-testid="stMetricValue"] {font-size: 1.9rem;}
.lo-card {background: #151a3d; border: 1px solid #2a2f5a; border-radius: 12px; padding: 14px 18px; margin-bottom: 10px;}
.lo-tag {display:inline-block; padding: 2px 10px; border-radius: 999px; font-size: .75rem; font-weight: 600; margin-right: 6px;}
.lo-crit {background:#ff4d6d33; color:#ff4d6d; border:1px solid #ff4d6d;}
.lo-alto {background:#ffc85733; color:#ffc857; border:1px solid #ffc857;}
.lo-medio {background:#5b8cff33; color:#5b8cff; border:1px solid #5b8cff;}
.lo-baixo {background:#2ee6a633; color:#2ee6a6; border:1px solid #2ee6a6;}
.lo-muted {color:#9aa3c7; font-size:.85rem;}
h1, h2, h3 {color:#e8ecff;}
</style>
""",
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown("## 📡 LocalOps")
    st.caption(f"AIOps · Challenge Locaweb · Paladinos · v{__version__}")
    st.divider()

paginas = [
    st.Page(views.visao_geral, title="Visão geral", icon="📊", default=True),
    st.Page(views.previsoes, title="Previsões D+1 / D+7", icon="📈"),
    st.Page(views.explicabilidade, title="Explicabilidade (SHAP)", icon="🔍"),
    st.Page(views.incident_map, title="IncidentMap NOC", icon="🗺️"),
    st.Page(views.agente, title="Agente IA", icon="🤖"),
    st.Page(views.recomendacoes, title="Recomendações", icon="⚡"),
]
st.navigation(paginas).run()

with st.sidebar:
    st.divider()
    st.caption("Dados: ITSM Locaweb 2023–2025 (122.543 incidentes)\n\nModelos: Prophet · XGBoost · SHAP")
