import { BASE, diaIdx, passa, periodos, semClasse, type Filtro } from "./filtros";

export type DimTendencia = "produtos" | "categorias" | "cis";
export type Metrica = "h" | "e" | "o";

export const ROTULO_METRICA: Record<Metrica, string> = { h: "Exigiram gente", e: "Entraram no KPI", o: "Violações de OLA" };
export const ROTULO_DIM_T: Record<DimTendencia, string> = { produtos: "Produto", categorias: "Categoria", cis: "Item de configuração" };

const SEMANAS = 12;
const semanaDoDia = BASE.dias.map((d) => {
  const dt = new Date(`${d}T12:00:00`);
  dt.setDate(dt.getDate() - ((dt.getDay() + 6) % 7));
  return BASE.semanas.indexOf(dt.toISOString().slice(0, 10));
});

export type Tendencia = {
  chave: string;
  serie: number[];
  ultimas4: number;
  anteriores4: number;
  delta: number | null;
  inclinacao: number; // per week, least squares over the window
  estado: "subindo" | "estavel" | "caindo";
};

function inclinacao(y: number[]) {
  const n = y.length;
  const mx = (n - 1) / 2;
  const my = y.reduce((a, b) => a + b, 0) / n;
  let num = 0;
  let den = 0;
  y.forEach((v, i) => {
    num += (i - mx) * (v - my);
    den += (i - mx) ** 2;
  });
  return den ? num / den : 0;
}

/** Weekly trend per product, category or configuration item over the 12 weeks ending at the period end. */
export function tendencias(f: Filtro, dim: DimTendencia, metrica: Metrica) {
  const fimDia = periodos(f).atual[1];
  const fim = semanaDoDia[fimDia];
  const ini = Math.max(0, fim - SEMANAS + 1);
  const semanas = BASE.semanas.slice(ini, fim + 1);
  const mapa = new Map<string, number[]>();

  if (dim === "cis") {
    const m = metrica === "e" ? "h" : metrica;
    for (const [ci, s] of Object.entries(BASE.tendenciaCi)) mapa.set(ci, s[m].slice(ini, fim + 1));
  } else {
    const col = metrica === "h" ? 6 : metrica === "o" ? 7 : 8;
    const nomes = dim === "produtos" ? BASE.produtos : BASE.categorias;
    const pos = dim === "produtos" ? 1 : 2;
    for (const linha of BASE.fatos) {
      const sem = semanaDoDia[linha[0]];
      if (sem < ini || sem > fim || !passa(f, linha)) continue;
      const k = nomes[linha[pos]];
      const s = mapa.get(k) ?? Array(semanas.length).fill(0);
      s[sem - ini] += linha[col];
      mapa.set(k, s);
    }
  }

  const itens: Tendencia[] = [...mapa.entries()]
    .filter(([k, s]) => !semClasse(k) && s.reduce((a, b) => a + b, 0) > 0)
    .map(([chave, serie]) => {
      const ultimas4 = serie.slice(-4).reduce((a, b) => a + b, 0);
      const anteriores4 = serie.slice(-8, -4).reduce((a, b) => a + b, 0);
      const delta = anteriores4 ? (ultimas4 - anteriores4) / anteriores4 : null;
      const inc = inclinacao(serie);
      const media = serie.reduce((a, b) => a + b, 0) / serie.length || 1;
      const rel = inc / media;
      return { chave, serie, ultimas4, anteriores4, delta, inclinacao: inc, estado: rel > 0.04 ? "subindo" : rel < -0.04 ? "caindo" : "estavel" } as Tendencia;
    })
    .sort((a, b) => b.inclinacao - a.inclinacao);

  return { semanas, itens, metricaUsada: dim === "cis" && metrica === "e" ? ("h" as Metrica) : metrica, hoje: diaIdx(f.ref) };
}
