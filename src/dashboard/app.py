"""
app.py - Dashboard executivo LinkedIn Engagement Tracker.

Executar com: streamlit run src/dashboard/app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from src.core.config import load_config
from src.core.logger import get_logger
from src.database.database import DatabaseManager
from src.repository.engagement_repository import EngagementRepository
from src.repository.post_repository import PostRepository
from src.repository.user_repository import UserRepository
from src.services.analytics_service import AnalyticsService
from src.services.engagement_service import EngagementService
from src.services.ranking_service import RankingService

logger = get_logger(__name__)

# --------------------------------------------------------------------------- #
#  Configuração da Página
# --------------------------------------------------------------------------- #

st.set_page_config(
    page_title="LinkedIn Engagement Tracker",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .main { background-color: #0f1116; }
    .block-container { padding: 6rem 3rem 2rem 3rem; }

    div[data-testid="metric-container"] {
        background: linear-gradient(135deg, #1e2130 0%, #252a3d 100%);
        border: 1px solid #3d4466;
        border-radius: 12px;
        padding: 1rem 1.5rem;
        box-shadow: 0 4px 12px rgba(0,0,0,0.4);
    }
    div[data-testid="metric-container"] label {
        color: #8892b0 !important;
        font-size: 0.85rem !important;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    div[data-testid="metric-container"] [data-testid="stMetricValue"] {
        color: #ccd6f6 !important;
        font-size: 2rem !important;
        font-weight: 700 !important;
    }

    .titulo-principal {
        background: linear-gradient(90deg, #0077b6, #00b4d8, #48cae4);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        display: inline-block;
        font-size: 2.2rem;
        font-weight: 800;
        margin-bottom: 0;
        padding: 0.3rem 0.1rem;
        line-height: 1.4;
    }
    .subtitulo { color: #8892b0; font-size: 1rem; margin-top: 0.3rem; }

    .top-card {
        background: linear-gradient(135deg, #1a1f35 0%, #252d4a 100%);
        border-radius: 16px;
        padding: 1.5rem;
        text-align: center;
        border: 1px solid #3d4466;
        box-shadow: 0 8px 24px rgba(0,0,0,0.5);
        margin: 0.5rem;
    }
    .top-card-gold   { border-color: #ffd700; box-shadow: 0 8px 24px rgba(255,215,0,0.2); }
    .top-card-silver { border-color: #c0c0c0; box-shadow: 0 8px 24px rgba(192,192,192,0.2); }
    .top-card-bronze { border-color: #cd7f32; box-shadow: 0 8px 24px rgba(205,127,50,0.2); }

    .medal      { font-size: 2.5rem; }
    .top-nome   { color: #ccd6f6; font-size: 1.1rem; font-weight: 700; margin: 0.5rem 0 0.2rem; }
    .top-pontos { color: #64ffda; font-size: 1.8rem; font-weight: 800; }
    .top-detalhe { color: #8892b0; font-size: 0.8rem; margin-top: 0.3rem; }

    hr { border-color: #2d3250; margin: 2rem 0; }
    section[data-testid="stSidebar"] { background-color: #13151f; }
    section[data-testid="stSidebar"] *:not(button):not(button *) { color: #ccd6f6; }
    section[data-testid="stSidebar"] button {
        background-color: #0077b6;
        color: #ffffff !important;
        border: none;
        border-radius: 8px;
    }
    section[data-testid="stSidebar"] button:hover {
        background-color: #00b4d8;
        color: #ffffff !important;
    }
</style>
""", unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
#  Inicialização (cached)
# --------------------------------------------------------------------------- #

@st.cache_resource(show_spinner=False)
def _init_analytics() -> tuple[AnalyticsService | None, str | None]:
    """Inicializa o AnalyticsService uma única vez por sessão."""
    try:
        config    = load_config()
        db        = DatabaseManager(config.database.db_path)
        db.create_tables()
        eng_repo  = EngagementRepository(db)
        post_repo = PostRepository(db)
        user_repo = UserRepository(db)
        eng_svc   = EngagementService(eng_repo, post_repo, user_repo)
        rank_svc  = RankingService()
        return AnalyticsService(eng_svc, rank_svc), None
    except Exception as e:
        return None, str(e)


@st.cache_data(ttl=300, show_spinner=False)
def _carregar_dados():
    """Carrega todos os dados do banco (cache de 5 minutos)."""
    analytics, erro = _init_analytics()
    if erro or analytics is None:
        return None, erro

    try:
        dados = {
            "kpis":     analytics.obter_kpis(),
            "ranking":  analytics.obter_ranking_completo(),
            "df_tipos": analytics.obter_distribuicao_tipos(),
            "df_temp":  analytics.obter_evolucao_temporal(),
            "df_posts": analytics.obter_posts_por_engajamento(),
            "niveis":   analytics.obter_resumo_por_nivel(),
        }
        return dados, None
    except Exception as e:
        logger.error("Erro ao carregar dados: %s", e, exc_info=True)
        return None, str(e)


# --------------------------------------------------------------------------- #
#  Sidebar
# --------------------------------------------------------------------------- #

def _render_sidebar() -> None:
    with st.sidebar:
        st.markdown("## 💼 LinkedIn Tracker")
        st.markdown("---")
        st.markdown("### Sobre")
        st.caption("Dashboard de acompanhamento de engajamento nos posts da página corporativa no LinkedIn.")

        st.markdown("---")
        st.markdown("### Sistema de Pontuação")
        st.markdown("""
| Tipo | Pontos |
|------|--------|
| 👍 Reações | **1 pt** |
| 💬 Comentários | **2 pts** |
| 🔄 Compartilhamentos | **2 pts** |
""")

        st.markdown("---")
        if st.button("🔄 Atualizar Dados", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

        st.markdown("---")
        st.caption("Dados desde 06/01/2026")


# --------------------------------------------------------------------------- #
#  Cabeçalho
# --------------------------------------------------------------------------- #

def _render_header() -> None:
    st.markdown('<p class="titulo-principal">LinkedIn Engagement Tracker</p>', unsafe_allow_html=True)
    st.markdown('<p class="subtitulo">Ranking de engajamento da página corporativa — 2026</p>', unsafe_allow_html=True)
    st.markdown("---")


# --------------------------------------------------------------------------- #
#  KPIs
# --------------------------------------------------------------------------- #

def _render_kpis(kpis: dict) -> None:
    cols = st.columns(7)
    items = [
        ("💬 Interações",   kpis["total_interacoes"]),
        ("⭐ Pontos Totais", kpis["pontos_totais"]),
        ("📄 Posts",         kpis["total_posts"]),
        ("👤 Usuários",      kpis["total_usuarios"]),
        ("👍 Reações",     kpis["total_reactions"]),
        ("💬 Comentários",   kpis["total_comentarios"]),
        ("🔄 Compartilhamentos",        kpis["total_shares"]),
    ]
    for col, (label, value) in zip(cols, items):
        with col:
            st.metric(label=label, value=f"{value:,}".replace(",", "."))


# --------------------------------------------------------------------------- #
#  Top 3 — Pódio
# --------------------------------------------------------------------------- #

def _render_top3(ranking) -> None:
    st.subheader("🏆 Pódio de Engajamento")

    if not ranking:
        st.info("Nenhum dado de engajamento disponível ainda.")
        return

    top3     = ranking[:3]
    medalhas = [("🥇", "top-card-gold"), ("🥈", "top-card-silver"), ("🥉", "top-card-bronze")]

    # Layout visual: 2° — 1° — 3°
    if len(top3) == 3:
        ordem = [1, 0, 2]
    else:
        ordem = list(range(len(top3)))

    colunas = st.columns(len(top3))
    for col_idx, rank_idx in enumerate(ordem[:len(top3)]):
        u = top3[rank_idx]
        medalha, classe = medalhas[rank_idx]
        with colunas[col_idx]:
            st.markdown(
                f"""
                <div class="top-card {classe}">
                    <div class="medal">{medalha}</div>
                    <div class="top-nome">{u.usuario}</div>
                    <div class="top-pontos">{u.pontos} pts</div>
                    <div class="top-detalhe">
                        👍 {u.reactions} &nbsp;|&nbsp;
                        💬 {u.comentarios} &nbsp;|&nbsp;
                        🔄 {u.shares}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )


# --------------------------------------------------------------------------- #
#  Gráficos
# --------------------------------------------------------------------------- #

_LABELS_TIPO = {
    "reaction":   "👍 Reações",
    "comentario": "💬 Comentário",
    "share":      "🔄 Compartilhamentos",
}

_COLOR_TIPO = {
    "👍 Reações":          "#0077b6",
    "💬 Comentário":       "#48cae4",
    "🔄 Compartilhamentos": "#64ffda",
}


def _render_graficos(df_tipos: pd.DataFrame, ranking) -> None:
    col1, col2 = st.columns(2)

    # Pizza — distribuição por tipo
    with col1:
        st.subheader("🎯 Distribuição por Tipo de Interação")
        if not df_tipos.empty:
            df = df_tipos.copy()
            df["tipo_label"] = df["tipo"].map(_LABELS_TIPO).fillna(df["tipo"])
            fig = px.pie(
                df,
                names="tipo_label",
                values="quantidade",
                color="tipo_label",
                color_discrete_map=_COLOR_TIPO,
                hole=0.45,
            )
            fig.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font_color="#ccd6f6",
                legend=dict(orientation="h", yanchor="bottom", y=-0.2),
                margin=dict(t=20, b=20, l=20, r=20),
            )
            fig.update_traces(
                textinfo="percent+label",
                textfont_size=13,
                hovertemplate="<b>%{label}</b><br>Quantidade: %{value}<br>Participação: %{percent}<extra></extra>",
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Sem dados para o gráfico de tipos.")

    # Barras horizontais — Top 10 usuários
    with col2:
        st.subheader("👥 Top 10 Usuários por Pontos")
        if ranking:
            top10 = ranking[:10]
            df_bar = pd.DataFrame([
                {"Usuário": r.usuario[:25], "Pontos": r.pontos}
                for r in reversed(top10)
            ])
            fig = px.bar(
                df_bar,
                x="Pontos", y="Usuário",
                orientation="h",
                color="Pontos",
                color_continuous_scale=["#023e8a", "#0077b6", "#00b4d8", "#48cae4", "#90e0ef"],
                text="Pontos",
            )
            fig.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font_color="#ccd6f6",
                coloraxis_showscale=False,
                xaxis=dict(showgrid=True, gridcolor="#2d3250"),
                yaxis=dict(showgrid=False),
                margin=dict(t=20, b=20, l=20, r=20),
            )
            fig.update_traces(
                textposition="outside",
                textfont_size=12,
                hovertemplate="<b>%{y}</b><br>Pontos: %{x}<extra></extra>",
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Sem dados.")


def _render_evolucao_temporal(df_temporal: pd.DataFrame) -> None:
    st.subheader("📈 Evolução Temporal do Engajamento")

    if df_temporal.empty:
        st.info("Sem dados temporais disponíveis.")
        return

    df = df_temporal.copy()
    df["data_interacao"] = pd.to_datetime(df["data_interacao"])
    df["tipo_label"]     = df["tipo"].map(_LABELS_TIPO).fillna(df["tipo"])

    fig = px.line(
        df,
        x="data_interacao", y="quantidade",
        color="tipo_label",
        markers=True,
        color_discrete_map=_COLOR_TIPO,
        labels={"data_interacao": "Data", "quantidade": "Quantidade", "tipo_label": "Tipo"},
    )
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font_color="#ccd6f6",
        xaxis=dict(showgrid=True, gridcolor="#2d3250"),
        yaxis=dict(showgrid=True, gridcolor="#2d3250"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(t=40, b=20, l=20, r=20),
        hovermode="x unified",
    )
    fig.update_traces(
        hovertemplate="<b>%{fullData.name}</b><br>Data: %{x|%d/%m/%Y}<br>Quantidade: %{y}<extra></extra>",
    )
    st.plotly_chart(fig, use_container_width=True)


# --------------------------------------------------------------------------- #
#  Ranking Completo
# --------------------------------------------------------------------------- #

def _render_ranking_completo(ranking) -> None:
    st.subheader("📊 Ranking Completo")

    if not ranking:
        st.info("Nenhum dado disponível.")
        return

    rank_svc = RankingService()
    df       = rank_svc.ranking_para_dataframe(ranking)

    def _cor_posicao(val):
        cores = {"1°": "#ffd700", "2°": "#c0c0c0", "3°": "#cd7f32"}
        return f"color: {cores.get(val, '#ccd6f6')}; font-weight: bold;"

    if "Nível" in df.columns:
        df = df.drop(columns=["Nível"])

    fmt_cols = {c: "{:,}" for c in ["Pontos", "Reactions", "Comentários", "Shares", "Total Interações"] if c in df.columns}

    styled = (
        df.style
        .applymap(_cor_posicao, subset=["Posição"])
        .format(fmt_cols)
        .set_properties(**{"text-align": "center"})
        .hide(axis="index")
    )

    st.dataframe(
        styled,
        use_container_width=True,
        height=min(400, len(df) * 40 + 50),
    )


# --------------------------------------------------------------------------- #
#  Engajamento por Post
# --------------------------------------------------------------------------- #

def _render_engajamento_por_post(df_posts: pd.DataFrame) -> None:
    st.subheader("📝 Engajamento por Post")

    if df_posts.empty:
        st.info("Nenhum post encontrado.")
        return

    df = df_posts.copy()

    if "url_post" in df.columns:
        df["Link"] = df["url_post"].where(df["url_post"].notna(), other=None)
        df = df.drop(columns=["url_post"])

    df = df.rename(columns={
        "post_id":          "Post ID",
        "data_post":        "Data",
        "reactions":        "👍 Reações",
        "comentarios":      "💬 Comentários",
        "shares":           "🔄 Compartilhamentos",
        "total_interacoes": "Total",
        "pontos":           "⭐ Pontos",
    })

    st.dataframe(
        df,
        use_container_width=True,
        column_config={"Link": st.column_config.LinkColumn("🔗 Link", display_text="Ver post")},
        hide_index=True,
    )


# --------------------------------------------------------------------------- #
#  Main
# --------------------------------------------------------------------------- #

def main() -> None:
    _render_sidebar()

    with st.spinner("Carregando dados..."):
        dados, erro = _carregar_dados()

    if erro or dados is None:
        st.error(f"Erro ao carregar dados: {erro}")
        st.info(
            "Verifique se:\n"
            "1. O arquivo `.env` está configurado corretamente.\n"
            "2. O banco de dados existe (execute `scripts/coletar_engajamento.py` primeiro).\n"
            "3. As variáveis `LINKEDIN_EMAIL`, `LINKEDIN_PASSWORD` e `LINKEDIN_COMPANY_URL` estão definidas."
        )
        return

    kpis    = dados["kpis"]
    ranking = dados["ranking"]

    _render_header()

    _render_kpis(kpis)
    st.markdown("---")

    _render_top3(ranking)
    st.markdown("---")

    _render_graficos(dados["df_tipos"], ranking)
    st.markdown("---")

    _render_evolucao_temporal(dados["df_temp"])
    st.markdown("---")

    _render_ranking_completo(ranking)
    st.markdown("---")

    _render_engajamento_por_post(dados["df_posts"])

    st.markdown("---")
    st.caption("LinkedIn Engagement Tracker | Dados desde 06/01/2026 | Uso interno")


if __name__ == "__main__":
    main()
