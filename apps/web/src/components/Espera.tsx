import { useEffect, useState } from "react";

/** Waiting text with elapsed seconds: the agent takes 20–40 s when it calls several tools. */
export function Espera() {
  const [s, setS] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setS((x) => x + 1), 1000);
    return () => clearInterval(t);
  }, []);
  return (
    <span role="status">
      O agente está consultando os dados… {s} s{s >= 25 ? " · com relatório leva até 40 s" : ""}
    </span>
  );
}
