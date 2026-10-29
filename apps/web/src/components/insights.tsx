import { ArrowDownRight, ArrowUpRight } from "lucide-react";
import { ANTERIOR, ROTULO_DIM, semClasse, useDados, useFiltro, variacao, type Dimensao, type Ranking } from "../data/filtros";
import { fmt, ordem } from "./ui";
import { CONFIANCA, FILA_METRICAS } from "../data/previsao";
import { useState } from "react";
import { Dica, ddmm, diaSemana, useCursor } from "./Dica";

const pct1 = (x: number) => `${(x * 100).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`;

export function Delta({ v, inverter = false, pp = false }: { v: number | null; inverter?: boolean; pp?: boolean }) {
  if (v === null || !Number.isFinite(v)) return <span className="text-faint text-[12px]">sem base</span>;
  if (Math.abs(v) < 0.0005) return <span className="text-muted text-[12px] font-medium">estável</span>;
  const sobe = v > 0;
  const ruim = inverter ? !sobe : sobe;
  const Icone = sobe ? ArrowUpRight : ArrowDownRight;
  return (
    <span className={(Math.abs(v) < 0.005 ? "text-muted" : ruim ? "text-amber-300" : "text-ok") + " inline-flex items-center gap-0.5 text-[12px] font-medium"}>
      <Icone size={13} aria-hidden="true" />
      {sobe ? "+" : "−"}
      {pp ? `${(Math.abs(v) * 100).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} p.p.` : pct1(Math.abs(v))}
    </span>
  );
}

/** Real totals for the filtered period with the change against the previous period. */
export function ResumoPeriodo({ n = 0 }: { n?: number }) {
  const d = useDados();
  const { filtro } = useFiltro();
  const ruido = d.tot.n ? 1 - d.tot.h / d.tot.n : 0;
  const ruidoAnt = d.ant?.n ? 1 - d.ant.h / d.ant.n : null;
  const itens = [
    { rotulo: "Alarmes", valor: fmt.format(d.tot.n), delta: variacao(d.tot.n, d.ant?.n) },
    { rotulo: "Exigiram gente", valor: fmt.format(d.tot.h), delta: variacao(d.tot.h, d.ant?.h), destaque: true },
    { rotulo: "Fecharam sozinhos", valor: pct1(ruido), delta: ruidoAnt === null ? null : ruido - ruidoAnt, inverter: true, pp: true },
    { rotulo: "Violações de OLA", valor: fmt.format(d.tot.o), delta: variacao(d.tot.o, d.ant?.o), risco: true },
  ];
  return (
    <section aria-label="Resumo do período" className="painel entra grid grid-cols-2 lg:grid-cols-4" style={ordem(n)}>
      {itens.map((i, k) => (
        <div key={i.rotulo} className={(k > 0 ? "lg:border-l " : "") + (k % 2 ? "border-l " : "") + (k > 1 ? "border-t lg:border-t-0 " : "") + "border-borda flex flex-col gap-1 px-5 py-4"}>
          <p className="text-muted text-[12px]">{i.rotulo}</p>
          <p className={(i.destaque ? "text-amber-300 " : i.risco ? "text-risco " : "") + "text-[26px] leading-none font-semibold tracking-[-0.03em]"}>{i.valor}</p>
          <p className="text-faint flex flex-wrap items-center gap-1.5 text-[12px]">
            <Delta v={i.delta} inverter={i.inverter} pp={i.pp} /> vs {ANTERIOR[filtro.gran]}
          </p>
        </div>
      ))}
    </section>
  );
}

export function RankingLista({ titulo, itens: todos, limite = 5 }: { titulo: string; itens: Ranking; limite?: number }) {
  const itens = todos.filter((r) => !semClasse(r.chave));
  const fora = todos.filter((r) => semClasse(r.chave)).reduce((s, r) => s + r.h, 0);
  const max = itens[0]?.h || 1;
  return (
    <div className="flex flex-col gap-3">
      <h3 className="text-muted text-[12px] font-medium">{titulo}</h3>
      <ol className="flex flex-col gap-2.5">
        {itens.slice(0, limite).map((r) => (
          <li key={r.chave} className="flex flex-col gap-1">
            <div className="flex items-baseline justify-between gap-2 text-[13px]">
              <span className="truncate font-mono">{r.chave}</span>
              <span className="flex items-baseline gap-2">
                <span className="font-semibold">{fmt.format(r.h)}</span>
                <Delta v={r.delta} />
              </span>
            </div>
            <span className="bg-fundo h-1 overflow-hidden rounded-full" aria-hidden="true">
              <span className="block h-full rounded-full bg-indigo-300/80" style={{ width: `${(r.h / max) * 100}%` }} />
            </span>
          </li>
        ))}
        {itens.length === 0 && <li className="text-muted text-[13px]">Sem alarmes com esses filtros.</li>}
      </ol>
      {fora > 0 && <p className="text-faint text-[12px]">+ {fmt.format(fora)} sem classificação</p>}
    </div>
  );
}

/** Where to act: who generates human work, and what grew against the previous period. */
export function OndeAgir({ n = 0 }: { n?: number }) {
  const d = useDados();
  const dims: Dimensao[] = ["produtos", "equipes", "categorias"];
  const altas = dims
    .flatMap((dim) => d.rank(dim).filter((r) => !semClasse(r.chave) && r.delta !== null && r.delta > 0 && r.hAnt >= 10 && r.h >= 20).map((r) => ({ ...r, dim })))
    .sort((a, b) => (b.delta ?? 0) * Math.sqrt(b.h) - (a.delta ?? 0) * Math.sqrt(a.h))
    .slice(0, 3);
  return (
    <section aria-labelledby="agir-titulo" className="painel entra flex flex-col gap-5 p-6" style={ordem(n)}>
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 id="agir-titulo" className="text-[15px] font-semibold">
          Onde agir · alarmes que exigiram gente
        </h2>
        <p className="text-muted text-[12px]">Base real 2025 · {d.rotulo}</p>
      </div>
      {altas.length > 0 && (
        <ul className="flex flex-col gap-2">
          {altas.map((a) => (
            <li key={a.dim + a.chave} className="bg-superficie-2 border-borda flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border px-3.5 py-2.5 text-[14px]">
              <span className="ponto-humano size-1.5 rounded-full" aria-hidden="true" />
              <span>
                {ROTULO_DIM[a.dim]} <span className="font-mono font-semibold">{a.chave}</span> subiu
              </span>
              <Delta v={a.delta} />
              <span className="text-muted">
                · {fmt.format(a.h)} alarmes, {pct1(a.parte)} do trabalho humano
              </span>
            </li>
          ))}
        </ul>
      )}
      <div className="grid gap-6 md:grid-cols-3">
        <RankingLista titulo="Produtos" itens={d.rank("produtos")} />
        <RankingLista titulo="Equipes" itens={d.rank("equipes")} />
        <RankingLista titulo="Categorias" itens={d.rank("categorias")} />
      </div>
    </section>
  );
}

const DIAS_SEMANA = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"];

export function MapaCalor({ n = 0 }: { n?: number }) {
  const d = useDados();
  const [cel, setCel] = useState<{ dow: number; h: number } | null>(null);
  const max = Math.max(1, ...d.calor.flat());
  let pico = { dow: 0, hora: 0, v: 0 };
  d.calor.forEach((linha, dow) => linha.forEach((v, hora) => v > pico.v && (pico = { dow, hora, v })));
  const meses = d.meses.map((m) => new Date(2025, m - 1, 1).toLocaleString("pt-BR", { month: "short" })).join(", ");
  return (
    <section aria-labelledby="calor-titulo" className="painel entra flex flex-col gap-4 p-6" style={ordem(n)}>
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 id="calor-titulo" className="text-[15px] font-semibold">
          Quando o trabalho humano acontece
        </h2>
        <p className="text-muted text-[12px]">Base real · {meses} de 2025 · sem filtro de dimensão</p>
      </div>
      <p className="text-[14px]">
        Pico em <span className="font-semibold text-amber-300">{DIAS_SEMANA[pico.dow]} às {pico.hora}h</span>
        <span className="text-muted"> com {fmt.format(pico.v)} alarmes que exigiram gente no período.</span>
      </p>
      <div className="relative" onPointerLeave={() => setCel(null)}>
      <div className="overflow-x-auto">
        <div className="grid min-w-[560px] grid-cols-[32px_repeat(24,minmax(0,1fr))] gap-[2px]" role="img" aria-label={`Mapa de calor por dia da semana e hora; pico ${DIAS_SEMANA[pico.dow]} às ${pico.hora}h.`}>
          <span />
          {Array.from({ length: 24 }, (_, h) => (
            <span key={h} className="text-faint text-center text-[10px]">
              {h % 3 === 0 ? h : ""}
            </span>
          ))}
          {d.calor.map((linha, dow) => (
            <div key={dow} className="contents">
              <span className="text-muted pr-1 text-[11px] leading-5">{DIAS_SEMANA[dow]}</span>
              {linha.map((v, h) => (
                <span
                  key={h}
                  onPointerEnter={() => setCel({ dow, h })}
                  className="h-5 rounded-[3px] outline-offset-1"
                  style={{
                    background: `rgb(251 191 36 / ${0.04 + 0.9 * Math.pow(v / max, 0.8)})`,
                    outline: cel?.dow === dow && cel?.h === h ? "2px solid #EDEEF0" : undefined,
                  }}
                />
              ))}
            </div>
          ))}
        </div>
      </div>
        {cel && (
          <Dica
            x={(cel.h + 1.5) / 25}
            topo={22 + cel.dow * 22}
            titulo={`${DIAS_SEMANA[cel.dow]}, ${cel.h}h–${cel.h + 1}h`}
            linhas={[
              { rotulo: "Exigiram gente", valor: fmt.format(d.calor[cel.dow][cel.h]) },
              { rotulo: "Do pico da semana", valor: `${Math.round((d.calor[cel.dow][cel.h] / max) * 100)}%` },
            ]}
          />
        )}
      </div>
    </section>
  );
}

export function SerieDiaria({ n = 0 }: { n?: number }) {
  const d = useDados();
  const max = Math.max(1, ...d.serie.map((s) => s.n));
  const L = 760;
  const A = 180;
  const x = (i: number) => (i / Math.max(1, d.serie.length - 1)) * L;
  const y = (v: number) => A - (v / max) * (A - 8);
  const caminho = (k: "n" | "h") => d.serie.map((s, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(s[k]).toFixed(1)}`).join(" ");
  const iniPeriodo = d.serie.findIndex((s) => s.noPeriodo);
  const { i, props } = useCursor(d.serie.length);
  const sel = i === null ? null : d.serie[i];
  const passo = Math.max(1, Math.ceil(d.serie.length / 7));
  return (
    <section aria-labelledby="serie-titulo" className="painel entra flex flex-col gap-4 p-6" style={ordem(n)}>
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 id="serie-titulo" className="text-[15px] font-semibold">
          Volume real por dia
        </h2>
        <p className="text-muted flex gap-4 text-[12px]">
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-0.5 w-4 bg-indigo-300" aria-hidden="true" /> todos os alarmes
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-0.5 w-4 bg-amber-400" aria-hidden="true" /> exigiram gente
          </span>
        </p>
      </div>
      <div className="relative">
      <svg viewBox={`0 0 ${L} ${A + 18}`} className="h-auto w-full cursor-crosshair outline-none" role="img" aria-label={`Série diária de ${d.serie.length} dias até o fim do período. Use as setas para ler cada dia.`} {...props}>
        {[0.5, 1].map((f) => (
          <g key={f}>
            <line x1="0" x2={L} y1={y(max * f)} y2={y(max * f)} stroke="#25272D" strokeDasharray="2 4" />
            <text x="2" y={y(max * f) - 4} fontSize="10" fill="#8B909A">
              {fmt.format(Math.round(max * f))}
            </text>
          </g>
        ))}
        {iniPeriodo > 0 && <rect x={x(iniPeriodo)} y="0" width={L - x(iniPeriodo)} height={A} fill="rgb(129 140 248 / 0.07)" />}
        <path d={`${caminho("n")} L${L},${A} L0,${A} Z`} fill="rgb(129 140 248 / 0.10)" />
        <path d={caminho("n")} fill="none" stroke="#A5B4FC" strokeWidth="1.75" />
        <path d={caminho("h")} fill="none" stroke="#FBBF24" strokeWidth="2" />
        <line x1="0" x2={L} y1={A} y2={A} stroke="#25272D" />
        {d.serie.map((s, k) =>
          k % passo === 0 || k === d.serie.length - 1 ? (
            <text key={s.dia} x={x(k)} y={A + 14} fontSize="10" fill="#8B909A" textAnchor={k === 0 ? "start" : k === d.serie.length - 1 ? "end" : "middle"}>
              {ddmm(s.dia)}
            </text>
          ) : null,
        )}
        {sel && i !== null && (
          <g pointerEvents="none">
            <line x1={x(i)} x2={x(i)} y1="0" y2={A} stroke="#8B909A" strokeDasharray="2 3" />
            <circle cx={x(i)} cy={y(sel.n)} r="4" fill="#A5B4FC" stroke="#101114" strokeWidth="2" />
            <circle cx={x(i)} cy={y(sel.h)} r="4" fill="#FBBF24" stroke="#101114" strokeWidth="2" />
          </g>
        )}
      </svg>
      {sel && i !== null && (
        <Dica
          x={x(i) / L}
          topo={4}
          titulo={`${diaSemana(sel.dia)}, ${ddmm(sel.dia)}/${sel.dia.slice(0, 4)}`}
          linhas={[
            { rotulo: "Todos os alarmes", valor: fmt.format(sel.n), cor: "#A5B4FC" },
            { rotulo: "Exigiram gente", valor: fmt.format(sel.h), cor: "#FBBF24" },
            { rotulo: "Fecharam sozinhos", valor: sel.n ? `${Math.round((1 - sel.h / sel.n) * 100)}%` : "—" },
            { rotulo: "Violações de OLA", valor: fmt.format(sel.o) },
          ]}
        />
      )}
      </div>
      <p className="text-muted text-[12px]">Faixa destacada: o período selecionado. Fora dela, os dias anteriores para dar contexto.</p>
    </section>
  );
}

export function OlaMensal({ n = 0 }: { n?: number }) {
  const d = useDados();
  const [mes, setMes] = useState<number | null>(null);
  const max = Math.max(1, ...d.olaMes.map((m) => m.total));
  const meses = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
  return (
    <section aria-labelledby="olames-titulo" className="painel entra flex flex-col gap-4 p-6" style={ordem(n)}>
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 id="olames-titulo" className="text-[15px] font-semibold">
          Violações de OLA (KPI) por mês · 2025
        </h2>
        <p className="text-muted text-[12px]">Base real · respeita os filtros de dimensão</p>
      </div>
      <div className="relative">
      <ol className="grid h-44 grid-cols-12 items-end gap-2" onPointerLeave={() => setMes(null)}>
        {d.olaMes.map((m, i) => (
          <li
            key={i}
            tabIndex={0}
            onPointerEnter={() => setMes(i)}
            onFocus={() => setMes(i)}
            onBlur={() => setMes(null)}
            className={(mes !== null && mes !== i ? "opacity-50 " : "") + "flex h-full cursor-default flex-col items-center justify-end gap-1 rounded-md transition-opacity outline-none"}
          >
            <span className="text-muted text-[11px]">{m.total}</span>
            <span className="relative w-full max-w-8 rounded-t-md bg-rose-400/25" style={{ height: `${(m.total / max) * 100}%` }}>
              <span className="bg-risco absolute inset-x-0 bottom-0 rounded-t-md" style={{ height: m.total ? `${(m.p2 / m.total) * 100}%` : 0 }} />
            </span>
            <span className="text-faint text-[11px]">{meses[i]}</span>
          </li>
        ))}
      </ol>
      {mes !== null && (
        <Dica
          x={(mes + 0.5) / 12}
          topo={0}
          titulo={`${meses[mes]}/2025`}
          linhas={[
            { rotulo: "Violações", valor: fmt.format(d.olaMes[mes].total) },
            { rotulo: "P2", valor: fmt.format(d.olaMes[mes].p2), cor: "#FB7185" },
            { rotulo: "P3", valor: fmt.format(d.olaMes[mes].total - d.olaMes[mes].p2), cor: "rgb(251 113 133 / 0.4)" },
          ]}
        />
      )}
      </div>
      <p className="text-muted flex flex-wrap gap-4 text-[12px]">
        <span className="flex items-center gap-1.5">
          <span className="bg-risco inline-block size-2.5 rounded-sm" aria-hidden="true" /> P2
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block size-2.5 rounded-sm bg-rose-400/25" aria-hidden="true" /> P3
        </span>
      </p>
    </section>
  );
}

export function ConfiancaModelo({ n = 0 }: { n?: number }) {
  return (
    <section aria-labelledby="conf-titulo" className="painel entra flex flex-col gap-4 p-6" style={ordem(n)}>
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 id="conf-titulo" className="text-[15px] font-semibold">
          Confiança do modelo
        </h2>
        <p className="text-muted text-[12px]">Erro médio (WAPE) · menor é melhor</p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[420px] border-collapse text-left text-[13px]">
          <thead className="text-muted border-borda border-b text-[12px]">
            <tr>
              <th className="py-2 pr-3 font-medium">Série</th>
              <th className="px-3 py-2 font-medium">D+1 · modelo / ingênuo</th>
              <th className="px-3 py-2 font-medium">D+7 · modelo / ingênuo</th>
            </tr>
          </thead>
          <tbody>
            {CONFIANCA.map((c) => (
              <tr key={c.serie} className="border-borda border-b last:border-b-0">
                <td className="py-2.5 pr-3 font-medium">{c.serie}</td>
                {[c.h1, c.h7].map((h, i) => (
                  <td key={i} className="px-3 py-2.5 font-mono">
                    <span className={h.modelo < h.base ? "text-ok" : "text-amber-300"}>{h.modelo.toLocaleString("pt-BR")}%</span>
                    <span className="text-faint"> / {h.base.toLocaleString("pt-BR")}%</span>
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ul className="text-muted flex flex-col gap-1 text-[12px]">
        <li>
          Walk-forward diário: modelo escolhido em out–nov/2025, erro medido em dez/2025 (31 previsões por série). Âmbar é onde o
          modelo não bate a regra simples.
        </li>
        <li>
          Filtro de ruído: AUC {FILA_METRICAS.auc_roc_teste.toLocaleString("pt-BR")} em dez/2025; mantém{" "}
          {(FILA_METRICAS.recall_teste * 100).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}% dos alarmes que exigiram gente
          (meta de 97%).
        </li>
      </ul>
    </section>
  );
}
