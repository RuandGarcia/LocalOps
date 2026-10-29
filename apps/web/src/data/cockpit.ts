import { FILA_METRICAS } from "./previsao";

// Real figures come from docs/PLANO_LocalOps_NEXT.md (recomputed 30/09/2026).
// Everything marked `ilustrativo` is synthetic until the walk-forward (S2) and the agent (S3) exist.

export const REAL = {
  alarmesDia: 766,
  semIntervencaoPct: 85.9,
  humanosDia: 108,
  humanosP90: 179,
  humanosPico: 433,
  picoData: "16/10/2025",
  olaP2Violacoes2025: 42,
  olaFaixaAtual: "75%",
  olaFaixa100: "36–39",
  olaP3Violacoes2025: 196,
  olaP3Faixa: "150%",
  // Noise filter from the pipeline: train Sep–Oct, thresholds picked on Nov, test Dec/2025.
  fila: {
    antes: Math.round(FILA_METRICAS.fila_por_dia_antes),
    porRecall: Object.fromEntries(
      Object.entries(FILA_METRICAS.por_recall).map(([r, v]) => [r, { depois: Math.round(v.fila_por_dia_depois), reducao: Math.round(v.reducao_fila * 100), recall: v.recall_teste }]),
    ) as Record<Recall, { depois: number; reducao: number; recall: number }>,
  },
};

export type Recall = 95 | 97 | 99;

export const FAIXAS_OLA = ["150%", "125%", "100%", "75%", "50%", "0%"] as const;

// Deterministic sample of alarm episodes: p = probability of needing a person.
function amostra(n: number, seed: number) {
  let s = seed;
  const rnd = () => {
    s = (s * 1664525 + 1013904223) % 4294967296;
    return s / 4294967296;
  };
  return Array.from({ length: n }, (_, i) => {
    const r = rnd();
    // Skewed: most episodes are noise, a few clearly need a person.
    const p = r < 0.78 ? rnd() * 0.12 : r < 0.92 ? 0.12 + rnd() * 0.35 : 0.47 + rnd() * 0.53;
    return { id: i, p };
  });
}

export const EPISODIOS = amostra(144, 20251016);

// Probability cut-offs that keep the recall shares on the illustrative sample.
export const CORTE: Record<Recall, number> = { 95: 0.2, 97: 0.12, 99: 0.06 };

export const DIAS_REPLAY = [
  { valor: "2025-09-22", rotulo: "seg, 22/09/2025" },
  { valor: "2025-10-16", rotulo: "qui, 16/10/2025" },
  { valor: "2025-12-08", rotulo: "seg, 08/12/2025" },
] as const;

// Illustrative queue rows built from the deterministic sample.
const MODELOS = [
  { alarme: "Unavailable by ICMP ping", produto: "Hospedagem" },
  { alarme: "Disk space is critically low", produto: "Cloud Server" },
  { alarme: "High CPU utilization", produto: "VPS" },
  { alarme: "MySQL replication lag", produto: "Banco gerenciado" },
  { alarme: "SMTP queue above threshold", produto: "E-mail" },
  { alarme: "HTTP 5xx rate above 2%", produto: "Site Builder" },
  { alarme: "Certificate expires in 3 days", produto: "Hospedagem" },
  { alarme: "Backup job failed", produto: "Cloud Server" },
] as const;

export const FILA_ITENS = EPISODIOS.slice(0, 40).map((e, i) => {
  const m = MODELOS[i % MODELOS.length];
  const minuto = 8 * 60 + Math.floor(i * 7.3);
  return {
    id: `EP-${(48210 + i).toString()}`,
    hora: `${String(Math.floor(minuto / 60)).padStart(2, "0")}:${String(minuto % 60).padStart(2, "0")}`,
    alarme: m.alarme,
    produto: m.produto,
    ci: `srv-${(1200 + ((i * 37) % 800)).toString()}`,
    repeticoes: 1 + ((i * 13) % 9),
    p: e.p,
  };
});

export const OLA_RISCO = [
  { id: "INC-771204", titulo: "Lentidão no painel de e-mail corporativo", equipe: "Team05", resta: 40, p: 0.82 },
  { id: "INC-771219", titulo: "Falha intermitente de DNS em revenda", equipe: "Team11", resta: 55, p: 0.64 },
  { id: "INC-771233", titulo: "Erro 502 em loja virtual", equipe: "Team09", resta: 70, p: 0.41 },
  { id: "INC-771241", titulo: "Backup não concluído em Cloud Server", equipe: "Team03", resta: 180, p: 0.12 },
];

export const AGENTES = [
  {
    nome: "Briefing do plantão",
    canal: "Sino do Cockpit · plantão N2",
    quando: "todo dia às 08h e 20h",
    faz: "Escreve a passagem de plantão: o que exige gente, a carga prevista e o risco de OLA.",
    estado: "planejado" as const,
    ultima: "—",
  },
  {
    nome: "Alerta de pico",
    canal: "Sino do Cockpit · plantonista",
    quando: "quando a carga prevista passa da capacidade",
    faz: "Avisa com 4 horas de antecedência e sugere quem reforçar.",
    estado: "planejado" as const,
    ultima: "—",
  },
  {
    nome: "Guarda da OLA",
    canal: "Sino do Cockpit · coordenação",
    quando: "a cada 15 minutos",
    faz: "Aponta os P2 com chance alta de estourar a OLA na próxima hora.",
    estado: "planejado" as const,
    ultima: "—",
  },
  {
    nome: "Copiloto web",
    canal: "Chat no LocalOps",
    quando: "quando alguém pergunta",
    faz: "Responde com número, motivo e fonte, usando as mesmas ferramentas dos outros agentes.",
    estado: "ativo" as const,
    ultima: "a cada pergunta (GPT via OpenClaw)",
  },
];

export type Coluna = "fazer" | "executando" | "visto" | "feito";
export const COLUNAS: { id: Coluna; rotulo: string }[] = [
  { id: "fazer", rotulo: "A fazer" },
  { id: "executando", rotulo: "Em execução" },
  { id: "visto", rotulo: "Aguardando visto" },
  { id: "feito", rotulo: "Concluído" },
];

// Illustrative run log until the OpenClaw agent writes the real one (S3).
export const EXECUCOES: { hora: string; agente: string; gatilho: string; duracao: string; resultado: "ok" | "alerta" | "falha"; saida: string }[] = [
  { hora: "08:15", agente: "Guarda da OLA", gatilho: "a cada 15 min", duracao: "2,1 s", resultado: "alerta", saida: "INC-771204 com 82% de chance de estourar em 40 min. Avisei a coordenação." },
  { hora: "08:01", agente: "Alerta de pico", gatilho: "carga prevista > capacidade", duracao: "3,4 s", resultado: "alerta", saida: "Pico previsto entre 17h e 19h: 61 alarmes que exigem gente. Sugeri reforço no N2 Hospedagem." },
  { hora: "08:00", agente: "Briefing do plantão", gatilho: "agenda 08h", duracao: "6,8 s", resultado: "ok", saida: "Folha 0291 publicada no Cockpit do N2. Três itens exigem o plantonista." },
  { hora: "07:45", agente: "Guarda da OLA", gatilho: "a cada 15 min", duracao: "1,9 s", resultado: "ok", saida: "Nenhum P2 acima de 50% de chance de estourar." },
  { hora: "07:30", agente: "Guarda da OLA", gatilho: "a cada 15 min", duracao: "3,0 s", resultado: "falha", saida: "A base de incidentes não respondeu em 3 s. Nova tentativa às 07:45." },
  { hora: "20:00", agente: "Briefing do plantão", gatilho: "agenda 20h", duracao: "7,2 s", resultado: "ok", saida: "Folha 0290 publicada. Turno fechou com 97 alarmes que exigiram gente." },
];
