import { useEffect, useRef, useState } from "react";
import { Check, ChevronDown, X } from "lucide-react";
import { BASE, FILTRO_INICIAL, ROTULO_DIM, periodos, useFiltro, type Dimensao, type Granularidade } from "../data/filtros";
import { Segmentado } from "./ui";

const GRANS: Granularidade[] = ["dia", "semana", "mes", "ano"];
const ROTULO_GRAN: Record<Granularidade, string> = { dia: "Dia", semana: "Semana", mes: "Mês", ano: "Ano" };
const DIMS: Dimensao[] = ["produtos", "categorias", "equipes", "prioridades"];

function MultiSelecao({ dim }: { dim: Dimensao }) {
  const { filtro, setFiltro } = useFiltro();
  const [aberto, setAberto] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const escolhidos = filtro[dim];
  const opcoes = BASE[dim];

  useEffect(() => {
    if (!aberto) return;
    const fora = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setAberto(false);
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setAberto(false);
    const fechar = () => setAberto(false);
    document.addEventListener("mousedown", fora);
    document.addEventListener("keydown", esc);
    window.addEventListener("hashchange", fechar);
    return () => {
      document.removeEventListener("mousedown", fora);
      document.removeEventListener("keydown", esc);
      window.removeEventListener("hashchange", fechar);
    };
  }, [aberto]);

  const alternar = (v: string) =>
    setFiltro({ ...filtro, [dim]: escolhidos.includes(v) ? escolhidos.filter((x) => x !== v) : [...escolhidos, v] });

  const resumo = escolhidos.length === 0 ? "Todos" : escolhidos.length === 1 ? escolhidos[0] : `${escolhidos[0]} +${escolhidos.length - 1}`;

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        aria-haspopup="listbox"
        aria-expanded={aberto}
        onClick={() => setAberto((a) => !a)}
        className={
          (escolhidos.length ? "border-agente-1/60 bg-indigo-400/10 text-texto " : "border-borda bg-superficie text-muted hover:text-texto ") +
          "flex min-h-9 items-center gap-1.5 rounded-md border px-3 text-[13px] whitespace-nowrap transition-colors"
        }
      >
        <span className={escolhidos.length ? "text-agente" : ""}>{ROTULO_DIM[dim]}:</span>
        <span className="max-w-[9rem] truncate">{resumo}</span>
        <ChevronDown size={14} aria-hidden="true" />
      </button>
      {aberto && (
        <div className="painel absolute top-full left-0 z-50 mt-1.5 flex max-h-80 w-60 flex-col overflow-hidden">
          <ul role="listbox" aria-multiselectable="true" aria-label={ROTULO_DIM[dim]} className="flex-1 overflow-y-auto p-1">
            {opcoes.map((o) => {
              const on = escolhidos.includes(o);
              return (
                <li key={o} role="option" aria-selected={on}>
                  <button
                    type="button"
                    onClick={() => alternar(o)}
                    className="hover:bg-white/[0.05] flex w-full items-center gap-2.5 rounded-md px-2.5 py-1.5 text-left text-[13px]"
                  >
                    <span
                      className={(on ? "bg-agente-1 border-agente-1 text-fundo " : "border-faint ") + "flex size-4 items-center justify-center rounded border"}
                      aria-hidden="true"
                    >
                      {on && <Check size={12} strokeWidth={3} />}
                    </span>
                    {o}
                  </button>
                </li>
              );
            })}
          </ul>
          {escolhidos.length > 0 && (
            <button
              type="button"
              onClick={() => setFiltro({ ...filtro, [dim]: [] })}
              className="text-muted hover:text-texto border-borda border-t px-3 py-2 text-left text-[12px]"
            >
              Limpar {ROTULO_DIM[dim].toLowerCase()}
            </button>
          )}
        </div>
      )}
    </div>
  );
}

export default function FiltroBarra() {
  const { filtro, setFiltro } = useFiltro();
  const { rotulo } = periodos(filtro);
  const ativos = DIMS.reduce((s, d) => s + filtro[d].length, 0);

  return (
    <div className="flex flex-wrap items-center gap-2">
      <Segmentado rotulo="Granularidade do período" opcoes={GRANS} valor={filtro.gran} aoMudar={(g) => setFiltro({ ...filtro, gran: g })} formatar={(g) => ROTULO_GRAN[g]} />

      {filtro.gran === "mes" ? (
        <label className="sr-only" htmlFor="ref-mes">
          Mês
        </label>
      ) : (
        <label className="sr-only" htmlFor="ref-dia">
          Data de referência
        </label>
      )}
      {filtro.gran === "mes" ? (
        <input
          id="ref-mes"
          type="month"
          min="2025-01"
          max="2025-12"
          value={filtro.ref.slice(0, 7)}
          onChange={(e) => e.target.value && setFiltro({ ...filtro, ref: `${e.target.value}-15` })}
          className="bg-superficie border-borda text-texto min-h-9 rounded-md border px-2.5 text-[13px]"
        />
      ) : filtro.gran === "ano" ? (
        <span className="bg-superficie border-borda text-texto flex min-h-9 items-center rounded-md border px-3 text-[13px]">2025</span>
      ) : (
        <input
          id="ref-dia"
          type="date"
          min="2025-01-01"
          max="2025-12-31"
          value={filtro.ref}
          onChange={(e) => e.target.value && setFiltro({ ...filtro, ref: e.target.value })}
          className="bg-superficie border-borda text-texto min-h-9 rounded-md border px-2.5 text-[13px]"
        />
      )}

      <span className="bg-borda mx-1 hidden h-5 w-px lg:block" aria-hidden="true" />

      {DIMS.map((d) => (
        <MultiSelecao key={d} dim={d} />
      ))}

      {ativos > 0 && (
        <button
          type="button"
          onClick={() => setFiltro({ ...FILTRO_INICIAL, gran: filtro.gran, ref: filtro.ref })}
          className="text-muted hover:text-texto flex min-h-9 items-center gap-1 px-2 text-[13px]"
        >
          <X size={14} aria-hidden="true" />
          Limpar filtros
        </button>
      )}

      <p className="text-muted ml-auto text-[12px]" aria-live="polite">
        Mostrando {rotulo}
      </p>
    </div>
  );
}
