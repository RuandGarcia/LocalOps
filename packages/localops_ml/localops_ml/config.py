"""Paths, windows and rules shared by the S2 pipeline (walk-forward forecast and noise filter)."""
from __future__ import annotations

import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
# Env overrides let the pipeline container point at its volumes (the installed package has no repo).
DADOS = Path(os.environ.get("LOCALOPS_DADOS", REPO / "dados"))  # raw base and per-incident caches: never versioned (plan E5)
ARTEFATOS = Path(os.environ.get("LOCALOPS_ARTEFATOS", REPO / "artefatos"))  # aggregated outputs read by the API and the agent

XLSX = Path(os.environ.get("LOCALOPS_XLSX", DADOS / "LW-DATASET.xlsx"))
INCIDENTES = DADOS / "incidentes.parquet"
FILA_ALARMES = DADOS / "fila_alarmes.parquet"
# Ingestion: the API drops new batches here; the pipeline worker merges them into INCIDENTES.
ENTRADA = Path(os.environ.get("LOCALOPS_ENTRADA", DADOS / "entrada"))

# Order of the 19 columns of the "Dataset Geral" sheet (Dicionário de Dados v2).
COLUNAS = [
    "numero", "prioridade_txt", "produto", "categoria", "subcategoria", "equipe", "item_config",
    "aberto", "resolvido", "encerrado", "duracao_seg", "codigo_fechamento", "descricao", "solucao",
    "aberto_por", "incidente_pai", "status", "entrou_kpi_txt", "kpi_violado_txt",
]

SEM_INTERVENCAO = "Sem Intervenção"
INICIO_BASE = "2025-01-01"  # 2023–2024 hold only 732 leftover records; the daily series starts in 2025

# The volume regime changed on 2025-09-01 (monitoring alarms went from ~2k to ~21k a month).
# Series that broke train only after the break; human load and the KPI perimeter did not break.
INICIO_TREINO = {
    "total": "2025-09-01",
    "humano": INICIO_BASE,
    "p2": "2025-09-01",
    "p3": "2025-09-01",
    "kpi": INICIO_BASE,
}
SERIES = {
    "total": "Volume total de registros",
    "humano": "Registros que exigiram uma pessoa",
    "p2": "Registros P2",
    "p3": "Registros P3",
    "kpi": "Perímetro do KPI (entrou para KPI)",
}
HORIZONTES = (1, 7)

# Walk-forward: one origin per day. Model and interval are chosen on target dates in SELECAO and
# measured, untouched, on TESTE.
SELECAO = ("2025-10-01", "2025-11-30")
TESTE = ("2025-12-01", "2025-12-31")
NIVEL_INTERVALO = 0.80

# Noise filter: train, pick the threshold, then test, each on its own month block.
FILA_TREINO = ("2025-09-01", "2025-10-31")
FILA_VALIDACAO = ("2025-11-01", "2025-11-30")
FILA_TESTE = ("2025-12-01", "2025-12-31")
FILA_RECALL_ALVO = 0.97
FILA_RECALLS = (0.95, 0.97, 0.99)  # alternatives shown on the panel

# Only fields that exist when the alarm opens may feed the filter (anti-leak test enforces it).
CAMPOS_NA_ABERTURA = {"aberto", "descricao", "item_config", "aberto_por"}

RANDOM_STATE = 42
