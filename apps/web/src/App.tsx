import { useEffect, useState } from "react";
import { BookOpenCheck, CalendarClock, Gauge, ListFilter, Bot, MessagesSquare, MonitorPlay, ScanSearch, TrendingUp, type LucideIcon } from "lucide-react";
import Cockpit from "./pages/Cockpit";
import Fila from "./pages/Fila";
import Previsao from "./pages/Previsao";
import MetaOla from "./pages/MetaOla";
import Agentes from "./pages/Agentes";
import Tendencias from "./pages/Tendencias";
import Apresentacao from "./pages/Apresentacao";
import VideoApresentacao from "./pages/VideoApresentacao";
import Chat from "./pages/Chat";
import Shap from "./pages/Shap";
import ChatAgente from "./components/ChatAgente";
import Campainha from "./components/Campainha";
import FiltroBarra from "./components/FiltroBarra";
import { FILTRO_INICIAL, FiltroCtx } from "./data/filtros";

const ROTAS: { id: string; rotulo: string; icone: LucideIcon; pagina: () => JSX.Element }[] = [
  { id: "cockpit", rotulo: "Cockpit", icone: BookOpenCheck, pagina: Cockpit },
  { id: "previsao", rotulo: "Previsão e replay", icone: CalendarClock, pagina: Previsao },
  { id: "tendencias", rotulo: "Tendências", icone: TrendingUp, pagina: Tendencias },
  { id: "meta", rotulo: "Meta de OLA", icone: Gauge, pagina: MetaOla },
  { id: "fila", rotulo: "Fila e onde agir", icone: ListFilter, pagina: Fila },
  { id: "shap", rotulo: "SHAP", icone: ScanSearch, pagina: Shap },
  { id: "agentes", rotulo: "Agentes", icone: Bot, pagina: Agentes },
  { id: "chat", rotulo: "Chat", icone: MessagesSquare, pagina: Chat },
];

// "#/shap?alarme=INC…" opens a tab with a parameter.
const rotaAtual = () => ROTAS.find((r) => `#/${r.id}` === window.location.hash.split("?")[0]) ?? ROTAS[0];

function Marca() {
  return (
    <div className="flex items-center gap-2.5">
      <svg width="24" height="24" viewBox="0 0 24 24" aria-hidden="true">
        <defs>
          <linearGradient id="marca-g" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="#818CF8" />
            <stop offset="1" stopColor="#22D3EE" />
          </linearGradient>
        </defs>
        <rect x="1" y="1" width="22" height="22" rx="6" fill="url(#marca-g)" />
        <path d="M6 13.5h3l2-5 2.5 9 2-4H18" fill="none" stroke="#08090B" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      <span className="text-[16px] font-semibold tracking-[-0.01em]">LocalOps</span>
    </div>
  );
}

export default function App() {
  const [rota, setRota] = useState(rotaAtual);
  const [filtro, setFiltro] = useState(FILTRO_INICIAL);

  useEffect(() => {
    const mudou = () => {
      setRota(rotaAtual());
      window.scrollTo(0, 0);
    };
    window.addEventListener("hashchange", mudou);
    return () => window.removeEventListener("hashchange", mudou);
  }, []);

  const Pagina = rota.pagina;
  // "Modo apresentação" plays the booth video; the interactive walkthrough lives one link away.
  const modo = () => (window.location.hash === "#/apresentacao" ? "video" : window.location.hash === "#/apresentacao-interativa" ? "interativa" : null);
  const [apresentando, setApresentando] = useState(modo);
  useEffect(() => {
    const mudou = () => setApresentando(modo());
    window.addEventListener("hashchange", mudou);
    return () => window.removeEventListener("hashchange", mudou);
  }, []);

  if (apresentando)
    return (
      <FiltroCtx.Provider value={{ filtro, setFiltro }}>
        {apresentando === "video" ? <VideoApresentacao /> : <Apresentacao />}
      </FiltroCtx.Provider>
    );

  return (
    <FiltroCtx.Provider value={{ filtro, setFiltro }}>
    <div className="min-h-screen md:grid md:grid-cols-[232px_minmax(0,1fr)]">
      <aside className="bg-trilho/80 border-borda flex flex-col border-b md:min-h-screen md:border-r md:border-b-0">
        <div className="px-4 pt-5 pb-4">
          <Marca />
        </div>
        <nav aria-label="Principal" className="px-2 pb-2 md:pb-0">
          <ul className="flex gap-0.5 overflow-x-auto [scrollbar-width:none] md:flex-col md:overflow-visible">
            {ROTAS.map(({ id, rotulo, icone: Icone }) => {
              const ativo = rota.id === id;
              return (
                <li key={id}>
                  <a
                    href={`#/${id}`}
                    aria-current={ativo ? "page" : undefined}
                    className={
                      (ativo ? "text-texto bg-white/[0.06] " : "text-muted hover:text-texto hover:bg-white/[0.04] ") +
                      "flex items-center gap-2.5 rounded-md px-2.5 py-2 text-[14px] whitespace-nowrap no-underline transition-colors"
                    }
                  >
                    <Icone size={16} strokeWidth={1.75} aria-hidden="true" />
                    {rotulo}
                  </a>
                </li>
              );
            })}
          </ul>
        </nav>
        <div className="mt-auto hidden flex-col gap-3 px-3 pt-8 pb-5 md:flex">
          <a
            href="#/apresentacao"
            className="border-borda bg-superficie text-muted hover:text-texto flex items-center gap-2.5 rounded-md border px-2.5 py-2 text-[13px] no-underline transition-colors"
          >
            <MonitorPlay size={16} strokeWidth={1.75} aria-hidden="true" />
            Modo apresentação
          </a>
          <p className="text-muted px-1 text-[12px]">Turno 08h–20h · plantão N2</p>
        </div>
      </aside>

      <div className="min-w-0">
        <header className="border-borda bg-fundo/75 z-40 md:sticky md:top-0 flex flex-col gap-2.5 border-b px-4 py-3 backdrop-blur-md sm:px-8">
          <div className="flex items-center gap-3">
            <p className="text-muted text-[13px]">
              Plantão N2 <span className="text-faint px-1">/</span> <span className="text-texto">{rota.rotulo}</span>
            </p>
            <div className="ml-auto">
              <Campainha />
            </div>
          </div>
          <FiltroBarra />
        </header>
        <Pagina key={rota.id} />
      </div>

      {rota.id !== "chat" && <ChatAgente />}
    </div>
    </FiltroCtx.Provider>
  );
}
