"""
etl/build_dataset.py — carrega o LW-DATASET.xlsx, tipa e limpa os dados
segundo o "Dicionário de Dados - v2" e grava:

  * tabela `incidentes`   (SQLite, granularidade por incidente)
  * tabela `serie_diaria` (SQLite, granularidade diária)
  * data/incidentes.parquet (mesma granularidade do incidente, para uso rápido)

Uso:
    python -m localops.etl.build_dataset
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from localops import config

# ---------------------------------------------------------------------------
# Leitura e tipagem
# ---------------------------------------------------------------------------

RENAME_COLUNAS = {
    "Número": "numero",
    "Prioridade": "prioridade",
    "Produto": "produto",
    "Categoria": "categoria",
    "Subcategoria": "subcategoria",
    "Grupo designado": "grupo_designado",
    "Item de configuração": "item_configuracao",
    "Aberto": "aberto",
    "Resolvido": "resolvido",
    "Encerrado": "encerrado",
    "Duração": "duracao_segundos",
    "Código de fechamento": "codigo_fechamento",
    "Descrição resumida": "descricao_resumida",
    "Solução": "solucao",
    "Aberto por": "aberto_por",
    "Incidente Pai": "incidente_pai",
    "Status": "status",
    "Entrou para KPI?": "entrou_kpi_raw",
    "KPI Violado?": "kpi_violado_raw",
}


def _ler_xlsx(path: Path = config.RAW_XLSX_PATH) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name="Dataset Geral", engine="openpyxl")
    df = df.rename(columns=RENAME_COLUNAS)
    return df


def _tipar(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # Prioridade "2 - Alta" -> "P2" (conforme dicionário)
    df["prioridade_cod"] = df["prioridade"].map(config.PRIORIDADE_CODIGO)

    # Datas
    for col in ("aberto", "resolvido", "encerrado"):
        df[col] = pd.to_datetime(df[col], errors="coerce")

    # Duração: segundos -> horas
    df["duracao_segundos"] = pd.to_numeric(df["duracao_segundos"], errors="coerce")
    df["duracao_horas"] = df["duracao_segundos"] / 3600.0

    # Categoria/Produto/Subcategoria: nulos marcados explicitamente, não descartados
    for col in ("produto", "categoria", "subcategoria"):
        df[col] = df[col].replace("", pd.NA)
        df[col] = df[col].fillna("Não informado")

    # Flags booleanas
    df["tem_pai"] = df["incidente_pai"].notna() & (df["incidente_pai"].astype(str).str.strip() != "")
    df["sem_intervencao"] = df["status"] == config.STATUS_SEM_INTERVENCAO
    df["origem"] = df["aberto_por"].where(
        df["aberto_por"].isin(["Manual", "Monitoramento"]), "Outro"
    )

    return df


def _aplicar_regras_kpi(df: pd.DataFrame) -> pd.DataFrame:
    """Elegibilidade ao KPI e violação de OLA.

    A base já vem com o resultado oficial calculado pelo sistema da Locaweb
    (colunas "Entrou para KPI?" e "KPI Violado?" -> aqui `entrou_kpi_raw` /
    `kpi_violado_raw`). Usamos essas colunas como fonte da verdade, em vez de
    recalcular a partir de `Duração` + limite por prioridade.

    Por quê: recalculando a partir de Duração (limite do dicionário: P1/P2
    até 4h, P3 até 12h) batíamos em 3.685 violações (14,3% dos elegíveis) —
    bem acima das 248 (0,97%) citadas na Sprint 3. Comparando com as colunas
    oficiais da planilha, a contagem delas já bate exatamente com o pptx
    (25.600 elegíveis, 248 violações), e checando incidente a incidente, tem
    caso com Duração de 27h num limite de 12h (P3) que a Locaweb marca como
    "não violado" — sinal de que o cálculo real usa alguma regra adicional
    não documentada no dicionário (ex.: horário comercial, pausas do
    atendimento). Sem essa regra, não dá pra reconstruir o resultado a partir
    da Duração sozinha — então confiamos no campo que a própria Locaweb já
    calculou, que é estritamente mais confiável do que a nossa reconstrução.

    `duracao_horas` e `ola_limite_horas` continuam calculados abaixo só como
    informação de apoio (ex.: para mostrar "quanto tempo o incidente levou"
    no dashboard) — não decidem mais elegibilidade nem violação.
    """
    df = df.copy()

    df["ola_limite_horas"] = df["prioridade_cod"].map(config.OLA_HORAS)

    entrou_kpi_bool = df["entrou_kpi_raw"].astype(str).str.strip().str.upper() == "SIM"
    violado_bool = df["kpi_violado_raw"].astype(str).str.strip().str.upper() == "SIM"

    df["elegivel_kpi"] = entrou_kpi_bool
    df["ola_estourado"] = entrou_kpi_bool & violado_bool

    return df


def construir_incidentes(path: Path = config.RAW_XLSX_PATH) -> pd.DataFrame:
    df = _ler_xlsx(path)
    df = _tipar(df)
    df = _aplicar_regras_kpi(df)

    colunas_finais = [
        "numero", "prioridade", "prioridade_cod", "produto", "categoria",
        "subcategoria", "grupo_designado", "item_configuracao",
        "aberto", "resolvido", "encerrado", "duracao_segundos", "duracao_horas",
        "codigo_fechamento", "descricao_resumida", "solucao", "aberto_por",
        "origem", "incidente_pai", "tem_pai", "status", "sem_intervencao",
        "entrou_kpi_raw", "kpi_violado_raw", "elegivel_kpi",
        "ola_limite_horas", "ola_estourado",
    ]
    return df[colunas_finais]


def construir_serie_diaria(incidentes: pd.DataFrame) -> pd.DataFrame:
    """Agrega os incidentes por dia (data de abertura): total, por prioridade,
    perímetro do KPI, violações de OLA e origem (manual x monitoramento)."""

    df = incidentes.copy()
    df["data"] = df["aberto"].dt.date

    agg = df.groupby("data").agg(
        total=("numero", "count"),
        p1=("prioridade_cod", lambda s: (s == "P1").sum()),
        p2=("prioridade_cod", lambda s: (s == "P2").sum()),
        p3=("prioridade_cod", lambda s: (s == "P3").sum()),
        p4=("prioridade_cod", lambda s: (s == "P4").sum()),
        p5=("prioridade_cod", lambda s: (s == "P5").sum()),
        kpi_elegivel=("elegivel_kpi", "sum"),
        kpi_violado=("ola_estourado", "sum"),
        manual=("origem", lambda s: (s == "Manual").sum()),
        monitoramento=("origem", lambda s: (s == "Monitoramento").sum()),
        sem_intervencao=("sem_intervencao", "sum"),
    ).reset_index()

    agg["data"] = pd.to_datetime(agg["data"])

    # Preenche dias sem incidentes (não deveria ocorrer no período coberto,
    # mas garante série contínua para os modelos de série temporal).
    idx_completo = pd.date_range(agg["data"].min(), agg["data"].max(), freq="D")
    agg = agg.set_index("data").reindex(idx_completo, fill_value=0).rename_axis("data").reset_index()

    return agg


def gravar_sqlite(incidentes: pd.DataFrame, serie_diaria: pd.DataFrame, db_path: Path = config.DB_PATH) -> None:
    conn = sqlite3.connect(db_path)
    try:
        incidentes_sql = incidentes.copy()
        for col in ("aberto", "resolvido", "encerrado"):
            incidentes_sql[col] = incidentes_sql[col].astype(str)
        incidentes_sql.to_sql("incidentes", conn, if_exists="replace", index=False)

        serie_sql = serie_diaria.copy()
        serie_sql["data"] = serie_sql["data"].astype(str)
        serie_sql.to_sql("serie_diaria", conn, if_exists="replace", index=False)

        conn.execute("CREATE INDEX IF NOT EXISTS idx_incidentes_aberto ON incidentes(aberto)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_incidentes_grupo ON incidentes(grupo_designado)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_incidentes_categoria ON incidentes(categoria)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_serie_data ON serie_diaria(data)")
        conn.commit()
    finally:
        conn.close()


def run(path: Path = config.RAW_XLSX_PATH) -> tuple[pd.DataFrame, pd.DataFrame]:
    incidentes = construir_incidentes(path)
    serie_diaria = construir_serie_diaria(incidentes)

    gravar_sqlite(incidentes, serie_diaria)
    incidentes.to_parquet(config.INCIDENTES_PARQUET_PATH, index=False)

    print(f"[build_dataset] {len(incidentes):,} incidentes carregados de {path.name}")
    print(f"[build_dataset] {len(serie_diaria):,} dias na série diária "
          f"({serie_diaria['data'].min().date()} -> {serie_diaria['data'].max().date()})")
    print(f"[build_dataset] {int(incidentes['elegivel_kpi'].sum()):,} incidentes elegíveis ao KPI, "
          f"{int(incidentes['ola_estourado'].sum()):,} violações de OLA")
    print(f"[build_dataset] SQLite gravado em {config.DB_PATH}")

    return incidentes, serie_diaria


if __name__ == "__main__":
    run()
