"""A Documento as an Excel workbook: a summary sheet with KPI blocks, one sheet per section with real
numbers, native charts and conditional formats, and an "Sobre" sheet with the source."""
from __future__ import annotations

import io
import re

from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.formatting.rule import CellIsRule, DataBarRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from localops_api.documento import Documento, Faixas, Lista, Serie, Tabela, Texto, gerado_em, numero

TINTA, SUAVE, ACENTO, CAPA = "1F2340", "5F6475", "4F46E5", "101114"
TOM = {"neutro": ACENTO, "bom": "047857", "alerta": "B45309", "ruim": "E11D48"}
_FUNDO_CAB = PatternFill("solid", fgColor=TINTA)
_ZEBRA = PatternFill("solid", fgColor="F9FAFC")
_SUP = PatternFill("solid", fgColor="F4F5FB")
_BORDA = Border(bottom=Side(style="thin", color="E2E4EC"))
_LARGURA_TEXTO = 8  # columns a paragraph spans


def _sem_md(s: str) -> str:
    return re.sub(r"\*\*|`", "", s)


def _nome_aba(titulo: str, usados: set) -> str:
    nome = re.sub(r"[\[\]:*?/\\]", "-", titulo).strip(" '")[:31] or "LocalOps"
    base, k = nome, 2
    while nome in usados:
        nome = f"{base[:28]} {k}"
        k += 1
    usados.add(nome)
    return nome


class _Aba:
    """Writes blocks top to bottom on one sheet and remembers the column widths."""

    def __init__(self, ws):
        self.ws, self.r, self.larguras, self.primeira = ws, 1, {}, True

    def _larg(self, j: int, v) -> None:
        self.larguras[j] = max(self.larguras.get(j, 0), len(str(v)) if v is not None else 0)

    def rotulo(self, texto: str) -> None:
        c = self.ws.cell(row=self.r, column=1, value=texto)
        c.font = Font(bold=True, color=TINTA, size=11)
        self.r += 1

    def texto(self, texto: str, cor: str = SUAVE, colunas: int = _LARGURA_TEXTO) -> None:
        self.ws.merge_cells(start_row=self.r, start_column=1, end_row=self.r, end_column=colunas)
        c = self.ws.cell(row=self.r, column=1, value=_sem_md(texto))
        c.font, c.alignment = Font(color=cor), Alignment(wrap_text=True, vertical="top")
        self.ws.row_dimensions[self.r].height = 15 * (1 + len(texto) // 110)
        self.r += 2

    def tabela(self, t: Tabela) -> None:
        if not t.cabecalho:
            return
        if t.titulo:
            self.rotulo(t.titulo)
        ini = self.r
        for j, v in enumerate(t.cabecalho, 1):
            c = self.ws.cell(row=ini, column=j, value=v)
            c.font, c.fill = Font(bold=True, color="FFFFFF"), _FUNDO_CAB
            c.alignment = Alignment(vertical="center")
            self._larg(j, v)
        self.ws.row_dimensions[ini].height = 22
        numericas: dict[int, bool] = {}
        variacao = {j for j, c in enumerate(t.cabecalho, 1) if re.search(r"varia|tend[eê]n", c, re.I)}
        for i, linha in enumerate(t.linhas, 1):
            for j, v in enumerate(linha, 1):
                valor, fmt = numero(v)
                if fmt == "0.0%" and j in variacao:
                    fmt = "+0.0%;-0.0%;0.0%"  # the sign is the point of a variation
                c = self.ws.cell(row=ini + i, column=j, value=valor)
                c.border = _BORDA
                if fmt:
                    c.number_format, c.alignment = fmt, Alignment(horizontal="right")
                if i % 2 == 0:
                    c.fill = _ZEBRA
                numericas[j] = numericas.get(j, True) and (fmt is not None or not v.strip())
                self._larg(j, v)
        fim = ini + len(t.linhas)
        if len(t.linhas) >= 2:
            for j, num in numericas.items():
                if not num or (j not in variacao and len(t.linhas) < 3):  # bars need a ranking to compare
                    continue
                col = get_column_letter(j)
                faixa = f"{col}{ini + 1}:{col}{fim}"
                if j in variacao:
                    self.ws.conditional_formatting.add(faixa, CellIsRule(operator="greaterThan", formula=["0"],
                                                                         font=Font(bold=True, color=TOM["alerta"])))
                    self.ws.conditional_formatting.add(faixa, CellIsRule(operator="lessThan", formula=["0"],
                                                                         font=Font(bold=True, color=TOM["bom"])))
                else:
                    self.ws.conditional_formatting.add(faixa, DataBarRule(start_type="num", start_value=0, end_type="max",
                                                                          color="818CF8"))
        if self.primeira and ini == 1:  # a data sheet that starts at the table: freeze and filter it
            self.ws.freeze_panes = "A2"
            if t.linhas:
                self.ws.auto_filter.ref = f"A1:{get_column_letter(len(t.cabecalho))}{fim}"
        self.primeira = False
        self.r = fim + 2

    def serie(self, s: Serie) -> None:
        self.rotulo(s.titulo)
        cab = ["Dia", "Exigiram uma pessoa", "Previsão", "Faixa mín.", "Faixa máx."]
        ini = self.r
        for j, v in enumerate(cab, 1):
            c = self.ws.cell(row=ini, column=j, value=v)
            c.font, c.fill = Font(bold=True, color="FFFFFF"), _FUNDO_CAB
            self._larg(j, v)
        linhas = [[r, v, None, None, None] for r, v in zip(s.rotulos, s.valores)]
        linhas += [[f"{rot} (+{d} d)", None, round(v, 1), round(lo, 1), round(hi, 1)] for rot, d, v, lo, hi in s.previsoes]
        for i, linha in enumerate(linhas, 1):
            for j, v in enumerate(linha, 1):
                c = self.ws.cell(row=ini + i, column=j, value=v)
                c.border = _BORDA
                if j > 1:
                    c.number_format = "#,##0"
        fim = ini + len(linhas)
        g = LineChart()
        g.title, g.height, g.width = s.titulo, 7.5, 18
        g.y_axis.title, g.legend.position = "alarmes", "b"
        g.add_data(Reference(self.ws, min_col=2, max_col=3, min_row=ini, max_row=fim), titles_from_data=True)
        g.set_categories(Reference(self.ws, min_col=1, min_row=ini + 1, max_row=fim))
        g.series[0].graphicalProperties.line.solidFill = ACENTO
        g.series[1].graphicalProperties.line.solidFill = "0E7490"
        g.series[1].marker.symbol = "circle"
        for serie in g.series:
            serie.smooth = False
        self.ws.add_chart(g, f"G{ini}")
        self.r = max(fim, ini + 16) + 2

    def faixas(self, f: Faixas) -> None:
        self.rotulo(f.titulo)
        ini = self.r
        for j, v in enumerate(["Faixa da meta", "Chance"], 1):
            c = self.ws.cell(row=ini, column=j, value=v)
            c.font, c.fill = Font(bold=True, color="FFFFFF"), _FUNDO_CAB
            self._larg(j, v)
        topo = max((p for _, p in f.faixas), default=0)
        for i, (nome, p) in enumerate(f.faixas, 1):
            a = self.ws.cell(row=ini + i, column=1, value=nome)
            b = self.ws.cell(row=ini + i, column=2, value=p)
            b.number_format, a.border, b.border = "0.0%", _BORDA, _BORDA
            if p == topo:
                a.font = b.font = Font(bold=True, color=ACENTO)
        fim = ini + len(f.faixas)
        g = BarChart()
        g.type, g.title, g.height, g.width, g.legend = "col", f.titulo, 6, 14, None
        g.y_axis.number_format, g.y_axis.scaling.max = "0%", 1
        g.add_data(Reference(self.ws, min_col=2, min_row=ini, max_row=fim), titles_from_data=True)
        g.set_categories(Reference(self.ws, min_col=1, min_row=ini + 1, max_row=fim))
        g.series[0].graphicalProperties.solidFill = ACENTO
        g.series[0].graphicalProperties.line.solidFill = ACENTO
        self.ws.add_chart(g, f"E{ini}")
        self.r = fim + 1
        self.texto(f.legenda, colunas=3)  # beside the chart, never under it
        self.r = max(self.r, ini + 13)

    def bloco(self, b) -> None:
        if isinstance(b, Tabela):
            self.tabela(b)
        elif isinstance(b, Serie):
            self.serie(b)
        elif isinstance(b, Faixas):
            self.faixas(b)
        elif isinstance(b, Lista):
            for k, item in enumerate(b.itens, 1):
                self.ws.cell(row=self.r, column=1, value=f"{k}. " if b.ordenada else "• ").font = Font(color=ACENTO, bold=True)
                self.ws.cell(row=self.r, column=2, value=_sem_md(item))
                self.r += 1
            self.r += 1
        elif isinstance(b, Texto):
            self.texto(b.texto, TINTA if b.nota else SUAVE)

    def fechar(self) -> None:
        _impressao(self.ws)
        for j, w in self.larguras.items():
            self.ws.column_dimensions[get_column_letter(j)].width = min(60, max(12, w + 3))


def _impressao(ws) -> None:
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True


def _resumo(ws, doc: Documento) -> None:
    _impressao(ws)
    for j in range(1, _LARGURA_TEXTO + 1):
        ws.column_dimensions[get_column_letter(j)].width = 17
    ws.merge_cells("A1:H1")
    ws["A1"] = doc.titulo
    ws["A1"].font = Font(bold=True, size=18, color="FFFFFF")
    ws["A1"].alignment = Alignment(vertical="center", indent=1)
    ws.merge_cells("A2:H2")
    ws["A2"] = doc.subtitulo or f"Gerado em {gerado_em()} pelo agente LocalOps · base real de 2025, em replay"
    ws["A2"].font = Font(color="C8CCD6", size=9)
    ws["A2"].alignment = Alignment(indent=1, vertical="top")
    for r in (1, 2):
        for j in range(1, _LARGURA_TEXTO + 1):
            ws.cell(row=r, column=j).fill = PatternFill("solid", fgColor=CAPA)
    ws.row_dimensions[1].height, ws.row_dimensions[2].height = 38, 20
    r = 4
    for i, k in enumerate(doc.kpis):
        linha, col = r + (i // 4) * 4, 1 + (i % 4) * 2
        cor = TOM.get(k.tom, ACENTO)
        for dr, (valor, fonte) in enumerate([(k.rotulo.upper(), Font(bold=True, size=8, color=SUAVE)),
                                             (k.valor, Font(bold=True, size=20, color=TOM["ruim"] if k.tom == "ruim" else TINTA)),
                                             (k.detalhe, Font(size=9, color=SUAVE))]):
            ws.merge_cells(start_row=linha + dr, start_column=col, end_row=linha + dr, end_column=col + 1)
            c = ws.cell(row=linha + dr, column=col, value=valor)
            c.font, c.alignment = fonte, Alignment(indent=1, vertical="center")
            for j in (col, col + 1):
                ws.cell(row=linha + dr, column=j).fill = _SUP
            ws.cell(row=linha + dr, column=col).border = Border(left=Side(style="thick", color=cor))
            ws.row_dimensions[linha + dr].height = 30 if dr == 1 else 16
    r += ((len(doc.kpis) + 3) // 4) * 4 + (0 if doc.kpis else 0)
    if doc.resumo:
        ws.merge_cells(start_row=r, start_column=1, end_row=r + 2, end_column=_LARGURA_TEXTO)
        c = ws.cell(row=r, column=1, value=_sem_md(doc.resumo))
        c.font, c.alignment = Font(size=11, color=TINTA), Alignment(wrap_text=True, vertical="top", indent=1)
        c.border = Border(left=Side(style="thick", color=ACENTO))
    ws.sheet_view.showGridLines = False


def livro(doc: Documento) -> Workbook:
    wb = Workbook()
    wb.remove(wb.active)
    usados: set = set()
    if doc.kpis or doc.resumo:
        _resumo(wb.create_sheet(_nome_aba("Resumo", usados)), doc)
    for s in doc.secoes:
        aba = _Aba(wb.create_sheet(_nome_aba(s.titulo, usados)))
        for b in s.blocos:
            aba.bloco(b)
        aba.fechar()
    sobre = wb.create_sheet(_nome_aba("Sobre", usados))
    sobre["A1"] = doc.titulo
    sobre["A1"].font = Font(bold=True, size=14, color=TINTA)
    sobre["A2"] = f"Gerado em {gerado_em()} pelo agente LocalOps · base real de 2025, em replay"
    sobre["A2"].font = Font(color=SUAVE)
    if doc.fonte:
        sobre["A4"], sobre["B4"] = "Fonte", doc.fonte
        sobre["A4"].font = Font(bold=True)
    sobre.column_dimensions["A"].width = 14
    sobre.column_dimensions["B"].width = 90
    return wb


def documento(doc: Documento) -> bytes:
    buf = io.BytesIO()
    livro(doc).save(buf)
    return buf.getvalue()
