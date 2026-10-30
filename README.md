# LocalOps: copiloto de AIOps para a operação de incidentes

🔗 **Painel ao vivo:** [localops-ten.vercel.app](https://localops-ten.vercel.app) (modo demonstração com a base real de 2025)

Challenge AIOps · Locaweb × FIAP 2026 · Equipe Paladinos · Turma 2TSCOA

O LocalOps faz quatro coisas pelo plantonista:

- filtra o ruído de alarmes no momento em que o alarme abre;
- prevê a carga humana de amanhã (D+1) e da semana (D+7);
- projeta a meta anual de OLA/KPI;
- explica o motivo de cada número com SHAP.

O objetivo é que o plantonista aja no que precisa de uma pessoa e ignore o que não precisa, antes de um pico ou de uma violação de OLA.

## O que tem neste repositório

| Pasta | O que é |
| --- | --- |
| `apps/web/` | **Dashboard novo** em React, Vite, TypeScript e Tailwind. Funciona sozinho em modo demonstração, com a base real de 2025 já agregada no código. |
| `apps/api/` | API FastAPI (contrato `/v1`), servidor MCP e o copiloto. Gera relatórios em PDF, HTML e Excel. |
| `packages/localops_ml/` | Pacote de ML: ingestão, fila (filtro de ruído), previsão D+1/D+7, agregados e SHAP, com testes. |
| `artefatos/` | JSONs que alimentam o painel: métricas, previsão, replay, fila, SHAP, KPI e tendências. |
| `scripts/` | `build_agregados.py` gera os agregados do painel a partir da base. `kit_offline.ps1` monta o kit offline do estande. |
| `DEPLOY.md` | Passo a passo do deploy do painel na Vercel. |
| `PRODUCT.md` | Visão de produto: usuários, propósito, princípios e decisões. |

## Telas do dashboard

| Tela | Para quê |
| --- | --- |
| **Cockpit** | Visão do plantão: o que precisa de ação agora |
| **Previsão e replay** | Previsão D+1/D+7, com qualquer dia de set–dez/2025 tocado como "hoje" |
| **Tendências** | Evolução diária do volume e da carga humana |
| **Meta de OLA** | Projeção da meta anual, com probabilidade por faixa |
| **Fila e onde agir** | Filtro de ruído e os alarmes que precisam de uma pessoa |
| **SHAP** | Por que cada alarme foi classificado como ruído ou não |
| **Agentes** | Agentes proativos (briefing de turno, alerta de pico, guarda de OLA). Estão planejados. |
| **Chat** | Copiloto que responde sobre os dados e gera arquivos |

Há também o **modo apresentação**, com o vídeo do estande do FIAP NEXT.

## Resultados principais (base 2025)

- **Filtro de ruído:** AUC de 0,916 em dez/2025. Com a meta de 97% de recall, a fila cai de 855 para 384 alarmes/dia e mantém 95,3% do que precisa de ação.
- **Contexto:** desde set/2025 são cerca de 766 alarmes/dia, mas 85,9% fecham sem intervenção. Só uns 108/dia precisam de uma pessoa.
- **Previsão:** D+1 e D+7 para total, P2, P3 e KPI. O modelo é escolhido por walk-forward diário, usando a mediana de modelos simples.

Este painel substitui o MVP da Sprint 4 (dashboard Streamlit com Prophet + XGBoost e classificadores de risco), que foi descontinuado. O código antigo continua no histórico do git.

## Como rodar

**Dashboard (não precisa de API):**

```bash
cd apps/web
npm ci
npm run dev
```

**API (opcional):**

```bash
cd apps/api
pip install -e .
uvicorn localops_api.api:app --reload
```

Para o painel conversar com a API, crie `apps/web/.env.local` com `VITE_LOCALOPS_API=http://localhost:8000`. Sem isso, o painel fica no modo demonstração.

**Deploy:** veja o [DEPLOY.md](DEPLOY.md). Na Vercel, use Root Directory = `apps/web`.

## Direitos

© 2026 Equipe LocalOps (FIAP Enterprise Challenge). Todos os direitos reservados. O código está publicado para consulta e apresentação. Reutilização só com autorização da equipe.
