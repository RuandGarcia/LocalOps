import replay from "../../../../artefatos/previsao_replay.json";
import final from "../../../../artefatos/previsao_final.json";
import metricas from "../../../../artefatos/metricas.json";
import serieDiaria from "../../../../artefatos/serie_diaria.json";

// Real daily walk-forward from the pipeline (packages/localops_ml, D15): one forecast per origin day,
// model chosen on Oct–Nov/2025, error measured on Dec/2025.

export const SERIES = ["Total", "Humano", "P2", "P3", "KPI"] as const;
export type Serie = (typeof SERIES)[number];
export type Horizonte = "D+1" | "D+7";
type Chave = "total" | "humano" | "p2" | "p3" | "kpi";
const CHAVE: Record<Serie, Chave> = { Total: "total", Humano: "humano", P2: "p2", P3: "p3", KPI: "kpi" };

type Linha = { serie: string; h: number; origem: string; alvo: string; previsto: number; ic_inf: number; ic_sup: number; real?: number | null };
const LINHAS = [...(replay as Linha[]), ...(final as Linha[])];
const DIARIA = serieDiaria as ({ data: string } & Record<Chave, number>)[];
type Metrica = { modelo_escolhido: string; wape_teste_escolhido: number; wape_teste_baseline: number; bate_baseline_no_teste: boolean; intervalo: { cobertura_teste: number } };
const MET = metricas.previsao.series as Record<Chave, Record<Horizonte, Metrica>>;

export const NOME_MODELO: Record<string, string> = {
  mediana: "mediana dos modelos",
  media_7d: "média de 7 dias",
  ingenuo_sazonal: "mesmo dia da semana passada",
  sazonal_4sem: "média das 4 últimas semanas",
  xgboost: "XGBoost",
  prophet: "Prophet",
};

const ddmm = (iso: string) => `${iso.slice(8, 10)}/${iso.slice(5, 7)}`;

/** The 14 most recent forecasts made up to `hoje`; `real` only for days already lived. */
export function janela(serie: Serie, hz: Horizonte, hoje: string) {
  const h = hz === "D+1" ? 1 : 7;
  const todas = LINHAS.filter((l) => l.serie === CHAVE[serie] && l.h === h).sort((a, b) => a.origem.localeCompare(b.origem));
  const primeira = todas[0].origem;
  const ultima = todas[todas.length - 1].origem;
  const ref = hoje < primeira ? primeira : hoje > ultima ? ultima : hoje;
  const pontos = todas
    .filter((l) => l.origem <= ref)
    .slice(-14)
    .map((l) => ({
      dia: ddmm(l.alvo),
      alvo: l.alvo,
      previsto: Math.round(l.previsto),
      inf: Math.round(l.ic_inf),
      sup: Math.round(l.ic_sup),
      real: l.alvo <= ref && l.real != null ? Math.round(l.real) : null,
    }));
  return { pontos, ref, ajustado: ref !== hoje, primeira, ultima, metrica: MET[CHAVE[serie]][hz] };
}

/** What the number stands on: recent level and the same weekday a week before the target. */
export function contexto(serie: Serie, ref: string, alvo: string) {
  const k = CHAVE[serie];
  const ate = DIARIA.filter((d) => d.data <= ref).map((d) => d[k]);
  const media = (n: number) => ate.slice(-n).reduce((a, b) => a + b, 0) / Math.min(n, ate.length);
  const semanaAntes = new Date(`${alvo}T00:00:00Z`);
  semanaAntes.setUTCDate(semanaAntes.getUTCDate() - 7);
  const iso = semanaAntes.toISOString().slice(0, 10);
  const mesmoDia = iso <= ref ? DIARIA.find((d) => d.data === iso)?.[k] ?? null : null;
  return { media7: media(7), media28: media(28), mesmoDia, diaMesmoDia: ddmm(iso) };
}

export const CONFIANCA = SERIES.map((s) => {
  const m = MET[CHAVE[s]];
  const c = (hz: Horizonte) => ({ modelo: +(m[hz].wape_teste_escolhido * 100).toFixed(1), base: +(m[hz].wape_teste_baseline * 100).toFixed(1) });
  return { serie: s, h1: c("D+1"), h7: c("D+7") };
});

export const FILA_METRICAS = metricas.fila;

/** Last six real days of records that needed a person, tomorrow's forecast and the 90-day p90 as reference. */
export function cargaSemana(hoje: string) {
  const prev = janela("Humano", "D+1", hoje);
  const ate = DIARIA.filter((d) => d.data <= prev.ref);
  const dias = ate.slice(-6).map((d) => ({ alvo: d.data, valor: Math.round(d.humano), previsto: false }));
  const amanha = prev.pontos[prev.pontos.length - 1];
  dias.push({ alvo: amanha.alvo, valor: amanha.previsto, previsto: true });
  const ult90 = ate.slice(-90).map((d) => d.humano).sort((a, b) => a - b);
  const p90 = Math.round(ult90[Math.floor(0.9 * (ult90.length - 1))]);
  return { dias, p90, amanha, ref: prev.ref };
}
