import { useMemo } from "react";
import qrcode from "qrcode-generator";

/** Public panel address: wherever this build is served; printed on the booth QR code. */
export const SITE = window.location.origin;

/** QR code drawn as SVG, generated in the browser so it works offline at the booth. */
export function QrCode({ texto = SITE, tamanho = 160 }: { texto?: string; tamanho?: number }) {
  const { n, d } = useMemo(() => {
    const q = qrcode(0, "M");
    q.addData(texto);
    q.make();
    const n = q.getModuleCount();
    let d = "";
    for (let r = 0; r < n; r++) for (let c = 0; c < n; c++) if (q.isDark(r, c)) d += `M${c} ${r}h1v1h-1z`;
    return { n, d };
  }, [texto]);
  // Dark on white with a quiet zone: phone cameras read it reliably on the dark booth screen.
  return (
    <svg viewBox={`-2 -2 ${n + 4} ${n + 4}`} width={tamanho} height={tamanho} role="img" aria-label={`QR code para ${texto}`} className="rounded-lg bg-white">
      <path d={d} fill="#08090b" shapeRendering="crispEdges" />
    </svg>
  );
}
