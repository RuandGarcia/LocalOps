import filaDiaria from "../../../../artefatos/fila_diaria.json";
import filaTemplates from "../../../../artefatos/fila_templates.json";
import type { Coluna } from "./cockpit";
import { diaIdx } from "./filtros";
import { ondeAgirMeta, projetar } from "./meta";
import { contexto, janela } from "./previsao";

// Tasks the shift agents would open on the replay day, computed from the real base and the pipeline
// artefacts. The numbers are real; the agents that would open them do not run yet (only the web copilot).

export type Tarefa = { id: string; chave: string; titulo: string; detalhe: string; agente: string; coluna: Coluna };

const num = new Intl.NumberFormat("pt-BR");
const ddmm = (iso: string) => `${iso.slice(8, 10)}/${iso.slice(5, 7)}`;
const pc = (v: number) => `${v > 0 ? "+" : "−"}${Math.abs(Math.round(v * 100))}%`;
type DiaFila = { data: string; alarmes: number; exigiram_pessoa: number; fila_filtrada: number; pessoa_fora_da_fila: number };
type Template = { tpl: string; alarmes: number; exigiram_pessoa: number; mantidos: number };

export function tarefasDoDia(hoje: string): Tarefa[] {
  const idx = diaIdx(hoje);
  const out: Omit<Tarefa, "id">[] = [];

  // Load: tomorrow's forecast of records that need a person, against the recent level.
  const prev = janela("Humano", "D+1", hoje);
  const amanha = prev.pontos[prev.pontos.length - 1];
  const ctx = contexto("Humano", prev.ref, amanha.alvo);
  const desvio = amanha.previsto / ctx.media28 - 1;
  out.push({
    chave: "carga",
    titulo: desvio > 0.1 ? `Reforçar o plantão de ${ddmm(amanha.alvo)}` : `Plantão de ${ddmm(amanha.alvo)} dentro do normal`,
    detalhe: `${num.format(amanha.previsto)} registros que exigem gente previstos (faixa ${num.format(amanha.inf)}–${num.format(amanha.sup)}), ${pc(desvio)} sobre a média de 28 dias.`,
    agente: "Alerta de pico",
    coluna: desvio > 0.1 ? "fazer" : "feito",
  });

  // Yesterday's forecast against what happened today.
  const hojeReal = prev.pontos.find((p) => p.alvo === prev.ref && p.real !== null);
  if (hojeReal && hojeReal.real !== null) {
    const erro = hojeReal.real / hojeReal.previsto - 1;
    out.push({
      chave: "fechamento",
      titulo: `Fechar o dia ${ddmm(prev.ref)}: previsto × real`,
      detalhe: `Previsto ${num.format(hojeReal.previsto)}, aconteceram ${num.format(hojeReal.real)} (${pc(erro)}). ${hojeReal.real >= hojeReal.inf && hojeReal.real <= hojeReal.sup ? "Dentro" : "Fora"} da faixa de 80%.`,
      agente: "Briefing do plantão",
      coluna: "visto",
    });
  }

  // Annual OLA target for P2 and P3.
  for (const pri of ["P2", "P3"] as const) {
    const p = projetar("violacoes", pri, idx);
    out.push({
      chave: `meta-${pri}`,
      titulo: `Meta de OLA ${pri}: faixa provável ${p.faixaProvavel.rotulo}`,
      detalhe: `${num.format(p.ateHoje)} violações até ${ddmm(hoje)}; projeção de ${num.format(Math.round(p.media))} em 31/12 (${num.format(p.baixo)}–${num.format(p.alto)}).`,
      agente: "Guarda da OLA",
      coluna: "executando",
    });
  }

  // Where to act: the configuration item and category that keep violating.
  const onde = ondeAgirMeta(idx);
  const [ci, n] = onde.cis[0] ?? [];
  if (ci) {
    out.push({
      chave: "item",
      titulo: `Atacar a causa do item ${ci}`,
      detalhe: `${n} violações de OLA até ${ddmm(hoje)}, o item mais reincidente; ${onde.reincidentes} de ${onde.total} violações repetem um item que já tinha violado.`,
      agente: "Guarda da OLA",
      coluna: "fazer",
    });
  }
  const [cat, nc] = onde.categorias[0] ?? [];
  if (cat) {
    out.push({
      chave: "categoria",
      titulo: `Revisar a categoria ${cat}`,
      detalhe: `${nc} violações de OLA até ${ddmm(hoje)}, a categoria que mais estoura.`,
      agente: "Guarda da OLA",
      coluna: "fazer",
    });
  }

  // Noise filter: the day itself when it is in the test month, otherwise the noisiest template of December.
  const dia = (filaDiaria as DiaFila[]).find((d) => d.data === hoje);
  if (dia) {
    out.push({
      chave: "fila",
      titulo: `Revisar ${num.format(dia.alarmes - dia.fila_filtrada)} alarmes escondidos`,
      detalhe: `O filtro deixou ${num.format(dia.fila_filtrada)} de ${num.format(dia.alarmes)} alarmes na fila; ${dia.pessoa_fora_da_fila} dos ${dia.exigiram_pessoa} que exigiram gente ${dia.pessoa_fora_da_fila === 1 ? "ficou" : "ficaram"} fora.`,
      agente: "Briefing do plantão",
      coluna: "visto",
    });
  } else {
    const t = (filaTemplates as Template[])[0];
    out.push({
      chave: "fila",
      titulo: "Silenciar o alarme mais ruidoso",
      detalhe: `"${t.tpl}" gerou ${num.format(t.alarmes)} alarmes em dez/2025 e só ${t.exigiram_pessoa} exigiram gente.`,
      agente: "Briefing do plantão",
      coluna: "fazer",
    });
  }

  return out.map((t, i) => ({ ...t, id: `T-${String(idx * 10 + i).padStart(4, "0")}` }));
}

const DIAS_SEMANA = ["dom", "seg", "ter", "qua", "qui", "sex", "sáb"];
const LIGACAO: Record<string, { fonte: string; acao: string; href: string }> = {
  carga: { fonte: "previsão D+1, walk-forward diário", acao: "Ver previsão", href: "#/previsao" },
  "meta-P2": { fonte: "projeção da meta anual", acao: "Ver meta", href: "#/meta" },
  fila: { fonte: "filtro de ruído, teste em dez/2025", acao: "Ver fila", href: "#/fila" },
};

/** The handover sheet for the replay day: three items picked from the same real tasks as the Kanban. */
export function passagemDoDia(hoje: string) {
  const tarefas = tarefasDoDia(hoje);
  const itens = ["carga", "meta-P2", "fila"].flatMap((k) => {
    const t = tarefas.find((x) => x.chave === k);
    return t ? [{ destaque: t.titulo, detalhe: t.detalhe, ...LIGACAO[k] }] : [];
  });
  const fechamento = tarefas.find((x) => x.chave === "fechamento");
  const d = new Date(`${hoje}T00:00:00Z`);
  return {
    folha: String(diaIdx(hoje) + 1).padStart(4, "0"),
    data: `${DIAS_SEMANA[d.getUTCDay()]}, ${hoje.split("-").reverse().join("/")}`,
    resumo: [fechamento && `Hoje: ${fechamento.detalhe}`, itens[0] && `Amanhã: ${itens[0].detalhe}`].filter(Boolean).join(" "),
    itens,
  };
}
