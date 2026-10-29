import { Download, FileText } from "lucide-react";
import type { Arquivo } from "../agent/cliente";

function baixar(a: Arquivo) {
  // BOM so Excel opens the agent's CSV with the right accents.
  const corpo = a.base64 ? Uint8Array.from(atob(a.base64), (c) => c.charCodeAt(0)) : a.tipo === "text/csv" ? "﻿" + a.conteudo : a.conteudo;
  const url = URL.createObjectURL(new Blob([corpo], { type: a.base64 ? a.tipo : `${a.tipo};charset=utf-8` }));
  const link = Object.assign(document.createElement("a"), { href: url, download: a.nome });
  link.click();
  URL.revokeObjectURL(url);
}

const bytes = (a: Arquivo) => (a.base64 ? Math.floor((a.base64.length * 3) / 4) : new Blob([a.conteudo]).size);
const kb = (a: Arquivo) => `${Math.max(1, Math.round(bytes(a) / 1024)).toLocaleString("pt-BR")} KB`;

/** Files the agent sent in the conversation, one download button each. */
export function Arquivos({ arquivos, compacto = false }: { arquivos?: Arquivo[]; compacto?: boolean }) {
  if (!arquivos?.length) return null;
  return (
    <ul className={(compacto ? "max-w-[290px] " : "max-w-[420px] ") + "flex w-full flex-col gap-1.5"}>
      {arquivos.map((a) => (
        <li key={a.nome}>
          <button
            type="button"
            onClick={() => baixar(a)}
            className="bg-fundo border-borda hover:border-agente-1 flex w-full items-center gap-2.5 rounded-xl border px-3 py-2.5 text-left transition-colors"
          >
            <FileText size={16} className="text-agente shrink-0" aria-hidden="true" />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-[13px] font-medium">{a.nome}</span>
              <span className="text-faint block text-[11px]">{kb(a)}</span>
            </span>
            <Download size={15} className="text-muted shrink-0" aria-hidden="true" />
            <span className="sr-only">Baixar {a.nome}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}
