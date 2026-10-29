"""Real files in the copilot chat: read PDF, Excel and HTML attachments as text for the model, and turn
the agent's Markdown/CSV blocks into HTML, PDF and Excel downloads (the model only ever writes text)."""
from __future__ import annotations

import base64
import io
import re
import zipfile
from html.parser import HTMLParser
from pathlib import Path

from openpyxl import load_workbook
from pypdf import PdfReader

from localops_api import render_html, render_pdf, render_xlsx
from localops_api.documento import Documento, de_csv, de_markdown, titulo_do_nome
from localops_api.documento import numero as _numero  # noqa: F401  (kept for callers of the old name)

MAX_BYTES = 5 * 1024 * 1024  # decoded size of one attachment
MAX_PAGINAS = 50
MAX_LINHAS = 2000
MAX_DESCOMPACTADO = 40 * 1024 * 1024  # what a .xlsx may expand to
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
LIDOS = (".pdf", ".xlsx", ".html", ".htm")
GERADOS = {".html": "text/html", ".pdf": "application/pdf", ".xlsx": XLSX}


class ErroFormato(ValueError):
    pass


# --- reading attachments --------------------------------------------------------------------------

class _Texto(HTMLParser):
    BLOCO = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "table", "section", "article"}

    def __init__(self) -> None:
        super().__init__()
        self.partes: list[str] = []
        self._pular = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self._pular += 1
        elif tag in self.BLOCO:
            self.partes.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript"):
            self._pular = max(0, self._pular - 1)
        elif tag in ("td", "th"):
            self.partes.append(" ; ")

    def handle_data(self, data):
        if not self._pular:
            self.partes.append(data)


def _html_texto(b: bytes) -> str:
    p = _Texto()
    p.feed(b.decode("utf-8", errors="replace"))
    return re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n\n", "".join(p.partes))).strip()


def _pdf_texto(b: bytes) -> str:
    leitor = PdfReader(io.BytesIO(b))
    paginas = [(pg.extract_text() or "").strip() for pg in leitor.pages[:MAX_PAGINAS]]
    texto = "\n\n".join(f"[página {i}]\n{t}" for i, t in enumerate(paginas, 1) if t)
    if not texto:
        raise ErroFormato("o PDF não tem texto selecionável (parece digitalizado)")
    return texto + (f"\n\n[só as {MAX_PAGINAS} primeiras de {len(leitor.pages)} páginas]" if len(leitor.pages) > MAX_PAGINAS else "")


def _xlsx_texto(b: bytes) -> str:
    # A .xlsx is a zip: check what it expands to before openpyxl loads it (a 200 KB file can hold a 200 MB cell).
    try:
        with zipfile.ZipFile(io.BytesIO(b)) as z:
            if sum(i.file_size for i in z.infolist()) > MAX_DESCOMPACTADO:
                raise ErroFormato("planilha grande demais quando descompactada (limite de 40 MB)")
    except zipfile.BadZipFile as e:
        raise ErroFormato("não é um arquivo .xlsx válido") from e
    wb = load_workbook(io.BytesIO(b), read_only=True, data_only=True)
    partes, n = [], 0
    for ws in wb.worksheets:
        partes.append(f"[aba {ws.title}]")
        for linha in ws.iter_rows(values_only=True):
            if n >= MAX_LINHAS:
                partes.append(f"[cortado em {MAX_LINHAS} linhas]")
                return "\n".join(partes)
            if any(v is not None for v in linha):
                partes.append(";".join("" if v is None else str(v) for v in linha).rstrip(";"))
                n += 1
    return "\n".join(partes)


def ler_anexo(nome: str, dados_b64: str) -> str:
    """Text of a PDF, XLSX or HTML attachment the browser sent as base64."""
    ext = Path(nome).suffix.lower()
    if ext not in LIDOS:
        raise ErroFormato(f"não leio arquivos {ext or 'sem extensão'}")
    try:
        b = base64.b64decode(dados_b64, validate=True)
    except ValueError as e:
        raise ErroFormato("arquivo corrompido no envio") from e
    if len(b) > MAX_BYTES:
        raise ErroFormato("arquivo maior que 5 MB")
    if ext == ".pdf":
        return _pdf_texto(b)
    if ext == ".xlsx":
        return _xlsx_texto(b)
    return _html_texto(b)


# --- generating downloads -------------------------------------------------------------------------
# Each format is drawn from one Documento (documento.py) by render_html, render_pdf and render_xlsx.

def html_documento(md: str, nome: str) -> str:
    return render_html.documento(de_markdown(md, nome))


def pdf_bytes(md: str, nome: str) -> bytes:
    return render_pdf.documento(de_markdown(md, nome))


def xlsx_bytes(texto_csv: str, titulo: str = "Planilha LocalOps") -> bytes:
    return render_xlsx.documento(de_csv(texto_csv, titulo))


def gerar(nome: str, fonte: "str | Documento") -> dict:
    """A download from the agent's text or from a built Documento: Markdown → .html/.pdf, CSV → .xlsx."""
    ext = Path(nome).suffix.lower()
    if isinstance(fonte, Documento):
        doc = fonte
    else:
        doc = de_csv(fonte, titulo_do_nome(nome)) if ext == ".xlsx" else de_markdown(fonte, nome)
    if ext == ".html":
        return {"nome": nome, "tipo": GERADOS[ext], "conteudo": render_html.documento(doc)}
    b = render_pdf.documento(doc) if ext == ".pdf" else render_xlsx.documento(doc)
    return {"nome": nome, "tipo": GERADOS[ext], "conteudo": "", "base64": base64.b64encode(b).decode()}
