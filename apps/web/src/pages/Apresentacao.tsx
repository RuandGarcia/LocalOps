import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Bot, ChevronLeft, ChevronRight, Filter, LineChart, Pause, Play, Target, Upload, X, type LucideIcon } from "lucide-react";
import { diaIdx, useDados } from "../data/filtros";
import { projetar } from "../data/meta";
import { EXECUCOES, REAL } from "../data/cockpit";
import { relatorio } from "../agent/cliente";
import { TelaViva, type Destaque } from "../components/TelaViva";
import { QrCode, SITE } from "../components/QrCode";
import Cockpit from "./Cockpit";
import Previsao from "./Previsao";
import Tendencias from "./Tendencias";
import MetaOla from "./MetaOla";
import Fila from "./Fila";
import Agentes from "./Agentes";
import Chat from "./Chat";

const PASSO = 2400; // time on each highlight of a product-tour scene
const nf = new Intl.NumberFormat("pt-BR");

function Sobrancelha({ children }: { children: ReactNode }) {
  return (
    <p className="border-borda bg-superficie/70 inline-flex rounded-full border px-3.5 py-1 text-[14px] font-medium">
      <span className="sobrancelha">{children}</span>
    </p>
  );
}

function Titulo({ children, grande = false }: { children: ReactNode; grande?: boolean }) {
  return (
    <h1
      className={
        (grande ? "text-[clamp(44px,6.4vw,96px)] " : "text-[clamp(32px,4vw,60px)] ") +
        "titulo-grad leading-[1.04] font-semibold tracking-[-0.045em] text-balance"
      }
    >
      {children}
    </h1>
  );
}

/** Counts up to `ate` once, like a motion title; static when the viewer asked for reduced motion. */
function Conta({ ate, ms = 1600, atraso = 300 }: { ate: number; ms?: number; atraso?: number }) {
  const reduzido = typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const [v, setV] = useState(reduzido ? ate : 0);
  useEffect(() => {
    if (reduzido) return;
    let quadro = 0;
    const t0 = performance.now() + atraso;
    const passo = (t: number) => {
      const k = Math.min(1, Math.max(0, (t - t0) / ms));
      setV(Math.round(ate * (1 - Math.pow(1 - k, 3))));
      if (k < 1) quadro = requestAnimationFrame(passo);
    };
    quadro = requestAnimationFrame(passo);
    return () => cancelAnimationFrame(quadro);
  }, [ate, ms, atraso, reduzido]);
  return <span className="tabular-nums">{nf.format(v)}</span>;
}

function Pontos() {
  // 200 dots ≈ one day of alarms; amber ones needed a person (14%).
  const [fase, setFase] = useState(0);
  useEffect(() => {
    const t = setTimeout(() => setFase(1), 1600);
    return () => clearTimeout(t);
  }, []);
  const pontos = useMemo(() => Array.from({ length: 200 }, (_, i) => ({ i, humano: Math.abs((Math.sin(i * 12.9898) * 43758.5453) % 1) > 0.86 })), []);
  return (
    <div className="grid w-full max-w-[720px] grid-cols-[repeat(25,minmax(0,1fr))] gap-[5px]" aria-hidden="true">
      {pontos.map((p) => {
        const some = fase >= 1 && !p.humano;
        return (
          <span key={p.i} className="flex aspect-square items-center justify-center">
            <span
              className={(p.humano && fase >= 1 ? "ponto-humano " : "bg-indigo-300/70 ") + "block rounded-full transition-all duration-1000"}
              style={{ width: some ? 4 : 11, height: some ? 4 : 11, opacity: some ? 0.18 : 1, transitionDelay: `${(p.i % 25) * 18}ms` }}
            />
          </span>
        );
      })}
    </div>
  );
}

/** Steps 0..n-1 once, `ms` apart, starting after `atraso`. */
function usePassos(n: number, ms: number, atraso = 0) {
  const [i, setI] = useState(0);
  useEffect(() => {
    const ts = Array.from({ length: n - 1 }, (_, k) => setTimeout(() => setI(k + 1), atraso + ms * (k + 1)));
    return () => ts.forEach(clearTimeout);
  }, [n, ms, atraso]);
  return i;
}

function CenaCentro({ children }: { children: ReactNode }) {
  return <div className="flex w-full max-w-[1100px] flex-col items-center gap-7 text-center">{children}</div>;
}

// ── Product tour ────────────────────────────────────────────────────────────

type Tour = { id: string; rotulo: string; sobrancelha: string; titulo: string; frase: string; destaques: Destaque[]; tela: () => ReactNode };

function CenaTour({ t }: { t: Tour }) {
  const ativo = usePassos(t.destaques.length, PASSO);
  return (
    <div className="grid w-full max-w-[1500px] items-center gap-8 lg:grid-cols-[minmax(0,5fr)_minmax(0,9fr)] lg:gap-12">
      <div className="flex flex-col gap-5 text-left">
        <div>
          <Sobrancelha>{t.sobrancelha}</Sobrancelha>
        </div>
        <Titulo>{t.titulo}</Titulo>
        <p className="text-[clamp(16px,1.4vw,20px)] leading-relaxed text-[#C7CCD6]">{t.frase}</p>
        <ol className="flex flex-col gap-2">
          {t.destaques.map((d, i) => (
            <li
              key={d.titulo}
              className={(i === ativo ? "border-agente-1/60 bg-white/[0.04] " : "border-transparent opacity-45 ") + "flex gap-3 rounded-xl border p-3 transition-all duration-500"}
            >
              <span className={(i === ativo ? "orbe-agente text-[#08090B] " : "border-borda text-muted border ") + "mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full text-[12px] font-semibold"}>
                {i + 1}
              </span>
              <div className="flex flex-col gap-0.5">
                <p className="text-[16px] font-semibold">{d.titulo}</p>
                <p className="text-muted text-[14px] leading-relaxed">{d.texto}</p>
              </div>
            </li>
          ))}
        </ol>
      </div>
      <div className="deriva">
        <TelaViva rotulo={t.rotulo} destaques={t.destaques} ativo={ativo}>
          {t.tela()}
        </TelaViva>
      </div>
    </div>
  );
}

function ChatDemo() {
  const dados = useDados();
  const inicial = useMemo(
    () => [
      { de: "voce" as const, texto: "Gerar relatório do período" },
      relatorio({ dados, gran: "dia", hoje: diaIdx("2025-10-16") }),
      { de: "voce" as const, texto: "Segue a planilha do turno.", anexos: [{ nome: "turno-16-10.csv", tipo: "text/csv", tamanho: 18_400 }] },
      { de: "agente" as const, texto: "Li os anexos:\nturno-16-10.csv: 214 linhas e 6 colunas (hora, alarme, produto, equipe, prioridade, status).\n\nQuer que eu cruze com a base de incidentes?", fonte: "anexos enviados" },
    ],
    [dados],
  );
  // The composer is sticky in the app; inside the frame it must sit at the end of the conversation.
  return (
    <div className="[&_form]:static">
      <Chat inicial={inicial} />
    </div>
  );
}

const TOUR: Tour[] = [
  {
    id: "cockpit",
    rotulo: "Cockpit",
    sobrancelha: "Tela 1 · Cockpit do plantão",
    titulo: "Uma tela para começar o turno",
    frase: "O plantonista abre o LocalOps e já sabe o que exige gente hoje, o que vem pela frente e como está a meta.",
    destaques: [
      { alvo: "#entrada-titulo", titulo: "Passagem de plantão", texto: "O agente escreve o resumo do turno. O operador lê e dá o visto." },
      { alvo: "#fila-titulo", titulo: "Fila filtrada", texto: "O ruído sai da frente; fica o que precisa de uma pessoa." },
      { alvo: "#ola-titulo", titulo: "Meta de OLA", texto: "A projeção do ano, atualizada todo dia." },
    ],
    tela: () => <Cockpit />,
  },
  {
    id: "previsao",
    rotulo: "Previsão e replay",
    sobrancelha: "Perguntas 1 e 2 da Locaweb",
    titulo: "Prevê o trabalho humano, não só o volume",
    frase: "Total, P2, P3 e KPI, para amanhã e para a semana, com intervalo e o motivo de cada número.",
    destaques: [
      { alvo: "#serie-titulo", titulo: "Volume real por dia", texto: "Qualquer dia de set–dez/2025 pode ser revisto como se fosse hoje." },
      { alvo: "#prev-titulo", titulo: "Previsão contra o observado", texto: "D+1 e D+7, com a faixa de confiança de 80%." },
      { alvo: "#pq-titulo", titulo: "Por que esse número", texto: "O contexto do número: média de 7 e 28 dias e o mesmo dia da semana passada." },
    ],
    tela: () => <Previsao />,
  },
  {
    id: "tendencias",
    rotulo: "Tendências",
    sobrancelha: "Pergunta 3 da Locaweb",
    titulo: "O que está subindo, antes de virar crise",
    frase: "Tendência de 12 semanas por produto, categoria e item de configuração.",
    destaques: [
      { alvo: "#altas-titulo", titulo: "O que está subindo", texto: "Inclinação das últimas semanas, item por item." },
      { alvo: "main > div > ul", titulo: "Cada item, semana a semana", texto: "A curva de 12 semanas e a variação contra as 4 anteriores." },
    ],
    tela: () => <Tendencias />,
  },
  {
    id: "meta",
    rotulo: "Meta de OLA",
    sobrancelha: "Pergunta 4 da Locaweb",
    titulo: "A meta do ano vai fechar?",
    frase: "Violações e volume tratado contra as faixas oficiais, com a chance de terminar em cada uma.",
    destaques: [
      { alvo: "[aria-label='Probabilidade de terminar em cada faixa']", titulo: "Probabilidade por faixa", texto: "150%, 125%, 100%… a chance de cada uma, recalculada todo dia." },
      { alvo: "#chegar-titulo", titulo: "Como chegar a 100%", texto: "Quantas violações evitar e em quais itens." },
      { alvo: "#risco-titulo", titulo: "P2 que podem estourar agora", texto: "Os incidentes com maior risco na próxima hora." },
    ],
    tela: () => <MetaOla />,
  },
  {
    id: "fila",
    rotulo: "Fila e onde agir",
    sobrancelha: "Pergunta 5 da Locaweb",
    titulo: "Onde agir para prevenir",
    frase: "Produtos, equipes e itens que concentram o trabalho, e os que voltam sempre.",
    destaques: [
      { alvo: "#agir-titulo", titulo: "Onde agir", texto: "Quem concentra os alarmes que exigiram gente no período." },
      { alvo: "#reinc-titulo", titulo: "Itens que mais voltam", texto: "Atacar a causa desses itens tira trabalho de vez." },
      { alvo: "[aria-label='Alarmes']", titulo: "Fila com probabilidade", texto: "Cada alarme com a chance de precisar de alguém." },
    ],
    tela: () => <Fila />,
  },
  {
    id: "agentes",
    rotulo: "Agentes",
    sobrancelha: "O diferencial",
    titulo: "Agentes que vão trabalhar sozinhos",
    frase: "O copiloto já responde no chat. Briefing, alerta de pico e guarda da OLA têm gatilho e saída definidos; as tarefas e o registro abaixo são ilustrativos.",
    destaques: [
      { alvo: "#tarefas-titulo", titulo: "Tarefas abertas pelos agentes", texto: "Como ficam quando os agentes rodarem: a fazer, em execução, aguardando visto, concluído." },
      { alvo: "#execucoes-titulo", titulo: "Registro de execuções", texto: "Gatilho, duração e resultado de cada rodada, falhas incluídas." },
    ],
    tela: () => <Agentes />,
  },
  {
    id: "chat",
    rotulo: "Chat",
    sobrancelha: "Converse com a operação",
    titulo: "Pergunte, anexe, receba o relatório",
    frase: "O mesmo agente responde no chat, com número, motivo e fonte, e lê os arquivos do turno.",
    destaques: [
      { alvo: "section[aria-label^='Conversa'] > div:nth-child(2)", titulo: "Relatório do período", texto: "Gerado da base real, com os filtros da tela." },
      { alvo: "form", titulo: "Anexos", texto: "CSV, texto, PDF, Excel e HTML vão para o agente; o relatório volta em PDF, Excel ou HTML." },
    ],
    tela: () => <ChatDemo />,
  },
];

// ── Story scenes ────────────────────────────────────────────────────────────

function Abertura() {
  return (
    <div className="flex w-full max-w-[1300px] flex-col items-center gap-10 text-center">
      <div className="flex flex-col items-center gap-6">
        <Sobrancelha>Paladinos · Challenge Locaweb × FIAP 2026</Sobrancelha>
        <Titulo grande>LocalOps</Titulo>
        <p className="max-w-[760px] text-[clamp(20px,2.2vw,30px)] leading-snug text-[#C7CCD6]">O copiloto da operação que avisa antes de alguém perguntar.</p>
      </div>
      <div className="w-full max-w-[1040px] [perspective:1600px]">
        <div className="deriva-abertura [transform-origin:top]">
          <TelaViva rotulo="Cockpit" destaques={[]} ativo={0}>
            <Cockpit />
          </TelaViva>
        </div>
      </div>
    </div>
  );
}

function Problema() {
  return (
    <CenaCentro>
      <Sobrancelha>O problema</Sobrancelha>
      <Titulo>
        <Conta ate={REAL.alarmesDia} /> alarmes por dia.
        <br />
        Só <span className="text-amber-300"><Conta ate={REAL.humanosDia} atraso={1400} ms={1000} /></span> precisam de alguém.
      </Titulo>
      <Pontos />
      <p className="text-muted max-w-[720px] text-[17px] leading-relaxed">
        O plantão N2 da Locaweb gasta o turno separando ruído. {REAL.semIntervencaoPct.toLocaleString("pt-BR")}% dos alarmes fecham sozinhos, e o pico de alarmes nem é o pico de trabalho.
      </p>
    </CenaCentro>
  );
}

const PILARES: [LucideIcon, string, string][] = [
  [Filter, "Filtra o ruído", "Na abertura, cada alarme ganha a chance de exigir uma pessoa."],
  [LineChart, "Prevê o trabalho humano", "Amanhã e a semana, com intervalo e motivo."],
  [Target, "Protege a meta", "Projeção da OLA do ano e onde agir para chegar a 100%."],
  [Bot, "Avisa antes", "Agentes avisam no painel do plantão e respondem no chat."],
];

function OQueE() {
  return (
    <CenaCentro>
      <Sobrancelha>A solução</Sobrancelha>
      <Titulo>Do alarme à ação, sem ninguém precisar perguntar</Titulo>
      <ul className="grid w-full gap-4 text-left sm:grid-cols-2 lg:grid-cols-4">
        {PILARES.map(([Icone, t, d], i) => (
          <li key={t} className="painel entra flex flex-col gap-3 p-6" style={{ "--ordem": i + 2 } as React.CSSProperties}>
            <span className="orbe-agente flex size-10 items-center justify-center rounded-xl text-[#08090B]">
              <Icone size={20} strokeWidth={2} aria-hidden="true" />
            </span>
            <p className="text-[19px] font-semibold tracking-[-0.01em]">{t}</p>
            <p className="text-muted text-[15px] leading-relaxed">{d}</p>
          </li>
        ))}
      </ul>
    </CenaCentro>
  );
}

const FLUXO: [LucideIcon, string, string][] = [
  [Upload, "Dados entram", "lote do ITSM pela API, validado linha a linha"],
  [Filter, "Filtro de ruído", "chance de exigir gente, só com o que se sabe na abertura"],
  [LineChart, "Previsão", "carga humana D+1 e D+7"],
  [Target, "Meta de OLA", "probabilidade de cada faixa"],
  [Bot, "Agentes", "sino do Cockpit e chat"],
];

function ComoFunciona() {
  const passo = usePassos(FLUXO.length, 700, 400);
  return (
    <CenaCentro>
      <Sobrancelha>Como funciona</Sobrancelha>
      <Titulo>Um pipeline, quatro decisões</Titulo>
      <ol className="flex w-full flex-col items-stretch gap-3 lg:flex-row lg:items-start lg:gap-0">
        {FLUXO.map(([Icone, t, d], i) => {
          const aceso = i <= passo;
          return (
            <li key={t} className="flex flex-1 flex-col items-center gap-3 lg:flex-row lg:items-start">
              <div className={(aceso ? "opacity-100 " : "opacity-30 ") + "flex flex-col items-center gap-3 px-2 transition-opacity duration-700 lg:w-full"}>
                <span className={(aceso ? "orbe-agente text-[#08090B] " : "border-borda text-muted border ") + "flex size-16 items-center justify-center rounded-2xl transition-all duration-700"}>
                  <Icone size={28} strokeWidth={1.75} aria-hidden="true" />
                </span>
                <p className="text-[18px] font-semibold">{t}</p>
                <p className="text-muted max-w-[200px] text-[14px] leading-relaxed">{d}</p>
              </div>
              {i < FLUXO.length - 1 && (
                <span className="bg-borda relative mt-8 hidden h-0.5 w-10 shrink-0 overflow-hidden rounded-full lg:block" aria-hidden="true">
                  <span className="absolute inset-y-0 left-0 bg-indigo-300 transition-all duration-700" style={{ width: i < passo ? "100%" : "0%" }} />
                </span>
              )}
            </li>
          );
        })}
      </ol>
    </CenaCentro>
  );
}

function AgentesProativos() {
  const msgs = [...EXECUCOES].filter((e) => e.resultado !== "falha" && e.hora.startsWith("08")).reverse();
  const n = usePassos(msgs.length + 1, 1100, 400);
  return (
    <div className="grid w-full max-w-[1200px] items-center gap-10 lg:grid-cols-[minmax(0,1fr)_380px]">
      <div className="flex flex-col gap-5 text-left">
        <div>
          <Sobrancelha>O diferencial</Sobrancelha>
        </div>
        <Titulo>O agente avisa antes, dentro do painel do plantão</Titulo>
        <ul className="flex flex-col gap-3 text-[18px] text-[#C7CCD6]">
          <li>Briefing do plantão às 08h e às 20h</li>
          <li>Alerta de pico com 4 horas de antecedência</li>
          <li>Guarda da OLA a cada 15 minutos</li>
        </ul>
        <p className="text-muted text-[14px] leading-relaxed">
          Demonstração com a base real de 2025. Os números vêm do pipeline; o modelo de linguagem só redige e pode rodar nas GPUs da própria Locaweb.
        </p>
      </div>
      <div className="border-borda mx-auto flex h-[540px] w-full max-w-[380px] flex-col overflow-hidden rounded-2xl border bg-[#0d0e11] shadow-[0_40px_120px_-30px_rgb(129_140_248/0.4)]">
        <div className="border-borda flex items-center gap-3 border-b px-4 py-3">
          <span className="orbe-agente size-9 rounded-full" aria-hidden="true" />
          <div className="text-left">
            <p className="text-[15px] font-semibold">Avisos do agente</p>
            <p className="text-muted text-[12px]">Sino do Cockpit · plantão N2</p>
          </div>
        </div>
        <div className="flex flex-1 flex-col gap-3 p-4 text-left">
          {msgs.slice(0, n).map((m) => (
            <div key={m.hora} className="cena-entra flex flex-col gap-1">
              <p className="text-agente text-[12px] font-medium">
                {m.agente} · {m.hora}
              </p>
              <p className="bg-superficie-2 border-borda rounded-2xl rounded-tl-sm border px-3.5 py-2.5 text-[14px] leading-relaxed">{m.saida}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

const CAMADAS: { nome: string; faz: string; estado: string; pronto: boolean }[] = [
  { nome: "Web · React, Vite, TypeScript, Tailwind", faz: "Cockpit, telas, chat e este modo apresentação", estado: "no ar", pronto: true },
  { nome: "Agente OpenClaw localops", faz: "copiloto do painel; ferramentas só de leitura via MCP", estado: "planejado", pronto: false },
  { nome: "API · FastAPI /v1", faz: "contrato único para painel e agente; ingestão com token e limite de uso", estado: "planejado", pronto: false },
  { nome: "Pipeline · Python", faz: "ingestão → filtro de ruído → previsão → meta; walk-forward diário", estado: "worker agendado", pronto: true },
  { nome: "VPS · Docker Swarm e Traefik", faz: "roda em qualquer nuvem ou on-prem; funciona offline no estande", estado: "planejado", pronto: false },
];

function Arquitetura() {
  return (
    <CenaCentro>
      <Sobrancelha>Arquitetura</Sobrancelha>
      <Titulo>Aberta, portátil e sem dependência de nuvem</Titulo>
      <ol className="flex w-full max-w-[860px] flex-col gap-2.5 text-left">
        {CAMADAS.map((c, i) => (
          <li key={c.nome} className="painel entra flex flex-wrap items-center gap-x-4 gap-y-1 px-5 py-4" style={{ "--ordem": i + 2 } as React.CSSProperties}>
            <div className="flex min-w-0 flex-1 flex-col">
              <p className="text-[17px] font-semibold">{c.nome}</p>
              <p className="text-muted text-[14px]">{c.faz}</p>
            </div>
            <span
              className={
                (c.pronto ? "text-ok border-emerald-400/30 bg-emerald-400/10" : "text-muted border-borda") +
                " rounded-full border px-2.5 py-0.5 text-[12px] font-medium whitespace-nowrap"
              }
            >
              {c.estado}
            </span>
          </li>
        ))}
      </ol>
    </CenaCentro>
  );
}

function Resultados() {
  const meta = useMemo(() => projetar("violacoes", "P2", diaIdx("2025-09-30")), []);
  const cards: [string, string, string][] = [
    [`−${REAL.fila.porRecall[97].reducao}%`, "na fila de alarmes", `${nf.format(REAL.fila.antes)} → ${nf.format(REAL.fila.porRecall[97].depois)} por dia, mantendo 95 de cada 100 que exigiram ação. AUC 0,916, teste em dez/2025.`],
    [`${meta.baixo}–${meta.alto}`, "violações de P2 previstas em 30/09", `O ano fechou em ${meta.real}. A projeção acertou a faixa com três meses de antecedência.`],
    ["r = 0,28", "entre volume e trabalho humano", "Prever alarmes não diz quantas pessoas o turno precisa. Por isso prevemos a carga humana."],
    ["0,991 ✕", "o número bonito que descartamos", "Com categoria e produto o AUC subia, mas era vazamento. Ficamos só com o que se sabe na abertura."],
  ];
  return (
    <CenaCentro>
      <Sobrancelha>O que o protótipo já prova</Sobrancelha>
      <Titulo>Resultados com dado real, e com os limites ditos</Titulo>
      <ul className="grid w-full gap-4 text-left sm:grid-cols-2">
        {cards.map(([n, r, d], i) => (
          <li key={r} className="painel entra flex flex-col gap-2 p-6" style={{ "--ordem": i + 2 } as React.CSSProperties}>
            <p className="numero-brilho text-[clamp(34px,3.6vw,52px)] leading-none font-semibold tracking-[-0.04em]">{n}</p>
            <p className="text-[16px] font-medium">{r}</p>
            <p className="text-muted text-[14px] leading-relaxed">{d}</p>
          </li>
        ))}
      </ul>
      <p className="text-faint text-[14px]">Previsão D+1 e D+7: walk-forward diário, erro medido em dez/2025.</p>
    </CenaCentro>
  );
}

const ETAPAS: { quando: string; ini: string; fim: string; o: string }[] = [
  { quando: "S1 · 01–07/10", ini: "2026-10-01", fim: "2026-10-07", o: "Front novo, rebranding e walk-forward" },
  { quando: "S2 · 08–14/10", ini: "2026-10-08", fim: "2026-10-14", o: "Modelos corrigidos, fila inteligente, meta" },
  { quando: "S3 · 15–21/10", ini: "2026-10-15", fim: "2026-10-21", o: "API, ingestão, deploy com TLS e agente no painel" },
  { quando: "24/10", ini: "2026-10-22", fim: "2026-10-24", o: "FIAP NEXT" },
];

function Proximos() {
  const hoje = new Date().toISOString().slice(0, 10);
  return (
    <CenaCentro>
      <Sobrancelha>Próximos passos</Sobrancelha>
      <Titulo>Do protótipo ao produto em quatro semanas</Titulo>
      <ol className="grid w-full gap-4 text-left sm:grid-cols-2 lg:grid-cols-4">
        {ETAPAS.map((e, i) => {
          const agora = hoje >= e.ini && hoje <= e.fim;
          const feito = hoje > e.fim;
          return (
            <li key={e.quando} className={(agora ? "anel-agente " : "") + "painel entra flex flex-col gap-2 p-5"} style={{ "--ordem": i + 2 } as React.CSSProperties}>
              <p className={(agora ? "text-agente " : feito ? "text-ok " : "text-muted ") + "font-mono text-[13px]"}>
                {e.quando}
                {agora ? " · agora" : feito ? " · feito" : ""}
              </p>
              <p className="text-[17px] leading-snug font-semibold">{e.o}</p>
            </li>
          );
        })}
      </ol>
    </CenaCentro>
  );
}

function Fim() {
  return (
    <CenaCentro>
      <Titulo grande>LocalOps</Titulo>
      <p className="max-w-[820px] text-[clamp(20px,2.2vw,30px)] leading-snug text-[#C7CCD6]">
        Separa o sinal do ruído, prevê o trabalho humano, protege a meta e avisa antes.
      </p>
      <div className="flex flex-col items-center gap-3 sm:flex-row sm:gap-6">
        <QrCode tamanho={180} />
        <div className="flex flex-col gap-1 text-center sm:text-left">
          <p className="text-[20px] font-semibold">Abra no celular</p>
          <p className="text-agente font-mono text-[16px]">{SITE.replace("https://", "")}</p>
          <p className="text-muted text-[14px]">Paladinos · Challenge Locaweb × FIAP 2026</p>
        </div>
      </div>
    </CenaCentro>
  );
}

const PICOS: { data: string; o: string; valor: number; humano: boolean }[] = [
  { data: "22/09/2025", o: "pico de alarmes", valor: 1431, humano: false },
  { data: "16/10/2025", o: "pico de trabalho humano", valor: 433, humano: true },
];

function Pico() {
  return (
    <CenaCentro>
      <Sobrancelha>O que os dados mostram</Sobrancelha>
      <Titulo>O dia com mais alarmes não foi o dia com mais trabalho</Titulo>
      <ul className="flex w-full max-w-[900px] flex-col gap-5 text-left">
        {PICOS.map((p, i) => (
          <li key={p.data} className="flex flex-col gap-2">
            <p className="text-muted flex justify-between text-[15px]">
              <span>
                <span className="text-texto font-semibold">{p.data}</span> · {p.o}
              </span>
              <span className={(p.humano ? "text-amber-300 " : "text-texto ") + "text-[22px] font-semibold"}>
                <Conta ate={p.valor} atraso={500 + i * 900} />
              </span>
            </p>
            <span className="bg-borda block h-4 overflow-hidden rounded-full">
              <span
                className={(p.humano ? "ponto-humano " : "bg-indigo-300 ") + "barra-cresce block h-full rounded-full"}
                style={{ width: `${(p.valor / 1431) * 100}%`, animationDelay: `${500 + i * 900}ms` }}
              />
            </span>
          </li>
        ))}
      </ul>
      <p className="text-muted max-w-[760px] text-[17px] leading-relaxed">
        Correlação diária entre volume e trabalho humano: <span className="text-texto font-semibold">r = 0,28</span>, em {nf.format(122543)} registros reais de 2025. Prever alarmes não diz quantas pessoas o turno precisa.
      </p>
    </CenaCentro>
  );
}

const CENAS: { id: string; rotulo: string; ms: number; render: () => ReactNode }[] = [
  { id: "abertura", rotulo: "LocalOps", ms: 5000, render: () => <Abertura /> },
  { id: "problema", rotulo: "O problema", ms: 5600, render: () => <Problema /> },
  { id: "pico", rotulo: "O que os dados mostram", ms: 6000, render: () => <Pico /> },
  { id: "solucao", rotulo: "A solução", ms: 5600, render: () => <OQueE /> },
  { id: "fluxo", rotulo: "Como funciona", ms: 5600, render: () => <ComoFunciona /> },
  ...TOUR.map((t) => ({ id: t.id, rotulo: t.rotulo, ms: t.destaques.length * PASSO + 1100, render: () => <CenaTour t={t} /> })),
  { id: "agentes-proativos", rotulo: "Agentes proativos", ms: 6300, render: () => <AgentesProativos /> },
  { id: "arquitetura", rotulo: "Arquitetura", ms: 6300, render: () => <Arquitetura /> },
  { id: "resultados", rotulo: "Resultados", ms: 7700, render: () => <Resultados /> },
  { id: "proximos", rotulo: "Próximos passos", ms: 5600, render: () => <Proximos /> },
  { id: "fim", rotulo: "Abra no celular", ms: 6300, render: () => <Fim /> },
];

const SAIDA_MS = 450; // the outgoing scene fades while the next one comes in: one continuous take

export default function Apresentacao() {
  const [cena, setCena] = useState(0);
  const [saindo, setSaindo] = useState<number | null>(null);
  const [tocando, setTocando] = useState(true);
  const total = CENAS.length;
  const atual = useRef(0);

  const ir = (n: number) => {
    const destino = (n + total) % total;
    if (destino === atual.current) return;
    setSaindo(atual.current);
    atual.current = destino;
    setCena(destino);
  };
  const irRef = useRef(ir);
  irRef.current = ir;

  useEffect(() => {
    if (saindo === null) return;
    const t = setTimeout(() => setSaindo(null), SAIDA_MS);
    return () => clearTimeout(t);
  }, [saindo, cena]);

  useEffect(() => {
    if (!tocando) return;
    const t = setTimeout(() => irRef.current(cena + 1), CENAS[cena].ms);
    return () => clearTimeout(t);
  }, [cena, tocando]);

  useEffect(() => {
    const tecla = (e: KeyboardEvent) => {
      if (e.key === "ArrowRight") irRef.current(atual.current + 1);
      else if (e.key === "ArrowLeft") irRef.current(atual.current - 1);
      else if (e.key === " " && !(e.target instanceof HTMLButtonElement)) {
        e.preventDefault();
        setTocando((t) => !t);
      } else if (e.key === "Escape") window.location.hash = "#/cockpit";
    };
    window.addEventListener("keydown", tecla);
    return () => window.removeEventListener("keydown", tecla);
  }, []);

  const visiveis = saindo !== null && saindo !== cena ? [saindo, cena] : [cena];
  const fim = CENAS[cena].id === "fim";

  return (
    <div className="relative flex min-h-screen flex-col overflow-hidden">
      <div className="fundo-vivo pointer-events-none absolute inset-0" aria-hidden="true" />
      <div className="absolute inset-x-0 top-0 z-10 flex gap-1.5 px-6 pt-5" aria-hidden="true">
        {CENAS.map((c, i) => (
          <span key={c.id} className="bg-borda h-1 flex-1 overflow-hidden rounded-full">
            <span
              key={i === cena ? `on-${cena}-${tocando}` : `off-${i}`}
              className="block h-full rounded-full bg-indigo-300"
              style={{
                width: i < cena ? "100%" : i === cena ? undefined : "0%",
                animation: i === cena && tocando ? `encher ${c.ms}ms linear forwards` : undefined,
              }}
            />
          </span>
        ))}
      </div>

      <div className="relative flex flex-1">
        {visiveis.map((i) => (
          <main
            key={i}
            className={
              (i === cena ? "cena-entra relative flex-1 " : "cena-sai pointer-events-none absolute inset-0 ") +
              "flex items-center justify-center px-6 py-20 sm:px-10"
            }
            aria-live={i === cena ? "polite" : undefined}
            aria-hidden={i === cena ? undefined : true}
          >
            {CENAS[i].render()}
          </main>
        ))}
      </div>

      {/* Lower third, like a video chapter: where we are in the story. */}
      <div key={`legenda-${cena}`} className="legenda-entra absolute bottom-5 left-6 hidden items-center gap-3 sm:flex" aria-hidden="true">
        <span className="text-faint font-mono text-[13px] tabular-nums">
          {String(cena + 1).padStart(2, "0")} / {String(total).padStart(2, "0")}
        </span>
        <span className="bg-borda h-4 w-px" />
        <span className="text-muted text-[14px] font-medium">{CENAS[cena].rotulo}</span>
      </div>

      {!fim && (
        <div className="absolute right-6 bottom-5 hidden items-center gap-3 md:flex">
          <div className="text-right">
            <p className="text-[13px] font-medium">Abra no celular</p>
            <p className="text-faint font-mono text-[12px]">{SITE.replace("https://", "")}</p>
          </div>
          <QrCode tamanho={76} />
        </div>
      )}

      <div className="absolute inset-x-0 bottom-0 flex items-center justify-center gap-2 pb-5">
        <button type="button" aria-label="Cena anterior" onClick={() => ir(cena - 1)} className="text-muted hover:text-texto flex size-10 items-center justify-center rounded-full hover:bg-white/[0.06]">
          <ChevronLeft size={18} />
        </button>
        <button type="button" aria-label={tocando ? "Pausar" : "Tocar"} onClick={() => setTocando((t) => !t)} className="text-muted hover:text-texto flex size-10 items-center justify-center rounded-full hover:bg-white/[0.06]">
          {tocando ? <Pause size={18} /> : <Play size={18} />}
        </button>
        <button type="button" aria-label="Próxima cena" onClick={() => ir(cena + 1)} className="text-muted hover:text-texto flex size-10 items-center justify-center rounded-full hover:bg-white/[0.06]">
          <ChevronRight size={18} />
        </button>
        <a href="#/cockpit" aria-label="Sair do modo apresentação" className="text-muted hover:text-texto ml-4 flex size-10 items-center justify-center rounded-full hover:bg-white/[0.06]">
          <X size={18} />
        </a>
      </div>
    </div>
  );
}
