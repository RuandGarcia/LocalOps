"""A Documento as an A4 PDF: dark cover band, KPI cards, forecast chart, band bars and clean tables."""
from __future__ import annotations

import re

from fpdf import FPDF, FontFace
from fpdf.enums import TableBordersLayout, TableCellFillMode
from fpdf.pattern import LinearGradient

from localops_api.documento import NUM, Documento, Faixas, Lista, Serie, Tabela, Texto, gerado_em, n, tom_variacao

# Paper colours: the darker variants of the panel tokens (apps/web/src/index.css), readable when printed.
TINTA, SUAVE, LINHA = (31, 35, 64), (95, 100, 117), (226, 228, 236)
SUP, ZEBRA = (244, 245, 251), (249, 250, 252)
ACENTO, ACENTO2, AREA = (79, 70, 229), (14, 116, 144), (224, 227, 252)
TOM = {"neutro": ACENTO, "bom": (4, 120, 87), "alerta": (180, 83, 9), "ruim": (225, 29, 72)}
CAPA_A, CAPA_B, CAPA_TXT = (16, 17, 20), (49, 46, 129), (200, 204, 214)
CAPA_H = 44.0

# The PDF core fonts are Latin-1: map the usual typographic characters, replace the rest.
_LATIN1 = str.maketrans({"–": "-", "—": "-", "−": "-", "…": "...", "“": '"', "”": '"', "‘": "'", "’": "'",
                         "•": "-", "→": "->", "≈": "~", "≥": ">=", "≤": "<=", "×": "x", " ": " "})


def _latin1(s: str) -> str:
    return s.translate(_LATIN1).encode("latin-1", "replace").decode("latin-1")


def _inline(s: str) -> str:
    """Markdown inline for fpdf2's markdown=True: keeps **bold**, drops `code` ticks, links and single * or _."""
    s = re.sub(r"`([^`]*)`", r"\1", s)
    s = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", s)
    s = re.sub(r"(?<!\*)\*(?!\*)([^*]+)(?<!\*)\*(?!\*)", r"\1", s)
    return _latin1(s.replace("__", ""))


def _clareia(cor: tuple, a: float) -> tuple:
    """`cor` at opacity `a` over white paper."""
    return tuple(round(255 - (255 - c) * a) for c in cor)


class _Pdf(FPDF):
    fonte = ""

    def header(self):
        if self.page_no() == 1:  # the first page carries the cover band instead
            return
        self.set_fill_color(*ACENTO)
        self.rect(0, 0, self.w, 1.6, "F")
        self.set_xy(self.l_margin, 7)
        self.set_font("helvetica", "B", 7.5)
        self.set_text_color(*ACENTO)
        self.cell(40, 4, "LOCALOPS")
        self.set_font("helvetica", "", 7.5)
        self.set_text_color(*SUAVE)
        self.cell(0, 4, _latin1("RELATÓRIO DE OPERAÇÃO"), align="R")
        self.set_y(16)

    def footer(self):
        self.set_draw_color(*LINHA)
        self.set_line_width(0.2)
        self.line(self.l_margin, self.h - 14, self.w - self.r_margin, self.h - 14)
        self.set_y(-12)
        self.set_font("helvetica", "", 7.5)
        self.set_text_color(*SUAVE)
        largura = self.w - self.l_margin - self.r_margin - 30
        texto = _latin1(f"Fonte: {self.fonte}") if self.fonte else "LocalOps · Challenge Locaweb x FIAP"
        while self.get_string_width(texto) > largura - 2 and len(texto) > 10:  # never runs into the page number
            texto = texto[:-4].rstrip() + "..."
        self.cell(largura, 5, texto)
        self.cell(30, 5, f"página {self.page_no()} de {{nb}}", align="R")


def _capa(pdf: _Pdf, doc: Documento, largura: float) -> None:
    with pdf.use_pattern(LinearGradient(0, 0, pdf.w, CAPA_H, [CAPA_A, CAPA_B])):
        pdf.rect(0, 0, pdf.w, CAPA_H, style="F")
    pdf.set_xy(pdf.l_margin, 11)
    pdf.set_font("helvetica", "B", 7.5)
    pdf.set_text_color(165, 180, 252)
    pdf.cell(largura, 4, _latin1("LOCALOPS  ·  RELATÓRIO DE OPERAÇÃO"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    pdf.set_font("helvetica", "B", 19)
    pdf.set_text_color(255, 255, 255)
    pdf.multi_cell(largura, 8.5, _latin1(doc.titulo), new_x="LMARGIN", new_y="NEXT", max_line_height=8.5)
    pdf.set_font("helvetica", "", 8.5)
    pdf.set_text_color(*CAPA_TXT)
    sub = doc.subtitulo or f"Gerado em {gerado_em()} pelo agente LocalOps · base real de 2025, em replay"
    pdf.cell(largura, 5, _latin1(sub), new_x="LMARGIN", new_y="NEXT")
    pdf.set_y(max(pdf.get_y(), CAPA_H) + 7)


def _resumo(pdf: _Pdf, texto: str, largura: float) -> None:
    pdf.set_font("helvetica", "", 10)
    pdf.set_text_color(*TINTA)
    pdf.set_fill_color(*SUP)
    y0 = pdf.get_y()
    pdf.set_x(pdf.l_margin + 1.4)
    pdf.multi_cell(largura - 1.4, 5.4, _inline(texto), markdown=True, fill=True, padding=(3.4, 4.5, 3.4, 4.5),
                   new_x="LMARGIN", new_y="NEXT")
    pdf.set_fill_color(*ACENTO)
    pdf.rect(pdf.l_margin, y0, 1.4, pdf.get_y() - y0, "F")
    pdf.ln(4)


def _kpis(pdf: _Pdf, kpis: list, largura: float) -> None:
    gap, alto = 3.5, 25.0
    for i in range(0, len(kpis), 4):
        fila = kpis[i:i + 4]
        w = (largura - gap * (len(fila) - 1)) / len(fila)
        if pdf.get_y() + alto > pdf.h - 22:
            pdf.add_page()
        y = pdf.get_y()
        for j, k in enumerate(fila):
            x = pdf.l_margin + j * (w + gap)
            pdf.set_fill_color(*SUP)
            pdf.rect(x, y, w, alto, style="F", round_corners=True, corner_radius=2.2)
            pdf.set_fill_color(*TOM.get(k.tom, ACENTO))
            pdf.rect(x, y + 4, 1.1, alto - 8, style="F")
            pdf.set_xy(x + 4, y + 3.2)
            pdf.set_font("helvetica", "B", 6.5)
            pdf.set_text_color(*SUAVE)
            pdf.cell(w - 6, 3.5, _latin1(k.rotulo.upper())[:40])
            valor, corpo = _latin1(k.valor), 17
            pdf.set_font("helvetica", "B", corpo)
            while pdf.get_string_width(valor) > w - 7 and corpo > 9:  # a long value shrinks, never spills
                corpo -= 1
                pdf.set_font("helvetica", "B", corpo)
            pdf.set_xy(x + 4, y + 8)
            pdf.set_text_color(*(TOM["ruim"] if k.tom == "ruim" else TINTA))
            pdf.cell(w - 6, 8, valor)
            pdf.set_font("helvetica", "", 7)
            pdf.set_text_color(*SUAVE)
            linhas = pdf.multi_cell(w - 6, 3.4, _latin1(k.detalhe), dry_run=True, output="LINES")
            if len(linhas) > 2:  # the detail stays inside the card: two lines at most
                linhas = [linhas[0], linhas[1].rstrip()[:-3].rstrip() + "..."]
            for m, texto in enumerate(linhas):
                pdf.set_xy(x + 4, y + 17.2 + m * 3.4)
                pdf.cell(w - 6, 3.4, texto)
        pdf.set_y(y + alto + gap)
    pdf.ln(2)


def _titulo_secao(pdf: _Pdf, titulo: str, nivel: int, largura: float, depois: float) -> None:
    if pdf.get_y() + 14 + depois > pdf.h - 22:  # a heading travels with what follows it
        pdf.add_page()
    pdf.ln(3)
    if nivel <= 2:
        y = pdf.get_y()
        pdf.set_fill_color(*ACENTO)
        pdf.rect(pdf.l_margin, y + 1.6, 2.2, 2.2, style="F", round_corners=True, corner_radius=0.5)
        pdf.set_x(pdf.l_margin + 4.5)
        pdf.set_font("helvetica", "B", 12.5)
        pdf.set_text_color(*TINTA)
        pdf.multi_cell(largura - 4.5, 5.6, _inline(titulo), markdown=True, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2.5)
    else:
        _rotulo(pdf, titulo, largura)


def _rotulo(pdf: _Pdf, texto: str, largura: float) -> None:
    pdf.set_font("helvetica", "B", 7.5)
    pdf.set_text_color(*SUAVE)
    pdf.cell(largura, 5, _latin1(texto.upper()), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(0.5)


def _serie(pdf: _Pdf, s: Serie, largura: float) -> None:
    if pdf.get_y() + 72 > pdf.h - 22:
        pdf.add_page()
    _rotulo(pdf, s.titulo, largura)
    x0, y0, h = pdf.l_margin, pdf.get_y() + 6, 46.0
    ult = len(s.valores) - 1
    dias = ult + max((p[1] for p in s.previsoes), default=0)
    topo = max(s.valores + [p[4] for p in s.previsoes]) * 1.08 or 1
    X = lambda i: x0 + 2 + i * (largura - 28) / max(dias, 1)
    Y = lambda v: y0 + h - v / topo * h
    pts = [(X(i), Y(v)) for i, v in enumerate(s.valores)]
    pdf.set_fill_color(*SUP)
    pdf.rect(x0 - 2, y0 - 6, largura + 4, h + 14, style="F", round_corners=True, corner_radius=2.2)
    pdf.set_fill_color(*AREA)
    pdf.polygon([(X(0), y0 + h)] + pts + [(X(ult), y0 + h)], style="F")
    pdf.set_draw_color(*ACENTO)
    pdf.set_line_width(0.55)
    pdf.polyline(pts)
    pdf.set_draw_color(*SUAVE)
    pdf.set_line_width(0.15)
    pdf.set_dash_pattern(dash=0.8, gap=1.2)
    pdf.line(X(ult), y0 - 2, X(ult), y0 + h)
    pdf.set_dash_pattern()
    pdf.set_font("helvetica", "", 6.5)
    pdf.set_text_color(*SUAVE)
    pdf.text(X(ult) - 2.5, y0 - 3, "hoje")
    for k in (0, ult // 2, ult):
        pdf.text(X(k) - (0 if k == 0 else 3), y0 + h + 4.5, s.rotulos[k])
    for rot, a_frente, v, lo, hi in s.previsoes:
        i = ult + a_frente
        pdf.set_draw_color(*_clareia(ACENTO2, 0.45))
        pdf.set_line_width(1.6)
        pdf.line(X(i), Y(lo), X(i), Y(hi))
        pdf.set_fill_color(*ACENTO2)
        pdf.rect(X(i) - 1.3, Y(v) - 1.3, 2.6, 2.6, style="F", round_corners=True, corner_radius=1.3)
        pdf.set_font("helvetica", "B", 7)
        pdf.set_text_color(*TINTA)
        pdf.text(X(i) + 2.6, Y(v) + 1.1, _latin1(f"{rot} · {n(v)}"))
    pdf.set_line_width(0.2)
    pdf.set_y(y0 + h + 12)


def _faixas(pdf: _Pdf, f: Faixas, largura: float) -> None:
    if pdf.get_y() + 26 > pdf.h - 22:
        pdf.add_page()
    _rotulo(pdf, f.titulo, largura)
    gap = 1.5
    w = (largura - gap * (len(f.faixas) - 1)) / max(len(f.faixas), 1)
    topo = max((p for _, p in f.faixas), default=0) or 1
    y = pdf.get_y() + 0.5
    for k, (nome, p) in enumerate(f.faixas):
        x = pdf.l_margin + k * (w + gap)
        pdf.set_fill_color(*_clareia(ACENTO, 0.12 + 0.88 * p / topo))
        pdf.rect(x, y, w, 7, style="F", round_corners=True, corner_radius=1.6)
        pdf.set_xy(x, y + 8)
        pdf.set_font("helvetica", "B" if p == topo else "", 7)
        pdf.set_text_color(*(TINTA if p == topo else SUAVE))
        pdf.cell(w, 4, _latin1(f"{nome} · {f'{p * 100:.1f}'.replace('.', ',')}%"), align="C")
    pdf.set_xy(pdf.l_margin, y + 13)
    pdf.set_font("helvetica", "", 7.5)
    pdf.set_text_color(*SUAVE)
    pdf.cell(largura, 4, _latin1(f.legenda), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)


def _larguras(pdf: _Pdf, cab: list, linhas: list, largura: float, corpo: float, corpo_cab: float) -> list:
    """Column widths in mm: every column fits its longest word (header or cell), so no word breaks in the
    middle; the room left goes to the columns whose text would otherwise wrap the most."""
    folga_cel = 2 * 2.6 + 1
    palavra = lambda s: max((pdf.get_string_width(_latin1(p)) for p in (s.split() or [""])), default=0)
    pdf.set_font("helvetica", "B", corpo_cab)
    minimo = [palavra(c) + folga_cel for c in cab]
    pdf.set_font("helvetica", "", corpo)
    for j in range(len(cab)):
        minimo[j] = min(45, max([minimo[j]] + [palavra(r[j]) + folga_cel for r in linhas]))
    natural = [max(minimo[j], min(70, max([pdf.get_string_width(_latin1(r[j])) + folga_cel for r in linhas] or [0])))
               for j in range(len(cab))]
    extra = largura - sum(minimo)
    if extra <= 0:
        return minimo
    folga = [natural[j] - minimo[j] for j in range(len(cab))]
    total = sum(folga)
    return [minimo[j] + (extra * folga[j] / total if total else extra / len(cab)) for j in range(len(cab))]


def _tabela(pdf: _Pdf, t: Tabela, largura: float) -> None:
    if not t.cabecalho:
        return
    n_cols = max([len(t.cabecalho)] + [len(r) for r in t.linhas])
    cab = t.cabecalho + [""] * (n_cols - len(t.cabecalho))
    linhas = [r + [""] * (n_cols - len(r)) for r in t.linhas]
    numerica = [bool(linhas) and all(NUM.match(r[j]) or not r[j] for r in linhas) for j in range(n_cols)]
    var = [bool(re.search(r"varia|tend[eê]n", c, re.I)) for c in cab]
    corpo, corpo_cab = (9.5, 8.5) if n_cols <= 4 else (8.5, 7.5) if n_cols <= 6 else (7.5, 7)  # wide tables get smaller type
    pesos = _larguras(pdf, cab, linhas, largura, corpo, corpo_cab)
    altura = (len(linhas) + 1) * 7.6 + (6 if t.titulo else 0)
    if pdf.get_y() + altura > pdf.h - 22 and altura < pdf.h / 2:  # a short table is not split across pages
        pdf.add_page()
    if t.titulo:
        _rotulo(pdf, t.titulo, largura)
    pdf.set_font("helvetica", "", corpo)
    pdf.set_text_color(*TINTA)
    pdf.set_draw_color(*LINHA)
    pdf.set_fill_color(*ZEBRA)  # an accent fill from a card or chart must not leak into the rows
    with pdf.table(width=largura, col_widths=pesos, line_height=6.2, padding=(1.5, 2.6),
                   text_align=["RIGHT" if numerica[j] else "LEFT" for j in range(n_cols)],
                   headings_style=FontFace(emphasis="BOLD", color=(255, 255, 255), fill_color=TINTA, size_pt=corpo_cab),
                   cell_fill_color=ZEBRA, cell_fill_mode=TableCellFillMode.EVEN_ROWS, repeat_headings=1,
                   borders_layout=TableBordersLayout.HORIZONTAL_LINES, markdown=True) as tb:
        linha = tb.row()
        for c in cab:
            linha.cell(_inline(c))
        for r in linhas:
            linha = tb.row()
            for j, c in enumerate(r):
                tom = tom_variacao(c) if var[j] else "neutro"
                estilo = FontFace(emphasis="BOLD", color=TOM[tom]) if tom != "neutro" else None
                linha.cell(_inline(c), style=estilo)
    pdf.ln(4)


def _bloco(pdf: _Pdf, b, largura: float) -> None:
    pdf.set_text_color(*TINTA)
    if isinstance(b, Tabela):
        _tabela(pdf, b, largura)
    elif isinstance(b, Serie):
        _serie(pdf, b, largura)
    elif isinstance(b, Faixas):
        _faixas(pdf, b, largura)
    elif isinstance(b, Lista):
        pdf.set_font("helvetica", "", 10)
        for k, item in enumerate(b.itens, 1):
            y = pdf.get_y()
            if b.ordenada:
                pdf.set_text_color(*ACENTO)
                pdf.cell(6, 5.2, f"{k}.")
                pdf.set_text_color(*TINTA)
            else:
                pdf.set_fill_color(*ACENTO)
                pdf.rect(pdf.l_margin + 1, y + 2.1, 1.3, 1.3, "F")
                pdf.set_x(pdf.l_margin + 6)
            pdf.multi_cell(largura - 6, 5.2, _inline(item), markdown=True, new_x="LMARGIN", new_y="NEXT")
            pdf.ln(0.6)
        pdf.ln(1.5)
    elif isinstance(b, Texto) and b.nota:
        _resumo(pdf, b.texto, largura)
    elif isinstance(b, Texto):
        pdf.set_font("helvetica", "", 9.5)
        pdf.set_text_color(*SUAVE)
        pdf.multi_cell(largura, 5, _inline(b.texto), markdown=True, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)


def _altura_inicial(b) -> float:
    if isinstance(b, Tabela):
        a = (len(b.linhas) + 1) * 7.6 + 6
        return a if a < 140 else 30
    return {Serie: 72, Faixas: 26}.get(type(b), 20)


def documento(doc: Documento) -> bytes:
    pdf = _Pdf(format="A4")
    pdf.fonte = doc.fonte
    pdf.alias_nb_pages()
    pdf.set_title(_latin1(doc.titulo))
    pdf.set_author("Agente LocalOps")
    pdf.set_margins(18, 16, 18)
    pdf.set_auto_page_break(True, margin=20)
    pdf.add_page()
    largura = pdf.w - pdf.l_margin - pdf.r_margin
    _capa(pdf, doc, largura)
    if doc.resumo:
        _resumo(pdf, doc.resumo, largura)
    if doc.kpis:
        _kpis(pdf, doc.kpis, largura)
    for s in doc.secoes:
        if s.titulo:
            depois = sum(_altura_inicial(b) for b in s.blocos[:2])
            _titulo_secao(pdf, s.titulo, s.nivel, largura, min(depois, 90))
        for b in s.blocos:
            _bloco(pdf, b, largura)
    return bytes(pdf.output())
