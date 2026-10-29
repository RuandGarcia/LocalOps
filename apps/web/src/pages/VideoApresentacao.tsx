import { useEffect, useRef, useState } from "react";
import { Maximize, MonitorPlay, Volume2, VolumeX, X } from "lucide-react";

// The booth presentation is the 73 s motion video (apps/video), not a live walkthrough. Browsers only
// autoplay muted, so sound is one click away. The interactive tour stays at #/apresentacao-interativa.
const BASE = import.meta.env.BASE_URL;
const VIDEO = `${BASE}video/localops-estande-1080p.mp4`;
const POSTER = `${BASE}video/localops-estande-poster.jpg`;

export default function VideoApresentacao() {
  const ref = useRef<HTMLVideoElement>(null);
  const [mudo, setMudo] = useState(true);
  const [parado, setParado] = useState(false);

  useEffect(() => {
    const tecla = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !document.fullscreenElement) window.location.hash = "#/cockpit";
      else if (e.key === "f" || e.key === "F") telaCheia();
      else if (e.key === "m" || e.key === "M") alternarSom();
    };
    window.addEventListener("keydown", tecla);
    return () => window.removeEventListener("keydown", tecla);
  }, []);

  function alternarSom() {
    const v = ref.current;
    if (!v) return;
    v.muted = !v.muted;
    setMudo(v.muted);
    if (v.paused) v.play().catch(() => setParado(true));
  }

  function telaCheia() {
    const el = document.documentElement;
    if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
    else el.requestFullscreen?.().catch(() => {});
  }

  const botao = "border-borda bg-superficie/80 text-muted hover:text-texto flex min-h-10 items-center gap-2 rounded-full border px-4 text-[13px] backdrop-blur transition-colors";

  return (
    <main className="bg-fundo relative flex h-screen w-screen items-center justify-center overflow-hidden">
      <video
        ref={ref}
        src={VIDEO}
        poster={POSTER}
        autoPlay
        muted
        loop
        playsInline
        onPause={() => setParado(true)}
        onPlay={() => setParado(false)}
        className="h-full w-full object-contain"
        aria-label="Vídeo de apresentação do LocalOps, 73 segundos em loop"
      />
      {parado && (
        <button
          type="button"
          onClick={() => ref.current?.play()}
          className="orbe-agente absolute flex size-20 items-center justify-center rounded-full text-[#08090B]"
          aria-label="Tocar o vídeo"
        >
          <MonitorPlay size={30} />
        </button>
      )}
      <a href="#/cockpit" aria-label="Sair do modo apresentação" className="text-muted hover:text-texto absolute top-4 right-4 flex size-10 items-center justify-center rounded-full bg-black/30 hover:bg-white/[0.08]">
        <X size={20} />
      </a>
      <div className="absolute bottom-4 left-1/2 flex -translate-x-1/2 flex-wrap items-center justify-center gap-2 opacity-70 transition-opacity hover:opacity-100 focus-within:opacity-100">
        <button type="button" onClick={alternarSom} className={botao}>
          {mudo ? <VolumeX size={15} aria-hidden="true" /> : <Volume2 size={15} aria-hidden="true" />}
          {mudo ? "Ativar som" : "Sem som"}
        </button>
        <button type="button" onClick={telaCheia} className={botao}>
          <Maximize size={15} aria-hidden="true" />
          Tela cheia
        </button>
        <a href="#/apresentacao-interativa" className={botao + " no-underline"}>
          Versão interativa
        </a>
      </div>
    </main>
  );
}
