import { useState, type KeyboardEvent, type PointerEvent } from "react";

// Shared hover layer for the panel's charts: one tooltip look, and a cursor that snaps to the nearest
// point under the pointer (or the arrow keys, when the chart has focus).

export type LinhaDica = { rotulo: string; valor: string; cor?: string };

/** Tooltip anchored at fraction `x` (0–1) of its relative parent; flips to the left past 60%. */
export function Dica({ x, topo = 0, titulo, linhas }: { x: number; topo?: number; titulo: string; linhas: LinhaDica[] }) {
  const lado = x > 0.6 ? { right: `${(1 - x) * 100}%`, marginRight: 12 } : { left: `${x * 100}%`, marginLeft: 12 };
  return (
    <div
      role="status"
      className="bg-superficie-2/95 border-borda pointer-events-none absolute z-20 flex min-w-40 flex-col gap-1 rounded-lg border px-3 py-2 text-[12px] shadow-lg shadow-black/40 backdrop-blur"
      style={{ top: topo, ...lado }}
    >
      <p className="text-muted">{titulo}</p>
      {linhas.map((l) => (
        <p key={l.rotulo} className="flex items-center justify-between gap-4">
          <span className="text-muted flex items-center gap-1.5">
            {l.cor && <span className="inline-block h-0.5 w-3 rounded-full" style={{ background: l.cor }} aria-hidden="true" />}
            {l.rotulo}
          </span>
          <span className="text-texto font-mono font-semibold">{l.valor}</span>
        </p>
      ))}
    </div>
  );
}

/** Index of the nearest of `n` evenly spaced points; the plot spans fractions `ini`–`fim` of the element's width. */
export function useCursor(n: number, ini = 0, fim = 1) {
  const [i, setI] = useState<number | null>(null);
  const onPointerMove = (e: PointerEvent<Element>) => {
    const r = e.currentTarget.getBoundingClientRect();
    const f = ((e.clientX - r.left) / r.width - ini) / (fim - ini);
    setI(Math.max(0, Math.min(n - 1, Math.round(f * (n - 1)))));
  };
  const onKeyDown = (e: KeyboardEvent) => {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    e.preventDefault();
    setI((v) => (e.key === "ArrowRight" ? Math.min(n - 1, (v ?? -1) + 1) : Math.max(0, (v ?? n) - 1)));
  };
  return { i, props: { onPointerMove, onPointerLeave: () => setI(null), onKeyDown, onBlur: () => setI(null), tabIndex: 0 } };
}

export const ddmm = (iso: string) => `${iso.slice(8, 10)}/${iso.slice(5, 7)}`;
const SEMANA = ["dom", "seg", "ter", "qua", "qui", "sex", "sáb"];
export const diaSemana = (iso: string) => SEMANA[new Date(`${iso}T00:00:00Z`).getUTCDay()];
