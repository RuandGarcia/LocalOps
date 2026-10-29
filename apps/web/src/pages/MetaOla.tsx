import { OLA_RISCO } from "../data/cockpit";
import { ChanceGente, Ilustrativo, Segmentado, TituloPagina, fmt, ordem } from "../components/ui";
import { OlaMensal } from "../components/insights";
import { BASE, diaIdx, useDados, useFiltro } from "../data/filtros";
import { faixaDe, ondeAgirMeta, projetar, teto100, type Kpi, type Pri, type Projecao } from "../data/meta";
import { useState } from "react";
import { Dica } from "../components/Dica";

const dataCurta = (iso: string) => iso.split("-").reverse().slice(0, 2).join("/");
const pct0 = (p: number) => `${Math.round(p * 100)}%`;
const ROTULO_KPI: Record<Kpi, string> = { violacoes: "Violações de OLA", volume: "Volume tratado" };
const CORTE_BACKTEST = "2025-09-30";

function CartaoProjecao({ p, n }: { p: Projecao; n: number }) {
  const bom = ["150%", "125%", "100%"].includes(p.faixaProvavel.rotulo);
  const faixaReal = faixaDe(p.kpi, p.pri, p.real);
  const maxP = Math.max(...p.prob.map((x) => x.p), 0.01);
  const [sel, setSel] = useState<number | null>(null);
  return (
    <section aria-label={`${ROTULO_KPI[p.kpi]} ${p.pri}`} className="painel entra flex flex-col gap-4 p-6" style={ordem(n)}>
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 className="text-[15px] font-semibold">
          {ROTULO_KPI[p.kpi]} · {p.pri}
        </h2>
        <p className="text-muted text-[12px]">
          {fmt.format(p.ateHoje)} até hoje · ritmo de {p.ritmoSemana.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}/semana
        </p>
      </div>
      <div className="flex flex-wrap items-end gap-x-4 gap-y-1">
        <p className={(bom ? "text-ok" : "text-risco") + " text-[40px] leading-none font-semibold tracking-[-0.04em]"}>
          {fmt.format(p.baixo)}–{fmt.format(p.alto)}
        </p>
        <p className="text-muted pb-1 text-[13px]">
          projeção para 31/12 (80%) · faixa mais provável <span className={(bom ? "text-ok" : "text-risco") + " font-semibold"}>{p.faixaProvavel.rotulo}</span>
        </p>
      </div>
      <div className="relative">
      <ol className="grid grid-cols-6 gap-1" aria-label="Probabilidade de terminar em cada faixa" onPointerLeave={() => setSel(null)}>
        {p.prob.map(({ faixa, p: prob }, k) => {
          const provavel = faixa.rotulo === p.faixaProvavel.rotulo;
          const boaFaixa = ["150%", "125%", "100%"].includes(faixa.rotulo);
          return (
            <li
              key={faixa.rotulo}
              tabIndex={0}
              onPointerEnter={() => setSel(k)}
              onFocus={() => setSel(k)}
              onBlur={() => setSel(null)}
              className={(sel !== null && sel !== k ? "opacity-50 " : "") + "flex cursor-default flex-col items-center gap-1.5 transition-opacity outline-none"}
            >
              <div className="bg-fundo border-borda flex h-16 w-full items-end overflow-hidden rounded-md border">
                <span
                  className={(boaFaixa ? "bg-emerald-400" : "bg-rose-400") + (provavel ? "" : " opacity-45") + " block w-full transition-all duration-500"}
                  style={{ height: `${(prob / maxP) * 100}%` }}
                />
              </div>
              <span className={(provavel ? "text-texto font-semibold" : "text-muted") + " text-[12px]"}>{faixa.rotulo}</span>
              <span className="text-faint font-mono text-[11px]">{pct0(prob)}</span>
            </li>
          );
        })}
      </ol>
      {sel !== null && (
        <Dica
          x={(sel + 0.5) / 6}
          topo={-12}
          titulo={`Faixa ${p.prob[sel].faixa.rotulo} da meta`}
          linhas={[
            {
              rotulo: p.kpi === "violacoes" ? "Violações no ano" : "Volume no ano",
              valor: p.prob[sel].faixa.max === Infinity ? `${fmt.format(p.prob[sel].faixa.min)} ou mais` : `${fmt.format(p.prob[sel].faixa.min)}–${fmt.format(p.prob[sel].faixa.max)}`,
            },
            { rotulo: "Chance de terminar aqui", valor: pct0(p.prob[sel].p) },
          ]}
        />
      )}
      </div>
      <p className="text-muted border-borda border-t pt-3 text-[12px]">
        Real em 31/12/2025: <span className="text-texto font-semibold">{fmt.format(p.real)}</span> (faixa {faixaReal.rotulo}).{" "}
        {p.real >= p.baixo && p.real <= p.alto ? "Dentro da projeção." : "Fora da faixa de 80% da projeção."}
      </p>
    </section>
  );
}

function ComoChegar({ hoje, n }: { hoje: number; n: number }) {
  const [pri, setPri] = useState<Pri>("P2");
  const p = projetar("violacoes", pri, hoje);
  const teto = teto100("violacoes", pri);
  const folga = teto - p.ateHoje;
  const semanas = Math.max(1, p.restantes / 7);
  const ritmoMax = Math.max(0, folga) / semanas;
  const a = ondeAgirMeta(hoje, pri);
  return (
    <section aria-labelledby="chegar-titulo" className="painel anel-agente entra flex flex-col gap-5 p-6" style={ordem(n)} data-visto="false">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id="chegar-titulo" className="text-[15px] font-semibold">
          Como chegar à faixa de 100%
        </h2>
        <Segmentado rotulo="Prioridade" opcoes={["P2", "P3"] as const} valor={pri} aoMudar={setPri} />
      </div>
      <div className="grid gap-4 md:grid-cols-3">
        <div className="bg-superficie-2 border-borda flex flex-col gap-1 rounded-xl border p-4">
          <p className="text-muted text-[12px]">Folga até o teto de {teto}</p>
          <p className={(folga > 0 ? "text-texto" : "text-risco") + " text-[28px] leading-none font-semibold"}>{folga > 0 ? folga : "estourou"}</p>
          <p className="text-muted text-[12px]">violações restantes no ano</p>
        </div>
        <div className="bg-superficie-2 border-borda flex flex-col gap-1 rounded-xl border p-4">
          <p className="text-muted text-[12px]">Ritmo máximo para chegar</p>
          <p className="text-[28px] leading-none font-semibold text-amber-300">{ritmoMax.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}/sem</p>
          <p className="text-muted text-[12px]">hoje o ritmo é {p.ritmoSemana.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}/semana</p>
        </div>
        <div className="bg-superficie-2 border-borda flex flex-col gap-1 rounded-xl border p-4">
          <p className="text-muted text-[12px]">Violações em item que já tinha violado</p>
          <p className="text-agente text-[28px] leading-none font-semibold">
            {a.reincidentes} <span className="text-muted text-[16px] font-normal">de {a.total}</span>
          </p>
          <p className="text-muted text-[12px]">atacar a causa desses itens evita a repetição</p>
        </div>
      </div>
      <div className="grid gap-6 md:grid-cols-2">
        <div className="flex flex-col gap-2.5">
          <h3 className="text-muted text-[12px] font-medium">Itens de configuração que já violaram mais de uma vez</h3>
          <ol className="flex flex-col gap-1.5">
            {a.cis.slice(0, 6).map(([ci, q]) => (
              <li key={ci} className="flex items-center justify-between gap-3 text-[13px]">
                <span className="font-mono">{ci}</span>
                <span className="text-risco font-semibold">{q} violações</span>
              </li>
            ))}
            {a.cis.length === 0 && <li className="text-muted text-[13px]">Nenhum item reincidente até esta data.</li>}
          </ol>
        </div>
        <div className="flex flex-col gap-2.5">
          <h3 className="text-muted text-[12px] font-medium">Categorias com mais violações</h3>
          <ol className="flex flex-col gap-1.5">
            {a.categorias.slice(0, 6).map(([c, q]) => (
              <li key={c} className="flex items-center justify-between gap-3 text-[13px]">
                <span className="font-mono">{c}</span>
                <span className="font-semibold">{q}</span>
              </li>
            ))}
          </ol>
        </div>
      </div>
      <p className="text-muted text-[12px]">
        Base real até {dataCurta(BASE.dias[hoje])}/2025. O agente Guarda da OLA usa esta lista para avisar a coordenação quando um destes itens abre um P2.
      </p>
    </section>
  );
}

function OlaPorEquipe({ n }: { n: number }) {
  const d = useDados();
  const itens = d.rank("equipes").filter((r) => r.o > 0).sort((a, b) => b.o - a.o).slice(0, 6);
  const max = itens[0]?.o || 1;
  return (
    <section aria-labelledby="olaeq-titulo" className="painel entra flex flex-col gap-4 p-6" style={ordem(n)}>
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 id="olaeq-titulo" className="text-[15px] font-semibold">
          Quem mais violou a OLA
        </h2>
        <p className="text-muted text-[12px]">Base real · {d.rotulo}</p>
      </div>
      <ol className="flex flex-col gap-2.5">
        {itens.map((r) => (
          <li key={r.chave} className="grid grid-cols-[72px_minmax(0,1fr)_auto] items-center gap-3 text-[13px]">
            <span className="font-mono">{r.chave}</span>
            <span className="bg-fundo h-1.5 overflow-hidden rounded-full" aria-hidden="true">
              <span className="bg-risco block h-full rounded-full" style={{ width: `${(r.o / max) * 100}%` }} />
            </span>
            <span className="font-semibold">
              {fmt.format(r.o)} <span className="text-muted font-normal">de {fmt.format(r.e)} no KPI</span>
            </span>
          </li>
        ))}
        {itens.length === 0 && <li className="text-muted text-[13px]">Nenhuma violação de OLA com esses filtros.</li>}
      </ol>
    </section>
  );
}

export default function MetaOla() {
  const { filtro } = useFiltro();
  const [kpi, setKpi] = useState<Kpi>("violacoes");
  const hoje = diaIdx(filtro.ref);
  const corte = diaIdx(CORTE_BACKTEST);
  const bt = (["P2", "P3"] as Pri[]).map((pri) => projetar("violacoes", pri, corte));

  return (
    <main className="px-4 py-6 sm:px-8 sm:py-8">
      <div className="mx-auto flex max-w-[1240px] flex-col gap-5">
        <TituloPagina titulo="A meta do ano vai fechar?">
          <Segmentado rotulo="KPI" opcoes={["violacoes", "volume"] as const} valor={kpi} aoMudar={setKpi} formatar={(k) => ROTULO_KPI[k]} />
        </TituloPagina>
        <p className="text-muted -mt-2 text-[13px]">
          Projeção feita em {dataCurta(filtro.ref)}/2025 com o que se sabia até esse dia. Mude a data no filtro para voltar no tempo. Faixas oficiais do dicionário de dados da Locaweb.
        </p>

        <div className="grid gap-5 lg:grid-cols-2 [&>*]:min-w-0">
          <CartaoProjecao p={projetar(kpi, "P2", hoje)} n={1} />
          <CartaoProjecao p={projetar(kpi, "P3", hoje)} n={2} />
        </div>

        <section aria-label="Teste da projeção" className="painel entra flex flex-wrap items-center gap-x-6 gap-y-2 px-6 py-4 text-[13px]" style={ordem(3)}>
          <span className="font-semibold">Teste em 30/09/2025</span>
          {bt.map((p) => (
            <span key={p.pri} className="text-muted">
              {p.pri}: projetou <span className="text-texto font-mono">{p.baixo}–{p.alto}</span>, real <span className="text-texto font-mono">{p.real}</span>{" "}
              <span className={p.real >= p.baixo && p.real <= p.alto ? "text-ok" : "text-amber-300"}>{p.real >= p.baixo && p.real <= p.alto ? "acertou" : "errou"}</span>
            </span>
          ))}
        </section>

        <ComoChegar hoje={hoje} n={4} />

        <div className="grid gap-5 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)] [&>*]:min-w-0">
          <OlaMensal n={5} />
          <OlaPorEquipe n={6} />
        </div>

        <section aria-labelledby="risco-titulo" className="painel entra overflow-hidden" style={ordem(7)}>
          <div className="flex flex-wrap items-center justify-between gap-3 px-6 pt-5 pb-3">
            <h2 id="risco-titulo" className="text-[15px] font-semibold">
              P2 que podem estourar agora
            </h2>
            <Ilustrativo />
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[680px] border-collapse text-left text-[14px]">
              <thead className="text-muted border-borda border-y text-[12px]">
                <tr>
                  <th className="px-6 py-2.5 font-medium">Incidente</th>
                  <th className="px-3 py-2.5 font-medium">Equipe</th>
                  <th className="px-3 py-2.5 font-medium">Tempo até a OLA</th>
                  <th className="px-6 py-2.5 font-medium">Chance de estourar</th>
                </tr>
              </thead>
              <tbody>
                {OLA_RISCO.map((r) => (
                  <tr key={r.id} className="border-borda hover:bg-white/[0.02] border-b last:border-b-0">
                    <td className="px-6 py-3">
                      <p className="font-medium">{r.titulo}</p>
                      <p className="text-faint font-mono text-[12px]">{r.id}</p>
                    </td>
                    <td className="text-muted px-3 py-3 text-[13px]">{r.equipe}</td>
                    <td className={(r.resta <= 60 ? "text-risco font-semibold " : "text-muted ") + "px-3 py-3 font-mono text-[13px]"}>{r.resta} min</td>
                    <td className="px-6 py-3">
                      <ChanceGente p={r.p} />
                    </td>
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
