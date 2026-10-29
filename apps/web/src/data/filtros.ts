import { createContext, useContext, useMemo } from "react";
import bruto from "./agregados.json";

// Real counts from the 2025 incident base (scripts/build_agregados.py).
type Base = {
  dias: string[];
  produtos: string[];
  categorias: string[];
  equipes: string[];
  prioridades: string[];
  fatos: [number, number, number, number, number, number, number, number, number][];
  calor: [number, number, number, number][];
  reincidentes: [number, string, number][];
  semanas: string[];
  tendenciaCi: Record<string, { h: number[]; o: number[] }>;
  violacoes: [number, number, string, number, number][]; // day, priority, CI, category, product
};
export const BASE = bruto as unknown as Base;

export type Granularidade = "dia" | "semana" | "mes" | "ano";
export type Dimensao = "produtos" | "categorias" | "equipes" | "prioridades";

export type Filtro = {
  gran: Granularidade;
  ref: string; // YYYY-MM-DD inside 2025
  produtos: string[];
  categorias: string[];
  equipes: string[];
  prioridades: string[];
};

export const FILTRO_INICIAL: Filtro = { gran: "dia", ref: "2025-10-16", produtos: [], categorias: [], equipes: [], prioridades: [] };

export const ROTULO_DIM: Record<Dimensao, string> = {
  produtos: "Produto",
  categorias: "Categoria",
  equipes: "Equipe",
  prioridades: "Prioridade",
};

const idxDia = new Map(BASE.dias.map((d, i) => [d, i]));
const dataDe = (s: string) => new Date(`${s}T12:00:00`);
const iso = (d: Date) => d.toISOString().slice(0, 10);

/** Inclusive day-index range of the selected period and of the one right before it. */
export function periodos(f: Filtro) {
  const d = dataDe(f.ref);
  let ini: Date;
  let fim: Date;
  if (f.gran === "dia") {
    ini = fim = d;
  } else if (f.gran === "semana") {
    const seg = (d.getDay() + 6) % 7;
    ini = new Date(d);
    ini.setDate(d.getDate() - seg);
    fim = new Date(ini);
    fim.setDate(ini.getDate() + 6);
  } else if (f.gran === "mes") {
    ini = new Date(d.getFullYear(), d.getMonth(), 1, 12);
    fim = new Date(d.getFullYear(), d.getMonth() + 1, 0, 12);
  } else {
    ini = new Date(d.getFullYear(), 0, 1, 12);
    fim = new Date(d.getFullYear(), 11, 31, 12);
  }
  const clamp = (x: Date) => Math.min(BASE.dias.length - 1, Math.max(0, idxDia.get(iso(x)) ?? (x < dataDe(BASE.dias[0]) ? 0 : BASE.dias.length - 1)));
  const a = clamp(ini);
  const b = clamp(fim);
  const len = b - a + 1;
  const anterior = a - len >= 0 ? ([a - len, a - 1] as const) : null;
  return { atual: [a, b] as const, anterior, rotulo: rotuloPeriodo(f, ini, fim) };
}

const fmtDia = new Intl.DateTimeFormat("pt-BR", { weekday: "short", day: "2-digit", month: "2-digit", year: "numeric" });
const fmtMes = new Intl.DateTimeFormat("pt-BR", { month: "long", year: "numeric" });
const fmtCurto = new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "2-digit" });

function rotuloPeriodo(f: Filtro, ini: Date, fim: Date) {
  if (f.gran === "dia") return fmtDia.format(ini);
  if (f.gran === "semana") return `semana de ${fmtCurto.format(ini)} a ${fmtCurto.format(fim)}`;
  if (f.gran === "mes") return fmtMes.format(ini);
  return String(ini.getFullYear());
}

export const ANTERIOR: Record<Granularidade, string> = { dia: "dia anterior", semana: "semana anterior", mes: "mês anterior", ano: "ano anterior" };

type Totais = { n: number; h: number; o: number; e: number };
const zero = (): Totais => ({ n: 0, h: 0, o: 0, e: 0 });

export function passa(f: Filtro, linha: Base["fatos"][number]) {
  const [, p, c, e, pr] = linha;
  return (
    (!f.produtos.length || f.produtos.includes(BASE.produtos[p])) &&
    (!f.categorias.length || f.categorias.includes(BASE.categorias[c])) &&
    (!f.equipes.length || f.equipes.includes(BASE.equipes[e])) &&
    (!f.prioridades.length || f.prioridades.includes(BASE.prioridades[pr]))
  );
}

function agregar(f: Filtro, faixa: readonly [number, number] | null) {
  const tot = zero();
  const porDim: Record<Dimensao, Map<string, Totais>> = {
    produtos: new Map(),
    categorias: new Map(),
    equipes: new Map(),
    prioridades: new Map(),
  };
  const porDia = new Map<number, Totais>();
  const porDiaP2 = new Map<number, number>();
  if (!faixa) return { tot, porDim, porDia, porDiaP2 };
  for (const linha of BASE.fatos) {
    const [dia, p, c, eq, pr, n, h, o, e] = linha;
    if (dia < faixa[0] || dia > faixa[1] || !passa(f, linha)) continue;
    tot.n += n;
    tot.h += h;
    tot.o += o;
    tot.e += e;
    const chaves: [Dimensao, string][] = [
      ["produtos", BASE.produtos[p]],
      ["categorias", BASE.categorias[c]],
      ["equipes", BASE.equipes[eq]],
      ["prioridades", BASE.prioridades[pr]],
    ];
    for (const [dim, k] of chaves) {
      const t = porDim[dim].get(k) ?? zero();
      t.n += n;
      t.h += h;
      t.o += o;
      t.e += e;
      porDim[dim].set(k, t);
    }
    const t = porDia.get(dia) ?? zero();
    t.n += n;
    t.h += h;
    t.o += o;
    t.e += e;
    porDia.set(dia, t);
    if (BASE.prioridades[pr] === "P2") porDiaP2.set(dia, (porDiaP2.get(dia) ?? 0) + o);
  }
  return { tot, porDim, porDia, porDiaP2 };
}

export type Ranking = { chave: string; h: number; hAnt: number; n: number; o: number; e: number; parte: number; delta: number | null }[];

/** Buckets that are not a real product, category or team: never an action target. */
export const semClasse = (k: string) => k.startsWith("(") || k === "outros" || k === "outras";

function ranking(atual: Map<string, Totais>, ant: Map<string, Totais> | null, totalH: number): Ranking {
  return [...atual.entries()]
    .map(([chave, t]) => {
      const a = ant?.get(chave)?.h;
      return { chave, h: t.h, hAnt: a ?? 0, n: t.n, o: t.o, e: t.e, parte: totalH ? t.h / totalH : 0, delta: a ? (t.h - a) / a : null };
    })
    .sort((x, y) => y.h - x.h);
}

export function calcular(f: Filtro) {
  const p = periodos(f);
  const atual = agregar(f, p.atual);
  const ant = p.anterior ? agregar(f, p.anterior) : null;
  const rank = (d: Dimensao) => ranking(atual.porDim[d], ant?.porDim[d] ?? null, atual.tot.h);

  // Daily series for charts: at least the 30 days ending at the period end.
  const ini = Math.min(p.atual[0], Math.max(0, p.atual[1] - 29));
  const serieAgg = agregar(f, [ini, p.atual[1]]);
  const serie = [] as { dia: string; n: number; h: number; o: number; noPeriodo: boolean }[];
  for (let i = ini; i <= p.atual[1]; i++) {
    const t = serieAgg.porDia.get(i) ?? zero();
    serie.push({ dia: BASE.dias[i], ...t, noPeriodo: i >= p.atual[0] });
  }

  // OLA breaches by month (period year, all months), respecting dimension filters.
  const anoTodo = agregar(f, [0, BASE.dias.length - 1]);
  const olaMes = Array.from({ length: 12 }, () => ({ total: 0, p2: 0 }));
  for (const [dia, t] of anoTodo.porDia) olaMes[Number(BASE.dias[dia].slice(5, 7)) - 1].total += t.o;
  for (const [dia, o] of anoTodo.porDiaP2) olaMes[Number(BASE.dias[dia].slice(5, 7)) - 1].p2 += o;

  // Heatmap: human alarms by weekday x hour over the months the period touches.
  const meses = new Set<number>();
  for (let i = p.atual[0]; i <= p.atual[1]; i++) meses.add(Number(BASE.dias[i].slice(5, 7)));
  const calor = Array.from({ length: 7 }, () => Array(24).fill(0) as number[]);
  for (const [mes, dow, hora, n] of BASE.calor) if (meses.has(mes)) calor[dow][hora] += n;

  const cis = new Map<string, number>();
  for (const [mes, ci, n] of BASE.reincidentes) if (meses.has(mes)) cis.set(ci, (cis.get(ci) ?? 0) + n);
  const reincidentes = [...cis.entries()].sort((a, b) => b[1] - a[1]).slice(0, 6);

  return {
    rotulo: p.rotulo,
    dias: p.atual[1] - p.atual[0] + 1,
    tot: atual.tot,
    ant: ant?.tot ?? null,
    rank,
    serie,
    olaMes,
    calor,
    reincidentes,
    meses: [...meses].sort((a, b) => a - b),
  };
}

export type Dados = ReturnType<typeof calcular>;

export const FiltroCtx = createContext<{ filtro: Filtro; setFiltro: (f: Filtro) => void }>({
  filtro: FILTRO_INICIAL,
  setFiltro: () => {},
});

export function useFiltro() {
  return useContext(FiltroCtx);
}

export function useDados() {
  const { filtro } = useFiltro();
  return useMemo(() => calcular(filtro), [filtro]);
}

export const diaIdx = (iso: string) => idxDia.get(iso) ?? 0;

export const variacao = (atual: number, ant: number | null | undefined) => (ant ? (atual - ant) / ant : null);
