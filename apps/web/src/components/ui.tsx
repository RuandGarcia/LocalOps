import type { CSSProperties, ReactNode } from "react";

export const fmt = new Intl.NumberFormat("pt-BR");
export const pct = (p: number) => `${Math.round(p * 100)}%`;
export const ordem = (n: number) => ({ "--ordem": n }) as CSSProperties;

export function Ilustrativo() {
  return (
    <span className="text-muted border-borda rounded-full border px-2 py-0.5 text-[11px] whitespace-nowrap">dados ilustrativos</span>
  );
}

export function TituloPagina({ titulo, children }: { titulo: string; children?: ReactNode }) {
  return (
    <div className="entra flex flex-wrap items-end justify-between gap-3" style={ordem(0)}>
      <h1 className="text-[30px] leading-tight font-semibold tracking-[-0.03em]">{titulo}</h1>
      {children}
    </div>
  );
}

export function Segmentado<T extends string | number>({
  rotulo,
  opcoes,
  valor,
  aoMudar,
  formatar = (v) => String(v),
}: {
  rotulo: string;
  opcoes: readonly T[];
  valor: T;
  aoMudar: (v: T) => void;
  formatar?: (v: T) => string;
}) {
  return (
    <div role="radiogroup" aria-label={rotulo} className="bg-fundo border-borda inline-flex rounded-lg border p-0.5">
      {opcoes.map((o) => (
        <button
          key={String(o)}
          type="button"
          role="radio"
          aria-checked={valor === o}
          onClick={() => aoMudar(o)}
          className={
            (valor === o ? "bg-superficie-2 text-texto shadow-[inset_0_1px_0_rgb(255_255_255/0.06)] " : "text-muted hover:text-texto ") +
            "min-h-8 rounded-md px-3 text-[13px] font-medium whitespace-nowrap transition-colors"
          }
        >
          {formatar(o)}
        </button>
      ))}
    </div>
  );
}

export function ChanceGente({ p }: { p: number }) {
  const cor = p >= 0.5 ? "bg-amber-400" : p >= 0.2 ? "bg-amber-400/60" : "bg-faint/60";
  return (
    <span className="flex items-center gap-2">
      <span className="bg-fundo border-borda h-1.5 w-16 overflow-hidden rounded-full border" aria-hidden="true">
        <span className={`${cor} block h-full rounded-full`} style={{ width: pct(p) }} />
      </span>
      <span className="font-mono text-[12px]">{pct(p)}</span>
    </span>
  );
}
