import { useEffect, useRef, useState, type FormEvent } from "react";
import { ArrowUp, FileText, MessageCircle, X } from "lucide-react";
import { perguntar, type Mensagem } from "../agent/cliente";
import { diaIdx, useDados, useFiltro } from "../data/filtros";
import { Arquivos } from "./Arquivos";
import { Espera } from "./Espera";

const SUGESTOES = ["Gerar relatório do período", "Onde agir agora?", "Quanto vem amanhã?", "Como está a meta de OLA?"];

export default function ChatAgente() {
  const [aberto, setAberto] = useState(false);
  const [texto, setTexto] = useState("");
  const [mensagens, setMensagens] = useState<Mensagem[]>([
    { de: "agente", texto: "Oi, equipe. Sou o agente localops. Pergunte sobre o turno ou peça um relatório e eu mando o arquivo." },
  ]);
  const [pensando, setPensando] = useState(false);
  const dados = useDados();
  const { filtro } = useFiltro();
  const fimRef = useRef<HTMLDivElement>(null);
  const campoRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (aberto) campoRef.current?.focus();
  }, [aberto]);

  useEffect(() => {
    fimRef.current?.scrollIntoView({ block: "end" });
  }, [mensagens, pensando]);

  useEffect(() => {
    if (!aberto) return;
    const fechar = (e: KeyboardEvent) => e.key === "Escape" && setAberto(false);
    window.addEventListener("keydown", fechar);
    return () => window.removeEventListener("keydown", fechar);
  }, [aberto]);

  async function enviar(pergunta: string) {
    const p = pergunta.trim();
    if (!p || pensando) return;
    setMensagens((m) => [...m, { de: "voce", texto: p }]);
    setTexto("");
    setPensando(true);
    try {
      const r = await perguntar(p, [], { dados, gran: filtro.gran, hoje: diaIdx(filtro.ref) });
      setMensagens((m) => [...m, r]);
    } catch (e) {
      setMensagens((m) => [...m, { de: "agente", texto: e instanceof Error ? e.message : "O agente não respondeu. Tente de novo." }]);
    } finally {
      setPensando(false);
    }
  }

  function aoEnviar(e: FormEvent) {
    e.preventDefault();
    enviar(texto);
  }

  return (
    <div className="fixed right-4 bottom-4 z-50 flex flex-col items-end gap-3 sm:right-6 sm:bottom-6">
      {aberto && (
        <section
          aria-label="Chat com o agente localops"
          className="painel anel-agente flex h-[min(560px,calc(100vh-7rem))] w-[min(380px,calc(100vw-2rem))] flex-col"
          data-visto="true"
        >
          <header className="border-borda flex items-center gap-3 border-b px-4 py-3">
            <span className="orbe-agente size-7 rounded-full" aria-hidden="true" />
            <div className="flex flex-1 flex-col">
              <p className="text-[14px] font-semibold">Agente localops</p>
              <p className="text-muted text-[12px]">Pergunte ou peça relatório · anexos na aba Chat</p>
            </div>
            <button
              type="button"
              onClick={() => setAberto(false)}
              aria-label="Fechar chat"
              className="text-muted hover:text-texto flex size-9 items-center justify-center rounded-md hover:bg-white/[0.06]"
            >
              <X size={16} />
            </button>
          </header>

          <div className="flex flex-1 flex-col gap-3 overflow-y-auto px-4 py-4" aria-live="polite">
            {mensagens.map((m, i) => (
              <div key={i} className={m.de === "voce" ? "self-end" : "self-start"}>
                <p
                  className={
                    (m.de === "voce" ? "bg-texto text-fundo rounded-br-sm " : "bg-superficie-2 border-borda rounded-bl-sm border ") +
                    "max-w-[290px] rounded-2xl px-3.5 py-2.5 text-[14px] leading-relaxed"
                  }
                >
                  {m.texto}
                </p>
                {m.relatorio && (
                  <div className="bg-fundo border-borda mt-2 max-w-[290px] rounded-xl border p-3">
                    <p className="mb-2 flex items-center gap-1.5 text-[13px] font-semibold">
                      <FileText size={14} className="text-agente" aria-hidden="true" />
                      {m.relatorio.titulo}
                    </p>
                    <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-[12px]">
                      {m.relatorio.linhas.map(([k, v]) => (
                        <div key={k} className="contents">
                          <dt className="text-muted">{k}</dt>
                          <dd className="text-right font-mono">{v}</dd>
                        </div>
                      ))}
                    </dl>
                  </div>
                )}
                {!!m.arquivos?.length && (
                  <div className="mt-2">
                    <Arquivos arquivos={m.arquivos} compacto />
                  </div>
                )}
                {m.fonte && <p className="text-faint mt-1 pl-1 text-[11px]">Fonte: {m.fonte}</p>}
              </div>
            ))}
            {mensagens.length === 1 && (
              <div className="mt-1 flex flex-wrap gap-2">
                {SUGESTOES.map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => enviar(s)}
                    className="text-agente border-borda hover:bg-white/[0.04] rounded-full border px-3 py-1.5 text-[13px]"
                  >
                    {s}
                  </button>
                ))}
              </div>
            )}
            {pensando && <p className="text-muted text-[13px]"><Espera /></p>}
            <div ref={fimRef} />
          </div>

          <form onSubmit={aoEnviar} className="border-borda flex items-center gap-2 border-t p-3">
            <label htmlFor="chat-campo" className="sr-only">
              Mensagem para o agente
            </label>
            <input
              id="chat-campo"
              ref={campoRef}
              value={texto}
              onChange={(e) => setTexto(e.target.value)}
              placeholder="Pergunte ao agente"
              className="bg-fundo border-borda placeholder:text-faint focus:border-agente-1 min-h-10 flex-1 rounded-lg border px-3 text-[14px] outline-none"
            />
            <button
              type="submit"
              aria-label="Enviar"
              disabled={pensando || !texto.trim()}
              className="bg-texto text-fundo flex size-10 items-center justify-center rounded-lg transition disabled:opacity-40"
            >
              <ArrowUp size={16} />
            </button>
          </form>
        </section>
      )}

      <button
        type="button"
        onClick={() => setAberto((a) => !a)}
        aria-expanded={aberto}
        aria-label={aberto ? "Fechar chat com o agente" : "Abrir chat com o agente"}
        className="orbe-agente flex size-14 items-center justify-center rounded-full text-[#08090B] transition hover:scale-105"
      >
        {aberto ? <X size={22} strokeWidth={2.25} /> : <MessageCircle size={22} strokeWidth={2.25} />}
      </button>
    </div>
  );
}
