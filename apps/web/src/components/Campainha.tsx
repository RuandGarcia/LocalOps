import { useEffect, useRef, useState } from "react";
import { Bell, CalendarClock, Gauge, BookOpenCheck, type LucideIcon } from "lucide-react";

type Alerta = { id: number; hora: string; agente: string; texto: string; rota: string; icone: LucideIcon; tom: "humano" | "risco" | "agente" };

// Illustrative until the OpenClaw agents run (S3).
const ALERTAS: Alerta[] = [
  { id: 1, hora: "08:15", agente: "Guarda da OLA", texto: "INC-771204 tem 82% de chance de estourar a OLA em 40 min.", rota: "#/meta", icone: Gauge, tom: "risco" },
  { id: 2, hora: "08:01", agente: "Alerta de pico", texto: "Pico entre 17h e 19h: 61 alarmes que exigem gente. Reforce o N2 Hospedagem a partir das 16h.", rota: "#/previsao", icone: CalendarClock, tom: "humano" },
  { id: 3, hora: "08:00", agente: "Briefing do plantão", texto: "Folha 0291 pronta: 3 itens exigem você.", rota: "#/cockpit", icone: BookOpenCheck, tom: "agente" },
];

const COR = { humano: "text-amber-300 bg-amber-400/10", risco: "text-risco bg-rose-400/10", agente: "text-agente bg-indigo-400/10" };

export default function Campainha() {
  const [aberto, setAberto] = useState(false);
  const [lidos, setLidos] = useState<number[]>([]);
  const ref = useRef<HTMLDivElement>(null);
  const naoLidos = ALERTAS.filter((a) => !lidos.includes(a.id)).length;

  useEffect(() => {
    if (!aberto) return;
    const fora = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setAberto(false);
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setAberto(false);
    document.addEventListener("mousedown", fora);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", fora);
      document.removeEventListener("keydown", esc);
    };
  }, [aberto]);

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setAberto((a) => !a)}
        aria-expanded={aberto}
        aria-label={naoLidos ? `Alertas dos agentes, ${naoLidos} não lidos` : "Alertas dos agentes"}
        className="border-borda bg-superficie text-muted hover:text-texto relative flex size-9 items-center justify-center rounded-md border transition-colors"
      >
        <Bell size={16} aria-hidden="true" className={naoLidos ? "text-texto" : ""} />
        {naoLidos > 0 && (
          <span className="bg-humano text-fundo absolute -top-1.5 -right-1.5 flex size-[18px] items-center justify-center rounded-full text-[11px] font-bold shadow-[0_0_12px_rgb(251_191_36/0.6)]">
            {naoLidos}
          </span>
        )}
      </button>

      {aberto && (
        <div className="painel absolute top-full right-0 z-50 mt-2 flex w-[min(380px,calc(100vw-2rem))] flex-col overflow-hidden">
          <div className="border-borda flex items-center justify-between gap-3 border-b px-4 py-3">
            <p className="text-[14px] font-semibold">Alertas dos agentes</p>
            {naoLidos > 0 && (
              <button type="button" onClick={() => setLidos(ALERTAS.map((a) => a.id))} className="text-agente text-[12px] hover:underline">
                Marcar todos como lidos
              </button>
            )}
          </div>
          <ul className="flex flex-col">
            {ALERTAS.map((a) => {
              const lido = lidos.includes(a.id);
              const Icone = a.icone;
              return (
                <li key={a.id} className="border-borda border-b last:border-b-0">
                  <a
                    href={a.rota}
                    onClick={() => {
                      setLidos((l) => [...new Set([...l, a.id])]);
                      setAberto(false);
                    }}
                    className="hover:bg-white/[0.03] flex gap-3 px-4 py-3 no-underline"
                  >
                    <span className={`${COR[a.tom]} flex size-8 shrink-0 items-center justify-center rounded-lg`} aria-hidden="true">
                      <Icone size={15} />
                    </span>
                    <span className="flex min-w-0 flex-col gap-0.5">
                      <span className="flex items-center gap-2 text-[12px]">
                        <span className="text-texto font-medium">{a.agente}</span>
                        <span className="text-faint font-mono">{a.hora}</span>
                        {!lido && <span className="ponto-humano size-1.5 rounded-full" aria-label="não lido" />}
                      </span>
                      <span className={(lido ? "text-muted" : "text-texto") + " text-[13px] leading-snug"}>{a.texto}</span>
                    </span>
                  </a>
                </li>
              );
            })}
          </ul>
          <p className="text-faint border-borda border-t px-4 py-2 text-[11px]">Alertas ilustrativos até os agentes rodarem (S3).</p>
        </div>
      )}
    </div>
  );
}
