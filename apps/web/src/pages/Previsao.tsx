import { useState } from "react";
import { NOME_MODELO, SERIES, contexto, janela, type Horizonte, type Serie } from "../data/previsao";
import { useFiltro } from "../data/filtros";
import { Segmentado, TituloPagina, fmt, ordem } from "../components/ui";
import { ConfiancaModelo, MapaCalor, SerieDiaria } from "../components/insights";
import { Dica, diaSemana, useCursor } from "../components/Dica";

const LARG = 760;
const ALT = 260;
const M = { t: 16, r: 16, b: 28, l: 44 };

type Ponto = ReturnType<typeof janela>["pontos"][number];

function Grafico({ dados, rotulo }: { dados: Ponto[]; rotulo: string }) {
  const max = Math.max(...dados.map((d) => Math.max(d.sup, d.real ?? 0))) * 1.08;
  const min = Math.min(...dados.map((d) => Math.min(d.inf, d.real ?? Infinity))) * 0.9;
  const x = (i: number) => M.l + (i / (dados.length - 1)) * (LARG - M.l - M.r);
  const y = (v: number) => M.t + (1 - (v - min) / (max - min)) * (ALT - M.t - M.b);
  const linha = (vals: (number | null)[]) =>
    vals
      .map((v, i) => (v === null ? null : `${x(i)},${y(v)}`))
      .filter(Boolean)
      .join(" ");
  const banda = [...dados.map((d, i) => `${x(i)},${y(d.sup)}`), ...dados.map((d, i) => `${x(i)},${y(d.inf)}`).reverse()].join(" ");
  const ticks = [0, 0.5, 1].map((f) => Math.round(min + f * (max - min)));
  const ultimo = dados[dados.length - 1];
  const { i, props } = useCursor(dados.length, M.l / LARG, (LARG - M.r) / LARG);
  const sel = i === null ? null : dados[i];

  return (
    <div className="relative">
    <svg viewBox={`0 0 ${LARG} ${ALT}`} className="h-auto w-full cursor-crosshair outline-none" role="img" aria-label={`${rotulo} contra o observado nos últimos 14 dias, com intervalo de 80%. Use as setas para ler cada dia.`} {...props}>
      <defs>
        <linearGradient id="banda" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#818CF8" stopOpacity="0.28" />
          <stop offset="1" stopColor="#22D3EE" stopOpacity="0.06" />
        </linearGradient>
      </defs>
      {ticks.map((t) => (
        <g key={t}>
          <line x1={M.l} x2={LARG - M.r} y1={y(t)} y2={y(t)} stroke="#25272D" />
          <text x={M.l - 8} y={y(t) + 4} textAnchor="end" fontSize="11" fill="#8B909A">
            {fmt.format(t)}
          </text>
        </g>
      ))}
      <polygon points={banda} fill="url(#banda)" />
      <polyline points={linha(dados.map((d) => d.previsto))} fill="none" stroke="#A5B4FC" strokeWidth="2" strokeDasharray="5 4" />
      <polyline points={linha(dados.map((d) => d.real))} fill="none" stroke="#EDEEF0" strokeWidth="2" />
      {dados.map((d, i) => (
        <text key={d.alvo} x={x(i)} y={ALT - 8} textAnchor="middle" fontSize="10" fill="#8B909A">
          {i % 2 === 0 ? d.dia : ""}
        </text>
      ))}
      <circle cx={x(dados.length - 1)} cy={y(ultimo.previsto)} r="5" fill="#A5B4FC" style={{ filter: "drop-shadow(0 0 8px rgb(129 140 248 / 0.8))" }} />
      {sel && i !== null && (
        <g pointerEvents="none">
          <line x1={x(i)} x2={x(i)} y1={M.t} y2={ALT - M.b} stroke="#8B909A" strokeDasharray="2 3" />
          <circle cx={x(i)} cy={y(sel.previsto)} r="4" fill="#A5B4FC" stroke="#101114" strokeWidth="2" />
          {sel.real !== null && <circle cx={x(i)} cy={y(sel.real)} r="4" fill="#EDEEF0" stroke="#101114" strokeWidth="2" />}
        </g>
      )}
    </svg>
    {sel && i !== null && (
      <Dica
        x={x(i) / LARG}
        topo={8}
        titulo={`${diaSemana(sel.alvo)}, ${sel.dia}`}
        linhas={[
          { rotulo: "Previsto", valor: fmt.format(sel.previsto), cor: "#A5B4FC" },
          { rotulo: "Faixa de 80%", valor: `${fmt.format(sel.inf)}–${fmt.format(sel.sup)}` },
          { rotulo: "Observado", valor: sel.real === null ? "ainda não aconteceu" : fmt.format(sel.real), cor: "#EDEEF0" },
          ...(sel.real !== null ? [{ rotulo: "Erro", valor: `${sel.real >= sel.previsto ? "+" : "−"}${Math.abs(Math.round((sel.real / sel.previsto - 1) * 100))}%` }] : []),
        ]}
      />
    )}
    </div>
  );
}

export default function Previsao() {
  const [serie, setSerie] = useState<Serie>("Total");
  const [horizonte, setHorizonte] = useState<Horizonte>("D+1");
  const { filtro } = useFiltro();
  const j = janela(serie, horizonte, filtro.ref);
  const ultimo = j.pontos[j.pontos.length - 1];
  const ctx = contexto(serie, j.ref, ultimo.alvo);
  const m = j.metrica;
  const pc = (v: number) => `${(v * 100).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`;
  const um = (v: number) => v.toLocaleString("pt-BR", { maximumFractionDigits: 1 });
  const fatores: [string, string][] = [
    ["Média dos últimos 7 dias", um(ctx.media7)],
    ["Média dos últimos 28 dias", um(ctx.media28)],
    [`Mesmo dia da semana anterior (${ctx.diaMesmoDia})`, ctx.mesmoDia === null ? "ainda não aconteceu" : fmt.format(ctx.mesmoDia)],
    ["Modelo escolhido em out–nov", NOME_MODELO[m.modelo_escolhido] ?? m.modelo_escolhido],
    ["Erro em dez/2025 (WAPE)", `${pc(m.wape_teste_escolhido)} · regra simples ${pc(m.wape_teste_baseline)}`],
    ["Faixa de 80% acertou em dez", pc(m.intervalo.cobertura_teste)],
  ];

  return (
    <main className="px-4 py-6 sm:px-8 sm:py-8">
      <div className="mx-auto flex max-w-[1240px] flex-col gap-5">
        <TituloPagina titulo="Previsão e replay">
          <div className="flex flex-wrap gap-2">
            <Segmentado rotulo="Série" opcoes={SERIES} valor={serie} aoMudar={setSerie} />
            <Segmentado rotulo="Horizonte" opcoes={["D+1", "D+7"] as const} valor={horizonte} aoMudar={setHorizonte} />
          </div>
        </TituloPagina>

        <SerieDiaria n={1} />

        <div className="grid gap-5 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)] [&>*]:min-w-0">
          <section aria-labelledby="prev-titulo" className="painel entra flex flex-col gap-4 p-6" style={ordem(1)}>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h2 id="prev-titulo" className="text-[15px] font-semibold">
                {serie} · {horizonte} contra o observado
              </h2>
              <span className="text-muted text-[12px]">feita em {j.ref.split("-").reverse().join("/")}</span>
            </div>
            <div className="flex flex-wrap items-end gap-x-4 gap-y-1">
              <p className="numero-brilho text-[44px] leading-none font-semibold tracking-[-0.04em]">{fmt.format(ultimo.previsto)}</p>
              <p className="text-muted pb-1 text-[13px]">
                previsto para {ultimo.dia} · intervalo de 80%: {fmt.format(ultimo.inf)}–{fmt.format(ultimo.sup)}
              </p>
            </div>
            <Grafico dados={j.pontos} rotulo={`Previsão ${horizonte} de ${serie}`} />
            <p className="text-muted flex flex-wrap gap-x-5 gap-y-1 text-[12px]">
              <span className="flex items-center gap-2">
                <span className="bg-texto inline-block h-0.5 w-5" aria-hidden="true" /> observado
              </span>
              <span className="flex items-center gap-2">
                <span className="border-agente inline-block w-5 border-t-2 border-dashed" aria-hidden="true" /> previsto
              </span>
              <span className="flex items-center gap-2">
                <span className="inline-block h-2.5 w-5 rounded-sm bg-indigo-400/25" aria-hidden="true" /> intervalo de 80%
              </span>
            </p>
            {j.ajustado && (
              <p className="text-muted text-[12px]">
                O replay da previsão vai de {j.primeira.split("-").reverse().join("/")} a {j.ultima.split("-").reverse().join("/")}; mostrando o dia mais próximo do escolhido no filtro.
              </p>
            )}
          </section>

          <section aria-labelledby="pq-titulo" className="painel entra flex flex-col gap-4 p-6" style={ordem(2)}>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h2 id="pq-titulo" className="text-[15px] font-semibold">
                Por que esse número
              </h2>
            </div>
            <dl className="flex flex-col gap-3 text-[13px]">
              {fatores.map(([rot, val]) => (
                <div key={rot} className="border-borda flex items-baseline justify-between gap-3 border-b pb-2 last:border-b-0">
                  <dt className="text-muted">{rot}</dt>
                  <dd className={(rot.startsWith("Erro") && !m.bate_baseline_no_teste ? "text-amber-300 " : "") + "text-right font-mono"}>{val}</dd>
                </div>
              ))}
            </dl>
            <p className="text-muted mt-auto text-[12px]">
              {m.bate_baseline_no_teste ? "Nesta série e horizonte o modelo bate a regra simples." : "Aqui o modelo não bate a regra simples; use a faixa, não o ponto."}
            </p>
          </section>
        </div>

        <div className="grid gap-5 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)] [&>*]:min-w-0">
          <MapaCalor n={3} />
          <ConfiancaModelo n={4} />
        </div>
      </div>
    </main>
  );
}
