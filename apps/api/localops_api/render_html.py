"""A Documento as one self-contained HTML page: dark like the panel, light on paper, no external resource."""
from __future__ import annotations

import re
from html import escape

import markdown

from localops_api.documento import NUM, SEM_IMAGEM, Documento, Faixas, Lista, Serie, Tabela, gerado_em, n, tom_variacao


def md_html(md: str) -> str:
    # Raw HTML switched off: the agent's text never becomes markup or script, only Markdown
    # (escaping `<` by hand double-escaped it inside code spans).
    conv = markdown.Markdown(extensions=["tables", "sane_lists"])
    conv.preprocessors.deregister("html_block")
    conv.inlinePatterns.deregister("html")
    html = re.sub(r'href="(?!https?://)[^"]*"', 'href="#"', conv.convert(SEM_IMAGEM.sub(r"\1", md)))
    # Numbers line up on the right, like in a spreadsheet, and so does the header of a numeric column.
    return re.sub(r"<table>.*?</table>", _alinha_tabela, html, flags=re.S)


def _alinha_tabela(m: re.Match) -> str:
    tabela = m.group(0)
    linhas = re.findall(r"<tr>(.*?)</tr>", tabela, re.S)
    corpo = [re.findall(r"<td[^>]*>(.*?)</td>", l, re.S) for l in linhas if "<td" in l]
    n_cols = max((len(r) for r in corpo), default=0)
    num = [bool(corpo) and all(j >= len(r) or not r[j].strip() or NUM.match(r[j].strip()) for r in corpo) for j in range(n_cols)]

    def celula(tag: str):
        def troca(mc: re.Match) -> str:
            troca.j += 1
            return f'<{tag} class="num">' if troca.j < n_cols and num[troca.j] else mc.group(0)
        troca.j = -1
        return troca

    def linha(ml: re.Match) -> str:
        l = ml.group(0)
        tag = "th" if "<th" in l else "td"
        return re.sub(rf"<{tag}(?: [^>]*)?>", celula(tag), l)
    return re.sub(r"<tr>.*?</tr>", linha, tabela, flags=re.S)


# Dark is the panel's own palette (apps/web/src/index.css); light is its paper version, also used to print.
_ESCURO = ("--fundo:#08090b;--folha:#101114;--sup:#16171b;--borda:#25272d;--texto:#edeef0;--muted:#8b909a;"
           "--acento:#818cf8;--acento2:#22d3ee;--alerta:#fbbf24;--ruim:#fb7185;--bom:#34d399;color-scheme:dark")
_CLARO = ("--fundo:#f4f5f8;--folha:#ffffff;--sup:#f4f5fb;--borda:#e2e4ec;--texto:#1f2340;--muted:#5f6475;"
          "--acento:#4f46e5;--acento2:#0e7490;--alerta:#b45309;--ruim:#e11d48;--bom:#047857;color-scheme:light")
_CSS = f""":root{{{_ESCURO}}}
@media (prefers-color-scheme: light){{:root{{{_CLARO}}}}}
@media print{{:root{{{_CLARO}}}body{{background:#fff}}.folha{{border:0;margin:0;box-shadow:none;border-radius:0}}@page{{size:A4;margin:12mm}}.grafico,.kpi,tr{{break-inside:avoid}}}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--fundo);color:var(--texto);font:15px/1.55 "Segoe UI",system-ui,-apple-system,Roboto,Arial,sans-serif;font-variant-numeric:tabular-nums;-webkit-font-smoothing:antialiased}}
.folha{{max-width:920px;margin:28px auto;background:var(--folha);border:1px solid var(--borda);border-radius:16px;overflow:hidden;box-shadow:0 24px 48px -24px rgb(0 0 0/.6)}}
.capa{{padding:32px 40px 26px;background:radial-gradient(700px 260px at 85% -40%,color-mix(in srgb,var(--acento) 35%,transparent),transparent 70%),var(--folha);border-bottom:1px solid var(--borda)}}
.eyebrow{{font-size:11.5px;letter-spacing:.14em;text-transform:uppercase;color:var(--acento);font-weight:600}}
h1{{font-size:30px;line-height:1.15;letter-spacing:-.02em;margin:10px 0 6px;text-wrap:balance}}
.sub{{color:var(--muted);font-size:13px;margin:0}}
main{{padding:8px 40px 32px}}
.resumo{{margin:22px 0 4px;padding:16px 20px;border-radius:12px;background:var(--sup);border:1px solid var(--borda);border-left:3px solid var(--acento)}}
.kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:18px 0 8px}}
.kpi{{padding:14px 16px 14px 18px;border-radius:12px;background:var(--sup);border:1px solid var(--borda);position:relative}}
.kpi::before{{content:"";position:absolute;left:0;top:14px;bottom:14px;width:3px;border-radius:0 3px 3px 0;background:var(--tom)}}
.kpi.neutro{{--tom:var(--acento)}}.kpi.bom{{--tom:var(--bom)}}.kpi.alerta{{--tom:var(--alerta)}}.kpi.ruim{{--tom:var(--ruim)}}
.kpi small{{display:block;font-size:11.5px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}}
.kpi b{{display:block;font-size:28px;line-height:1.2;margin:4px 0 2px;letter-spacing:-.02em}}
.kpi.ruim b{{color:var(--ruim)}}
.kpi span{{font-size:12.5px;color:var(--muted)}}
section{{margin-top:32px}}
h2{{font-size:18px;margin:0 0 10px;display:flex;align-items:center;gap:10px}}
h2::before{{content:"";width:8px;height:8px;border-radius:2px;background:var(--acento);flex:none}}
h3{{font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin:18px 0 8px}}
p{{margin:8px 0}}
.tabela{{overflow-x:auto;border:1px solid var(--borda);border-radius:10px;margin:6px 0 10px}}
table{{width:100%;border-collapse:collapse;font-size:14px}}
th{{text-align:left;font-weight:600;font-size:12.5px;color:var(--muted);background:var(--sup);padding:9px 12px;border-bottom:1px solid var(--borda)}}
td{{padding:9px 12px;border-bottom:1px solid var(--borda)}}tr:last-child td{{border-bottom:0}}
td.num,th.num{{text-align:right;white-space:nowrap}}
.var{{display:inline-block;padding:1px 8px;border-radius:999px;font-weight:600;font-size:12.5px}}
.var.alerta{{color:var(--alerta);background:color-mix(in srgb,var(--alerta) 14%,transparent)}}
.var.bom{{color:var(--bom);background:color-mix(in srgb,var(--bom) 14%,transparent)}}
.grafico{{background:var(--sup);border:1px solid var(--borda);border-radius:12px;padding:4px 16px 12px;margin:6px 0 12px}}
.grafico svg{{width:100%;height:auto;display:block}}
.eixo{{fill:var(--muted);font-size:11px}}.linha{{fill:none;stroke:var(--acento);stroke-width:2;stroke-linejoin:round}}
.area{{fill:color-mix(in srgb,var(--acento) 18%,transparent)}}.hoje{{stroke:var(--muted);stroke-dasharray:3 4}}
.faixa{{stroke:var(--acento2);stroke-width:6;stroke-linecap:round;opacity:.4}}
.prev{{fill:var(--acento2)}}.rot{{fill:var(--texto);font-size:11.5px;font-weight:600}}
.seg{{fill:var(--acento)}}.seg-txt{{fill:var(--texto);font-size:11.5px}}.seg-txt.forte{{font-weight:700}}
.legenda{{color:var(--muted);font-size:12.5px;margin:2px 0 0}}
ul,ol{{padding-left:22px}}li{{margin:3px 0}}li::marker{{color:var(--acento)}}
code{{font:13px Consolas,monospace;background:var(--sup);padding:1px 5px;border-radius:4px}}
footer{{display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap;padding:14px 40px;border-top:1px solid var(--borda);color:var(--muted);font-size:12px}}
@media (max-width:640px){{.capa,main,footer{{padding-left:18px;padding-right:18px}}.folha{{margin:0;border-radius:0;border:0}}h1{{font-size:24px}}}}"""


def _inline(md: str) -> str:
    """Inline Markdown only (bold, code), without the <p> wrapper."""
    return re.sub(r"^<p>|</p>$", "", md_html(md).strip())


def _tabela(t: Tabela) -> str:
    var = [j for j, c in enumerate(t.cabecalho) if re.search(r"varia|tend[eê]n", c, re.I)]
    linha_md = lambda r: "| " + " | ".join(c.replace("|", "\\|") for c in r) + " |"
    html = md_html(linha_md(t.cabecalho) + "\n|" + "---|" * len(t.cabecalho) + "\n" + "\n".join(linha_md(r) for r in t.linhas))
    if var:  # only the variation columns become coloured chips, cell by cell
        def chip_linha(ml: re.Match) -> str:
            k = -1

            def td(mc: re.Match) -> str:
                nonlocal k
                k += 1
                tom = tom_variacao(mc.group(2)) if k in var else "neutro"
                return mc.group(0) if tom == "neutro" else f'{mc.group(1)}<span class="var {tom}">{mc.group(2)}</span></td>'
            return re.sub(r"(<td[^>]*>)(.*?)</td>", td, ml.group(0), flags=re.S)
        html = re.sub(r"<tr>.*?</tr>", chip_linha, html, flags=re.S)
    titulo = f"<h3>{escape(t.titulo)}</h3>" if t.titulo else ""
    return f'{titulo}<div class="tabela">{html}</div>'


def _serie(s: Serie) -> str:
    W, H, E, D, T, B = 720, 230, 14, 70, 30, 26   # width, height, left/right/top/bottom room
    ult = len(s.valores) - 1
    dias = ult + max((p[1] for p in s.previsoes), default=0)
    topo = max(s.valores + [p[4] for p in s.previsoes]) * 1.08 or 1
    x = lambda i: E + i * (W - E - D) / max(dias, 1)
    y = lambda v: H - B - v / topo * (H - T - B)
    pts = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(s.valores))
    partes = [f'<polygon class="area" points="{x(0):.1f},{H - B} {pts} {x(ult):.1f},{H - B}"/>',
              f'<polyline class="linha" points="{pts}"/>',
              f'<line class="hoje" x1="{x(ult):.1f}" x2="{x(ult):.1f}" y1="{T - 6}" y2="{H - B}"/>',
              f'<text class="eixo" x="{x(ult):.1f}" y="{T - 12}" text-anchor="middle">hoje</text>',
              f'<circle cx="{x(ult):.1f}" cy="{y(s.valores[-1]):.1f}" r="3.5" fill="var(--acento)"/>']
    for k in (0, ult // 2, ult):
        partes.append(f'<text class="eixo" x="{x(k):.1f}" y="{H - 6}" text-anchor="{"start" if k == 0 else "middle"}">'
                      f"{escape(s.rotulos[k])}</text>")
    for rot, a_frente, v, lo, hi in s.previsoes:
        i = ult + a_frente
        partes += [f'<line class="faixa" x1="{x(i):.1f}" x2="{x(i):.1f}" y1="{y(lo):.1f}" y2="{y(hi):.1f}"/>',
                   f'<circle class="prev" cx="{x(i):.1f}" cy="{y(v):.1f}" r="5"/>',
                   f'<text class="rot" x="{x(i) + 10:.1f}" y="{y(v) + 4:.1f}">{escape(rot)} · {n(v)}</text>']
    return (f'<div class="grafico"><h3>{escape(s.titulo)}</h3><svg viewBox="0 0 {W} {H}" role="img" '
            f'aria-label="{escape(s.titulo)}">{"".join(partes)}</svg></div>')


def _faixas(f: Faixas) -> str:
    W, H = 720, 58
    largura = W / max(len(f.faixas), 1)
    topo = max((p for _, p in f.faixas), default=0) or 1
    segs = []
    for k, (nome, p) in enumerate(f.faixas):
        x0 = k * largura
        forte = " forte" if p == topo else ""
        segs.append(f'<rect class="seg" x="{x0 + 2:.1f}" y="4" width="{largura - 4:.1f}" height="28" rx="6" '
                    f'opacity="{0.12 + 0.88 * p / topo:.2f}"/>'
                    f'<text class="seg-txt{forte}" x="{x0 + largura / 2:.1f}" y="50" text-anchor="middle">{escape(nome)} · '
                    f'{f"{p * 100:.1f}".replace(".", ",")}%</text>')
    return (f'<div class="grafico"><h3>{escape(f.titulo)}</h3><svg viewBox="0 0 {W} {H}" role="img" '
            f'aria-label="{escape(f.titulo)}">{"".join(segs)}</svg><p class="legenda">{escape(f.legenda)}</p></div>')


def _bloco(b) -> str:
    if isinstance(b, Tabela):
        return _tabela(b)
    if isinstance(b, Serie):
        return _serie(b)
    if isinstance(b, Faixas):
        return _faixas(b)
    if isinstance(b, Lista):
        tag = "ol" if b.ordenada else "ul"
        return f"<{tag}>" + "".join(f"<li>{_inline(i)}</li>" for i in b.itens) + f"</{tag}>"
    return f'<div class="resumo">{_inline(b.texto)}</div>' if b.nota else f"<p>{_inline(b.texto)}</p>"


def documento(doc: Documento) -> str:
    kpis = "".join(f'<div class="kpi {k.tom}"><small>{escape(k.rotulo)}</small><b>{escape(k.valor)}</b>'
                   f"<span>{escape(k.detalhe)}</span></div>" for k in doc.kpis)
    secoes = "".join(
        (f"<section><h{s.nivel}>{escape(s.titulo)}</h{s.nivel}>" if s.titulo else "<section>")
        + "".join(_bloco(b) for b in s.blocos) + "</section>" for s in doc.secoes)
    resumo = f'<div class="resumo">{_inline(doc.resumo)}</div>' if doc.resumo else ""
    fonte = f"<span>Fonte: {escape(doc.fonte)}</span>" if doc.fonte else "<span></span>"
    sub = doc.subtitulo or f"Gerado em {gerado_em()} pelo agente LocalOps · base real de 2025, em replay"
    return (f'<!doctype html>\n<html lang="pt-BR"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(doc.titulo)}</title>'
            f"<style>{_CSS}</style></head>\n<body><div class=\"folha\"><header class=\"capa\">"
            f'<div class="eyebrow">LocalOps · Relatório de operação</div><h1>{escape(doc.titulo)}</h1>'
            f'<p class="sub">{escape(sub)}</p></header>\n<main>{resumo}'
            f"{f'<div class=\"kpis\">{kpis}</div>' if kpis else ''}{secoes}</main>\n"
            f"<footer>{fonte}<span>LocalOps · Challenge Locaweb × FIAP</span></footer></div></body></html>\n")
