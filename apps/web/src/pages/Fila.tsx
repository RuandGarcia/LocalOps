import { useEffect, useMemo, useState } from "react";
import { ArrowDown, ArrowUp, Search } from "lucide-react";
import { REAL, type Recall } from "../data/cockpit";
import { ChanceGente, Segmentado, TituloPagina, fmt, ordem } from "../components/ui";
import { OndeAgir } from "../components/insights";
import { useDados, useFiltro } from "../data/filtros";
import { FILA_METRICAS } from "../data/previsao";

// Every December/2025 alarm (the filter's test month) with the probability the model gave at opening.
// [number, opened at, template index, CI, same template in the last hour, same CI in 24 h, P(person), needed a person]
type Alarme = [string, string, number, string, number, number, number, number];
type Arquivo = { templates: string[]; alarmes: Alarme[] };
const LIMIAR = FILA_METRICAS.por_recall as Record<string, { limiar: number }>;
const MOSTRAR = 150;

function Reincidentes() {
  const d = useDados();
  const max = d.reincidentes[0]?.[1] || 1;
  return (
    <section aria-labelledby="reinc-titulo" className="painel entra flex flex-col gap-4 p-6" style={ordem(3)}>
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 id="reinc-titulo" className="text-[15px] font-semibold">
          Itens de configuração que mais voltam
        </h2>
        <p className="text-muted text-[12px]">Base real · meses do período · alarmes que exigiram gente</p>
      </div>
      <ol className="grid gap-x-8 gap-y-2.5 md:grid-cols-2">
        {d.reincidentes.map(([ci, n], i) => (
          <li key={ci} className="grid grid-cols-[20px_96px_minmax(0,1fr)_auto] items-center gap-3 text-[13px]">
            <span className="text-faint font-mono">{i + 1}</span>
            <span className="font-mono">{ci}</span>
            <span className="bg-fundo h-1.5 overflow-hidden rounded-full" aria-hidden="true">
              <span className="block h-full rounded-full bg-amber-400" style={{ width: `${(n / max) * 100}%` }} />
            </span>
            <span className="font-semibold">{fmt.format(n)}</span>
          </li>
        ))}
      </ol>
      <p className="text-muted text-[12px]">Um item que volta toda semana pede correção de causa, não mais gente no plantão.</p>
    </section>
  );
}

type Ordenar = "hora" | "p";

export default function Fila() {
  const [recall, setRecall] = useState<Recall>(97);
  const [busca, setBusca] = useState("");
  const [verEscondidos, setVerEscondidos] = useState(false);
  const [ordenar, setOrdenar] = useState<Ordenar>("p");
  const [arquivo, setArquivo] = useState<Arquivo | null>(null);
  const { filtro } = useFiltro();
  const corte = LIMIAR[String(recall)].limiar;
  const dia = filtro.ref >= "2025-12-01" ? filtro.ref : "2025-12-01";

  useEffect(() => {
    import("../../../../artefatos/fila_alarmes_dez.json").then((m) => setArquivo(m.default as unknown as Arquivo));
  }, []);

  const doDia = useMemo(
    () =>
      (arquivo?.alarmes ?? [])
        .filter((a) => a[1].startsWith(dia))
        .map(([id, aberto, t, ci, rajada, ci24, p, humano]) => ({ id, hora: aberto.slice(11), alarme: arquivo!.templates[t], ci, rajada, ci24, p, humano: humano === 1 })),
    [arquivo, dia],
  );
  const resumo = useMemo(() => {
    const fila = doDia.filter((l) => l.p >= corte);
    const humanos = doDia.filter((l) => l.humano);
    return { total: doDia.length, fila: fila.length, humanos: humanos.length, fora: humanos.filter((l) => l.p < corte).length };
  }, [doDia, corte]);
  const linhas = useMemo(() => {
    const termo = busca.trim().toLowerCase();
    return doDia
      .filter((l) => verEscondidos || l.p >= corte)
      .filter((l) => !termo || `${l.alarme} ${l.ci} ${l.id}`.toLowerCase().includes(termo))
      .sort((a, b) => (ordenar === "p" ? b.p - a.p : a.hora.localeCompare(b.hora)));
  }, [doDia, busca, verEscondidos, ordenar, corte]);

  const atual = REAL.fila.porRecall[recall];

  return (
    <main className="px-4 py-6 sm:px-8 sm:py-8">
      <div className="mx-auto flex max-w-[1240px] flex-col gap-5">
        <TituloPagina titulo="Fila">
          <p className="text-muted text-[13px]">
            {fmt.format(atual.depois)} de {fmt.format(REAL.fila.antes)} alarmes por dia no recall {recall}% · −{atual.reducao}%
          </p>
        </TituloPagina>

        <section aria-label="Filtros da fila" className="painel entra flex flex-wrap items-center gap-3 p-3" style={ordem(1)}>
          <label className="bg-fundo border-borda focus-within:border-agente-1 flex min-h-9 min-w-[16rem] flex-1 items-center gap-2 rounded-lg border px-3">
            <Search size={14} className="text-muted" aria-hidden="true" />
            <span className="sr-only">Buscar na fila</span>
            <input
              value={busca}
              onChange={(e) => setBusca(e.target.value)}
              placeholder="Buscar por alarme, CI ou número"
              className="placeholder:text-faint w-full bg-transparent text-[14px] outline-none"
            />
          </label>
          <Segmentado rotulo="Recall do filtro de ruído" opcoes={[95, 97, 99] as const} valor={recall} aoMudar={setRecall} formatar={(r) => `Recall ${r}%`} />
          <label className="text-muted flex min-h-9 items-center gap-2 text-[13px]">
            <input type="checkbox" checked={verEscondidos} onChange={(e) => setVerEscondidos(e.target.checked)} className="accent-indigo-400" />
            Mostrar escondidos
          </label>
        </section>

        <OndeAgir n={2} />
        <Reincidentes />

        <section aria-label="Alarmes" className="painel entra overflow-hidden" style={ordem(4)}>
          <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-3">
            <p className="text-[13px]">
              <span className="font-semibold">{dia.split("-").reverse().join("/")}</span>
              <span className="text-muted">
                {" "}
                · {fmt.format(resumo.total)} alarmes, {fmt.format(resumo.fila)} na fila · {resumo.humanos} exigiram gente, {resumo.fora} {resumo.fora === 1 ? "ficou escondido" : "ficaram escondidos"}
              </span>
            </p>
            <p className="text-muted text-[12px]">
              {arquivo === null
                ? "carregando os alarmes…"
                : filtro.ref < "2025-12-01"
                  ? "O filtro foi testado em dez/2025; escolha um dia de dezembro no topo."
                  : `Mostrando ${Math.min(MOSTRAR, linhas.length)} de ${fmt.format(linhas.length)}`}
            </p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] border-collapse text-left text-[14px]">
              <thead className="text-muted border-borda border-y text-[12px]">
                <tr>
                  <th className="px-5 py-2.5 font-medium">
                    <button type="button" onClick={() => setOrdenar("hora")} className="hover:text-texto inline-flex items-center gap-1">
                      Abertura {ordenar === "hora" && <ArrowUp size={12} aria-hidden="true" />}
                    </button>
                  </th>
                  <th className="px-3 py-2.5 font-medium">Alarme</th>
                  <th className="px-3 py-2.5 font-medium">CI</th>
                  <th className="px-3 py-2.5 font-medium" title="Alarmes do mesmo tipo na hora anterior · do mesmo CI nas 24 h anteriores">
                    Rajada 1 h · CI 24 h
                  </th>
                  <th className="px-3 py-2.5 font-medium">
                    <button type="button" onClick={() => setOrdenar("p")} className="hover:text-texto inline-flex items-center gap-1">
                      Chance de exigir gente {ordenar === "p" && <ArrowDown size={12} aria-hidden="true" />}
                    </button>
                  </th>
                  <th className="px-3 py-2.5 font-medium">Situação</th>
                  <th className="px-5 py-2.5 font-medium">O que aconteceu</th>
                </tr>
              </thead>
              <tbody>
                {linhas.slice(0, MOSTRAR).map((l) => {
                  const naFila = l.p >= corte;
                  return (
                    <tr key={l.id} className={(naFila ? "" : "opacity-55 ") + "border-borda hover:bg-white/[0.02] border-b last:border-b-0"}>
                      <td className="text-muted px-5 py-3 font-mono text-[13px]">{l.hora}</td>
                      <td className="px-3 py-3">
                        <p className="font-medium">{l.alarme}</p>
                        <p className="text-faint font-mono text-[12px]">{l.id}</p>
                      </td>
                      <td className="text-muted px-3 py-3 font-mono text-[13px]">{l.ci}</td>
                      <td className="text-muted px-3 py-3 font-mono text-[13px]">
                        ×{l.rajada} · ×{l.ci24}
                      </td>
                      <td className="px-3 py-3">
                        <ChanceGente p={l.p} />
                        <a href={`#/shap?alarme=${l.id}`} className="text-agente hover:text-texto ml-1 text-[12px]">
                          por quê?
                        </a>
                      </td>
                      <td className="px-3 py-3">
                        {naFila ? (
                          <span className="inline-flex items-center gap-1.5 rounded-full border border-amber-400/30 bg-amber-400/10 px-2 py-0.5 text-[12px] font-medium text-amber-300">
                            <span className="ponto-humano size-1.5 rounded-full" aria-hidden="true" />
                            Na fila
                          </span>
                        ) : (
                          <span className="text-muted border-borda rounded-full border px-2 py-0.5 text-[12px]">Escondido</span>
                        )}
                      </td>
                      <td className={(l.humano ? (naFila ? "text-amber-300" : "text-risco") : "text-muted") + " px-5 py-3 text-[13px]"}>
                        {l.humano ? (naFila ? "Exigiu gente" : "Exigiu gente · perdido") : "Fechou sozinho"}
                      </td>
                    </tr>
                  );
                })}
                {linhas.length === 0 && (
                  <tr>
                    <td colSpan={7} className="text-muted px-5 py-10 text-center text-[14px]">
                      Nenhum alarme com esse termo. Limpe a busca ou marque "Mostrar escondidos".
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </main>
  );
}
