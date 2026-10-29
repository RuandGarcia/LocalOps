import { useMemo, useState, type CSSProperties } from "react";
import { ArrowUpRight, Check, CornerDownLeft } from "lucide-react";
import { CORTE, EPISODIOS, REAL, type Recall } from "../data/cockpit";
import { cargaSemana } from "../data/previsao";
import { passagemDoDia } from "../data/tarefas";
import { Dica, ddmm } from "../components/Dica";
import { diaIdx, useFiltro } from "../data/filtros";
import { projetar } from "../data/meta";
import { OndeAgir, ResumoPeriodo } from "../components/insights";

const fmt = new Intl.NumberFormat("pt-BR");
const ordem = (n: number) => ({ "--ordem": n }) as CSSProperties;

function Ilustrativo() {
  return (
    <span className="text-muted border-borda rounded-full border px-2 py-0.5 text-[11px] whitespace-nowrap">dados ilustrativos</span>
  );
}

function EntradaPlantao() {
  const [visto, setVisto] = useState<string | null>(null);
  const { filtro } = useFiltro();
  const ENTRADA = passagemDoDia(filtro.ref);

  return (
    <section aria-labelledby="entrada-titulo" data-visto={visto ? "true" : "false"} className="painel anel-agente entra" style={ordem(0)}>
      <header className="flex flex-wrap items-center gap-x-5 gap-y-3 px-6 pt-5 pb-4">
        <span className="orbe-agente size-9 shrink-0 rounded-full" aria-hidden="true" />
        <div className="flex min-w-[14rem] flex-1 flex-col gap-0.5">
          <h2 id="entrada-titulo" className="text-[17px] font-semibold tracking-[-0.01em]">
            Passagem de plantão
          </h2>
          <p className="text-muted text-[13px]">
            Montada com dados reais do replay ·{" "}
            <span className="font-mono">
              folha {ENTRADA.folha} · {ENTRADA.data} · 08:00
            </span>
          </p>
        </div>
        {visto ? (
          <p role="status" className="text-ok flex items-center gap-1.5 rounded-full border border-emerald-400/30 bg-emerald-400/10 px-3 py-1.5 text-[13px] font-medium">
            <Check size={14} aria-hidden="true" />
            Visto às {visto} pela equipe
          </p>
        ) : (
          <button
            type="button"
            onClick={() => setVisto("08:04")}
            className="bg-texto text-fundo flex min-h-10 items-center gap-2 rounded-lg px-4 text-[14px] font-semibold transition hover:bg-white"
          >
            Dar visto e assumir o turno
            <CornerDownLeft size={14} aria-hidden="true" className="opacity-60" />
          </button>
        )}
      </header>

      <div className="flex flex-col gap-4 px-6 pb-6">
        <p className="text-texto max-w-[64ch] text-[20px] leading-snug font-medium tracking-[-0.01em]">{ENTRADA.resumo}</p>
        <ol className="grid gap-3 lg:grid-cols-3">
          {ENTRADA.itens.map((item) => (
            <li key={item.destaque} className="bg-superficie-2 border-borda flex flex-col gap-2 rounded-xl border p-4">
              <p className="flex items-center gap-2 text-[12px] font-medium tracking-[0.02em] text-amber-300">
                <span className="ponto-humano inline-block size-1.5 rounded-full" aria-hidden="true" />
                Exige você
              </p>
              <p className="text-[15px] leading-snug font-semibold">{item.destaque}</p>
              <p className="text-muted text-[14px] leading-relaxed">{item.detalhe}</p>
              <div className="mt-auto flex items-center justify-between gap-3 pt-2">
                <p className="text-faint text-[12px]">{item.fonte}</p>
                <a href={item.href} className="text-agente inline-flex items-center gap-1 text-[13px] font-medium whitespace-nowrap no-underline hover:underline">
                  {item.acao}
                  <ArrowUpRight size={14} aria-hidden="true" />
                </a>
              </div>
            </li>
          ))}
        </ol>
        <p className="text-muted text-[12px]">Números reais do dia no replay. O agente que publicaria esta folha às 08h ainda não roda; o texto é montado pelo painel.</p>
      </div>
    </section>
  );
}

const RECALLS: Recall[] = [95, 97, 99];

function Fila() {
  const [recall, setRecall] = useState<Recall>(97);
  const atual = REAL.fila.porRecall[recall];
  const corte = CORTE[recall];
  const naFila = useMemo(() => EPISODIOS.filter((e) => e.p >= corte).length, [corte]);

  return (
    <section aria-labelledby="fila-titulo" className="painel entra flex flex-col gap-5 p-6" style={ordem(1)}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id="fila-titulo" className="text-[15px] font-semibold">
          Fila filtrada
        </h2>
        <div role="radiogroup" aria-label="Recall do filtro de ruído" className="bg-fundo border-borda inline-flex rounded-lg border p-0.5">
          {RECALLS.map((r) => (
            <button
              key={r}
              type="button"
              role="radio"
              aria-checked={recall === r}
              onClick={() => setRecall(r)}
              className={
                (recall === r ? "bg-superficie-2 text-texto shadow-[inset_0_1px_0_rgb(255_255_255/0.06)] " : "text-muted hover:text-texto ") +
                "min-h-8 rounded-md px-3 text-[13px] font-medium whitespace-nowrap transition-colors"
              }
            >
              Recall {r}%
            </button>
          ))}
        </div>
      </div>

      <div className="flex flex-wrap items-end gap-x-4 gap-y-1" aria-live="polite">
        <p className="numero-brilho text-[52px] leading-none font-semibold tracking-[-0.04em]">{fmt.format(atual.depois)}</p>
        <div className="flex flex-col gap-0.5 pb-1.5">
          <p className="text-ok text-[14px] font-medium">−{atual.reducao}% de ruído</p>
          <p className="text-muted text-[13px]">alarmes por dia, de {fmt.format(REAL.fila.antes)}</p>
        </div>
      </div>
      <p className="text-muted -mt-2 text-[13px]">
        Limiar calibrado em nov para manter {recall}% dos alarmes que exigiram ação; no teste de dez/2025 manteve {(atual.recall * 100).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%. Só usa o que se sabe na abertura.
      </p>

      <figure className="flex flex-col gap-3">
        <div
          className="grid grid-cols-[repeat(18,minmax(0,1fr))] gap-[3px]"
          role="img"
          aria-label={`Amostra ilustrativa de ${EPISODIOS.length} episódios; ${naFila} entram na fila no recall ${recall}%.`}
        >
          {EPISODIOS.map((e) => {
            const tamanho = e.p >= 0.5 ? 13 : e.p >= 0.2 ? 9 : e.p >= 0.06 ? 6 : 4;
            const entra = e.p >= corte;
            return (
              <span key={e.id} className="flex aspect-square items-center justify-center">
                <span
                  className={(entra ? "ponto-humano " : "border-faint/70 border ") + "rounded-full transition-all duration-500"}
                  style={{ width: tamanho, height: tamanho }}
                />
              </span>
            );
          })}
        </div>
        <figcaption className="text-muted flex flex-wrap items-center gap-x-4 gap-y-1 text-[12px]">
          <span>Tamanho: chance de exigir gente</span>
          <span className="flex items-center gap-1.5">
            <span className="ponto-humano inline-block size-2 rounded-full" aria-hidden="true" />
            entra na fila ({naFila} de {EPISODIOS.length})
          </span>
          <Ilustrativo />
        </figcaption>
      </figure>
    </section>
  );
}

const SEMANA = ["dom", "seg", "ter", "qua", "qui", "sex", "sáb"];

function CargaHumana() {
  const { filtro } = useFiltro();
  const { dias: brutos, p90: capacidadeTurno, amanha } = cargaSemana(filtro.ref);
  const dias = brutos.map((d) => {
    const dt = new Date(`${d.alvo}T00:00:00Z`);
    return { ...d, rotulo: `${d.previsto ? "amanhã" : SEMANA[dt.getUTCDay()]} ${d.alvo.slice(8, 10)}` };
  });
  const escala = Math.max(capacidadeTurno, ...dias.map((d) => d.valor)) * 1.15;
  const [sel, setSel] = useState<number | null>(null);
  const altura = 190;
  const y = (v: number) => altura - (v / escala) * altura;

  return (
    <section aria-labelledby="carga-titulo" className="painel entra flex flex-col gap-5 p-6" style={ordem(2)}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id="carga-titulo" className="text-[15px] font-semibold">
          Carga humana · 6 dias e amanhã
        </h2>
      </div>
      <p className="text-[15px] leading-snug">
        <span className={(amanha.previsto > capacidadeTurno ? "text-amber-300 " : "") + "font-semibold"}>
          {amanha.previsto > capacidadeTurno ? "Amanhã passa do p90." : "Amanhã fica abaixo do p90."}
        </span>{" "}
        <span className="text-muted">
          {fmt.format(amanha.previsto)} registros que exigem gente previstos (faixa {fmt.format(amanha.inf)}–{fmt.format(amanha.sup)}); o p90 dos últimos 90 dias é {capacidadeTurno}.
        </span>
      </p>

      <figure className="flex flex-col gap-3">
        <div className="relative" style={{ height: altura + 26 }}>
          <div className="border-risco/70 absolute inset-x-0 border-t border-dashed" style={{ top: y(capacidadeTurno) }} aria-hidden="true" />
          <span className="text-risco bg-superficie absolute right-0 -translate-y-1/2 pl-2 text-[11px] font-medium" style={{ top: y(capacidadeTurno) }}>
            p90 {capacidadeTurno}
          </span>
          <ol className="absolute inset-x-0 top-0 grid grid-cols-7 gap-3 pr-20" onPointerLeave={() => setSel(null)}>
            {dias.map((d, k) => {
              const passa = d.valor > capacidadeTurno;
              return (
                <li
                  key={d.alvo}
                  tabIndex={0}
                  onPointerEnter={() => setSel(k)}
                  onFocus={() => setSel(k)}
                  onBlur={() => setSel(null)}
                  className={(sel !== null && sel !== k ? "opacity-50 " : "") + "flex cursor-default flex-col items-center gap-2 transition-opacity outline-none"}
                >
                  <div className="flex w-full flex-col items-center justify-end gap-1.5" style={{ height: altura }}>
                    <span className={(passa ? "text-amber-300 font-semibold" : "text-muted") + " bg-superficie relative px-1 text-[12px]"}>{d.valor}</span>
                    <span
                      className="w-full max-w-10 rounded-t-md"
                      style={{
                        height: (d.valor / escala) * altura,
                        opacity: d.previsto ? 0.75 : 1,
                        outline: d.previsto ? "1px dashed rgb(165 180 252 / 0.8)" : undefined,
                        background: passa
                          ? "linear-gradient(180deg, #FBBF24, rgb(251 191 36 / 0.15))"
                          : "linear-gradient(180deg, rgb(129 140 248 / 0.9), rgb(129 140 248 / 0.08))",
                        boxShadow: passa ? "0 0 24px rgb(251 191 36 / 0.35)" : undefined,
                      }}
                      aria-hidden="true"
                    />
                  </div>
                  <span className="text-muted text-[11px] whitespace-nowrap">{d.rotulo}</span>
                </li>
              );
            })}
          </ol>
          {sel !== null && (
            <Dica
              x={((sel + 0.5) / 7) * 0.88}
              topo={0}
              titulo={`${dias[sel].rotulo.split(" ")[0]}, ${ddmm(dias[sel].alvo)}${dias[sel].previsto ? " · previsão" : " · real"}`}
              linhas={[
                { rotulo: dias[sel].previsto ? "Previstos" : "Exigiram gente", valor: fmt.format(dias[sel].valor) },
                ...(dias[sel].previsto ? [{ rotulo: "Faixa de 80%", valor: `${fmt.format(amanha.inf)}–${fmt.format(amanha.sup)}` }] : []),
                { rotulo: "Contra o p90", valor: `${dias[sel].valor >= capacidadeTurno ? "+" : "−"}${fmt.format(Math.abs(dias[sel].valor - capacidadeTurno))}` },
              ]}
            />
          )}
        </div>
        <figcaption className="text-muted text-[12px]">
          Real, set–dez/2025: média de {REAL.humanosDia} por dia, p90 de {REAL.humanosP90}, pico de {REAL.humanosPico} em {REAL.picoData}.
        </figcaption>
      </figure>
    </section>
  );
}

function MetaOla() {
  const { filtro } = useFiltro();
  const hoje = diaIdx(filtro.ref);
  const proj = (["P2", "P3"] as const).map((pri) => projetar("violacoes", pri, hoje));
  return (
    <section aria-labelledby="ola-titulo" className="painel entra flex flex-col gap-4 p-6" style={ordem(4)}>
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 id="ola-titulo" className="text-[15px] font-semibold">
          A meta de OLA do ano vai fechar?
        </h2>
        <a href="#/meta" className="text-agente text-[13px] font-medium no-underline hover:underline">
          Ver projeção completa
        </a>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        {proj.map((p) => {
          const bom = ["150%", "125%", "100%"].includes(p.faixaProvavel.rotulo);
          const pf = p.prob.find((x) => x.faixa.rotulo === p.faixaProvavel.rotulo)!.p;
          return (
            <div key={p.pri} className="bg-superficie-2 border-borda flex flex-col gap-1.5 rounded-xl border p-4">
              <p className="text-muted text-[12px]">
                {p.pri} · {p.ateHoje} violações até hoje
              </p>
              <p className={(bom ? "text-ok" : "text-risco") + " text-[26px] leading-none font-semibold tracking-[-0.03em]"}>
                {p.baixo}–{p.alto}
              </p>
              <p className="text-[13px]">
                Faixa mais provável <span className={(bom ? "text-ok" : "text-risco") + " font-semibold"}>{p.faixaProvavel.rotulo}</span>{" "}
                <span className="text-muted">({Math.round(pf * 100)}% de chance)</span>
              </p>
            </div>
          );
        })}
      </div>
    </section>
  );
}

export default function Cockpit() {
  return (
    <main className="px-4 py-6 sm:px-8 sm:py-8">
      <div className="mx-auto flex max-w-[1240px] flex-col gap-5">
        <div className="entra flex flex-wrap items-end justify-between gap-3" style={ordem(0)}>
          <h1 className="text-[30px] leading-tight font-semibold tracking-[-0.03em]">Bom dia, equipe.</h1>
        </div>

        <ResumoPeriodo n={0} />

        <EntradaPlantao />

        <div className="grid gap-5 lg:grid-cols-2">
          <Fila />
          <CargaHumana />
        </div>

        <OndeAgir n={3} />

        <MetaOla />
      </div>
    </main>
  );
}
