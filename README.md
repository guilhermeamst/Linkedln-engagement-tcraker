# LinkedIn Engagement Tracker

Sistema interno para medir e ranquear o engajamento de colaboradores e parceiros nos posts da página corporativa do LinkedIn, com coleta via automação de browser e dashboard interativo.

---

## Sumário

1. [Visão Geral](#visão-geral)
2. [Arquitetura](#arquitetura)
3. [Estrutura do Projeto](#estrutura-do-projeto)
4. [Pré-requisitos](#pré-requisitos)
5. [Instalação](#instalação)
6. [Configuração](#configuração)
7. [Como Executar](#como-executar)
8. [Coleta de Post Único](#coleta-de-post-único)
9. [Dashboard](#dashboard)
10. [Sistema de Pontuação](#sistema-de-pontuação)
11. [Banco de Dados](#banco-de-dados)
12. [Testes](#testes)
13. [Limitações e Boas Práticas](#limitações-e-boas-práticas)
14. [Troubleshooting](#troubleshooting)

---

## Visão Geral

O LinkedIn Engagement Tracker identifica e rankeia quais colaboradores e parceiros mais engajam nos posts da empresa no LinkedIn desde **03/01/2026**.

O sistema coleta reações, comentários e compartilhamentos via automação de browser (sem API oficial), persiste os dados em SQLite e exibe um dashboard executivo com pódio, ranking, gráficos e evolução temporal.

**Casos de uso:**
- Identificar embaixadores da marca digital
- Métricas de presença corporativa no LinkedIn
- Campanhas de employer branding e reconhecimento interno

---

## Arquitetura

O projeto segue **Clean Architecture** com separação clara de responsabilidades:

```
Scraper → Pipeline (ETL) → Services → Repositories → SQLite
                                ↑
                          Models (domínio)
                                ↓
                        Dashboard (Streamlit)
```

| Camada | Responsabilidade |
|--------|-----------------|
| `core/` | Configuração e logging — infraestrutura transversal |
| `models/` | Entidades de domínio puras (sem dependência de ORM) |
| `database/` | Engine SQLite, sessões, WAL mode |
| `repository/` | CRUD — implementa interfaces abstratas |
| `services/` | Regras de negócio — orquestra repositórios |
| `scraper/` | Automação Playwright — sem lógica de negócio |
| `pipeline/` | Orquestração ETL (Extract → Transform → Load) |
| `dashboard/` | Visualização Streamlit — sem lógica de negócio |
| `scripts/` | Ponto de entrada CLI |

**Princípios aplicados:** Single Responsibility, Dependency Inversion, Open/Closed, Low Coupling.

---

## Estrutura do Projeto

```
linkedin-engagement-tracker/
│
├── src/
│   ├── core/
│   │   ├── config.py              # Carrega .env, configurações tipadas e imutáveis
│   │   └── logger.py              # Logging com rotação de arquivo (5MB, 5 backups)
│   │
│   ├── models/
│   │   ├── engagement.py          # Entidade Engagement + enum TipoInteracao
│   │   ├── post.py                # Entidade Post
│   │   └── user.py                # Entidade User
│   │
│   ├── database/
│   │   └── database.py            # DatabaseManager (engine, sessões, contexto transacional)
│   │
│   ├── repository/
│   │   ├── engagement_repository.py  # CRUD engagements + queries analíticas
│   │   ├── post_repository.py        # CRUD posts (upsert)
│   │   └── user_repository.py        # CRUD usuários
│   │
│   ├── services/
│   │   ├── engagement_service.py  # Persistência e consultas de engajamento
│   │   ├── ranking_service.py     # Cálculo de rankings e pontuações
│   │   └── analytics_service.py   # Agregações para o dashboard
│   │
│   ├── scraper/
│   │   └── linkedin_scraper.py    # Automação Playwright: login, posts, reações, comentários
│   │
│   ├── pipeline/
│   │   └── etl_pipeline.py        # Orquestrador ETL (Extract → Transform → Load)
│   │
│   └── dashboard/
│       └── app.py                 # Dashboard executivo Streamlit
│
├── scripts/
│   ├── coletar_engajamento.py     # Entry point CLI da coleta completa
│   └── coletar_post_unico.py      # Coleta de um post específico por ID ou URL
│
├── tests/
│   ├── test_ranking_service.py    # 20+ testes unitários
│   └── test_engagement_service.py # 15+ testes unitários
│
├── logs/                          # Criado automaticamente na primeira execução
│   ├── linkedin_tracker.log
│   └── errors.log
│
├── linkedin_engagement.db         # Banco SQLite
├── .env.example                   # Template de configuração
├── requirements.txt
└── README.md
```

---

## Pré-requisitos

- Python **3.10** ou superior
- pip
- Acesso de administrador à página corporativa do LinkedIn

---

## Instalação

```bash
# 1. Clone o repositório e entre na pasta
cd "linkedin-engagement-tracker"

# 2. Crie e ative o ambiente virtual
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux / macOS
source .venv/bin/activate

# 3. Instale as dependências
pip install -r requirements.txt

# 4. Instale o browser do Playwright
playwright install chromium
```

---

## Configuração

### Criar o arquivo `.env`

```bash
# Windows
copy .env.example .env

# Linux / macOS
cp .env.example .env
```

### Variáveis obrigatórias

```env
LINKEDIN_EMAIL=seu_email@empresa.com.br
LINKEDIN_PASSWORD=sua_senha
LINKEDIN_COMPANY_URL=https://www.linkedin.com/company/SUA_EMPRESA/admin/page-posts/published/
```

> **Atenção:** Use uma conta secundária dedicada ao scraper. Nunca use sua conta pessoal principal.

### Variáveis opcionais

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `DB_PATH` | `linkedin_engagement.db` | Caminho do banco SQLite |
| `SCRAPER_DATA_INICIO` | `2026-01-01` (01/01/2026) | Data de início da coleta |
| `SCRAPER_DATA_FIM` | — | Data de fim (vazio = até hoje) — formato `AAAA-MM-DD` |
| `SCRAPER_MAX_POSTS` | `200` | Máximo de posts por execução |
| `BROWSER_HEADLESS` | `true` | `false` para ver o browser em tempo real |
| `BROWSER_SLOW_MO_MS` | `100` | Delay entre ações em ms (simula humano) |
| `SCRAPER_DELAY_POSTS_S` | `2.5` | Pausa entre posts em segundos |
| `SCRAPER_WAIT_TIMEOUT_MS` | `30000` | Timeout de espera por elementos |
| `SCRAPER_RETRY_ATTEMPTS` | `3` | Tentativas em caso de falha |

---

## Como Executar

### Coleta de dados

```bash
# Execução padrão
python scripts/coletar_engajamento.py

# Limitar número de posts
python scripts/coletar_engajamento.py --max-posts 50

# Coletar a partir de uma data específica (formato obrigatório: AAAA-MM-DD)
# Exemplo: 01/02/2026 → 2026-02-01
python scripts/coletar_engajamento.py --desde 2026-02-01

# Ver o browser durante a execução (útil para debug e captchas)
python scripts/coletar_engajamento.py --mostrar-browser

# Apenas exibir o ranking atual (sem scraping)
python scripts/coletar_engajamento.py --apenas-ranking

# Combinações
python scripts/coletar_engajamento.py --max-posts 100 --mostrar-browser
```

### Saída esperada no terminal

```
============================================================
  RANKING DE ENGAJAMENTO LINKEDIN
============================================================
Pos  Usuário                        Pts  React  Coment  Shares  Nível
--------------------------------------------------------------------
 1°  João Silva                      47     10      12       3  ★ Embaixador
 2°  Maria Santos                    31      5       8       4  ★ Embaixador
 3°  Pedro Costa                     18     12       3       0  ◆ Entusiasta
...
```

---

## Coleta de Post Único

Use o script `coletar_post_unico.py` quando quiser processar apenas um post específico — sem varrer toda a página de admin.

```bash
# Passando o ID numérico do post
python scripts/coletar_post_unico.py --post-id 7439626651308826624

# Passando a URL completa do LinkedIn
python scripts/coletar_post_unico.py --url "https://www.linkedin.com/feed/update/urn:li:activity:7439626651308826624/"

# Exibir o browser durante a execução
python scripts/coletar_post_unico.py --post-id 7439626651308826624 --mostrar-browser

# Forçar reprocessamento mesmo que o post já esteja atualizado no banco
python scripts/coletar_post_unico.py --post-id 7439626651308826624 --forcar
```

**Como encontrar o ID ou a URL do post:**

- Na página do LinkedIn, clique nos três pontinhos do post → **Copiar link do post**
- O ID numérico aparece no final da URL: `...activity:7439626651308826624/`

**Comportamento:**
- O bot faz login normalmente e navega até a página de admin
- Ignora todos os posts exceto o alvo (sem coletar engajamentos desnecessários)
- Ao encontrar o post, coleta reações, comentários e shares e salva no banco
- Se o post já estiver no banco com os mesmos totais, avisa sem reprocessar (use `--forcar` para sobrescrever)

---

## Dashboard

```bash
streamlit run src/dashboard/app.py
```

Acesse em: `http://localhost:8501`

### Seções do dashboard

| Seção | Descrição |
|-------|-----------|
| **KPIs** | Total de interações, pontos, posts e usuários |
| **Pódio** | Top 3 com cards visuais em ouro, prata e bronze |
| **Ranking Completo** | Tabela com posição, pontos por tipo e nível de engajamento |
| **Distribuição por Tipo** | Gráfico de pizza: proporção de reações / comentários / shares |
| **Top 10** | Gráfico de barras horizontais dos 10 primeiros |
| **Evolução Temporal** | Linha do tempo do engajamento por tipo de interação |
| **Engajamento por Post** | Tabela detalhada por post com link direto no LinkedIn |

**Tema:** Dark mode com cor primária azul LinkedIn (`#0077b6`)

---

## Sistema de Pontuação

| Tipo de Interação | Pontos |
|-------------------|--------|
| Reação (like, love, support, etc.) | 1 pt |
| Comentário | 2 pts |
| Share | 2 pts |

### Níveis de engajamento

| Nível | Pontos Mínimos | Símbolo |
|-------|---------------|---------|
| Embaixador | 30 | ★ |
| Entusiasta | 15 | ◆ |
| Colaborador | 5 | ● |
| Iniciante | 1 | ○ |

O identificador único de cada usuário é um hash MD5 da URL do perfil, garantindo que a mesma pessoa não seja contada em duplicata mesmo com variações de nome.

---

## Banco de Dados

Arquivo: `linkedin_engagement.db` (SQLite com WAL mode ativo)

### Tabela `engagement`

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `id` | INTEGER PK | Auto-incremento |
| `usuario` | TEXT | Nome completo |
| `usuario_id` | TEXT | Hash MD5 da URL do perfil |
| `tipo` | TEXT | `reaction`, `comentario` ou `share` |
| `post_id` | TEXT | ID numérico do post no LinkedIn |
| `data_interacao` | DATE | Data da interação |
| `data_coleta` | DATETIME | Timestamp da coleta |

**Constraint única:** `(usuario_id, tipo, post_id)` — impede duplicatas em reexecuções.

### Tabela `posts`

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `post_id` | TEXT UNIQUE | ID numérico do post |
| `url_post` | TEXT | URL completa |
| `data_post` | DATE | Data de publicação |
| `total_likes` | INTEGER | Contagem de reações |
| `total_comentarios` | INTEGER | Contagem de comentários |
| `total_shares` | INTEGER | Contagem de shares |
| `data_coleta` | DATETIME | Timestamp da coleta |

### Tabela `users`

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `usuario_id` | TEXT PK | Hash MD5 do perfil |
| `nome` | TEXT | Nome do usuário |
| `data_coleta` | DATETIME | Timestamp da coleta |

---

## Testes

```bash
# Todos os testes
pytest tests/ -v

# Com relatório de cobertura
pytest tests/ -v --cov=src --cov-report=html

# Arquivo específico
pytest tests/test_ranking_service.py -v
```

| Módulo | Testes |
|--------|--------|
| `ranking_service.py` | 20 testes (pontuação, ranking, top N, exportação) |
| `engagement_service.py` | 15 testes (persistência, estatísticas, delegação) |

---

## Limitações e Boas Práticas

### Por que automação de browser?

O LinkedIn **não oferece API pública** para dados de reações e comentários de páginas corporativas. A única forma de acessar esses dados é simulando um usuário humano via browser.

### Limitações conhecidas

1. **Rate limiting** — O LinkedIn detecta acessos rápidos e pode bloquear a conta temporariamente.
2. **Mudanças de layout** — O LinkedIn atualiza seletores CSS com frequência. Se o scraper parar de funcionar, atualize a classe `_Selectors` em `linkedin_scraper.py`.
3. **Reações incompletas** — Posts virais podem não ter todas as reações carregadas pelo LinkedIn.
4. **Shares** — São os mais difíceis de coletar pois geram posts independentes no feed.
5. **2FA** — Login automático falha se autenticação em dois fatores estiver ativa. Desative-a na conta do scraper.
6. **Captchas** — Use `--mostrar-browser` para resolver manualmente quando necessário.

### Recomendações operacionais

- Execute no máximo **1-2 vezes por semana**
- Varie os horários de execução
- Use `--max-posts 50` nas primeiras execuções para testar
- **Nunca use sua conta pessoal principal** — crie uma conta dedicada
- Aumente os delays se necessário: `SCRAPER_DELAY_POSTS_S=5.0`
- Monitore `logs/errors.log` para sinais de bloqueio
- Após muitos erros consecutivos, aguarde 24-48h antes de tentar novamente

### Sinais de bloqueio / limitação

- Login redireciona para verificação ou captcha
- Posts aparecem vazios ou não carregam
- Reações retornam 0 consistentemente
- Timeouts frequentes durante a coleta

---

## Troubleshooting

**"Variável de ambiente obrigatória não definida"**
→ Verifique se o arquivo `.env` existe na raiz do projeto com `LINKEDIN_EMAIL`, `LINKEDIN_PASSWORD` e `LINKEDIN_COMPANY_URL`.

**"Timeout no login"**
→ Verifique sua conexão. Tente com `BROWSER_HEADLESS=false` para ver o que acontece. Aumente `SCRAPER_WAIT_TIMEOUT_MS=60000`.

**"Nenhum post encontrado"**
→ Os seletores CSS podem ter mudado. Execute com `--mostrar-browser`, inspecione os elementos e atualize a classe `_Selectors` em `src/scraper/linkedin_scraper.py`.

**Dashboard não exibe dados**
→ Execute a coleta antes:
```bash
python scripts/coletar_engajamento.py --max-posts 10
```

**Erro de importação Python (ModuleNotFoundError)**
→ Execute sempre a partir da raiz do projeto:
```bash
# Correto
python scripts/coletar_engajamento.py

# Incorreto
cd scripts && python coletar_engajamento.py
```

---

## Licença

Uso interno. Proibida a distribuição externa.
