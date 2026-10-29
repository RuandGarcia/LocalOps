import { useEffect, useRef, useState, type DragEvent, type FormEvent, type KeyboardEvent } from "react";
import { ArrowUp, FileText, Loader2, Paperclip, X } from "lucide-react";
import { MAX_ANEXOS, MODO, lerAnexo, perguntar, type Anexo, type Mensagem } from "../agent/cliente";
import { diaIdx, useDados, useFiltro } from "../data/filtros";
import { TituloPagina, ordem } from "../components/ui";
import { Arquivos } from "../components/Arquivos";
import { Espera } from "../components/Espera";

const SUGESTOES = ["Gerar relatório do período", "Como está a meta de OLA?", "Onde agir agora?", "Quanto a fila cai com o filtro de ruído?"];
const kb = (b: number) => `${Math.max(1, Math.round(b / 1024)).toLocaleString("pt-BR")} KB`;

function Balao({ m }: { m: Mensagem }) {
  const voce = m.de === "voce";
  return (
    <div className={(voce ? "items-end self-end" : "items-start self-start") + " flex max-w-[min(680px,100%)] flex-col gap-1.5"}>
      {!!m.anexos?.length && (
        <ul className="flex flex-wrap justify-end gap-1.5">
          {m.anexos.map((a) => (
            <li key={a.nome} className="border-borda bg-superficie text-muted flex items-center gap-1.5 rounded-md border px-2 py-1 text-[12px]">
              <FileText size={13} aria-hidden="true" />
              {a.nome}
            </li>
          ))}
        </ul>
      )}
      <p
        className={
          (voce ? "bg-texto text-fundo rounded-br-sm " : "bg-superficie-2 border-borda rounded-bl-sm border ") +
          "rounded-2xl px-4 py-3 text-[15px] leading-relaxed whitespace-pre-line"
        }
      >
        {m.texto}
      </p>
      {m.relatorio && (
        <div className="bg-fundo border-borda w-full max-w-[420px] rounded-xl border p-4">
          <p className="mb-2.5 flex items-center gap-1.5 text-[14px] font-semibold">
            <FileText size={15} className="text-agente" aria-hidden="true" />
            {m.relatorio.titulo}
          </p>
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-[13px]">
            {m.relatorio.linhas.map(([k, v]) => (
              <div key={k} className="contents">
                <dt className="text-muted">{k}</dt>
                <dd className="text-right font-mono">{v}</dd>
              </div>
            ))}
          </dl>
        </div>
      )}
      <Arquivos arquivos={m.arquivos} />
      {(m.fonte || m.modo === "offline") && (
        <p className="text-faint pl-1 text-[12px]">
          {m.fonte && `Fonte: ${m.fonte}`}
          {m.modo === "offline" && `${m.fonte ? " · " : ""}resposta sem IA (agente fora do ar)`}
        </p>
      )}
    </div>
  );
}

const SAUDACAO: Mensagem = { de: "agente", texto: "Oi, equipe. Sou o agente localops. Pergunte sobre o turno, peça um relatório ou uma planilha, ou anexe um arquivo para eu analisar." };

/** `inicial` lets the booth presentation open the tab mid-conversation. */
export default function Chat({ inicial }: { inicial?: Mensagem[] } = {}) {
  const dados = useDados();
  const { filtro } = useFiltro();
  const [mensagens, setMensagens] = useState<Mensagem[]>(inicial ?? [SAUDACAO]);
  const [texto, setTexto] = useState("");
  const [anexos, setAnexos] = useState<Anexo[]>([]);
  const [pensando, setPensando] = useState(false);
  const [erro, setErro] = useState("");
  const [arrastando, setArrastando] = useState(false);
  const arquivoRef = useRef<HTMLInputElement>(null);
  const fimRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fimRef.current?.scrollIntoView({ block: "end" });
  }, [mensagens, pensando]);

  async function anexar(lista: FileList | null) {
    if (!lista?.length) return;
    const novos = await Promise.all([...lista].map(lerAnexo));
    setAnexos((a) => {
      const todos = [...a, ...novos.filter((n) => !a.some((x) => x.nome === n.nome))];
      // The agent reads at most 3 files per message: say so instead of dropping the 4th in silence.
      setErro(todos.length > MAX_ANEXOS ? `O agente lê até ${MAX_ANEXOS} arquivos por mensagem; ficaram os ${MAX_ANEXOS} primeiros.` : "");
      return todos.slice(0, MAX_ANEXOS);
    });
  }

  async function enviar(pergunta: string) {
    const p = pergunta.trim();
    if ((!p && !anexos.length) || pensando) return;
    const enviados = anexos;
    setMensagens((m) => [...m, { de: "voce", texto: p || "Segue anexo.", anexos: enviados }]);
    setTexto("");
    setAnexos([]);
    setErro("");
    setPensando(true);
    try {
      const r = await perguntar(p, enviados, { dados, gran: filtro.gran, hoje: diaIdx(filtro.ref) });
      setMensagens((m) => [...m, r]);
    } catch (e) {
      setErro(e instanceof Error ? e.message : "O agente não respondeu. Tente de novo.");
    } finally {
      setPensando(false);
    }
  }

  function aoEnviar(e: FormEvent) {
    e.preventDefault();
    enviar(texto);
  }

  function aoTeclar(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      enviar(texto);
    }
  }

  function aoSoltar(e: DragEvent) {
    e.preventDefault();
    setArrastando(false);
    anexar(e.dataTransfer.files);
  }

  return (
    <main
      className="px-4 py-6 sm:px-8 sm:py-8"
      onDragOver={(e) => {
        e.preventDefault();
        setArrastando(true);
      }}
      onDragLeave={(e) => e.currentTarget === e.target && setArrastando(false)}
      onDrop={aoSoltar}
    >
      <div className="mx-auto flex max-w-[880px] flex-col gap-5">
        <TituloPagina titulo="Chat">
          <p className="text-muted text-[13px]">
            {MODO === "demo" ? "Modo demonstração, com a base real de 2025" : "Agente OpenClaw localops"} · filtro de {dados.rotulo}
          </p>
        </TituloPagina>

        <section aria-label="Conversa com o agente localops" className="entra flex flex-col gap-4" style={ordem(1)} aria-live="polite">
          {mensagens.map((m, i) => (
            <Balao key={i} m={m} />
          ))}
          {mensagens.length === 1 && (
            <div className="flex flex-wrap gap-2">
              {SUGESTOES.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => enviar(s)}
                  className="text-agente border-borda rounded-full border px-3 py-1.5 text-[13px] hover:bg-white/[0.04]"
                >
                  {s}
                </button>
              ))}
            </div>
          )}
          {pensando && (
            <p className="text-muted flex items-center gap-2 text-[14px]">
              <Loader2 size={15} className="animate-spin" aria-hidden="true" />
              <Espera />
            </p>
          )}
          {erro && <p className="text-risco text-[14px]">{erro}</p>}
          <div ref={fimRef} />
        </section>

        <form
          onSubmit={aoEnviar}
          className={(arrastando ? "border-agente-1 " : "border-borda ") + "painel sticky bottom-4 flex flex-col gap-2 border p-3"}
        >
          {!!anexos.length && (
            <ul className="flex flex-wrap gap-1.5">
              {anexos.map((a) => (
                <li key={a.nome} className="bg-fundo border-borda flex items-center gap-1.5 rounded-md border py-1 pr-1 pl-2 text-[12px]">
                  <FileText size={13} className="text-agente" aria-hidden="true" />
                  {a.nome}
                  <span className="text-faint">{kb(a.tamanho)}</span>
                  <button
                    type="button"
                    onClick={() => setAnexos((l) => l.filter((x) => x.nome !== a.nome))}
                    aria-label={`Remover ${a.nome}`}
                    className="text-muted hover:text-texto flex size-6 items-center justify-center rounded hover:bg-white/[0.06]"
                  >
                    <X size={13} />
                  </button>
                </li>
              ))}
            </ul>
          )}
          <div className="flex items-end gap-2">
            <input ref={arquivoRef} type="file" multiple className="hidden" onChange={(e) => (anexar(e.target.files), (e.target.value = ""))} />
            <button
              type="button"
              onClick={() => arquivoRef.current?.click()}
              aria-label="Anexar arquivo"
              className="text-muted hover:text-texto flex size-10 shrink-0 items-center justify-center rounded-lg hover:bg-white/[0.06]"
            >
              <Paperclip size={17} />
            </button>
            <label htmlFor="chat-pagina-campo" className="sr-only">
              Mensagem para o agente
            </label>
            <textarea
              id="chat-pagina-campo"
              rows={1}
              value={texto}
              onChange={(e) => setTexto(e.target.value)}
              onKeyDown={aoTeclar}
              placeholder={arrastando ? "Solte os arquivos aqui" : "Pergunte ao agente ou arraste um arquivo"}
              className="bg-fundo border-borda placeholder:text-faint focus:border-agente-1 max-h-40 min-h-10 flex-1 resize-none rounded-lg border px-3 py-2 text-[15px] [field-sizing:content] outline-none"
            />
            <button
              type="submit"
              aria-label="Enviar"
              disabled={pensando || (!texto.trim() && !anexos.length)}
              className="bg-texto text-fundo flex size-10 shrink-0 items-center justify-center rounded-lg transition disabled:opacity-40"
            >
              <ArrowUp size={17} />
            </button>
          </div>
          <p className="text-faint px-1 text-[11px]">Texto, CSV, PDF, Excel e HTML vão para o agente. Peça um relatório e ele devolve em PDF, Excel ou HTML. Imagem ainda não é lida.</p>
        </form>
      </div>
    </main>
  );
}
