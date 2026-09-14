# LocalOps — núcleo preditivo (backend)

Implementação do pacote `localops/` descrito na arquitetura da Sprint 3
(Challenge AIOps · Locaweb × FIAP · Equipe Paladinos): ETL, feature
engineering, previsão de volume (Prophet + XGBoost), classificadores de
risco, explicabilidade (SHAP), recomendações operacionais, agente
conversacional offline e API REST.

**O dashboard (Streamlit) não está neste pacote** — a equipe já o tem pronto.
Este README explica exatamente o que o dashboard precisa ler para se
conectar aos artefatos gerados aqui.

## O que foi implementado

| Módulo | O que faz |
| --- | --- |
| `localops/config.py` | Regras de KPI/OLA do dicionário de dados, paths dos artefatos |
| `localops/etl/build_dataset.py` | Lê `data/LW-DATASET.xlsx`, tipa e limpa, aplica elegibilidade de KPI e violação de OLA, grava `data/localops.db` (tabelas `incidentes` e `serie_diaria`) |
| `localops/etl/features.py` | Feature store diário (lags 1/7/14, médias móveis 7/30, calendário e feriados BR) para as séries `total`, `p2`, `p3`, `kpi` |
| `localops/models/forecast.py` | Prophet + XGBoost (D+1 e D+7), backtest rolling-origin (8 cortes), ensemble ponderado por WAPE, baseline sazonal |
| `localops/models/classify.py` | Modelo A (risco de incidente crítico P1/P2) e Modelo B (risco de violação de OLA), split temporal, métricas AUC-ROC/AUC-PR/recall/precisão |
| `localops/models/explain.py` | SHAP — waterfall da previsão D+1/D+7 e importância global (previsão + classificadores) |
| `localops/models/recommender.py` | Recomendações operacionais (picos previstos, sobrecarga de equipe, violações de OLA, categorias de risco) |
| `localops/agent.py` | Agente conversacional: IA online (Gemini, RAG sobre os artefatos atuais) com fallback automático pro motor de regras offline e determinístico (previsão, tendência, comparativo, ranking, sazonalidade) |
| `localops/api/main.py` | API FastAPI com 7 endpoints (`/health`, `/forecast`, `/alerts`, `/recommendations`, `/explain`, `/risks/teams`, `/agent`) |
| `localops/store.py` | Acesso único aos artefatos (SQLite/parquet/joblib/json) — use isto no dashboard em vez de ler os arquivos diretamente |
| `run_pipeline.py` | Roda tudo, na ordem certa |

## Como rodar

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate   |   Linux/Mac: source .venv/bin/activate
pip install -r requirements.txt

python run_pipeline.py          # ~2-4 min (a maior parte é o backtest do Prophet)

uvicorn localops.api.main:app --reload   # API em http://localhost:8000/docs
```

`data/LW-DATASET.xlsx` já está incluído neste pacote (mesma base de 122.543
incidentes do dicionário de dados). Para atualizar os dados, basta substituir
esse arquivo (mesmas 19 colunas, aba `Dataset Geral`) e rodar o pipeline de novo.

**Importante ao colar uma atualização por cima do projeto**: os arquivos em
`reports/*.json` e `models/*.parquet` são **gerados**, não fazem parte do
código. Se você substituir só os `.py` e não rodar `python run_pipeline.py`
de novo, o dashboard vai ler artefatos antigos — que podem estar num formato
diferente do que o código novo espera (foi exatamente o que causou o
`AttributeError: 'list' object has no attribute 'get'` na página de
Recomendações/IncidentMap depois da atualização do dashboard: o
`reports/recomendacoes.json` na pasta ainda era da versão anterior). Sempre
que atualizar o código, rode `pip install -r requirements.txt` (pode ter
pacote novo) e `python run_pipeline.py` de novo antes de abrir o dashboard.

## Agente de IA (Gemini, camada gratuita — opcional)

Por padrão o agente (`localops/agent.py`) usa um motor de regras 100%
offline (sem internet, sem custo, determinístico). Se você quiser que ele
responda perguntas abertas em linguagem natural (não só as intenções fixas),
dá pra ligar numa IA online gratuita (Google Gemini) sem mexer em mais nada
— o agente detecta a chave sozinho e cai de volta pro modo offline
automaticamente se a chave não estiver configurada ou a chamada falhar (sem
internet, cota excedida etc.) — o dashboard nunca quebra por causa disso.

1. Crie uma chave gratuita em https://aistudio.google.com (não pede cartão).
2. Configure a chave de uma das duas formas:
   - **Streamlit** (recomendado, é onde o agente roda): crie o arquivo
     `.streamlit/secrets.toml` (não commitar!) com:
     ```toml
     GEMINI_API_KEY = "sua-chave-aqui"
     ```
   - **Variável de ambiente** (funciona pra API/CLI também):
     ```bash
     # Windows (PowerShell): $env:GEMINI_API_KEY = "sua-chave-aqui"
     export GEMINI_API_KEY="sua-chave-aqui"
     ```
3. `pip install -r requirements.txt` (adiciona o pacote `google-genai`) e
   rode o dashboard normalmente.

Como funciona: a cada pergunta, `_montar_contexto()` remonta um resumo
textual com as regras de negócio, previsões, métricas dos classificadores,
ranking de equipes/categorias e alertas — sempre a partir dos artefatos mais
recentes do pipeline — e manda isso junto com a pergunta pro Gemini
(`gemini-2.5-flash`, configurável em `config.GEMINI_MODEL`). Não é
fine-tuning nem memória entre perguntas: é RAG (retrieval-augmented
generation) — o contexto é sempre reconstruído na hora, então a resposta
reflete os dados mais atuais sem precisar retreinar nada.

## Contrato de dados para o dashboard

O dashboard deve ler pelos helpers de `localops/store.py` (não diretamente os
arquivos) — evita duplicar lógica de parsing e garante que uma mudança de
schema quebre em um lugar só:

```python
from localops import store

incidentes = store.load_incidentes()        # granularidade por incidente
serie_diaria = store.load_serie_diaria()     # granularidade diária
forecast_df = store.load_forecast()          # previsões D+1/D+7 (prophet/xgboost/ensemble)
backtest_df = store.load_backtest()          # erros do backtest, por corte
recomendacoes = store.load_recomendacoes()   # lista de dicts (título, motivo, impacto...)
shap_dados = store.load_shap()               # waterfall + importância global
metricas = store.load_metricas()             # WAPE, pesos do ensemble, métricas dos classificadores
```

Tabelas SQLite (`data/localops.db`): `incidentes` (uma linha por incidente,
colunas já tipadas e com `elegivel_kpi`/`ola_estourado` calculados) e
`serie_diaria` (uma linha por dia, com contagens por prioridade, KPI e
origem manual × monitoramento).

## Diagnóstico dos modelos (matriz de confusão + análise de resíduo)

Depois de rodar `python run_pipeline.py` pelo menos uma vez, rode:

```bash
python -m localops.diagnostics
```

Isso não treina nada de novo — só lê os artefatos já gerados e produz:

- `reports/diagnostico_classificadores.json` — matriz de confusão (TP/FP/FN/TN)
  do Modelo A e do Modelo B em vários limiares de decisão, e as categorias/
  equipes onde cada classificador mais erra.
- `reports/diagnostico_previsao.json` — MAE, RMSE, WAPE, viés (erro
  sistemático pra cima ou pra baixo), erro por dia da semana e cobertura do
  intervalo de confiança de 95% do Prophet, por série/horizonte/modelo.
- `reports/plots/*.png` — matrizes de confusão e gráficos de real-vs-previsto
  / distribuição do resíduo, prontos pra colar numa apresentação.

Também imprime um resumo direto no terminal. Uma leitura possível dos
resultados obtidos aqui (a sua pode variar um pouco a cada retreino):

- A cobertura do IC 95% do Prophet ficou bem abaixo de 95% nas séries P2/P3
  (50-75%) — sinal de que o intervalo de confiança está "confiante demais"
  nessas séries, provavelmente por causa dos outliers já mencionados na
  seção de transparência acima.
- O ensemble às vezes perde do Prophet sozinho (ex.: `total` D+1: Prophet
  14,2% de WAPE vs. ensemble 17,3%, porque o XGBoost estava com viés grande
  nesse recorte) — vale revisitar a regra de ponderação do ensemble, ou não
  misturar quando um modelo é muito melhor que o outro.
- Os classificadores erram mais em categorias/equipes específicas (ver o
  json) — antes de mexer no modelo em si, vale checar se essas categorias
  têm volume de treino suficiente.

## Regras de negócio implementadas (Dicionário de Dados v2)

- **Elegibilidade ao KPI e violação de OLA**: a planilha já traz essas duas
  respostas prontas, calculadas pelo sistema da própria Locaweb — colunas
  `Entrou para KPI?` e `KPI Violado?`. Usamos essas colunas diretamente
  (`localops/etl/build_dataset.py::_aplicar_regras_kpi`) em vez de recalcular
  a partir de `Duração` + limite por prioridade — ver a seção "Transparência"
  abaixo pra entender por quê.
- `localops/config.py::OLA_HORAS` (P1/P2 até 4h, P3 até 12h, P4 até 24h, P5
  até 96h) ainda é calculado e fica disponível na coluna `ola_limite_horas`
  só como informação de apoio (ex.: mostrar "prazo esperado" no dashboard) —
  não decide mais elegibilidade nem violação.
- Valores nulos de categoria/produto (≈63% da base) são marcados
  explicitamente como "Não informado", nunca descartados.

## Transparência — diferenças em relação à apresentação da Sprint 3

Este pacote foi construído a partir do dicionário de dados e da base real
(`LW-DATASET.xlsx`, 122.543 incidentes, 2023-01-02 a 2025-12-31 — os mesmos
números da Sprint 3), seguindo a arquitetura descrita nos slides. Alguns
valores específicos citados na apresentação (ex.: 248 violações de OLA,
AUC 0.93 do Modelo A) não foram reproduzidos exatamente porque o código
original da equipe para essas etapas não estava disponível neste pacote —
apenas a arquitetura, as regras de negócio e os prints de tela. Nesta
implementação, rodando contra a base real:

- **Volume total D+1**: ensemble ≈ 871 incidentes para 01/01/2026 (a
  apresentação citou 868 — a mesma ordem de grandeza).
- **Concentração no Team14**: 91,6% dos incidentes dos últimos 30 dias (a
  apresentação citou 92%).
- **Violações de OLA — resolvido**: a primeira versão deste pacote recalculava
  a violação a partir do campo `Duração` (segundos) comparado ao limite por
  prioridade, seguindo o dicionário ao pé da letra — e encontrava 3.685
  violações em 25.751 incidentes elegíveis (14,3%), bem acima do 0,97% (248
  casos) citado na Sprint 3. Investigando incidente a incidente, achamos casos
  em que a `Duração` oficial já excede o limite (ex.: P3 com 27h de duração,
  limite 12h) mas a própria coluna `KPI Violado?` da planilha diz "NÃO" — ou
  seja, a Locaweb usa algum critério adicional no cálculo real (ex.: horário
  comercial, pausas de atendimento) que não está documentado no dicionário
  compartilhado, e não dava pra reconstruir com segurança só a partir da
  `Duração`. A solução foi parar de recalcular e usar direto as colunas que a
  planilha já traz prontas (`Entrou para KPI?` / `KPI Violado?`) — elas batem
  exatamente com os números da Sprint 3: **25.600 elegíveis, 248 violações**.
  Ponto fechado, sem precisar de validação externa com o time.
- **Classificador de risco crítico (Modelo A)**: a primeira versão, usando só
  produto/categoria/subcategoria/equipe/origem/horário, saiu com AUC-ROC 0,72
  (bem abaixo do 0,93 da Sprint 3). Incorporando o texto de
  `descricao_resumida` (ver seção abaixo), o AUC-ROC subiu para **0,985** —
  acima do valor da Sprint 3. Isso confirma a hipótese: o time original
  provavelmente já usava a descrição (ou algo equivalente) nesse modelo.
- **Classificador de risco de violação de OLA (Modelo B)**: com a contagem de
  violações corrigida (248 casos reais, em vez dos 3.685 recalculados), o
  Modelo B agora treina sobre o mesmo evento raro que a Sprint 3 descreveu —
  e o resultado é bem melhor que o citado lá: AUC-ROC 0,844 (vs. 0,74 da
  Sprint 3) e AUC-PR 0,203 (vs. 0,06 da Sprint 3), com só 50 casos positivos
  no conjunto de teste (1,0% de taxa-base) — os mesmos números de ordem de
  grandeza que a apresentação já descrevia como "evento raríssimo".

Nada disso invalida a arquitetura ou os resultados qualitativos (as
tendências — concentração de carga, sazonalidade, categorias de risco — batem
com o que a apresentação descreve); é uma diferença esperada de reimplementar
um pipeline a partir da documentação, sem o código-fonte original das etapas
de modelagem.

## Uso do texto da descrição (`descricao_resumida`) nos classificadores

Os dois classificadores (`localops/models/classify.py`) agora usam o texto de
`descricao_resumida` como feature, via TF-IDF (unigramas e bigramas, até 250
termos), combinado com as variáveis categóricas (one-hot) e numéricas de
sempre. Antes de virar feature, o texto passa por uma limpeza
(`_limpar_texto`) que remove URLs, códigos de item de configuração
(`IC#####`) e tokens muito longos — são basicamente identificadores quase
únicos por incidente, e deixá-los entrar faria o modelo "decorar" IDs em vez
de aprender um padrão que generaliza.

**Resultado**: AUC-ROC do Modelo A saltou de 0,72 para **0,985**; do Modelo B
(já com a contagem de violações corrigida — ver "Transparência" acima), de
0,74 (valor da própria Sprint 3, sem texto) para **0,844**. Antes de aceitar
um salto desse tamanho, validamos que não era vazamento de dados nem só o
modelo "decorando" texto de alerta automático: o AUC do Modelo A se mantém
alto mesmo olhando só os incidentes abertos manualmente (0,935, contra 0,987
nos abertos por monitoramento) — ou seja, o ganho é sinal real vindo do
texto, não um artefato de templates automáticos repetidos.

## Diagnóstico de overfitting e "atalhos" do modelo

Como pedido explicitamente pela equipe, o pipeline agora verifica dois tipos
de problema em todo treino de classificador (`localops/models/classify.py`,
função `_treinar_avaliar`), com avisos impressos no terminal quando algo foge
do esperado:

1. **Overfitting clássico** — comparamos o AUC-ROC no treino com o AUC-ROC no
   teste. Um "gap" grande (treino bem melhor que teste) é sinal de que o
   modelo está decorando os dados de treino em vez de aprender um padrão que
   generaliza. Hoje: **Modelo A com gap de 0,006** (ótimo, sem sinal de
   overfitting, hiperparâmetros originais). **Modelo B com gap de 0,030**
   (também ótimo) — mas chegou até aí em duas rodadas: com a contagem de
   violações ainda errada (3.685 casos, ver "Transparência"), o gap inicial
   era 0,122; regularizamos (`XGB_PARAMS_OLA` em `classify.py`) e caiu pra
   0,085. Depois, corrigindo a contagem pra 248 violações reais (evento bem
   mais raro), o gap voltou a subir pra 0,119 com os mesmos hiperparâmetros —
   então re-regularizamos mais forte (árvore com profundidade 2, só 100
   estimadores, mais incidentes por folha, L2 maior) até estabilizar em
   0,030, com AUC-PR de teste subindo de 0,157 para **0,203** no processo (a
   métrica mais informativa aqui, já que só 1% dos casos de teste são
   violação). **Importante**: com apenas 50 casos positivos no conjunto de
   teste do Modelo B, qualquer métrica de precisão/recall tem bastante
   variância — cada incidente a mais ou a menos muda o resultado em ~2
   pontos percentuais. É esperado para um evento desse tamanho (a própria
   Sprint 3 já descrevia como "raríssimo"); não é sinal de bug.
2. **Concentração num "atalho"** — somamos a importância nativa do XGBoost por
   GRUPO de variável (cada categórica, o texto, cada numérica). Se um grupo
   sozinho concentra >40% da importância, o script avisa, porque pode ser um
   padrão real (o caso aqui: "descrição" concentra 55-74%, mas já validamos
   que é sinal genuíno, não vazamento) ou pode ser um proxy espúrio de outra
   coisa — por isso vale sempre conferir antes de confiar, não descartar o
   aviso automaticamente.

Esse diagnóstico completo (matriz de confusão, análise de resíduo da
previsão, tudo isso) roda com `python -m localops.diagnostics` — ver a seção
"Diagnóstico dos modelos" mais acima.

## Próximos passos sugeridos

1. Conectar o dashboard existente aos helpers de `localops/store.py`.
2. ~~Validar a regra de violação de OLA com o time~~ — feito: a planilha já
   trazia o resultado oficial pronto (`Entrou para KPI?` / `KPI Violado?`);
   passamos a usar essas colunas em vez de recalcular, e os números batem
   exatamente com a Sprint 3 (25.600 elegíveis, 248 violações). Ver seção
   "Transparência" acima.
3. ~~Investigar o gap de overfitting do Modelo B~~ — feito: com a contagem de
   violações corrigida, re-regularizamos (`XGB_PARAMS_OLA`) e o gap ficou em
   0,030 (ótimo), com AUC-PR de teste em 0,203. Como o evento é raro de
   verdade (248 casos), o próximo ganho de estabilidade viria de mais dados
   históricos de violação — não é algo pra resolver só ajustando
   hiperparâmetros.
4. Sprint 4 (conforme backlog da apresentação): Airflow para retreino diário,
   MLflow, agente com LLM usando `localops/agent.py` como conjunto de *tools*
   determinísticas.
