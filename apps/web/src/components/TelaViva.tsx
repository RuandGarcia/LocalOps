import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";

export type Destaque = { alvo: string; titulo: string; texto: string };

const LARGURA = 1280; // the real page renders at desktop width and is scaled into the frame

/**
 * A live app screen inside the booth presentation: the real page, scaled into a browser frame,
 * panned to the section of the active highlight with a ring around it. Decorative and inert.
 */
export function TelaViva({ rotulo, destaques, ativo, children }: { rotulo: string; destaques: Destaque[]; ativo: number; children: ReactNode }) {
  const moldura = useRef<HTMLDivElement>(null);
  const escala = useRef<HTMLDivElement>(null);
  const [s, setS] = useState(0.5);
  const [y, setY] = useState(0);
  const [anel, setAnel] = useState<{ x: number; y: number; w: number; h: number } | null>(null);

  useLayoutEffect(() => {
    const m = moldura.current!;
    m.setAttribute("inert", "");
    const ro = new ResizeObserver(() => setS(m.clientWidth / LARGURA));
    ro.observe(m);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    // Wait for the scene entrance and the page's own entrance before measuring.
    const t = setTimeout(() => {
      const m = moldura.current;
      const e = escala.current;
      const seletor = destaques[ativo]?.alvo;
      const alvo = seletor ? e?.querySelector(seletor) : null; // the opening scene has no highlights
      if (!m || !e || !alvo) return setAnel(null);
      const caixa = alvo.closest("section, .painel, form") ?? alvo;
      const base = e.getBoundingClientRect();
      const r = caixa.getBoundingClientRect();
      const ox = (r.left - base.left) / s;
      const oy = (r.top - base.top) / s;
      const max = Math.max(0, e.offsetHeight - m.clientHeight / s);
      const novoY = Math.min(max, Math.max(0, oy - 28));
      setY(novoY);
      setAnel({ x: ox - 8, y: oy - novoY - 8, w: r.width / s + 16, h: r.height / s + 16 });
    }, ativo === 0 ? 1100 : 60);
    return () => clearTimeout(t);
  }, [ativo, s, destaques]);

  return (
    <div className="moldura-tela w-full overflow-hidden rounded-2xl" aria-hidden="true">
      <div className="border-borda flex items-center gap-2 border-b bg-[#0d0e11] px-4 py-2.5">
        <span className="size-2.5 rounded-full bg-white/15" />
        <span className="size-2.5 rounded-full bg-white/15" />
        <span className="size-2.5 rounded-full bg-white/15" />
        <span className="text-faint ml-3 font-mono text-[12px]">localops / {rotulo}</span>
      </div>
      <div ref={moldura} className="relative aspect-[16/10] overflow-hidden" onScroll={(e) => (e.currentTarget.scrollTop = 0)}>
        <div
          ref={escala}
          className="pointer-events-none absolute top-0 left-0 transition-transform duration-[1100ms] ease-[cubic-bezier(0.16,1,0.3,1)]"
          style={{ width: LARGURA, transform: `scale(${s}) translateY(${-y}px)`, transformOrigin: "0 0" }}
        >
          {children}
        </div>
        {anel && (
          <div
            className="anel-destaque absolute rounded-xl transition-all duration-[1100ms] ease-[cubic-bezier(0.16,1,0.3,1)]"
            style={{ left: anel.x * s, top: anel.y * s, width: anel.w * s, height: anel.h * s }}
          >
            <span className="orbe-agente absolute -top-3 -left-3 flex size-7 items-center justify-center rounded-full text-[13px] font-semibold text-[#08090B]">
              {ativo + 1}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
