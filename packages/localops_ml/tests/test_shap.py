import math

import pytest

from localops_ml import config, fila


@pytest.fixture(scope="module")
def explicado():
    if not (config.DADOS / "incidentes.parquet").exists():
        pytest.skip("base local ausente")
    from localops_ml import dados
    r = fila.treinar(fila.montar_alarmes(dados.carregar_incidentes()))
    return (r, *fila.explicar(r))


def test_contribuicoes_somam_a_probabilidade(explicado):
    _, _, por = explicado
    for numero, v in list(por["alarmes"].items())[:200]:
        logit = por["base"] + sum(v[6:12])
        assert abs(1 / (1 + math.exp(-logit)) - v[12]) < 0.01, numero


def test_resumo_bate_com_metricas(explicado):
    r, resumo, _ = explicado
    assert [i["feature"] for i in resumo["importancia"]] == list(r["metricas"]["importancia_shap_media"])
    assert abs(sum(i["peso_pct"] for i in resumo["importancia"]) - 100) < 0.5
    assert resumo["n_alarmes"] == len(r["teste"]) and len(resumo["exemplos"]) == 3


def test_exemplos_cobrem_alto_limiar_e_baixo(explicado):
    _, resumo, por = explicado
    p = [por["alarmes"][n][12] for n in resumo["exemplos"]]
    assert p[0] > resumo["limiar"] * 10 and p[2] < resumo["limiar"]


def test_dependencia_cobre_todos_os_alarmes(explicado):
    _, resumo, _ = explicado
    for f, faixas in resumo["dependencia"].items():
        assert sum(x["n"] for x in faixas) == resumo["n_alarmes"], f


def test_na_fila_bate_com_o_filtro_mesmo_perto_do_limiar(explicado):
    # Audit 20/10: probabilities rounded to 4 places put INC8629839 (p=0,0044616, out of the queue) "in the queue".
    r, resumo, por = explicado
    t = r["teste"].set_index("numero")
    for numero in ("INC8629839", "INC8632861", "INC8634120"):
        assert (por["alarmes"][numero][12] >= resumo["limiar"]) == bool(t.loc[numero, "mantido"]), numero


def test_resumo_traz_a_taxa_real_alem_do_valor_base(explicado):
    r, resumo, _ = explicado
    assert resumo["taxa_humano"] == r["metricas"]["taxa_humano_teste"] and resumo["taxa_humano"] < resumo["base_prob"]
