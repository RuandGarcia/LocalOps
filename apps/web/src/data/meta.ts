import { BASE, semClasse } from "./filtros";

// Official annual KPI goals (Dicionario_de_Dados_v2.docx, "Metas Anuais de KPI").
export type Faixa = { rotulo: string; min: number; max: number };
const faixas = (limites: [number, number, number, number, number]): Faixa[] => {
  const [a, b, c, d, e] = limites;
  return [
    { rotulo: "150%", min: 0, max: a - 1 },
    { rotulo: "125%", min: a, max: b },
    { rotulo: "100%", min: b + 1, max: c },
    { rotulo: "75%", min: c + 1, max: d },
    { rotulo: "50%", min: d + 1, max: e },
    { rotulo: "0%", min: e + 1, max: Infinity },
  ];
};

export type Kpi = "violacoes" | "volume";
export type Pri = "P2" | "P3";

export const FAIXAS: Record<Kpi, Record<Pri, Faixa[]>> = {
  violacoes: { P2: faixas([31, 35, 39, 45, 53]), P3: faixas([201, 230, 263, 290, 320]) },
  volume: { P2: faixas([4585, 5388, 6168, 6252, 6336]), P3: faixas([19489, 22116, 22524, 23892, 24276]) },
};

export const faixaDe = (kpi: Kpi, pri: Pri, v: number) => FAIXAS[kpi][pri].find((f) => v >= f.min && v <= f.max)!;
/** Highest count that still reaches 100%. */
export const teto100 = (kpi: Kpi, pri: Pri) => FAIXAS[kpi][pri][2].max;

// Daily company-wide series per KPI and priority (the KPI ignores product/team filters).
const N = BASE.dias.length;
const serie: Record<Kpi, Record<Pri, number[]>> = {
  violacoes: { P2: Array(N).fill(0), P3: Array(N).fill(0) },
  volume: { P2: Array(N).fill(0), P3: Array(N).fill(0) },
};
for (const [dia, , , , pr, , , o, e] of BASE.fatos) {
  const p = BASE.prioridades[pr];
  if (p !== "P2" && p !== "P3") continue;
  serie.violacoes[p][dia] += o;
  serie.volume[p][dia] += e;
}

const phi = (z: number) => 0.5 * (1 + erf(z / Math.SQRT2));
function erf(x: number) {
  const t = 1 / (1 + 0.3275911 * Math.abs(x));
  const y = 1 - ((((1.061405429 * t - 1.453152027) * t + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * Math.exp(-x * x);
  return x >= 0 ? y : -y;
}

export type Projecao = {
  kpi: Kpi;
  pri: Pri;
  ateHoje: number;
  restantes: number;
  ritmoSemana: number;
  media: number;
  baixo: number;
  alto: number;
  faixaProvavel: Faixa;
  prob: { faixa: Faixa; p: number }[];
  real: number; // year-end actual, known in the replay
};

/**
 * Year-end projection as of day index `hoje`: observed total so far plus the remaining days at the
 * pace of the last 90 days, with the spread of that pace (daily variance, at least Poisson).
 */
export function projetar(kpi: Kpi, pri: Pri, hoje: number, janela = 90): Projecao {
  const s = serie[kpi][pri];
  const ateHoje = s.slice(0, hoje + 1).reduce((a, b) => a + b, 0);
  const ini = Math.max(0, hoje - janela + 1);
  const recorte = s.slice(ini, hoje + 1);
  const m = recorte.reduce((a, b) => a + b, 0) / recorte.length;
  const v = recorte.reduce((a, b) => a + (b - m) ** 2, 0) / Math.max(1, recorte.length - 1);
  const restantes = N - 1 - hoje;
  const media = ateHoje + m * restantes;
  const dp = Math.sqrt(Math.max(v, m) * restantes);
  const z80 = 1.2816;
  const prob = FAIXAS[kpi][pri].map((faixa) => {
    if (dp === 0) return { faixa, p: media >= faixa.min && media <= faixa.max ? 1 : 0 };
    const sup = faixa.max === Infinity ? 1 : phi((faixa.max + 0.5 - media) / dp);
    const inf = faixa.min === 0 ? 0 : phi((faixa.min - 0.5 - media) / dp);
    return { faixa, p: Math.max(0, sup - inf) };
  });
  return {
    kpi,
    pri,
    ateHoje,
    restantes,
    ritmoSemana: m * 7,
    media,
    baixo: Math.max(ateHoje, Math.round(media - z80 * dp)),
    alto: Math.round(media + z80 * dp),
    faixaProvavel: prob.reduce((a, b) => (b.p > a.p ? b : a)).faixa,
    prob,
    real: s.reduce((a, b) => a + b, 0),
  };
}

/** Violations so far, their configuration items and how many repeat an item that already violated. */
export function ondeAgirMeta(hoje: number, pri?: Pri) {
  const vistos = new Map<string, number>();
  let reincidentes = 0;
  let total = 0;
  const porCategoria = new Map<string, number>();
  for (const [dia, pr, ci, cat] of BASE.violacoes) {
    if (dia > hoje || (pri && BASE.prioridades[pr] !== pri)) continue;
    total++;
    if (vistos.has(ci)) reincidentes++;
    vistos.set(ci, (vistos.get(ci) ?? 0) + 1);
    const c = BASE.categorias[cat];
    porCategoria.set(c, (porCategoria.get(c) ?? 0) + 1);
  }
  const cis = [...vistos.entries()].filter(([, n]) => n >= 2).sort((a, b) => b[1] - a[1]);
  const categorias = [...porCategoria.entries()].filter(([c]) => !semClasse(c)).sort((a, b) => b[1] - a[1]);
  return { total, reincidentes, cis, categorias };
}
