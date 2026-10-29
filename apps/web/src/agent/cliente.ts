import { ANTERIOR, BASE, variacao, type Dados, type Granularidade } from "../data/filtros";
import { projetar } from "../data/meta";

// One entry point for every conversation with the agent. With VITE_LOCALOPS_API set, questions go to
// {API}/v1/copilot (apps/api); without it, the panel answers in demo mode from the real aggregates.
const API = (import.meta.env.VITE_LOCALOPS_API as string | undefined)?.replace(/\/$/, "");
export const MODO: "demo" | "api" = API ? "api" : "demo";
const CONVERSA = Math.random().toString(36).slice(2, 12);

export const MAX_ANEXOS = 3;
const MAX_TEXTO = 20_000;
// Long text files are cut, and the agent is told so (the same note the API adds to PDF/XLSX).
const cortar = (t: string) => (t.length > MAX_TEXTO ? `${t.slice(0, MAX_TEXTO)}
[cortado em ${MAX_TEXTO.toLocaleString("pt-BR")} caracteres]` : t);

export type Anexo = { nome: string; tipo: string; tamanho: number; texto?: string; base64?: string };
export type Relatorio = { titulo: string; linhas: [string, string][] };
/** A file the agent hands back in the conversation; the panel offers it as a download. PDF and XLSX come as base64. */
export type Arquivo = { nome: string; tipo: string; conteudo: string; base64?: string };
export type Mensagem = { de: "agente" | "voce"; texto: string; fonte?: string; relatorio?: Relatorio; arquivos?: Arquivo[]; anexos?: Anexo[]; modo?: "llm" | "offline" };
export type Contexto = { dados: Dados; gran: Granularidade; hoje: number };

const num = new Intl.NumberFormat("pt-BR");
const pc = (v: number | null) => (v === null ? "sem base" : `${v > 0 ? "+" : "−"}${Math.abs(v * 100).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`);

export function relatorio({ dados: d, gran }: Contexto): Mensagem {
  const top = d.rank("produtos").find((r) => !r.chave.startsWith("("));
  const eq = d.rank("equipes")[0];
  const linhas: [string, string][] = [
    ["Alarmes", `${num.format(d.tot.n)} (${pc(variacao(d.tot.n, d.ant?.n))} vs ${ANTERIOR[gran]})`],
    ["Exigiram gente", `${num.format(d.tot.h)} (${pc(variacao(d.tot.h, d.ant?.h))})`],
    ["Fecharam sozinhos", d.tot.n ? `${((1 - d.tot.h / d.tot.n) * 100).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%` : "—"],
    ["Violações de OLA (KPI)", num.format(d.tot.o)],
    ["Produto com mais trabalho", top ? `${top.chave} · ${num.format(top.h)}` : "—"],
    ["Equipe mais demandada", eq ? `${eq.chave} · ${num.format(eq.h)}` : "—"],
  ];
  const csv = ["indicador;valor", ...linhas.map(([k, v]) => `${k};${v}`), `fonte;base real 2025, agregada`].join("\n") + "\n";
  return {
    de: "agente",
    texto: `Relatório de ${d.rotulo}, com os filtros atuais. A planilha vai junto.`,
    fonte: "base real 2025, agregada",
    relatorio: { titulo: `Relatório · ${d.rotulo}`, linhas },
    arquivos: [{ nome: `relatorio-localops-${d.rotulo.replace(/[^\p{L}\d]+/gu, "-").toLowerCase()}.csv`, tipo: "text/csv", conteudo: csv }],
  };
}

function resumoAnexos(anexos: Anexo[]): string {
  return anexos
    .map((a) => {
      if (a.texto && /\.(csv|tsv)$/i.test(a.nome)) {
        const linhas = a.texto.split(/\r?\n/).filter(Boolean);
        const sep = a.nome.endsWith(".tsv") ? "\t" : a.texto.includes(";") ? ";" : ",";
        const cols = (linhas[0] ?? "").split(sep).map((c) => c.trim());
        return `${a.nome}: ${num.format(Math.max(0, linhas.length - 1))} linhas e ${cols.length} colunas (${cols.slice(0, 6).join(", ")}${cols.length > 6 ? "…" : ""}).`;
      }
      if (a.texto) {
        const palavras = a.texto.split(/\s+/).filter(Boolean).length;
        return `${a.nome}: ${num.format(palavras)} palavras de texto lidas.`;
      }
      return `${a.nome}: recebido (${Math.round(a.tamanho / 1024)} KB). No modo demonstração só leio texto; PDF, Excel e HTML são lidos pelo agente.`;
    })
    .join("\n");
}

function responderDemo(pergunta: string, anexos: Anexo[], ctx: Contexto): Mensagem {
  const q = pergunta.toLowerCase();
  const d = ctx.dados;
  if (anexos.length) {
    return { de: "agente", texto: `Li os anexos:\n${resumoAnexos(anexos)}\n\nQuer que eu cruze com a base de incidentes?`, fonte: "anexos enviados" };
  }
  if (q.includes("relat")) return relatorio(ctx);
  if (q.includes("meta") || q.includes("ola") || q.includes("kpi")) {
    const [p2, p3] = (["P2", "P3"] as const).map((pri) => projetar("violacoes", pri, ctx.hoje));
    return {
      de: "agente",
      texto: `Até hoje: P2 com ${p2.ateHoje} violações e P3 com ${p3.ateHoje}. Projeção para 31/12: P2 entre ${p2.baixo} e ${p2.alto} (faixa mais provável ${p2.faixaProvavel.rotulo}) e P3 entre ${p3.baixo} e ${p3.alto} (${p3.faixaProvavel.rotulo}).`,
      fonte: "projeção da meta, faixas do dicionário de dados",
    };
  }
  if (q.includes("agir") || q.includes("refor") || q.includes("equipe") || q.includes("produto")) {
    const p = d.rank("produtos").find((r) => !r.chave.startsWith("("));
    const e = d.rank("equipes")[0];
    return {
      de: "agente",
      texto: p && e ? `Em ${d.rotulo}, o produto ${p.chave} gerou ${num.format(p.h)} alarmes que exigiram gente e a equipe ${e.chave} recebeu ${num.format(e.h)}. Comece por eles.` : "Não há alarmes com esses filtros.",
      fonte: "base real 2025, agregada",
    };
  }
  if (q.includes("fila") || q.includes("ruído") || q.includes("ruido")) {
    return {
      de: "agente",
      texto: "Com o limiar calibrado para recall de 97%, a fila cai de 855 para 384 alarmes por dia (−55%). No teste de dez/2025 ela manteve 95,3% dos alarmes que exigiram ação.",
      fonte: "filtro de ruído, teste em dez/2025",
    };
  }
  if (q.includes("amanhã") || q.includes("amanha") || q.includes("previs")) {
    return {
      de: "agente",
      texto: `Em ${d.rotulo}, ${num.format(d.tot.h)} alarmes exigiram gente. No walk-forward diário, o erro do total em D+1 foi 14,2% em dez/2025, contra 17,5% da regra simples.`,
      fonte: "métricas de backtest atuais",
    };
  }
  return {
    de: "agente",
    texto: "No modo demonstração respondo sobre relatório do período, meta de OLA, onde agir, fila e previsão, e leio anexos de texto e CSV. Conversa livre entra quando o agente OpenClaw estiver conectado.",
  };
}

export async function perguntar(pergunta: string, anexos: Anexo[], ctx: Contexto): Promise<Mensagem> {
  // Everything goes to the agent: questions, report requests and attachments (text read here; PDF, XLSX and HTML read by the API).
  if (MODO === "api") {
    const r = await fetch(`${API}/v1/copilot`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        pergunta: pergunta || "Analise os anexos.",
        hoje: BASE.dias[ctx.hoje],
        conversa: CONVERSA,
        filtro: ctx.dados.rotulo,
        anexos: anexos.slice(0, MAX_ANEXOS).map((a) => ({ nome: a.nome, texto: cortar(a.texto ?? ""), base64: a.base64 ?? "" })),
      }),
    });
    if (r.status === 429) throw new Error("Muitas perguntas seguidas. Espere um minuto.");
    if (!r.ok) throw new Error(`O agente respondeu ${r.status}. Tente de novo em instantes.`);
    return (await r.json()) as Mensagem;
  }
  await new Promise((ok) => setTimeout(ok, 450));
  return responderDemo(pergunta, anexos, ctx);
}

async function emBase64(f: File): Promise<string> {
  const url = await new Promise<string>((ok, falha) => {
    const r = new FileReader();
    r.onload = () => ok(r.result as string);
    r.onerror = () => falha(r.error);
    r.readAsDataURL(f);
  });
  return url.slice(url.indexOf(",") + 1);
}

/** Text files are read in the browser; PDF, XLSX and HTML (up to 5 MB) go to the API as base64; other binaries keep only their metadata. */
export async function lerAnexo(f: File): Promise<Anexo> {
  const texto = /\.(csv|tsv|txt|md|json|log)$/i.test(f.name) && f.size < 2_000_000 ? await f.text() : undefined;
  const base64 = /\.(pdf|xlsx|html?)$/i.test(f.name) && f.size <= 5 * 1024 * 1024 ? await emBase64(f) : undefined;
  return { nome: f.name, tipo: f.type || "arquivo", tamanho: f.size, texto, base64 };
}
