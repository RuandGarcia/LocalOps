"""The standard shift report, written from the tools rather than by the model: right numbers, pt-BR
formatting, tables for every figure and nothing from after the replay day. The agent asks for it with a
one-line file block (`@relatorio-turno`, see workspace/AGENTS.md); the offline fallback uses it too. It is built
as a Documento, so PDF, HTML and Excel draw the same cards, chart and bands."""
from __future__ import annotations

import re
from datetime import date

from localops_api import ferramentas as f
from localops_api.documento import Documento, Faixas, Kpi, Secao, Serie, Tabela, Texto, n as _n, pc as _pc

_SEMANA = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
_MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro",
          "novembro", "dezembro"]
FONTE = "ferramentas prever, meta_kpi, tendencias e fila_ruido do LocalOps, sobre a base real de 2025"


def _var(x: float | None) -> str:
    return "—" if x is None else ("+" if x > 0 else "−" if x < 0 else "") + _pc(abs(x))


def _dia(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d:%d/%m/%Y} ({_SEMANA[d.weekday()]})"


def turno(hoje: str) -> dict:
    """{"doc": the report as a Documento (drawn as PDF, HTML or Excel), "resumo": one sentence for the chat}."""
    h, t = f.prever("humano", hoje)["previsoes"], f.prever("total", hoje)["previsoes"]
    h1, t1 = h[0], t[0]
    metas = [k for k in f.meta_kpi(hoje)["kpis"] if k["kpi"] == "violacoes"]
    mes = hoje[:7]
    eq = f.tendencias("equipe", mes, top=5, dia=hoje)
    pr = f.tendencias("produto", mes, top=5, dia=hoje)
    fila = f.fila_ruido(hoje)
    r = fila["resumo_dez25"]
    dia_fila = fila.get("dia")
    p2 = next((k for k in metas if k["prioridade"] == "P2"), metas[0])
    nome_mes = _MESES[int(mes[5:]) - 1]
    topo_eq, topo_pr = eq["ranking"][0], pr["ranking"][0]
    d1 = date.fromisoformat(h1["dia_alvo"])

    a, b = h1["faixa_80"]
    hoje_d = date.fromisoformat(hoje)
    resumo_md = (f"**Resumo.** Amanhã ({d1:%d/%m}) devem chegar cerca de **{_n(h1['previsto'])} alarmes que exigem uma pessoa** "
                 f"(faixa de 80%: {_n(a)} a {_n(b)}), em {_n(t1['previsto'])} no total. As violações de OLA de P2 devem fechar "
                 f"o ano em {_n(p2['projecao_31_12'])} (teto para 100%: {_n(p2['teto_para_100pct'])}). Onde agir primeiro: "
                 f"**{topo_eq['valor']}** e o produto **{topo_pr['valor']}**.")
    kpis = [Kpi("Exigem uma pessoa amanhã", _n(h1["previsto"]), f"faixa {_n(a)}–{_n(b)} · {_n(t1['previsto'])} no total",
                "alerta" if h1["previsto"] > h1["contexto"]["media_28d"] * 1.15 else "neutro")]
    kpis += [Kpi(f"Violações {k['prioridade']} em 31/12", _n(k["projecao_31_12"]),
                 f"teto para 100%: {_n(k['teto_para_100pct'])}", "ruim" if k["folga_ate_teto_100pct"] < 0 else "bom") for k in metas]
    kpis.append(Kpi("Fila depois do filtro", f"{_n(r['fila_por_dia_depois'])}/dia",
                    f"era {_n(r['fila_por_dia_antes'])} · −{_pc(r['reducao_fila_pct'])}", "bom"))

    hist = f.historico("humano", hoje, 28)
    serie = Serie("Exigem uma pessoa: últimos 28 dias e previsão",
                  [f"{date.fromisoformat(x):%d/%m}" for x, _ in hist], [v for _, v in hist],
                  [(p["horizonte"], (date.fromisoformat(p["dia_alvo"]) - hoje_d).days, p["previsto"], *p["faixa_80"]) for p in h])
    previsao = Secao("Previsão", [serie, Tabela(
        ["Indicador", "Amanhã", "Faixa de 80%", "Em 7 dias", "Média 7 dias"],
        [[nome, _n(s[0]["previsto"]), f"{_n(s[0]['faixa_80'][0])}–{_n(s[0]['faixa_80'][1])}", _n(s[-1]["previsto"]),
          _n(s[0]["contexto"]["media_7d"])] for nome, s in (("Exigem uma pessoa", h), ("Total de alarmes", t))]),
        Texto(f"Mesmo dia da semana passada: {_n(h1['contexto']['mesmo_dia_semana_passada'])}; "
              f"média de 28 dias: {_n(h1['contexto']['media_28d'])}.")])

    meta = Secao("Meta de OLA", [Texto("Violações projetadas para 31/12 e a chance de cada faixa oficial da meta.")])
    for k in metas:
        meta.blocos.append(Faixas(f"{k['prioridade']} · {_n(k['ate_hoje'])} violações até hoje",
                                  [(p["faixa"], p["prob"]) for p in k["probabilidades"]],
                                  f"Projeção {_n(k['projecao_31_12'])} (80%: {_n(k['faixa_80'][0])}–{_n(k['faixa_80'][1])}) · "
                                  f"teto para 100%: {_n(k['teto_para_100pct'])}"))

    agir = Secao("Onde agir", [Texto(f"{nome_mes.capitalize()} até {hoje_d:%d/%m}, contra os mesmos dias de "
                                     f"{_MESES[int(eq['periodo_anterior'][0][5:7]) - 1]}.")])
    for titulo, rk, col in (("Equipes", eq, "Equipe"), ("Produtos", pr, "Produto")):
        agir.blocos.append(Tabela([col, "Exigiram uma pessoa", "Variação"],
                                  [[x["valor"], _n(x["humano"]), _var(x["variacao_pct"])] for x in rk["ranking"]], titulo))

    linhas_fila = []
    if dia_fila:
        linhas_fila += [["Alarmes no dia", _n(dia_fila["alarmes"])], ["Ficaram na fila", _n(dia_fila["fila_filtrada"])],
                        ["Exigiram uma pessoa", _n(dia_fila["exigiram_pessoa"])],
                        ["Exigiram uma pessoa e ficaram fora", _n(dia_fila["pessoa_fora_da_fila"])]]
    fator = r["o_que_mais_pesa"][0]
    linhas_fila += [["Fila por dia em dez/2025", f"{_n(r['fila_por_dia_antes'])} → {_n(r['fila_por_dia_depois'])}"],
                    ["Redução da fila", _pc(r["reducao_fila_pct"])],
                    ["Quem exigiu uma pessoa e ficou na fila", _pc(r["recall_obtido"] * 100)],
                    ["O que mais pesa na decisão", f"{re.sub(r' *[(].*[)]', '', fator['fator']).capitalize()} ({_pc(fator['peso_pct'])})"]]
    filtro = Secao("Filtro de ruído", [Tabela(["Indicador", "Valor"], linhas_fila)])

    doc = Documento(f"Relatório do turno · {_dia(hoje)}", "", resumo_md, kpis, [previsao, meta, agir, filtro], FONTE)
    resumo = (f"Relatório de {hoje_d:%d/%m/%Y} pronto: amanhã devem chegar cerca de {_n(h1['previsto'])} "
              f"alarmes que exigem uma pessoa, e quem mais concentra o trabalho no mês é {topo_eq['valor']}.")
    return {"doc": doc, "resumo": resumo}
