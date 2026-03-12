# LinkedIn Engagement Tracker

Sistema interno para medir e ranquear o engajamento de usuários nos posts da página corporativa do LinkedIn, a partir de 01/01/2026.

---

## Sumário

1. [Objetivo](#objetivo)
2. [Arquitetura](#arquitetura)
3. [Estrutura de Pastas](#estrutura-de-pastas)
4. [Instalação](#instalação)
5. [Configuração](#configuração)
6. [Como Executar a Coleta](#como-executar-a-coleta)
7. [Como Rodar o Dashboard](#como-rodar-o-dashboard)
8. [Sistema de Pontuação](#sistema-de-pontuação)
9. [Banco de Dados](#banco-de-dados)
10. [Testes](#testes)
11. [Limitações do Scraping](#limitações-do-scraping)
12. [Como Evitar Bloqueio do LinkedIn](#como-evitar-bloqueio-do-linkedin)
13. [Integração com PhantomBuster](#integração-com-phantombuster)
14. [Fluxo Completo do Sistema](#fluxo-completo-do-sistema)

---

## Objetivo

Medir e ranquear quais colaboradores e parceiros mais engajaram nos posts da página da empresa no LinkedIn desde 01/01/2026, usando um sistema de pontuação baseado no tipo de interação.

Uso: análise interna de engajamento para campanhas de employer branding, reconhecimento de embaixadores e métricas de presença digital.

---

## Arquitetura

O projeto segue **Clean Architecture** com separação clara de responsabilidades:

```
Scraper → Services → Repositories → Database
                ↑
            Models (entidades de domínio)
                ↓
           Dashboard (Streamlit)
```

### Camadas

| Camada | Responsabilidade |
|--------|-----------------|
| `core/` | Configuração, logging — infraestrutura transversal |
| `models/` | Entidades de domínio puras (sem dependência de ORM) |
| `database/` | Gerenciamento de conexão e sessões SQLite |
| `repository/` | Acesso a dados (CRUD) — implementa interfaces |
| `services/` | Regras de negócio — orquestra repositórios |
| `scraper/` | Coleta de dados via Playwright — sem regras de negócio |
| `dashboard/` | Visualização Streamlit — sem lógica de negócio |
| `scripts/` | Ponto de entrada CLI para execução da coleta |

### Princípios aplicados

- **Single Responsibility**: cada classe tem uma única razão para mudar
- **Open/Closed**: repositórios implementam interfaces abstratas (fácil substituição)
- **Dependency Inversion**: serviços dependem de interfaces, não de implementações concretas
- **Separation of Concerns**: scraping, persistência e apresentação são completamente separados
- **Low Coupling**: cada camada se comunica apenas com a imediatamente abaixo

---

## Estrutura de Pastas

```
linkedin-engagement-tracker/
│
├── src/
│   ├── core/
│   │   ├── config.py              # Carrega .env, expõe configurações tipadas
│   │   └── logger.py              # Factory de loggers com arquivo rotativo
│   │
│   ├── models/
│   │   ├── engagement.py          # Entidade Engagement + ORM + TipoInteracao enum
│   │   └── post.py                # Entidade Post + ORM
│   │
│   ├── database/
│   │   └── database.py            # DatabaseManager (engine, sessões, WAL mode)
│   │
│   ├── repository/
│   │   ├── engagement_repository.py  # CRUD engagement + queries analíticas
│   │   └── post_repository.py        # CRUD posts (upsert)
│   │
│   ├── services/
│   │   ├── engagement_service.py  # Orquestra persistência e consultas
│   │   └── ranking_service.py     # Calcula rankings e pontuações
│   │
│   ├── scraper/
│   │   └── linkedin_scraper.py    # Playwright: login, coleta posts/reações/comentários
│   │
│   └── dashboard/
│       └── app.py                 # Dashboard executivo Streamlit
│
├── scripts/
│   └── coletar_engajamento.py     # Script CLI principal
│
├── tests/
│   ├── test_ranking_service.py    # 20+ testes unitários do ranking
│   └── test_engagement_service.py # 15+ testes unitários do serviço
│
├── logs/                          # Criado automaticamente
│   ├── linkedin_tracker.log
│   └── errors.log
│
├── .env.example                   # Template de configuração
├── .gitignore
├── requirements.txt
└── README.md
```

---

## Instalação

### Pré-requisitos

- Python 3.10 ou superior
- pip

### Passo a passo

```bash
# 1. Clone ou baixe o projeto
cd "LinkedIn Engagement Tracker"

# 2. Crie e ative o ambiente virtual
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux/macOS
source .venv/bin/activate

# 3. Instale as dependências Python
pip install -r requirements.txt

```

---

## Configuração

### Criar o arquivo .env

```bash
# Copie o template
copy .env.example .env       # Windows
cp .env.example .env         # Linux/macOS
```

### Preencher as variáveis obrigatórias

Abra o arquivo `.env` e configure:

```env
LINKEDIN_EMAIL=seu_email@empresa.com.br
LINKEDIN_PASSWORD=sua_senha
LINKEDIN_COMPANY_URL=https://www.linkedin.com/company/nome-da-empresa/
```

### Variáveis opcionais importantes

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `SCRAPER_DATA_INICIO` | `2026-01-01` | Data de início da coleta |
| `SCRAPER_MAX_POSTS` | `200` | Máximo de posts por execução |
| `BROWSER_HEADLESS` | `true` | `false` para ver o browser |
| `BROWSER_SLOW_MO_MS` | `100` | Delay entre ações (ms) |
| `SCRAPER_DELAY_POSTS_S` | `2.5` | Delay entre posts (segundos) |

---

## Como Executar a Coleta

### Execução padrão

```bash
python scripts/coletar_engajamento.py
```

### Com opções

```bash
# Limitar a 50 posts
python scripts/coletar_engajamento.py --max-posts 50

# Coletar apenas desde fevereiro
python scripts/coletar_engajamento.py --desde 2026-02-01

# Exibir o browser durante a coleta (útil para debug)
python scripts/coletar_engajamento.py --mostrar-browser

# Apenas exibir o ranking atual (sem scraping)
python scripts/coletar_engajamento.py --apenas-ranking

# Combinações
python scripts/coletar_engajamento.py --max-posts 100 --mostrar-browser
```

### Saída esperada

```
============================================================
  RANKING DE ENGAJAMENTO LINKEDIN
============================================================
Pos  Usuário                        Pts  Likes  Coment  Shares  Nível
--------------------------------------------------------------------
 1°  João Silva                      47     10      12       3  ★ Embaixador
 2°  Maria Santos                    31      5       8       4  ★ Embaixador
 3°  Pedro Costa                     18     12       3       0  ◆ Entusiasta
...
```

---

## Como Rodar o Dashboard

```bash
streamlit run src/dashboard/app.py
```

Acesse no browser: `http://localhost:8501`

### Funcionalidades do Dashboard

| Seção | Descrição |
|-------|-----------|
| KPIs | Total de interações, pontos, posts, likes, comentários, shares |
| Pódio | Top 3 usuários com cards visuais em ouro/prata/bronze |
| Ranking Completo | Tabela com posição, pontos, tipos e nível de engajamento |
| Distribuição por Tipo | Gráfico de pizza: proporção de likes/comentários/shares |
| Top 10 por Pontos | Gráfico de barras horizontais dos 10 primeiros |
| Evolução Temporal | Linha do tempo do engajamento por tipo |
| Engajamento por Post | Tabela detalhada por post com link direto |

---

## Sistema de Pontuação

| Tipo de Interação | Pontos |
|-------------------|--------|
| Like | 1 pt |
| Comentário | 2 pts |
| Share | 3 pts |

### Níveis de Engajamento

| Nível | Pontos Mínimos | Símbolo |
|-------|---------------|---------|
| Embaixador | 30 | ★ |
| Entusiasta | 15 | ◆ |
| Colaborador | 5 | ● |
| Iniciante | 1 | ○ |

### Query SQL de ranking

```sql
SELECT
    usuario,
    usuario_id,
    SUM(
        CASE
            WHEN tipo = 'like'       THEN 1
            WHEN tipo = 'comentario' THEN 2
            WHEN tipo = 'share'      THEN 3
            ELSE 0
        END
    ) AS pontos,
    SUM(CASE WHEN tipo = 'like'       THEN 1 ELSE 0 END) AS likes,
    SUM(CASE WHEN tipo = 'comentario' THEN 1 ELSE 0 END) AS comentarios,
    SUM(CASE WHEN tipo = 'share'      THEN 1 ELSE 0 END) AS shares,
    COUNT(*) AS total_interacoes
FROM engagement
GROUP BY usuario, usuario_id
ORDER BY pontos DESC;
```

---

## Banco de Dados

Arquivo: `linkedin_engagement.db` (SQLite)

### Tabela `engagement`

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `id` | INTEGER PK | ID auto-incremento |
| `usuario` | TEXT | Nome completo do usuário |
| `usuario_id` | TEXT | Hash MD5 da URL do perfil |
| `tipo` | TEXT | `like`, `comentario` ou `share` |
| `post_id` | TEXT | ID numérico do post no LinkedIn |
| `data_interacao` | DATE | Data aproximada da interação |

Constraint única: `(usuario_id, tipo, post_id)` — evita duplicatas.

### Tabela `posts`

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `id` | INTEGER PK | ID auto-incremento |
| `post_id` | TEXT UNIQUE | ID numérico do post |
| `data_post` | DATE | Data de publicação |
| `url_post` | TEXT | URL completa do post |
| `titulo` | TEXT | Trecho do texto do post |
| `total_likes` | INTEGER | Contagem de likes |
| `total_comentarios` | INTEGER | Contagem de comentários |
| `total_shares` | INTEGER | Contagem de shares |

---

## Testes

```bash
# Rodar todos os testes
pytest tests/ -v

# Com cobertura de código
pytest tests/ -v --cov=src --cov-report=html

# Apenas um arquivo
pytest tests/test_ranking_service.py -v
```

### Cobertura atual

| Módulo | Testes |
|--------|--------|
| `ranking_service.py` | 20 testes (pontuação, ranking, top N, export) |
| `engagement_service.py` | 15 testes (persistência, estatísticas, delegação) |

---

## Limitações do Scraping

### Por que o scraping é complexo

O LinkedIn **não possui API pública** para dados de reações e comentários de páginas. A única forma de acessar esses dados é via automação de browser simulando um usuário humano.

### Limitações conhecidas

1. **Rate limiting**: O LinkedIn detecta acessos muito rápidos e pode bloquear temporariamente a conta.

2. **Mudanças de layout**: O LinkedIn atualiza frequentemente seus seletores CSS e estrutura HTML. Os seletores em `linkedin_scraper.py` (classe `_Selectors`) precisam ser atualizados quando o scraper para de funcionar.

3. **Reações completas**: O LinkedIn limita a exibição de reações. Para posts com milhares de reações, pode não ser possível carregar a lista completa.

4. **Shares**: Compartilhamentos são os mais difíceis de coletar pois geram posts independentes no feed.

5. **Autenticação de dois fatores**: Se a conta tiver 2FA ativo, o login automático falhará. Desative o 2FA para a conta usada no scraper, ou implemente suporte manual.

6. **Captchas**: O LinkedIn pode apresentar desafios de verificação. Use `BROWSER_HEADLESS=false` para resolver manualmente.

7. **Dados históricos**: Posts muito antigos podem não carregar todas as reações. O sistema coleta o máximo possível.

---

## Como Evitar Bloqueio do LinkedIn

### Boas práticas implementadas no código

- Delays aleatórios entre ações (simula comportamento humano)
- User-agent de browser real (Chrome)
- Remoção do atributo `webdriver` do navigator
- Viewport realista (1366x768)
- Locale e timezone brasileiros configurados
- `slow_mo` para não executar ações instantâneas

### Recomendações operacionais

1. **Execute com baixa frequência**: No máximo 1-2 vezes por semana
2. **Use horários variados**: Evite sempre executar no mesmo horário
3. **Limite o número de posts por execução**: Use `--max-posts 50` inicialmente
4. **Use uma conta secundária**: Nunca use sua conta principal pessoal
5. **Aumentue os delays**: Configure `SCRAPER_DELAY_POSTS_S=5.0` para mais segurança
6. **Monitore os logs**: Verifique `logs/errors.log` para sinais de bloqueio
7. **Pause após erros**: Se houver muitos erros, espere 24-48 horas antes de tentar novamente

### Sinais de que a conta foi bloqueada/limitada

- Login redireciona para página de verificação
- Posts não carregam ou aparecem vazios
- Reações retornam 0 consistentemente
- Erros de timeout frequentes

---

## Integração com PhantomBuster

### O que é o PhantomBuster?

[PhantomBuster](https://phantombuster.com) é uma plataforma SaaS de automação de LinkedIn que oferece "Phantoms" (scripts prontos) para extrair dados do LinkedIn de forma mais segura e confiável, pois:

- Opera em servidores deles (não na sua máquina/IP)
- Usa sessões de cookies em vez de login por senha
- Tem phantoms específicos para LinkedIn Page Posts, Reactions e Comments
- Limita automaticamente as chamadas para evitar bloqueios

### Como integrar ao projeto

#### Opção 1: Substituir o scraper pelo PhantomBuster (recomendado)

1. **Crie uma conta** em phantombuster.com (plano pago necessário para LinkedIn)

2. **Configure o Phantom "LinkedIn Page Posts Export"** para exportar posts da sua página

3. **Configure o Phantom "LinkedIn Post Likers Export"** para exportar quem deu like

4. **Baixe os resultados** em CSV/JSON via API do PhantomBuster:

```python
# Exemplo de integração via API do PhantomBuster
import requests

PHANTOMBUSTER_API_KEY = "sua_chave_api"
AGENT_ID = "id_do_seu_phantom"

# Dispara o phantom
response = requests.post(
    f"https://api.phantombuster.com/api/v2/agents/launch",
    headers={"X-Phantombuster-Key": PHANTOMBUSTER_API_KEY},
    json={"id": AGENT_ID}
)

# Baixa o resultado (CSV)
resultado_url = response.json()["data"]["resultObject"]
df = pd.read_csv(resultado_url)
```

4. **Adapte o script de coleta** para ler os CSVs do PhantomBuster e importar no banco:

```python
# scripts/importar_phantombuster.py
import pandas as pd
from src.models.engagement import Engagement, TipoInteracao

def importar_csv_likers(caminho_csv: str, post_id: str) -> List[Engagement]:
    df = pd.read_csv(caminho_csv)
    return [
        Engagement(
            usuario=row["fullName"],
            usuario_id=row["profileUrl"].split("/in/")[1],
            tipo=TipoInteracao.LIKE,
            post_id=post_id,
        )
        for _, row in df.iterrows()
    ]
```

#### Opção 2: Usar PhantomBuster como fallback

Manter o scraper Playwright para uso interno e acionar o PhantomBuster automaticamente quando o scraper falhar:

```python
try:
    dados = scraper.coletar_posts()
except ScraperBloqueadoError:
    dados = phantombuster_client.coletar_posts()
```

#### Phantoms úteis do PhantomBuster para este projeto

| Phantom | Coleta |
|---------|--------|
| LinkedIn Page Posts Export | Lista de posts da página |
| LinkedIn Post Likers Export | Usuários que deram like |
| LinkedIn Post Comments Export | Usuários que comentaram |

---

## Fluxo Completo do Sistema

```
┌─────────────────────────────────────────────────────────────┐
│                    EXECUÇÃO DA COLETA                        │
│                                                             │
│  scripts/coletar_engajamento.py                             │
│       │                                                     │
│       ▼                                                     │
│  core/config.py ──── carrega .env                          │
│       │                                                     │
│       ▼                                                     │
│  database/database.py ──── inicializa SQLite               │
│       │                                                     │
│       ▼                                                     │
│  scraper/linkedin_scraper.py                               │
│       │  1. Login                                          │
│       │  2. Navega para página da empresa                  │
│       │  3. Para cada post desde 01/01/2026:               │
│       │     a. Coleta reações (likes)                      │
│       │     b. Coleta comentários                          │
│       │     c. yield (Post, List[Engagement])              │
│       │                                                     │
│       ▼                                                     │
│  services/engagement_service.py                            │
│       │  - Valida e orquestra persistência                 │
│       │                                                     │
│       ▼                                                     │
│  repository/engagement_repository.py                       │
│  repository/post_repository.py                             │
│       │  - Upsert posts                                    │
│       │  - INSERT OR IGNORE engagements                    │
│       │                                                     │
│       ▼                                                     │
│  linkedin_engagement.db (SQLite)                           │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                    VISUALIZAÇÃO                              │
│                                                             │
│  streamlit run src/dashboard/app.py                        │
│       │                                                     │
│       ▼                                                     │
│  services/engagement_service.py                            │
│       │  - obter_estatisticas_gerais()                     │
│       │  - get_ranking_dataframe()                         │
│       │  - get_evolucao_temporal_dataframe()               │
│       │                                                     │
│       ▼                                                     │
│  services/ranking_service.py                               │
│       │  - calcular_ranking_from_df_agregado()             │
│       │  - obter_top_n()                                   │
│       │                                                     │
│       ▼                                                     │
│  dashboard/app.py (Streamlit)                              │
│       - KPIs, Pódio Top 3, Ranking, Gráficos               │
└─────────────────────────────────────────────────────────────┘
```

---

## Troubleshooting

### "Variável de ambiente obrigatória não definida"

Certifique-se de que o arquivo `.env` existe na raiz do projeto e contém `LINKEDIN_EMAIL`, `LINKEDIN_PASSWORD` e `LINKEDIN_COMPANY_URL`.

### "Timeout no login"

- Verifique sua conexão com a internet
- Tente com `BROWSER_HEADLESS=false` para ver o que está acontecendo
- Aumente `SCRAPER_WAIT_TIMEOUT_MS=60000`

### "Nenhum post encontrado"

Os seletores CSS do LinkedIn podem ter mudado. Abra o browser com `--mostrar-browser` e inspecione os elementos para atualizar a classe `_Selectors` em `linkedin_scraper.py`.

### Dashboard não carrega dados

Execute primeiro a coleta:
```bash
python scripts/coletar_engajamento.py --max-posts 10
```

### Erros de importação Python

Certifique-se de executar os scripts a partir da raiz do projeto:
```bash
# Correto (na raiz)
python scripts/coletar_engajamento.py

# Incorreto
cd scripts && python coletar_engajamento.py
```

---

## Licença

Uso interno. Proibida a distribuição externa.
