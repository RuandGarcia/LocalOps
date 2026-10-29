"""Ingestion: a batch merges by incident number, bad rows are rejected with a reason, and nothing
reaches the pipeline when the batch changes nothing."""
import pandas as pd
import pytest

from localops_ml import config, dados, ingestao

CAB = ["Número", "Prioridade", "Produto", "Categoria", "Subcategoria", "Grupo designado", "Item de configuração",
       "Aberto", "Resolvido", "Encerrado", "Duração", "Código de fechamento", "Descrição resumida", "Solução",
       "Aberto por", "Incidente Pai", "Status", "Entrou para KPI?", "KPI Violado?"]


def _linha(numero, aberto, prioridade="3 - Média", status="Sem Intervenção"):
    return [numero, prioridade, "", "", "", "Team14", "IC00001", aberto, "", aberto, "14", "",
            "Problem: Apache Busy Workers", "", "Monitoramento", "", status, "NAO", ""]


@pytest.fixture
def base(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DADOS", tmp_path)
    monkeypatch.setattr(config, "INCIDENTES", tmp_path / "incidentes.parquet")
    monkeypatch.setattr(config, "ENTRADA", tmp_path / "entrada")
    monkeypatch.setattr(config, "ARTEFATOS", tmp_path / "artefatos")
    inicial = pd.DataFrame([_linha("INC1", "2025-12-30 10:00:00"), _linha("INC2", "2025-12-31 11:00:00")], columns=CAB)
    dados.tipar(inicial).to_parquet(config.INCIDENTES, index=False)
    config.ENTRADA.mkdir()
    return tmp_path


def _csv(pasta, nome, linhas, sep=";"):
    arq = pasta / "entrada" / nome
    pd.DataFrame(linhas, columns=CAB).to_csv(arq, index=False, sep=sep, encoding="utf-8")
    return arq


def test_lote_incorpora_novos_e_atualiza_pelo_numero(base):
    arq = _csv(base, "lote.csv", [
        _linha("INC2", "31/12/2025 11:00", status="Encerrado"),  # update, Brazilian date format
        _linha("INC3", "05/01/2026 08:30"),                      # new; 5 Jan, not 1 May
        _linha("", "2026-01-01 09:00:00"),                       # no number
        _linha("INC4", "ontem"),                                 # bad date
        _linha("INC5", "2026-01-01 09:00:00", prioridade="X"),   # bad priority
    ])
    chamadas = []
    e = ingestao.processar([arq], rodar_pipeline=lambda: chamadas.append(1))
    r = e["lotes"][0]
    assert (r["estado"], r["novos"], r["atualizados"], r["rejeitados"]) == ("incorporado", 1, 1, 3)
    assert {x["motivo"] for x in r["exemplos_rejeitados"]} == {
        "sem número do incidente", "data de abertura vazia ou inválida", "prioridade fora do dicionário (1 a 5)"}
    df = dados.carregar_incidentes()
    assert len(df) == 3 and df.loc[df["numero"] == "INC2", "humano"].item()
    assert df.loc[df["numero"] == "INC3", "aberto"].item() == pd.Timestamp("2026-01-05 08:30")
    assert chamadas == [1] and e["pipeline"]["estado"] == "ok"
    assert (base / "entrada" / "processados" / "lote.csv").exists() and not arq.exists()


def test_arquivo_ilegivel_vai_para_rejeitados_sem_rodar_o_pipeline(base):
    arq = base / "entrada" / "lixo.csv"
    arq.write_text("a,b\n1,2\n", encoding="utf-8")
    chamadas = []
    e = ingestao.processar([arq], rodar_pipeline=lambda: chamadas.append(1))
    assert e["lotes"][0]["estado"] == "recusado" and "19 colunas" in e["lotes"][0]["erro"]
    assert chamadas == [] and (base / "entrada" / "rejeitados" / "lixo.csv").exists()


def test_falha_do_pipeline_fica_registrada(base):
    arq = _csv(base, "lote.csv", [_linha("INC9", "2026-01-02 08:00:00")], sep=",")
    def quebra():
        raise RuntimeError("prophet caiu")
    e = ingestao.processar([arq], rodar_pipeline=quebra)
    assert e["pipeline"]["estado"] == "falhou" and "prophet caiu" in e["pipeline"]["erro"]
    assert ingestao._estado()["pipeline"]["estado"] == "falhou"


def test_datas_com_precisao_diferente_no_mesmo_lote():
    # Audit 20/10: pandas inferred the format from the first row, so '2025-12-31 23:45' after
    # '2025-12-31 23:45:18' became NaT and a valid row was rejected as "data inválida".
    import pandas as pd
    from localops_ml import config, dados
    linhas = [["INC1", "3 - Média"] + [""] * 17, ["INC2", "3 - Média"] + [""] * 17]
    bruto = pd.DataFrame(linhas, columns=range(19)).astype(str)
    i_aberto = config.COLUNAS.index("aberto")
    bruto.iloc[0, i_aberto], bruto.iloc[1, i_aberto] = "2025-12-31 23:45:18", "2025-12-31 23:45"
    df = dados.tipar(bruto)
    assert df["aberto"].notna().all()
