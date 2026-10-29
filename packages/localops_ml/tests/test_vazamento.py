"""Anti-leak tests: a forecast or a filter score must not change when the future changes."""
import numpy as np
import pandas as pd
import pytest

from localops_ml import config, fila, previsao


@pytest.fixture
def serie():
    dias = pd.date_range("2025-01-01", "2025-12-31", freq="D")
    rng = np.random.default_rng(0)
    y = 100 + 20 * (dias.dayofweek < 5) + rng.normal(0, 5, len(dias))
    return pd.DataFrame({s: y for s in config.SERIES}, index=dias).rename_axis("data")


@pytest.mark.parametrize("modelo", list(previsao.MODELOS))
def test_previsao_ignora_o_futuro(serie, modelo):
    origem = pd.Timestamp("2025-10-15")
    so_ate_origem = previsao.prever_na_origem(serie["humano"], "humano", origem, {modelo: previsao.MODELOS[modelo]})
    futuro_alterado = serie["humano"].copy()
    futuro_alterado[futuro_alterado.index > origem] *= 50
    com_futuro = previsao.prever_na_origem(futuro_alterado, "humano", origem, {modelo: previsao.MODELOS[modelo]})
    for a, b in zip(so_ate_origem, com_futuro):
        assert a["treino_ate"] == origem
        assert a["previsto"] == pytest.approx(b["previsto"])


def test_mediana_ignora_o_futuro(serie):
    origem = pd.Timestamp("2025-10-15")
    futuro_alterado = serie["humano"].copy()
    futuro_alterado[futuro_alterado.index > origem] *= 50
    med = lambda y: [r["previsto"] for r in previsao.prever_na_origem(y, "humano", origem) if r["modelo"] == "mediana"]
    assert med(serie["humano"]) == pytest.approx(med(futuro_alterado))


def test_features_da_fila_so_usam_campos_da_abertura():
    assert set(fila.FEATURES) == set(fila.ORIGEM_DAS_FEATURES)
    usados = set().union(*fila.ORIGEM_DAS_FEATURES.values())
    assert usados <= config.CAMPOS_NA_ABERTURA, usados - config.CAMPOS_NA_ABERTURA


def test_contagens_da_fila_so_olham_o_passado():
    t = pd.to_datetime(["2025-09-01 10:00", "2025-09-01 10:10", "2025-09-01 10:20", "2025-09-01 12:00"])
    df = pd.DataFrame({"numero": list("abcd"), "aberto": t, "descricao": ["Disk 1"] * 4,
                       "item_config": ["IC1"] * 4, "humano": [True, False, False, True], "monitoramento": True})
    a = fila.montar_alarmes(df)
    assert a["n1h_tpl"].tolist() == [0, 1, 2, 0]
    assert a["n24h_ci"].tolist() == [0, 1, 2, 3]


def test_janelas_da_fila_e_da_previsao_nao_se_sobrepoem():
    assert config.FILA_TREINO[1] < config.FILA_VALIDACAO[0] <= config.FILA_VALIDACAO[1] < config.FILA_TESTE[0]
    assert config.SELECAO[1] < config.TESTE[0]
