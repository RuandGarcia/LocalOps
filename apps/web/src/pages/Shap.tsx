import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Search } from "lucide-react";
import { Dica } from "../components/Dica";
import { Segmentado, TituloPagina, fmt, ordem } from "../components/ui";
import { useFiltro } from "../data/filtros";
import { NOMES, RESUMO, explicar, frase, pc, type ArquivoShap, type Feature, type Tipo } from "../data/shap";

// The panel's own colour jobs (PRODUCT.md, Cockpit contract): what needs a person is amber, the model/agent side is
// indigo. Pair checked with the dataviz validator on #101114: CVD ΔE 33.7, contrast ≥ 3:1; direction is also encoded
// by side (left/right, up/down) and by the ×/÷ labels, so colour is never alone.
const SOBE = "#FBBF24";
const DESCE = "#818CF8";
const FATORES = ["hora", "dow", "n1h_tpl", "n24h_tpl", "n24h_ci"] as const;
type FatorNum = (typeof FATORES)[number];
const DIAS = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"];
const ROTULO_EXEMPLO = ["Precisou de gente", "No limite da fila", "Ruído"];

const alarmeDoHash = () => new URLSearchParams(window.location.hash.split("?")[1] ?? "").get("alarme") ?? "";
const prob = (l: number) => 1 / (1 + Math.exp(-l));
const logit = (p: number) => Math.log(p / (1 - p));
/** A SHAP value in log-odds read as a multiplier on the odds: +0,7 → "×2", −1,1 → "÷3". */
function vezes(v: number) {
  const m = Math.exp(Math.abs(v));
  // Tiny effects keep two decimals, so they read "÷1,03" instead of a misleading "÷1".
  const n = m >= 10 ? fmt.format(Math.round(m)) : m.toLocaleString("pt-BR", { maximumFractionDigits: m < 1.1 ? 2 : 1 });
  return `${v >= 0 ? "×" : "÷"}${n}`;
}

function Legenda() {
  return (
    <p className="text-muted flex flex-wrap gap-x-4 gap-y-1 text-[12px]">
      <span className="flex items-center gap-1.5">
        <span className="size-2.5 rounded-sm" style={{ background: SOBE }} aria-hidden="true" /> empurra para precisa de gente (×)
      </span>
      <span className="flex items-center gap-1.5">
        <span className="size-2.5 rounded-sm" style={{ background: DESCE }} aria-hidden="true" /> empurra para ruído (÷)
      </span>
    </p>
  );
}

function Cabecalho() {
  const { filtro } = useFiltro();
  const top = RESUMO.importancia[0];
  const stats = [
    { rotulo: "alarmes explicados", valor: fmt.format(RESUMO.n_alarmes) },
    { rotulo: "precisaram de gente em dez/2025", valor: pc(RESUMO.taxa_humano) },
    { rotulo: "limiar da fila (recall 97%)", valor: pc(RESUMO.limiar) },
  ];
  return (
    <section aria-label="Resumo do SHAP" className="painel entra flex flex-col gap-5 p-6" style={ordem(1)}>
      <div className="flex flex-wrap items-end justify-between gap-6">
        <div className="flex flex-wrap items-end gap-x-4 gap-y-1">
          <p className="numero-brilho text-[52px] leading-none font-semibold tracking-[-0.04em]">{top.peso_pct.toLocaleString("pt-BR")}%</p>
          <div className="flex flex-col gap-0.5 pb-1.5">
            <p className="text-[14px] font-medium">da decisão vem do {NOMES[top.feature].toLowerCase()}</p>
            <p className="text-muted text-[13px]">média do |SHAP| no filtro de ruído, dez/2025</p>
          </div>
        </div>
        <dl className="grid grid-cols-3 gap-6">
          {stats.map((s) => (
            <div key={s.rotulo} className="flex flex-col gap-1">
              <dt className="text-faint max-w-[9rem] text-[12px] leading-tight">{s.rotulo}</dt>
              <dd className="font-mono text-[18px] font-semibold">{s.valor}</dd>
            </div>
          ))}
        </dl>
      </div>
      <div className="border-borda flex flex-col gap-1.5 border-t pt-4 text-[13px] leading-relaxed">
        <p>
          SHAP mede quanto cada fator empurrou a decisão do modelo, alarme por alarme. Aqui ele explica o <span className="font-medium">filtro de ruído</span>, que estima na abertura de cada alarme a chance de ele precisar de uma pessoa. Os rótulos “×2” e “÷3” dizem quantas vezes o fator multiplicou ou dividiu essa chance (em odds).
        </p>
        <p className="text-muted">{RESUMO.previsao}</p>
        {filtro.ref < "2025-12-01" && <p className="text-muted">Seu replay está antes de dezembro: o SHAP usa dez/2025, o mês em que o filtro foi testado.</p>}
      </div>
    </section>
  );
}

function Pesos() {
  const [i, setI] = useState<number | null>(null);
  const max = RESUMO.importancia[0]?.peso_pct || 1;
  const sel = i === null ? null : RESUMO.importancia[i];
  return (
    <section aria-labelledby="pesos-titulo" className="painel entra flex flex-col gap-4 p-6" style={ordem(2)}>
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 id="pesos-titulo" className="text-[15px] font-semibold">
          Peso de cada fator na decisão
        </h2>
        <p className="text-muted text-[12px]">participação na média do |SHAP| · {fmt.format(RESUMO.n_alarmes)} alarmes</p>
      </div>
      <div className="relative">
        <ol className="flex flex-col gap-3" onPointerLeave={() => setI(null)}>
          {RESUMO.importancia.map((f, k) => (
            <li
              key={f.feature}
              tabIndex={0}
              onPointerEnter={() => setI(k)}
              onFocus={() => setI(k)}
              onBlur={() => setI(null)}
              className={(i !== null && i !== k ? "opacity-45 " : "") + "grid cursor-default grid-cols-[minmax(0,10.5rem)_minmax(0,1fr)] items-center gap-3 rounded-md text-[13px] transition-opacity outline-none"}
            >
              <span className="truncate">{NOMES[f.feature]}</span>
              <span className="flex items-center gap-2.5">
                <span className="bg-fundo h-3 flex-1 overflow-hidden rounded-full" aria-hidden="true">
                  <span
                    className="block h-full rounded-full"
                    style={{ width: `${(f.peso_pct / max) * 100}%`, background: "linear-gradient(90deg, #818CF8, #22D3EE)", boxShadow: k === 0 ? "0 0 14px rgb(129 140 248 / 0.45)" : undefined }}
                  />
                </span>
                <span className={(k === 0 ? "text-texto " : "text-muted ") + "w-12 text-right font-mono font-semibold"}>{f.peso_pct.toLocaleString("pt-BR")}%</span>
              </span>
            </li>
          ))}
        </ol>
        {sel && i !== null && (
          <Dica
            x={0.55}
            topo={i * 28 + 22}
            titulo={NOMES[sel.feature]}
            linhas={[
              { rotulo: "Peso na decisão", valor: `${sel.peso_pct.toLocaleString("pt-BR")}%`, cor: "#818CF8" },
              { rotulo: "Posição", valor: `${i + 1}º de ${RESUMO.importancia.length}` },
              { rotulo: "Média do |SHAP|", valor: sel.media_abs.toLocaleString("pt-BR", { maximumFractionDigits: 2 }) },
            ]}
          />
        )}
      </div>
      <p className="text-muted text-[12px]">O tipo de alarme decide quase sozinho. Os outros fatores ajustam: o mesmo item voltando, rajadas e o horário.</p>
    </section>
  );
}

function rotuloFaixa(f: FatorNum, faixa: string) {
  if (f === "hora") return `${faixa}h`;
  if (f === "dow") return DIAS[Number(faixa)];
  return faixa;
}

function ComoEmpurra() {
  const [f, setF] = useState<FatorNum>("hora");
  const [i, setI] = useState<number | null>(null);
  const faixas = RESUMO.dependencia[f];
  const max = Math.max(...faixas.map((x) => Math.abs(x.shap_medio)), 0.01);
  const kMax = faixas.reduce((a, x, k) => (x.shap_medio > faixas[a].shap_medio ? k : a), 0);
  const kMin = faixas.reduce((a, x, k) => (x.shap_medio < faixas[a].shap_medio ? k : a), 0);
  const sel = i === null ? null : faixas[i];
  const eixo = f === "hora" ? "hora em que o alarme abriu" : f === "dow" ? "dia da semana" : "quantos alarmes vieram antes, na janela";
  return (
    <section aria-labelledby="empurra-titulo" className="painel entra flex flex-col gap-4 p-6" style={ordem(3)}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id="empurra-titulo" className="text-[15px] font-semibold">
          Como cada fator empurra
        </h2>
        <div className="max-w-full overflow-x-auto">
          <Segmentado rotulo="Fator" opcoes={FATORES} valor={f} aoMudar={(x) => (setF(x), setI(null))} formatar={(x) => NOMES[x as Feature]} />
        </div>
      </div>
      <Legenda />
      <div className="relative">
        <div className="overflow-x-auto">
          <ol
            className="relative grid h-56 min-w-[520px] gap-[3px] pt-4"
            style={{ gridTemplateColumns: `repeat(${faixas.length}, minmax(0,1fr))` }}
            onPointerLeave={() => setI(null)}
            aria-label={`Efeito médio por faixa de ${NOMES[f].toLowerCase()}. Maior alta em ${rotuloFaixa(f, faixas[kMax].faixa)}, maior queda em ${rotuloFaixa(f, faixas[kMin].faixa)}.`}
          >
            {faixas.map((x, k) => {
              const h = (Math.abs(x.shap_medio) / max) * 36; // leaves room for the data label above/below the tallest bar
              const rotulo = k === kMax || k === kMin || i === k;
              const sobe = x.shap_medio >= 0;
              return (
                <li
                  key={x.faixa}
                  tabIndex={0}
                  onPointerEnter={() => setI(k)}
                  onFocus={() => setI(k)}
                  onBlur={() => setI(null)}
                  className={(i !== null && i !== k ? "opacity-45 " : "") + "flex cursor-default flex-col rounded-md transition-opacity outline-none"}
                >
                  <span className="relative flex-1">
                    <span className="bg-borda absolute inset-x-0 top-1/2 h-px" aria-hidden="true" />
                    <span
                      className={(sobe ? "bottom-1/2 rounded-t-[4px]" : "top-1/2 rounded-b-[4px]") + " absolute inset-x-[14%]"}
                      style={{ height: `max(2px, ${h}%)`, background: sobe ? SOBE : DESCE }}
                    />
                    {rotulo && (
                      <span className="text-texto absolute inset-x-[-6px] text-center font-mono text-[10px] font-semibold whitespace-nowrap" style={sobe ? { bottom: `calc(50% + ${h}% + 3px)` } : { top: `calc(50% + ${h}% + 3px)` }}>
                        {vezes(x.shap_medio)}
                      </span>
                    )}
                  </span>
                  <span className="text-faint h-5 text-center text-[10px] leading-5">{f !== "hora" || Number(x.faixa) % 3 === 0 ? rotuloFaixa(f, x.faixa) : ""}</span>
                </li>
              );
            })}
          </ol>
        </div>
        {sel && i !== null && (
          <Dica
            x={(i + 0.5) / faixas.length}
            topo={4}
            titulo={`${NOMES[f]}: ${rotuloFaixa(f, sel.faixa)}${f === "hora" ? `–${Number(sel.faixa) + 1}h` : ""}`}
            linhas={[
              { rotulo: "Efeito médio na chance", valor: vezes(sel.shap_medio), cor: sel.shap_medio >= 0 ? SOBE : DESCE },
              { rotulo: "Alarmes nesta faixa", valor: fmt.format(sel.n) },
              { rotulo: "Direção", valor: sel.shap_medio >= 0 ? "pede gente" : "ruído" },
            ]}
          />
        )}
      </div>
      <p className="text-faint text-[12px]">
        Eixo: {eixo}. Acima da linha o fator aumenta a chance de precisar de gente; abaixo, diminui. Passe o mouse ou use Tab para ler cada faixa.
      </p>
      <div className="border-borda grid gap-6 border-t pt-5 md:grid-cols-2">
        <ListaTipos titulo="Tipos de alarme que mais pedem gente" tipos={RESUMO.tipos.sobem.slice(0, 6)} cor={SOBE} />
        <ListaTipos titulo="Tipos de alarme que mais são ruído" tipos={RESUMO.tipos.descem.slice(0, 6)} cor={DESCE} />
      </div>
    </section>
  );
}

function ListaTipos({ titulo, tipos, cor }: { titulo: string; tipos: Tipo[]; cor: string }) {
  const [i, setI] = useState<number | null>(null);
  const max = Math.max(...tipos.map((t) => Math.abs(t.shap_medio)), 0.01);
  const sel = i === null ? null : tipos[i];
  return (
    <div className="relative flex min-w-0 flex-col gap-2.5">
      <h3 className="text-muted text-[12px] font-medium">{titulo}</h3>
      <p className="text-faint -mt-1.5 text-[11px]">barra: força do efeito no modelo · número: quantos precisaram de gente</p>
      <ol className="flex flex-col gap-2.5" onPointerLeave={() => setI(null)}>
        {tipos.map((t, k) => (
          <li
            key={t.tpl}
            tabIndex={0}
            onPointerEnter={() => setI(k)}
            onFocus={() => setI(k)}
            onBlur={() => setI(null)}
            className={(i !== null && i !== k ? "opacity-45 " : "") + "flex cursor-default flex-col gap-1 rounded-md text-[13px] transition-opacity outline-none"}
          >
            <div className="flex items-baseline justify-between gap-3">
              <span className="min-w-0 truncate font-mono text-[12px]">{t.tpl}</span>
              <span className="shrink-0 text-[12px]">
                <span className="font-mono font-semibold">{pc(t.taxa_humano)}</span>
                <span className="text-muted"> de {fmt.format(t.n)}</span>
              </span>
            </div>
            <span className="bg-fundo h-1.5 overflow-hidden rounded-full" aria-hidden="true">
              <span className="block h-full rounded-full" style={{ width: `${(Math.abs(t.shap_medio) / max) * 100}%`, background: cor }} />
            </span>
          </li>
        ))}
      </ol>
      {sel && i !== null && (
        <Dica
          x={0.4}
          topo={i * 38 + 66}
          titulo={sel.tpl.length > 48 ? `${sel.tpl.slice(0, 48)}…` : sel.tpl}
          linhas={[
            { rotulo: "Efeito médio na chance", valor: vezes(sel.shap_medio), cor },
            { rotulo: "Precisaram de gente", valor: pc(sel.taxa_humano) },
            { rotulo: "Alarmes em dez/2025", valor: fmt.format(sel.n) },
          ]}
        />
      )}
    </div>
  );
}

const TICKS = [0.001, 0.01, 0.1, 0.5, 0.9, 0.99, 0.999];
// Waterfall rows: narrower label column on a phone so the bar keeps room.
const LINHA = "grid grid-cols-[minmax(0,6.5rem)_minmax(0,1fr)] items-center gap-3 sm:grid-cols-[minmax(0,10.5rem)_minmax(0,1fr)]";

/** Background guides of the waterfall: probability ticks and the queue threshold (dashed amber). */
function Guias({ ticks, limiar }: { ticks: number[]; limiar: number | null }) {
  return (
    <span className="pointer-events-none absolute inset-0" aria-hidden="true">
      {ticks.map((x) => (
        <span key={x} className="bg-borda absolute inset-y-0 w-px opacity-60" style={{ left: `${x}%` }} />
      ))}
      {limiar !== null && <span className="absolute inset-y-0 border-l border-dashed border-amber-400/70" style={{ left: `${limiar}%` }} />}
    </span>
  );
}

function UmAlarme() {
  const [arquivo, setArquivo] = useState<ArquivoShap | null>(null);
  const [numero, setNumero] = useState(alarmeDoHash() || RESUMO.exemplos[0]);
  const [campo, setCampo] = useState(numero);
  const [i, setI] = useState<number | null>(null);

  useEffect(() => {
    import("../../../../artefatos/fila_shap_alarmes.json").then((m) => setArquivo(m.default as unknown as ArquivoShap));
    const mudou = () => {
      const a = alarmeDoHash();
      if (a) (setNumero(a), setCampo(a));
    };
    window.addEventListener("hashchange", mudou);
    return () => window.removeEventListener("hashchange", mudou);
  }, []);

  const e = useMemo(() => (arquivo ? explicar(numero, arquivo) : null), [arquivo, numero]);
  // Waterfall on the log-odds axis: from the average chance, each factor moves the running total.
  const w = useMemo(() => {
    if (!e || !arquivo) return null;
    const pontos = e.fatores.reduce((acc, f) => [...acc, acc[acc.length - 1] + f.shap], [arquivo.base]);
    const lo = Math.min(...pontos, logit(RESUMO.limiar)) - 0.5;
    const hi = Math.max(...pontos) + 0.5;
    const pos = (x: number) => ((x - lo) / (hi - lo)) * 100;
    const ticks = TICKS.filter((p) => logit(p) > lo && logit(p) < hi);
    return { pontos, pos, ticks, guias: ticks.map((p) => pos(logit(p))), limiar: pos(logit(RESUMO.limiar)) };
  }, [e, arquivo]);

  function buscar(ev: FormEvent) {
    ev.preventDefault();
    setNumero(campo);
  }

  const selF = e && i !== null ? e.fatores[i] : null;

  return (
    <section aria-labelledby="alarme-titulo" className="painel entra flex flex-col gap-4 p-6" style={ordem(4)}>
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 id="alarme-titulo" className="text-[15px] font-semibold">
          Por que este alarme
        </h2>
        <p className="text-muted text-[12px]">qualquer alarme de monitoramento de dez/2025 · ou “por quê?” na Fila</p>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <form onSubmit={buscar} className="bg-fundo border-borda focus-within:border-agente-1 flex min-h-9 min-w-0 flex-1 items-center gap-2 rounded-lg border px-3 sm:max-w-xs">
          <Search size={14} className="text-muted shrink-0" aria-hidden="true" />
          <label htmlFor="shap-numero" className="sr-only">
            Número do alarme
          </label>
          <input id="shap-numero" value={campo} onChange={(x) => setCampo(x.target.value)} placeholder="INC…" className="placeholder:text-faint w-full min-w-0 bg-transparent font-mono text-[14px] outline-none" />
        </form>
        <div role="radiogroup" aria-label="Alarmes de exemplo" className="bg-fundo border-borda inline-flex flex-wrap rounded-lg border p-0.5">
          {RESUMO.exemplos.map((n, k) => (
            <button
              key={n}
              type="button"
              role="radio"
              aria-checked={numero.toUpperCase() === n}
              onClick={() => (setNumero(n), setCampo(n))}
              className={(numero.toUpperCase() === n ? "bg-superficie-2 text-texto shadow-[inset_0_1px_0_rgb(255_255_255/0.06)] " : "text-muted hover:text-texto ") + "min-h-8 rounded-md px-3 text-[13px] font-medium whitespace-nowrap transition-colors"}
            >
              {ROTULO_EXEMPLO[k]}
            </button>
          ))}
        </div>
      </div>

      {arquivo === null && <p className="text-muted text-[13px]">carregando as explicações…</p>}
      {arquivo && !e && <p className="text-muted text-[13px]">Não achei {numero}. Só explico alarmes de monitoramento de dez/2025, o mês de teste do filtro.</p>}
      {e && w && (
        <>
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div className="flex flex-wrap items-end gap-x-4 gap-y-1">
              <p className={(e.naFila ? "text-amber-300 " : "") + "numero-brilho text-[44px] leading-none font-semibold tracking-[-0.04em]"}>{pc(e.prob)}</p>
              <div className="flex flex-col gap-0.5 pb-1">
                <p className="text-[14px] font-medium">
                  de chance de precisar de gente ·{" "}
                  {e.naFila ? (
                    <span className="inline-flex items-center gap-1.5 text-amber-300">
                      <span className="ponto-humano size-1.5 rounded-full" aria-hidden="true" /> fica na fila
                    </span>
                  ) : (
                    <span className="text-muted">sai da fila</span>
                  )}
                </p>
                <p className="text-muted font-mono text-[12px]">{e.numero}</p>
              </div>
            </div>
            <Legenda />
          </div>
          <p className="border-agente-1/40 bg-agente-1/[0.06] rounded-lg border px-4 py-3 text-[14px] leading-relaxed">{frase(e)}</p>

          <div className="relative" onPointerLeave={() => setI(null)}>
            <div className={LINHA + " text-faint text-[10px]"} aria-hidden="true">
              <span />
              <span className="relative h-4">
                {w.ticks.map((p) => (
                  <span key={p} className="absolute -translate-x-1/2 whitespace-nowrap" style={{ left: `${w.pos(logit(p))}%` }}>
                    {pc(p)}
                  </span>
                ))}
              </span>
            </div>
            <ol className="relative flex flex-col gap-1" aria-label="Contribuição de cada fator, do maior para o menor">
              <li className={LINHA + " text-[13px]"}>
                <span className="text-muted">Ponto de partida</span>
                <span className="relative h-6">
                  <Guias ticks={w.guias} limiar={w.limiar} />
                  <span className="bg-texto absolute top-1 bottom-1 w-0.5 rounded-full" style={{ left: `${w.pos(w.pontos[0])}%` }} />
                  <span className="text-muted absolute top-1/2 ml-2 -translate-y-1/2 font-mono text-[11px]" style={{ left: `${w.pos(w.pontos[0])}%` }}>
                    {pc(RESUMO.base_prob)}
                  </span>
                </span>
              </li>
              {e.fatores.map((f, k) => {
                const a = w.pontos[k];
                const b = w.pontos[k + 1];
                const esq = w.pos(Math.min(a, b));
                const larg = Math.abs(w.pos(b) - w.pos(a));
                const direita = esq + larg < 82;
                return (
                  <li
                    key={f.feature}
                    tabIndex={0}
                    onPointerEnter={() => setI(k)}
                    onFocus={() => setI(k)}
                    onBlur={() => setI(null)}
                    className={(i !== null && i !== k ? "opacity-45 " : "") + LINHA + " cursor-default rounded-md text-[13px] transition-opacity outline-none"}
                  >
                    <span className="truncate">{NOMES[f.feature]}</span>
                    <span className="relative h-6">
                      <Guias ticks={w.guias} limiar={w.limiar} />
                      <span
                        className="absolute top-1 bottom-1 rounded-[4px]"
                        style={{
                          left: `${esq}%`,
                          width: `max(3px, ${larg}%)`,
                          background: f.shap >= 0 ? SOBE : DESCE,
                          boxShadow: k === 0 ? `0 0 12px ${f.shap >= 0 ? "rgb(251 191 36 / 0.4)" : "rgb(129 140 248 / 0.45)"}` : undefined,
                        }}
                      />
                      <span className="text-texto absolute top-1/2 -translate-y-1/2 font-mono text-[11px] font-semibold whitespace-nowrap" style={direita ? { left: `calc(${esq + larg}% + 6px)` } : { right: `calc(${100 - esq}% + 6px)` }}>
                        {vezes(f.shap)}
                      </span>
                    </span>
                  </li>
                );
              })}
              <li className={LINHA + " text-[13px]"}>
                <span className="font-medium">Chance deste alarme</span>
                <span className="relative h-6">
                  <Guias ticks={w.guias} limiar={w.limiar} />
                  <span
                    className="absolute top-1/2 size-3 -translate-x-1/2 -translate-y-1/2 rounded-full"
                    style={{ left: `${w.pos(w.pontos[w.pontos.length - 1])}%`, background: e.naFila ? SOBE : DESCE, boxShadow: `0 0 12px ${e.naFila ? "rgb(251 191 36 / 0.65)" : "rgb(129 140 248 / 0.6)"}` }}
                  />
                </span>
              </li>
            </ol>
            {selF && i !== null && (
              <Dica
                x={0.62}
                topo={i * 28 + 46}
                titulo={`${NOMES[selF.feature]} = ${selF.valor.length > 40 ? `${selF.valor.slice(0, 40)}…` : selF.valor}`}
                linhas={[
                  { rotulo: "Efeito na chance", valor: vezes(selF.shap), cor: selF.shap >= 0 ? SOBE : DESCE },
                  { rotulo: "Chance antes", valor: pc(prob(w.pontos[i])) },
                  { rotulo: "Chance depois", valor: pc(prob(w.pontos[i + 1])) },
                ]}
              />
            )}
          </div>
          <p className="text-faint text-[12px]">
            Cada barra parte de onde a anterior terminou: o ponto de partida do modelo ({pc(RESUMO.base_prob)}, o valor-base do SHAP) é multiplicado fator a fator até a chance deste alarme. A linha âmbar tracejada é o limiar da fila ({pc(RESUMO.limiar)}). Escala em odds.
          </p>
        </>
      )}
    </section>
  );
}

export default function Shap() {
  return (
    <main className="px-4 py-6 sm:px-8 sm:py-8">
      <div className="mx-auto flex max-w-[1240px] flex-col gap-5">
        <TituloPagina titulo="SHAP">
          <p className="text-muted text-[13px]">por que o filtro de ruído decide · teste em dez/2025</p>
        </TituloPagina>
        <Cabecalho />
        <Pesos />
        <ComoEmpurra />
        <UmAlarme />
      </div>
    </main>
  );
}
