import { useState, type DragEvent } from "react";
import { ChevronLeft, ChevronRight, Clock, Radio, Send } from "lucide-react";
import { AGENTES, COLUNAS, EXECUCOES, type Coluna } from "../data/cockpit";
import { useFiltro } from "../data/filtros";
import { tarefasDoDia } from "../data/tarefas";
import { Ilustrativo, TituloPagina, ordem } from "../components/ui";

const RESULTADO = {
  ok: { rotulo: "ok", cor: "text-ok border-emerald-400/30 bg-emerald-400/10" },
  alerta: { rotulo: "alerta", cor: "text-amber-300 border-amber-400/30 bg-amber-400/10" },
  falha: { rotulo: "falha", cor: "text-risco border-rose-400/30 bg-rose-400/10" },
} as const;

function Kanban({ dia }: { dia: string }) {
  const [tarefas, setTarefas] = useState(() => tarefasDoDia(dia));
  const [sobre, setSobre] = useState<Coluna | null>(null);
  const mover = (id: string, coluna: Coluna) => setTarefas((l) => l.map((t) => (t.id === id ? { ...t, coluna } : t)));
  const vizinha = (c: Coluna, passo: number) => COLUNAS[COLUNAS.findIndex((x) => x.id === c) + passo]?.id;

  function soltar(e: DragEvent, coluna: Coluna) {
    e.preventDefault();
    setSobre(null);
    mover(e.dataTransfer.getData("text/plain"), coluna);
  }

  return (
    <section aria-labelledby="tarefas-titulo" className="entra flex flex-col gap-3" style={ordem(2)}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id="tarefas-titulo" className="text-[15px] font-semibold">
          Tarefas abertas pelos agentes
        </h2>
        <span className="text-muted border-borda rounded-full border px-2 py-0.5 text-[11px] whitespace-nowrap">
          números reais de {dia.split("-").reverse().join("/")}
        </span>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4 [&>*]:min-w-0">
        {COLUNAS.map((col) => {
          const lista = tarefas.filter((t) => t.coluna === col.id);
          return (
            <div
              key={col.id}
              onDragOver={(e) => (e.preventDefault(), setSobre(col.id))}
              onDragLeave={(e) => e.currentTarget === e.target && setSobre(null)}
              onDrop={(e) => soltar(e, col.id)}
              className={(sobre === col.id ? "border-agente-1 " : "border-borda ") + "bg-trilho flex min-h-40 flex-col gap-2 rounded-xl border p-2.5 transition-colors"}
            >
              <p className="text-muted flex items-center justify-between px-1 pt-0.5 text-[13px] font-medium">
                {col.rotulo}
                <span className="font-mono text-[12px]">{lista.length}</span>
              </p>
              {lista.map((t) => {
                const antes = vizinha(t.coluna, -1);
                const depois = vizinha(t.coluna, 1);
                return (
                  <article
                    key={t.id}
                    draggable
                    onDragStart={(e) => e.dataTransfer.setData("text/plain", t.id)}
                    className="painel flex cursor-grab flex-col gap-2 p-3 active:cursor-grabbing"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <h3 className="text-[14px] leading-snug font-semibold">{t.titulo}</h3>
                      <span className="text-faint font-mono text-[11px]">{t.id}</span>
                    </div>
                    <p className="text-muted text-[13px] leading-relaxed">{t.detalhe}</p>
                    <div className="flex items-center gap-1">
                      <span className="text-agente mr-auto text-[12px]">{t.agente}</span>
                      {t.coluna === "visto" && (
                        <button
                          type="button"
                          onClick={() => mover(t.id, "feito")}
                          className="bg-texto text-fundo rounded-md px-2.5 py-1 text-[12px] font-medium"
                        >
                          Dar visto
                        </button>
                      )}
                      <button
                        type="button"
                        disabled={!antes}
                        onClick={() => antes && mover(t.id, antes)}
                        aria-label={`Mover ${t.id} para a coluna anterior`}
                        className="text-muted hover:text-texto flex size-7 items-center justify-center rounded hover:bg-white/[0.06] disabled:opacity-30"
                      >
                        <ChevronLeft size={15} />
                      </button>
                      <button
                        type="button"
                        disabled={!depois}
                        onClick={() => depois && mover(t.id, depois)}
                        aria-label={`Mover ${t.id} para a próxima coluna`}
                        className="text-muted hover:text-texto flex size-7 items-center justify-center rounded hover:bg-white/[0.06] disabled:opacity-30"
                      >
                        <ChevronRight size={15} />
                      </button>
                    </div>
                  </article>
                );
              })}
            </div>
          );
        })}
      </div>
    </section>
  );
}

export default function Agentes() {
  const { filtro } = useFiltro();
  return (
    <main className="px-4 py-6 sm:px-8 sm:py-8">
      <div className="mx-auto flex max-w-[1240px] flex-col gap-6">
        <TituloPagina titulo="Agentes">
          <p className="text-muted text-[13px]">Eles trabalham antes de alguém perguntar.</p>
        </TituloPagina>

        <ul className="entra grid gap-3 sm:grid-cols-2 xl:grid-cols-4" style={ordem(1)}>
          {AGENTES.map((a) => (
            <li key={a.nome} className={(a.estado === "ativo" ? "anel-agente " : "") + "painel flex flex-col gap-2 p-4"}>
              <div className="flex items-center gap-2.5">
                <span className={(a.estado === "ativo" ? "orbe-agente" : "bg-superficie-2 border-borda border") + " size-6 shrink-0 rounded-full"} aria-hidden="true" />
                <h2 className="min-w-0 flex-1 truncate text-[14px] font-semibold">{a.nome}</h2>
                {a.estado === "ativo" ? (
                  <span className="text-ok inline-flex items-center gap-1.5 text-[12px] font-medium">
                    <span className="pulso size-1.5 rounded-full bg-emerald-400" aria-hidden="true" />
                    Ativo
                  </span>
                ) : (
                  <span className="text-muted text-[12px]">Planejado</span>
                )}
              </div>
              <p className="text-muted text-[13px] leading-relaxed">{a.faz}</p>
              <div className="text-faint mt-auto flex flex-col gap-0.5 text-[12px]">
                <span className="flex items-center gap-1.5">
                  <Send size={12} aria-hidden="true" />
                  {a.canal}
                </span>
                <span className="flex items-center gap-1.5">
                  <Radio size={12} aria-hidden="true" />
                  {a.quando}
                </span>
                <span className="flex items-center gap-1.5">
                  <Clock size={12} aria-hidden="true" />
                  última execução: {a.ultima}
                </span>
              </div>
            </li>
          ))}
        </ul>

        <Kanban key={filtro.ref} dia={filtro.ref} />

        <section aria-labelledby="execucoes-titulo" className="painel entra flex flex-col gap-1 p-6" style={ordem(3)}>
          <div className="flex flex-wrap items-center justify-between gap-3 pb-3">
            <h2 id="execucoes-titulo" className="text-[15px] font-semibold">
              Registro de execuções
            </h2>
            <Ilustrativo />
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-left text-[13px]">
              <thead className="text-muted">
                <tr>
                  {["Hora", "Agente", "Gatilho", "Duração", "Resultado", "Saída"].map((c) => (
                    <th key={c} scope="col" className="border-borda border-b pr-4 pb-2 font-medium">
                      {c}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {EXECUCOES.map((x) => (
                  <tr key={x.hora + x.agente} className="border-borda border-b last:border-b-0">
                    <td className="text-muted py-3 pr-4 font-mono whitespace-nowrap">{x.hora}</td>
                    <td className="text-agente py-3 pr-4 whitespace-nowrap">{x.agente}</td>
                    <td className="text-muted py-3 pr-4 whitespace-nowrap">{x.gatilho}</td>
                    <td className="py-3 pr-4 font-mono whitespace-nowrap">{x.duracao}</td>
                    <td className="py-3 pr-4">
                      <span className={RESULTADO[x.resultado].cor + " rounded-full border px-2 py-0.5 text-[12px] font-medium"}>{RESULTADO[x.resultado].rotulo}</span>
                    </td>
                    <td className="py-3 leading-relaxed">{x.saida}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </main>
  );
}
