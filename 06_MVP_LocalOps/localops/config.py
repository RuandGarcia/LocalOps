"""
config.py — parâmetros globais e regras de negócio do LocalOps.

As regras de KPI/OLA abaixo vêm do "Dicionário de Dados - v2" (Challenge AIOps,
Locaweb x FIAP). Qualquer mudança nessas regras deve ser validada contra o
dicionário antes de alterar este arquivo.
"""

from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = ROOT_DIR / "data"
MODELS_DIR = ROOT_DIR / "models"
REPORTS_DIR = ROOT_DIR / "reports"

RAW_XLSX_PATH = DATA_DIR / "LW-DATASET.xlsx"
DB_PATH = DATA_DIR / "localops.db"
FEATURES_PARQUET_PATH = DATA_DIR / "features_serie_diaria.parquet"
INCIDENTES_PARQUET_PATH = DATA_DIR / "incidentes.parquet"

FORECAST_PARQUET_PATH = MODELS_DIR / "forecast.parquet"
BACKTEST_PARQUET_PATH = MODELS_DIR / "backtest.parquet"

METRICS_JSON_PATH = REPORTS_DIR / "metricas.json"
SHAP_JSON_PATH = REPORTS_DIR / "shap.json"
RECOMMENDATIONS_JSON_PATH = REPORTS_DIR / "recomendacoes.json"

for _dir in (DATA_DIR, MODELS_DIR, REPORTS_DIR):
    _dir.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Regras de KPI / OLA (Dicionário de Dados v2)
# ---------------------------------------------------------------------------

# Mapeamento do texto de prioridade ("1 - Crítica", ...) para código curto.
PRIORIDADE_CODIGO = {
    "1 - Crítica": "P1",
    "2 - Alta": "P2",
    "3 - Média": "P3",
    "4 - Baixa": "P4",
    "5 - Muito Baixa": "P5",
}

# Somente P1, P2 e P3 entram no cálculo do KPI (conforme dicionário).
KPI_PRIORIDADES = {"P1", "P2", "P3"}

# Limite de OLA (tempo de resolução/encerramento) por prioridade, em horas.
# P1/P2 até 4h, P3 até 12h, P4 até 24h, P5 até 96h.
OLA_HORAS = {
    "P1": 4,
    "P2": 4,
    "P3": 12,
    "P4": 24,
    "P5": 96,
}

# Status que, segundo o dicionário, não entram no cálculo do KPI mesmo que a
# prioridade seja elegível (a maioria vem de Aberto por = "Monitoramento").
STATUS_SEM_INTERVENCAO = "Sem Intervenção"

# ---------------------------------------------------------------------------
# Janelas de previsão e modelagem
# ---------------------------------------------------------------------------

HORIZONTES_PREVISAO = (1, 7)  # D+1 e D+7
FORECAST_HORIZON = 7  # horizonte "longo" usado pelo dashboard (D+7)

# Séries previstas: total, por prioridade (P2/P3) e perímetro do KPI.
SERIES_PREVISTAS = {
    "total": "Volume total",
    "p2": "P2 (alta)",
    "p3": "P3 (média)",
    "kpi": "Perímetro KPI",
}

LAGS_DIAS = (1, 7, 14)
MEDIAS_MOVEIS_DIAS = (7, 30)

# Número de cortes no backtest rolling-origin.
BACKTEST_N_CORTES = 8

# Split temporal para os classificadores de risco (Modelo A e Modelo B).
CLASSIFICADORES_CORTE_TREINO = "2025-10-01"
CLASSIFICADORES_JANELA_TESTE_DIAS = 90

# Anos considerados para feriados nacionais (BR).
ANOS_FERIADOS = list(range(2023, 2027))

RANDOM_STATE = 42

# ---------------------------------------------------------------------------
# Agente conversacional — IA online (Gemini, camada gratuita)
# ---------------------------------------------------------------------------

# A chave é lida em runtime (nunca fica hardcoded aqui): de GEMINI_API_KEY no
# ambiente, ou de st.secrets["GEMINI_API_KEY"] (arquivo .streamlit/secrets.toml,
# que NÃO deve ir pro Git). Sem chave configurada, o agente cai automaticamente
# no motor de regras offline (ver localops/agent.py) — o dashboard nunca quebra
# por falta de IA online.
GEMINI_MODEL = "gemini-2.5-flash"
