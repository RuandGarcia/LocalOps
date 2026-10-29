import { useMemo, useState } from "react";
import { useFiltro } from "../data/filtros";
import { ROTULO_DIM_T, ROTULO_METRICA, tendencias, type DimTendencia, type Metrica, type Tendencia } from "../data/tendencias";
import { Delta } from "../components/insights";
import { Segmentado, TituloPagina, fmt, ordem } from "../components/ui";
import { Dica, ddmm, useCursor } from "../components/Dica";

const COR: Record<Tendencia["estado"], { linha: string; area: string; chip: string; rotulo: string }> = {
  subindo: { linha: "#FBBF24", area: "rgb(251 191 36 / 0.16)", chip: "text-amber-300 border-amber-400/30 bg-amber-400/10", rotulo: "Subindo" },
  estavel: { linha: "#A5B4FC", area: "rgb(129 140 248 / 0.12)", chip: "text-agente border-indigo-400/30 bg-indigo-400/10", rotulo: "Estável" },
  caindo: { linha: "#34D399", area: "rgb(52 211 153 / 0.12)", chip: "text-ok border-emerald-400/30 bg-emerald-400/10", rotulo: "Caindo" },
};

function Faisca({ serie, estado, semanas, rotulo }: { serie: number[]; estado: Tendencia["estado"]; semanas: string[]; rotulo: string }) {
  const L = 220;
  const A = 56;
  const max = Math.max(1, ...serie);
  const x = (i: number) => (i / Math.max(1, serie.length - 1)) * L;
  const y = (v: number) => A - 4 - (v / max) * (A - 8);
  const d = serie.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const c = COR[estado];
  const { i, props } = useCursor(serie.length);
  return (
    <div className="relative">
      <svg viewBox={`0 0 ${L} ${A}`} className="h-14 w-full cursor-crosshair outline-none" preserveAspectRatio="none" role="img" aria-label={`${rotulo} por semana; use as setas para ler cada semana.`} {...props}>
        <path d={`${d} L${L},${A} L0,${A} Z`} fill={c.area} />
        <path d={d} fill="none" stroke={c.linha} strokeWidth="2" vectorEffect="non-scaling-stroke" />
        <circle cx={x(serie.length - 1)} cy={y(serie[serie.length - 1])} r="3" fill={c.linha} />
        {i !== null && <line x1={x(i)} x2={x(i)} y1="0" y2={A} stroke="#8B909A" strokeDasharray="2 3" vectorEffect="non-scaling-stroke" />}
      </svg>
      {i !== null && (
        <Dica x={x(i) / L} topo={-8} titulo={`semana de ${ddmm(semanas[i] ?? "")}`} linhas={[{ rotulo, valor: fmt.format(serie[i]), cor: c.linha }]} />
      )}
    </div>
  );
}

export default function Tendencias() {
  const { filtro } = useFiltro();
  const [dim, setDim] = useState<DimTendencia>("produtos");
  const [metrica, setMetrica] = useState<Metrica>("h");
  const [todos, setTodos] = useState(false);
  const t = useMemo(() => tendencias(filtro, dim, metrica), [filtro, dim, metrica]);
  const altas = t.itens.filter((i) => i.estado === "subindo").slice(0, 3);
  const visiveis = todos ? t.itens : t.itens.slice(0, 12);
  const ini = t.semanas[0]?.split("-").reverse().slice(0, 2).join("/");
  const fim = t.semanas[t.semanas.length - 1]?.split("-").reverse().slice(0, 2).join("/");

  return (
    <main className="px-4 py-6 sm:px-8 sm:py-8">
      <div className="mx-auto flex max-w-[1240px] flex-col gap-5">
        <TituloPagina titulo="Tendências">
          <div className="flex flex-wrap gap-2">
            <Segmentado rotulo="Dimensão" opcoes={["produtos", "categorias", "cis"] as const} valor={dim} aoMudar={setDim} formatar={(d) => ROTULO_DIM_T[d]} />
            <Segmentado rotulo="Métrica" opcoes={["h", "e", "o"] as const} valor={metrica} aoMudar={setMetrica} formatar={(m) => ROTULO_METRICA[m]} />
          </div>
        </TituloPagina>
        <p className="text-muted -mt-2 text-[13px]">
          Base real 2025 · 12 semanas, de {ini} a {fim} · ordenado pela inclinação da reta.
          {dim === "cis" && " Itens de configuração: os 30 que mais exigiram gente no ano."}
          {dim === "cis" && metrica === "e" && " Para itens, a métrica de KPI usa os alarmes que exigiram gente."}
        </p>

        <section aria-labelledby="altas-titulo" className="painel anel-agente entra flex flex-col gap-3 p-6" style={ordem(1)} data-visto="false">
          <h2 id="altas-titulo" className="text-[15px] font-semibold">
            O que está subindo
          </h2>
          {altas.length ? (
            <ul className="grid gap-3 md:grid-cols-3">
              {altas.map((a) => (
                <li key={a.chave} className="bg-superficie-2 border-borda flex flex-col gap-1 rounded-xl border p-4">
                  <p className="font-mono text-[15px] font-semibold">{a.chave}</p>
                  <p className="text-[13px]">
                    {fmt.format(a.ultimas4)} nas últimas 4 semanas <Delta v={a.delta} />
                  </p>
                  <p className="text-muted text-[12px]">
                    +{a.inclinacao.toLocaleString("pt-BR", { maximumFractionDigits: 1 })} por semana em {ROTULO_METRICA[t.metricaUsada].toLowerCase()}
                  </p>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-muted text-[14px]">Nada subindo de forma consistente nestas 12 semanas com estes filtros.</p>
          )}
        </section>

        <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {visiveis.map((i, k) => (
            <li key={i.chave} className="painel entra flex flex-col gap-2 p-4" style={ordem(Math.min(k + 2, 8))}>
              <div className="flex items-center justify-between gap-2">
                <p className="truncate font-mono text-[14px] font-semibold">{i.chave}</p>
                <span className={`${COR[i.estado].chip} rounded-full border px-2 py-0.5 text-[11px] font-medium`}>{COR[i.estado].rotulo}</span>
              </div>
              <Faisca serie={i.serie} estado={i.estado} semanas={t.semanas} rotulo={ROTULO_METRICA[t.metricaUsada]} />
              <div className="text-muted flex items-baseline justify-between gap-2 text-[12px]">
                <span>
                  <span className="text-texto font-semibold">{fmt.format(i.ultimas4)}</span> últimas 4 sem.
                </span>
                <Delta v={i.delta} />
              </div>
            </li>
          ))}
          {t.itens.length === 0 && <li className="text-muted text-[14px]">Sem dados para estes filtros.</li>}
        </ul>
        {t.itens.length > 12 && (
          <button type="button" onClick={() => setTodos((v) => !v)} className="text-agente self-center text-[13px] hover:underline">
            {todos ? "Mostrar só os 12 principais" : `Ver todos os ${t.itens.length}`}
          </button>
        )}
      </div>
    </main>
  );
}
