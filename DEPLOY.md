# LocalOps — deploy do painel na Vercel

O painel (`apps/web`, React + Vite) sobe sozinho, sem API: responde em **modo demonstração** com a base real de 2025 já agregada no código.

## Vercel

1. Suba esta pasta num repositório do GitHub e importe na Vercel.
2. **Root Directory:** `apps/web` (o framework Vite é detectado sozinho).
3. Build: `npm run build` · Output: `dist`.
4. Não precisa de variável de ambiente.

## Rodar local

```bash
cd apps/web
npm ci
npm run dev
```

## Opcional: ligar a API

`apps/api` é a API FastAPI (contrato `/v1`). Se você hospedar a API, defina `VITE_LOCALOPS_API=https://sua-api` na Vercel e o chat passa a perguntar a ela. Sem isso, o painel fica no modo demonstração.

## Direitos

© 2026 Equipe LocalOps (FIAP Enterprise Challenge). Todos os direitos reservados. Código publicado para consulta e apresentação; reutilização só com autorização da equipe.
