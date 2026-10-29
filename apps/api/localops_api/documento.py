"""One report model for the three downloads. The standard shift report builds it from the tools; the
agent's Markdown/CSV is parsed into it; render_html, render_pdf and render_xlsx draw it."""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path


@dataclass
class Kpi:
    rotulo: str
    valor: str
    detalhe: str = ""
    tom: str = "neutro"  # neutro | bom | alerta | ruim


@dataclass
class Tabela:
    cabecalho: list[str]
    linhas: list[list[str]]
    titulo: str = ""


@dataclass
class Serie:
    titulo: str
    rotulos: list[str]                                       # dd/mm, only days up to "hoje"
    valores: list[float]
    previsoes: list[tuple[str, int, float, float, float]]  # (label, days ahead, forecast, band low, band high)


@dataclass
class Faixas:
    titulo: str
    faixas: list[tuple[str, float]]  # official bands, best first: ("150%", 0.0), ..., ("0%", 0.0)
    legenda: str                     # projection sentence under the bar


@dataclass
class Texto:
    texto: str
    nota: bool = False


@dataclass
class Lista:
    itens: list[str]
    ordenada: bool = False


@dataclass
class Secao:
    titulo: str
    blocos: list = field(default_factory=list)
    nivel: int = 2


@dataclass
class Documento:
    titulo: str
    subtitulo: str = ""
    resumo: str = ""
    kpis: list[Kpi] = field(default_factory=list)
    secoes: list[Secao] = field(default_factory=list)
    fonte: str = ""


# --- numbers in pt-BR -----------------------------------------------------------------------------

NUM = re.compile(r"^[−\-+]?[\d.,]+\s*(%|p\.p\.|pp)?$|^[\d.,]+\s*[–-]\s*[\d.,]+%?$|^—$")
_VARIACAO = re.compile(r"^\s*([+−-])\s*\d")


def gerado_em() -> str:
    return datetime.now(timezone(timedelta(hours=-3))).strftime("%d/%m/%Y %H:%M")


def n(x: float) -> str:
    return f"{round(x):,}".replace(",", ".")


def pc(x: float, casas: int = 1) -> str:
    return f"{x:.{casas}f}".replace(".", ",") + "%"


def tom_variacao(v: str) -> str:
    """More human work is the warning colour, less is the good one; anything else stays neutral."""
    m = _VARIACAO.match(v)
    return "neutro" if not m else ("alerta" if m.group(1) == "+" else "bom")


def numero(v: str):
    """A pt-BR cell as (number, Excel format), or (text, None) when it is not a number."""
    s = re.sub(r"^\+", "", v.strip().replace("−", "-"))  # "+11,3%" is a number too
    pct = s.endswith("%")
    s = s.rstrip("%").strip()
    if re.fullmatch(r"-?\d{1,3}(\.\d{3})+(,\d+)?|-?\d+(,\d+)?", s):
        x = float(s.replace(".", "").replace(",", "."))
    elif re.fullmatch(r"-?\d+\.\d{1,2}", s):  # "109.7": the model's dot decimal, never a thousands mark here
        x = float(s)
    else:
        return v, None
    x = x / 100 if pct else x
    fmt = "0.0%" if pct else ("#,##0" if x.is_integer() else "#,##0.0")
    return (int(x) if x.is_integer() and not pct else x), fmt


# --- Markdown and CSV into the model --------------------------------------------------------------

SEM_IMAGEM = re.compile(r"!\[([^\]]*)\]\([^)]*\)")  # ![alt](url) keeps only the alt text


def titulo_md(md: str, nome: str) -> str:
    m = re.search(r"^#\s+(.+)$", md, re.M)
    return m.group(1).strip() if m else titulo_do_nome(nome)


def titulo_do_nome(nome: str) -> str:
    return Path(nome).stem.replace("-", " ").capitalize() if nome else "Relatório LocalOps"


def separa(md: str) -> tuple[str, str, str]:
    """(title, body without the title line, source sentence or '')."""
    m = re.search(r"^#\s+(.+)$", md, re.M)
    titulo = m.group(1).strip() if m else ""
    md = SEM_IMAGEM.sub(r"\1", md)
    corpo = re.sub(r"^#\s+.+$\n?", "", md, count=1, flags=re.M)
    fontes = re.findall(r"^\s*[*_]*Fonte[*_]*:[*_]*\s*(.+?)\s*$", corpo, re.M)
    corpo = re.sub(r"^\s*[*_]*Fonte[*_]*:.*$\n?", "", corpo, flags=re.M)
    return titulo, corpo.strip(), (fontes[-1] if fontes else "")


def blocos_md(md: str) -> list[tuple]:
    """A small Markdown block reader: headings, paragraphs, lists, quotes and pipe tables."""
    linhas, i, out = md.splitlines(), 0, []
    eh_item = lambda l: re.match(r"^\s*([-*+]|\d+[.)])\s+", l)
    while i < len(linhas):
        l = linhas[i]
        if not l.strip():
            i += 1
        elif m := re.match(r"^(#{1,4})\s+(.*)", l):
            out.append(("h", len(m.group(1)), m.group(2).strip()))
            i += 1
        elif l.lstrip().startswith("|"):
            linhas_t = []
            while i < len(linhas) and linhas[i].lstrip().startswith("|"):
                if not re.fullmatch(r"[\s|:\-]+", linhas[i]):
                    celulas = re.split(r"(?<!\\)\|", linhas[i].strip().strip("|"))  # "\|" is a pipe inside a cell
                    linhas_t.append([c.strip().replace("\\|", "|") for c in celulas])
                i += 1
            out.append(("tabela", linhas_t))
        elif l.lstrip().startswith(">"):
            partes = []
            while i < len(linhas) and linhas[i].lstrip().startswith(">"):
                partes.append(linhas[i].lstrip()[1:].strip())
                i += 1
            out.append(("nota", " ".join(p for p in partes if p)))
        elif eh_item(l):
            itens, ordenada = [], bool(re.match(r"^\s*\d", l))
            while i < len(linhas) and (eh_item(linhas[i]) or (linhas[i].startswith("  ") and itens)):
                if m := eh_item(linhas[i]):
                    itens.append(linhas[i][m.end():].strip())
                else:
                    itens[-1] += " " + linhas[i].strip()
                i += 1
            out.append(("lista", ordenada, itens))
        else:
            partes = []
            while i < len(linhas) and linhas[i].strip() and not re.match(r"^(#{1,4}\s|\||>)", linhas[i].lstrip()) and not eh_item(linhas[i]):
                partes.append(linhas[i].strip())
                i += 1
            out.append(("p", " ".join(partes)))
    return out


def limpo(s: str) -> str:
    """Bold and code marks out: titles, KPI cells and sheet names are plain text."""
    return re.sub(r"\*\*|__|`", "", s).strip()


def de_markdown(md: str, nome: str = "") -> Documento:
    titulo, corpo, fonte = separa(md)
    doc = Documento(titulo=limpo(titulo) or titulo_do_nome(nome), fonte=fonte)
    atual: Secao | None = None
    for b in blocos_md(corpo):
        if b[0] == "h":
            atual = Secao(limpo(b[2]), nivel=2 if b[1] <= 2 else 3)
            doc.secoes.append(atual)
            continue
        if b[0] == "nota" and atual is None and not doc.resumo:
            doc.resumo = b[1]
            continue
        if b[0] == "tabela" and b[1] and b[1][0][0].strip().lower() == "kpi" and not doc.kpis:
            doc.kpis = [Kpi(*[limpo(c) for c in (r + ["", ""])[:3]]) for r in b[1][1:]]
            continue
        if b[0] == "tabela" and not b[1]:
            continue
        bloco = {"tabela": lambda: Tabela(b[1][0], b[1][1:]), "nota": lambda: Texto(b[1], nota=True),
                 "p": lambda: Texto(b[1]), "lista": lambda: Lista(b[2], b[1])}[b[0]]()
        if atual is None:
            atual = Secao("")
            doc.secoes.append(atual)
        atual.blocos.append(bloco)
    return doc


def de_csv(texto: str, titulo: str) -> Documento:
    """The agent's CSV (or a Markdown table it sent instead) as a one-table document."""
    linhas = [l for l in texto.strip().splitlines() if l.strip()]
    tabela = [i for i, l in enumerate(linhas) if l.lstrip().startswith("|")]
    if tabela:  # the model sometimes sends a Markdown table, often under a title: the sheet starts at the table
        linhas = [";".join(c.strip() for c in l.strip().strip("|").split("|")) if l.lstrip().startswith("|") else l
                  for l in linhas[tabela[0]:] if not re.fullmatch(r"[\s|:\-]+", l)]
    fontes = [re.split(r"[:;]", l, maxsplit=1)[1].strip(" ;").replace(";", " · ") for l in linhas if re.match(r"^\s*Fonte\s*[:;]", l)]
    linhas = [l for l in linhas if not re.match(r"^\s*Fonte\s*[:;]", l)]
    sep = ";" if ";" in (linhas[0] if linhas else "") else ","
    rows = list(csv.reader(linhas, delimiter=sep))
    t = Tabela(rows[0] if rows else [], rows[1:])
    return Documento(titulo=titulo, secoes=[Secao("", [t])], fonte=fontes[-1] if fontes else "")


def para_texto(doc: Documento) -> str:
    """The document as plain text with ';' tables, for a marker that lands in a .csv/.md/.txt block."""
    out = [doc.titulo, ""] + ([re.sub(r"\*\*", "", doc.resumo), ""] if doc.resumo else [])
    out += [f"{k.rotulo};{k.valor};{k.detalhe}" for k in doc.kpis] + ([""] if doc.kpis else [])
    for s in doc.secoes:
        out += [s.titulo] if s.titulo else []
        for b in s.blocos:
            if isinstance(b, Tabela):
                out += ([b.titulo] if b.titulo else []) + [";".join(b.cabecalho)] + [";".join(r) for r in b.linhas] + [""]
    return "\n".join(out + ([f"Fonte;{doc.fonte}"] if doc.fonte else [])) + "\n"
