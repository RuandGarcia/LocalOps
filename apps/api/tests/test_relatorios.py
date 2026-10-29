import io

from pypdf import PdfReader

from localops_api import documento as d
from localops_api import formatos, relatorio, render_html, render_pdf, render_xlsx

MD = """# Escala do sábado

> **Resumo.** Plantão reforçado em Team14.

| KPI | Valor | Detalhe |
|---|---|---|
| Exigem uma pessoa | 112 | faixa 70–154 |

## Equipes

| Equipe | Exigiram uma pessoa | Variação |
|---|---|---|
| Team14 | 404 | +11,3% |
| Team02 | 25 | −7,5% |

Fonte: tendencias
"""


def test_markdown_vira_documento():
    doc = d.de_markdown(MD, "e.pdf")
    assert doc.titulo == "Escala do sábado" and doc.resumo.startswith("**Resumo.**")
    assert [(k.rotulo, k.valor, k.detalhe) for k in doc.kpis] == [("Exigem uma pessoa", "112", "faixa 70–154")]
    assert doc.secoes[0].titulo == "Equipes" and isinstance(doc.secoes[0].blocos[0], d.Tabela)
    assert doc.fonte == "tendencias"


def test_csv_vira_documento_com_uma_tabela():
    doc = d.de_csv("Equipe;Exigiram\nTeam14;404\nFonte;tendencias\n", "Equipes")
    t = doc.secoes[0].blocos[0]
    assert (doc.titulo, doc.fonte, t.cabecalho, t.linhas) == ("Equipes", "tendencias", ["Equipe", "Exigiram"], [["Team14", "404"]])


def test_tom_da_variacao():
    assert d.tom_variacao("+11,3%") == "alerta" and d.tom_variacao("−7,5%") == "bom"
    assert d.tom_variacao("-7,5%") == "bom" and d.tom_variacao("—") == "neutro" and d.tom_variacao("Team14") == "neutro"


def test_relatorio_do_turno_nao_mostra_dia_depois_de_hoje():
    doc = relatorio.turno("2025-12-10")["doc"]
    serie = next(b for s in doc.secoes for b in s.blocos if isinstance(b, d.Serie))
    assert serie.rotulos[-1] == "10/12" and len(serie.valores) == 28
    assert [p[1] for p in serie.previsoes] == [1, 7]
    assert [s.titulo for s in doc.secoes] == ["Previsão", "Meta de OLA", "Onde agir", "Filtro de ruído"]
    assert len(doc.kpis) == 4 and doc.kpis[1].tom == "ruim"  # P2: projection 43 above the 100% ceiling of 39
    faixas = [b for b in doc.secoes[1].blocos if isinstance(b, d.Faixas)]
    assert [f.faixas[0][0] for f in faixas] == ["150%", "150%"] and abs(sum(p for _, p in faixas[0].faixas) - 1) < 0.01


def test_html_e_escuro_imprimivel_e_offline():
    h = render_html.documento(d.de_markdown(MD + "\n<script>x</script> ![a](https://x.y/z.png) [l](javascript:alert(1))"))
    assert "<script" not in h and "https://" not in h and "javascript:" not in h
    assert "prefers-color-scheme: light" in h and "@media print" in h
    assert 'class="kpi neutro"' in h and 'class="var alerta"' in h and 'class="var bom"' in h


def test_html_do_turno_tem_grafico_e_faixas():
    h = render_html.documento(relatorio.turno("2025-12-10")["doc"])
    assert h.count("<svg") == 3  # forecast chart + P2 and P3 band bars
    assert "91,6%" in h  # chance of the most likely P2 band, shown on the bar


def test_pdf_do_turno_tem_capa_kpis_e_cabe_em_3_paginas():
    r = PdfReader(io.BytesIO(render_pdf.documento(relatorio.turno("2025-12-10")["doc"])))
    texto = "".join(p.extract_text() for p in r.pages)
    assert len(r.pages) <= 3 and "Team14" in texto and "55,1%" in texto and "EXIGEM UMA PESSOA" in texto.upper()


def test_pdf_aguenta_caracteres_fora_do_latin1_e_tabela_longa():
    linhas = "\n".join(f"| item {i} 🚨 ≥ → produto-com-nome-bem-comprido-{i} | {i} |" for i in range(400))
    b = render_pdf.documento(d.de_markdown(f"# Longo\n\n| Item | N |\n|---|---|\n{linhas}\n"))
    r = PdfReader(io.BytesIO(b))
    assert len(r.pages) > 5 and "Item" in r.pages[3].extract_text()  # header repeated after a page break


def test_excel_do_turno_tem_abas_graficos_e_formatacao():
    wb = render_xlsx.livro(relatorio.turno("2025-12-10")["doc"])
    assert wb.sheetnames == ["Resumo", "Previsão", "Meta de OLA", "Onde agir", "Filtro de ruído", "Sobre"]
    assert len(wb["Previsão"]._charts) == 1 and len(wb["Meta de OLA"]._charts) == 2
    assert len(wb["Onde agir"].conditional_formatting) >= 2   # data bars on both rankings
    linha = next(r for r in wb["Onde agir"].iter_rows(values_only=True) if r[0] == "Team14")
    assert isinstance(linha[1], int) and isinstance(linha[2], float)  # numbers, not text


def test_excel_do_agente_continua_comecando_na_tabela():
    wb = render_xlsx.livro(d.de_csv("Equipe;Exigiram\nTeam14;404\n", "Equipes"))
    assert wb.sheetnames == ["LocalOps", "Sobre"] and wb["LocalOps"]["A1"].value == "Equipe"


def test_molde_do_agente_gera_os_tres_formatos():
    for nome in ("e.pdf", "e.html", "e.xlsx"):
        assert formatos.gerar(nome, MD if nome != "e.xlsx" else "Equipe;Exigiram\nTeam14;404\n")["nome"] == nome
    assert d.de_markdown(MD).kpis


def test_marcador_em_csv_vira_texto():
    txt = d.para_texto(relatorio.turno("2025-12-10")["doc"])
    assert txt.startswith("Relatório do turno") and "Team14;404;" in txt and "Fonte;" in txt


def test_achados_da_revisao_do_redesenho():
    # A pipe escaped inside a cell stays in the cell and the number after it is kept (all formats share the parser).
    md = "# T\n\n## Status\n\n| Status | N |\n|---|---|\n| status \\| erro | 3 |\n"
    h = render_html.documento(d.de_markdown(md))
    assert "status | erro" in h and '<td class="num">3</td>' in h
    # Only the variation column gets a chip, not another signed number.
    h = render_html.documento(d.de_markdown("# T\n\n| Equipe | Saldo | Variação |\n|---|---|---|\n| Team14 | -3 | +5,0% |\n"))
    assert '<span class="var bom">-3</span>' not in h and '<span class="var alerta">+5,0%</span>' in h
    # Bold marks never reach titles, KPI cells or sheet names.
    doc = d.de_markdown("# **Turno**\n\n| KPI | Valor | Detalhe |\n|---|---|---|\n| Gente | **112** | faixa `70–154` |\n\n## **Equipes**\n\n| A | B |\n|---|---|\n| x | 1 |\n")
    assert (doc.titulo, doc.secoes[0].titulo, doc.kpis[0].valor, doc.kpis[0].detalhe) == ("Turno", "Equipes", "112", "faixa 70–154")
    assert "Equipes" in render_xlsx.livro(doc).sheetnames
    # A long KPI detail and value stay inside a card that starts near the page foot.
    kpis = "\n".join(f"| K{i} | 12,5% → 9,8% | era 1.234 alarmes por dia na fila, agora 456 depois do filtro de ruido aplicado em dezembro |" for i in range(4))
    md = "# T\n\n" + "Linha de texto para empurrar o cartão.\n\n" * 1 + f"| KPI | Valor | Detalhe |\n|---|---|---|\n{kpis}\n"
    r = PdfReader(io.BytesIO(render_pdf.documento(d.de_markdown(md))))
    assert len(r.pages) == 1 and "..." in r.pages[0].extract_text()


def test_tabela_larga_nao_quebra_palavra_e_rodape_nao_invade_a_pagina():
    # The custom report the agent wrote in production on 23/10: 8 columns broke "Indicado/r" and "Prioridad/e",
    # and a long source ran over "página 1 de 2".
    md = ("# OLA e operação\n\n## Meta OLA\n\n"
          "| Indicador | Prioridade | Acumulado | Projeção | Faixa de 80% | Faixa mais provável | Probabilidade | Folga até 100% |\n"
          "|---|---|---|---|---|---|---|---|\n"
          "| Violações | P2 | 33 | 40 | 35–44 | 75% | 48,6% | 6 |\n"
          "| Volume | P3 | 16.998 | 21.631 | 21.337–21.925 | 125% | 98,3% | 5.526 |\n\n"
          "Fonte: projeção da meta: acumulado + ritmo dos últimos 90 dias; base real 2025, agregada por dia; "
          "SHAP do filtro de ruído (XGBoost), teste em dez/2025\n")
    texto = PdfReader(io.BytesIO(render_pdf.documento(d.de_markdown(md)))).pages[0].extract_text()
    for palavra in ("Indicador", "Prioridade", "Acumulado", "Probabilidade", "21.337-21.925"):
        assert palavra in texto, palavra
    assert "..." in texto and "página 1 de 1" in texto
