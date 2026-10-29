import resumo from "../../../../artefatos/fila_shap.json";

// SHAP of the noise filter (XGBoost), test month Dec/2025, written by localops_ml.shap_fila.
// Contributions are log-odds: positive pushes towards "needs a person", negative towards noise.
export type Feature = "tpl" | "hora" | "dow" | "n1h_tpl" | "n24h_tpl" | "n24h_ci";
export const NOMES: Record<Feature, string> = {
  tpl: "Tipo de alarme",
  hora: "Hora do dia",
  dow: "Dia da semana",
  n1h_tpl: "Rajada do mesmo tipo (1 h)",
  n24h_tpl: "Mesmo tipo em 24 h",
  n24h_ci: "Mesmo item em 24 h",
};
export type Faixa = { faixa: string; n: number; shap_medio: number };
export type Tipo = { tpl: string; n: number; shap_medio: number; taxa_humano: number };
export const RESUMO = resumo as {
  mes: string;
  n_alarmes: number;
  base_prob: number; // SHAP base value: the model's starting point, not the real rate
  taxa_humano: number;
  limiar: number;
  importancia: { feature: Feature; media_abs: number; peso_pct: number }[];
  dependencia: Record<Exclude<Feature, "tpl">, Faixa[]>;
  tipos: { sobem: Tipo[]; descem: Tipo[] };
  exemplos: string[];
  previsao: string;
};

/** [template index, hour, weekday, burst 1 h, same type 24 h, same CI 24 h, six SHAP values, P(person)] */
export type ArquivoShap = { features: Feature[]; templates: string[]; base: number; alarmes: Record<string, number[]> };
export type Fator = { feature: Feature; valor: string; shap: number };
export type AlarmeExplicado = { numero: string; prob: number; naFila: boolean; fatores: Fator[] };

const DIAS = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"];
export const pc = (p: number) => `${(p * 100).toLocaleString("pt-BR", { maximumFractionDigits: p < 0.01 ? 2 : 1 })}%`;

export function explicar(numero: string, a: ArquivoShap): AlarmeExplicado | null {
  const chave = numero.trim().toUpperCase();
  const v = a.alarmes[chave];
  if (!v) return null;
  const valores = [a.templates[v[0]], `${v[1]}h`, DIAS[v[2]], String(v[3]), String(v[4]), String(v[5])];
  const fatores = a.features
    .map((f, i) => ({ feature: f, valor: valores[i], shap: v[6 + i] }))
    .sort((x, y) => Math.abs(y.shap) - Math.abs(x.shap));
  return { numero: chave, prob: v[12], naFila: v[12] >= RESUMO.limiar, fatores };
}

/** SHAP in one sentence: the chance, the strongest push up and the strongest push down. */
export function frase(e: AlarmeExplicado): string {
  const sobe = e.fatores.find((f) => f.shap > 0);
  const desce = e.fatores.find((f) => f.shap < 0);
  return [
    `${e.numero} tem ${pc(e.prob)} de chance de precisar de gente e ${e.naFila ? "fica na fila" : "sai da fila"}.`,
    sobe && `O que mais empurrou para cima: ${NOMES[sobe.feature].toLowerCase()} (${sobe.valor}).`,
    desce && `Para baixo: ${NOMES[desce.feature].toLowerCase()} (${desce.valor}).`,
  ]
    .filter(Boolean)
    .join(" ");
}
