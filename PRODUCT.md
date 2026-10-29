# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

React + Vite + TypeScript + Tailwind + shadcn/ui + ECharts for the new front; FastAPI `/v1` for the API (decisions D06 and plan §3 in `docs/`). The Streamlit dashboard in `06_MVP_LocalOps/dashboard/` is the incumbent MVP and is being replaced.

## Users

Primary: the on-call operator of the Locaweb operations floor (NOC / SRE analyst) deciding what to act on now, during a shift, often on a wall screen and on a phone.

Secondary audiences (confirmed by context, not primary): the operations manager accountable for the OLA target, and visitors and judges at FIAP NEXT (24/10/2026, D18), who see the product running on real data in replay.

## Product Purpose

LocalOps is an AIOps copilot for incident operations. It filters alarm noise at the moment an alarm opens, forecasts tomorrow's and the week's human workload, projects the yearly OLA/KPI target, and explains the reason behind each number. Success: the on-call person acts on what needs a human and ignores what does not, before a peak or an OLA breach happens.

## Positioning

Proactive agents. LocalOps does not wait to be asked: its agents watch the queue, the forecast and the OLA target, and reach the on-call person where they already are (briefing, peak alert, breach risk), with the source of every claim. Dashboards are where you check; the agents are what make LocalOps different.

## Operating Context

- 24/7 incident operations with shifts; Locaweb ITSM data (122.543 incidents opened 2023–2025; the models and the panel use 2025).
- Volume regime changed in Sep/2025: ~766 alarms/day, 85,9% close with no intervention, ~108/day need a person (p90 179, peak 433 on 16/10/2025). Correlation between total volume and human load: r = 0,28.
- Obligatory forecasts: total, P2, P3 and KPI, D+1 and D+7 (challenge rules p.7–8).
- Replay: any day of Sep–Dec/2025 can be played as "today".
- Event setting: a booth at FIAP NEXT; product runs unattended on a large screen and opens by QR code on visitors' phones.

## Capabilities and Constraints

- Live (D15, D16, D19, D24–D26): D+1/D+7 forecast chosen by daily walk-forward (median of simple models), noise filter at alarm open (AUC 0,916 on Dec/2025; at the 97% recall target the queue drops from 855 to 384/day, keeping 95,3%), OLA target projection with probability per band, SHAP of the noise filter (SHAP tab), FastAPI + MCP, the OpenClaw agent `localops` (Grok) as the panel copilot with real PDF/Excel/HTML files, and the booth video as the presentation mode.
- Discontinued (D15): the risk classifiers and the Prophet + XGBoost ensemble of the Sprint 3 MVP.
- Planned: the proactive agents (shift briefing, peak alert, OLA guard) shown as "planejado" in the Agents tab.
- Decided: D11 put the proactive agent in the NEXT core scope; D19 and D24 changed that: the copilot in the panel is what runs, and the proactive agents stay planned.
- Constraints: feature freeze 21/10/2026; front on Vercel; must work offline at the booth (deterministic fallback); incident text is untrusted input.

## Brand Commitments

- Name: LocalOps (kept).
- The previous look (Streamlit dark navy with saturated blue, red, yellow, green, purple) is rejected. Three later directions (light instrument, dark graphite with amber, ultramarine with coral) were also rejected for style and color combination.
- No Locaweb branding presented as Locaweb's own.
- Pinned aesthetic (2026-10-05): dark premium at the craft level of Linear, Vercel and Raycast, with subtle glows and gradients. The "wow" lives in both surfaces: contained in the operator Cockpit, full in the booth presentation mode. The Livro de Passagem logbook palette (green, blue ink, red stamp, yellow highlighter) was rejected as dull; its mechanism (the agent writes the shift handover, the operator signs it) stays.

## Evidence on Hand

- Real data and metrics: `artefatos/metricas.json` and `artefatos/fila_shap.json` (current), `docs/PLANO_LocalOps_NEXT.md` (numbers recomputed 30/09/2026), spike `docs/spikes/spike_ruido.py`.
- No testimonials, customers, logos, or production usage. Do not invent them.

## Product Principles

1. Act before being asked: every screen and agent message leads to an action for the on-call person.
2. Every number carries its reason and its source.
3. Human load over raw volume: the number that matters is what needs a person.
4. Honest metrics: report what the model really achieved, including its limits.
5. Works without the internet at the booth.

## Accessibility & Inclusion

Readable at distance on a wall or booth screen and on a phone; WCAG 2.1 AA contrast.
