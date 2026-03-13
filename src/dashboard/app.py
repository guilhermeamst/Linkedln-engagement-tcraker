"""
app.py - Dashboard executivo LinkedIn Engagement Tracker.

Executar com: streamlit run src/dashboard/app.py
"""

from __future__ import annotations

import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st
import streamlit.components.v1 as components

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from src.core.logger import get_logger
from src.database.database import DatabaseManager
from src.repository.engagement_repository import EngagementRepository
from src.repository.post_repository import PostRepository
from src.repository.user_repository import UserRepository
from src.services.analytics_service import AnalyticsService
from src.services.engagement_service import EngagementService
from src.services.ranking_service import RankingService

logger = get_logger(__name__)


def _inject_calendario_pt() -> None:
    """Traduz o calendário Streamlit para português.

    - CSS puro para abreviações dos dias (100% confiável, sem JS).
    - requestAnimationFrame para nomes dos meses (sobrevive a re-renders do React).
    """
    # ── Dias via CSS ::after ──────────────────────────────────────────────────
    st.markdown("""
<style>
[data-baseweb="calendar"] abbr { font-size: 0 !important; }
[data-baseweb="calendar"] abbr[title="Sunday"]::after    { content: "Dom"; font-size: 0.85rem; }
[data-baseweb="calendar"] abbr[title="Monday"]::after    { content: "Seg"; font-size: 0.85rem; }
[data-baseweb="calendar"] abbr[title="Tuesday"]::after   { content: "Ter"; font-size: 0.85rem; }
[data-baseweb="calendar"] abbr[title="Wednesday"]::after { content: "Qua"; font-size: 0.85rem; }
[data-baseweb="calendar"] abbr[title="Thursday"]::after  { content: "Qui"; font-size: 0.85rem; }
[data-baseweb="calendar"] abbr[title="Friday"]::after    { content: "Sex"; font-size: 0.85rem; }
[data-baseweb="calendar"] abbr[title="Saturday"]::after  { content: "S\00e1b"; font-size: 0.85rem; }
</style>
""", unsafe_allow_html=True)

    # ── Meses via JS com rAF (combate re-renders do React) ───────────────────
    components.html("""
<script>
(function(){
    var M={
        'January':'Janeiro','February':'Fevereiro','March':'Mar\u00e7o',
        'April':'Abril','May':'Maio','June':'Junho','July':'Julho',
        'August':'Agosto','September':'Setembro','October':'Outubro',
        'November':'Novembro','December':'Dezembro'
    };
    function run(){
        try{
            var d=window.parent.document;
            d.querySelectorAll('[data-baseweb="calendar"] select option')
             .forEach(function(e){ if(M[e.text]) e.text=M[e.text]; });
            d.querySelectorAll('[data-baseweb="calendar"] button')
             .forEach(function(e){
                 if(!e.children.length){ var t=e.textContent.trim(); if(M[t]) e.textContent=M[t]; }
             });
        }catch(x){}
        requestAnimationFrame(run);
    }
    run();
})();
</script>
""", height=1, scrolling=False)


# --------------------------------------------------------------------------- #
#  Configuração da Página
# --------------------------------------------------------------------------- #

st.set_page_config(
    page_title="LinkedIn Engagement Tracker",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
    /* ── Base ────────────────────────────────────────────────────────── */
    .main { background-color: #0f1116; }
    .block-container {
        padding: 4rem 2rem 2rem 2rem;
        max-width: 100%;
    }

    /* ── KPI Grid ────────────────────────────────────────────────────── */
    .kpi-grid {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 0.85rem;
        margin-bottom: 1.5rem;
    }
    .kpi-card {
        background: linear-gradient(145deg, #1a1f35 0%, #1e2438 100%);
        border: 1px solid rgba(255,255,255,0.06);
        border-radius: 16px;
        padding: 1.25rem 1.4rem 1.1rem;
        position: relative;
        overflow: hidden;
        transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
        box-shadow: 0 4px 16px rgba(0,0,0,0.3);
    }
    .kpi-card:hover {
        transform: translateY(-3px);
        box-shadow: 0 10px 30px rgba(0,0,0,0.5);
        border-color: var(--accent);
    }
    .kpi-card::before {
        content: "";
        position: absolute;
        top: 0; left: 0; right: 0;
        height: 3px;
        background: var(--accent);
        border-radius: 16px 16px 0 0;
    }
    .kpi-card::after {
        content: "";
        position: absolute;
        bottom: -22px; right: -22px;
        width: 88px; height: 88px;
        background: var(--accent);
        border-radius: 50%;
        opacity: 0.07;
        pointer-events: none;
    }
    .kpi-icon { font-size: 1.4rem; line-height: 1; margin-bottom: 0.65rem; display: block; }
    .kpi-value {
        font-size: 2rem; font-weight: 800;
        color: #e8eaf6;
        line-height: 1; margin-bottom: 0.35rem; letter-spacing: -0.02em;
    }
    .kpi-label {
        font-size: 0.7rem; font-weight: 600;
        color: #5a6685;
        text-transform: uppercase; letter-spacing: 0.09em;
    }
    .kpi-section-title {
        font-size: 0.68rem; font-weight: 700;
        color: #3d4b65;
        text-transform: uppercase; letter-spacing: 0.13em;
        margin: 1.2rem 0 0.55rem 0.1rem;
        display: flex; align-items: center; gap: 0.5rem;
    }
    .kpi-section-title::after {
        content: ""; flex: 1; height: 1px;
        background: linear-gradient(90deg, #2d3250 0%, transparent 100%);
    }

    /* ── Título principal ────────────────────────────────────────────── */
    .main-title {
        background: linear-gradient(90deg, #0077b6, #00b4d8, #48cae4);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        display: block; font-size: 2.8rem; font-weight: 800;
        margin-bottom: 0; padding: 0.3rem 0.1rem; line-height: 1.2;
    }
    .subtitulo { color: #8892b0; font-size: 0.95rem; margin-top: 0.3rem; }

    /* ── Top 3 cards ─────────────────────────────────────────────────── */
    .top-card {
        background: linear-gradient(135deg, #1a1f35 0%, #252d4a 100%);
        border-radius: 16px; padding: 1.5rem 1rem; text-align: center;
        border: 1px solid #3d4466;
        box-shadow: 0 8px 24px rgba(0,0,0,0.5);
        margin: 0.4rem; height: 100%; box-sizing: border-box;
        transition: transform 0.18s ease, box-shadow 0.18s ease;
    }
    .top-card:hover { transform: translateY(-4px); }
    .top-card-gold   { border-color: #ffd700; box-shadow: 0 8px 24px rgba(255,215,0,0.2); }
    .top-card-silver { border-color: #c0c0c0; box-shadow: 0 8px 24px rgba(192,192,192,0.2); }
    .top-card-bronze { border-color: #cd7f32; box-shadow: 0 8px 24px rgba(205,127,50,0.2); }
    .top-card-gold:hover   { box-shadow: 0 14px 36px rgba(255,215,0,0.35); }
    .top-card-silver:hover { box-shadow: 0 14px 36px rgba(192,192,192,0.35); }
    .top-card-bronze:hover { box-shadow: 0 14px 36px rgba(205,127,50,0.35); }

    .medal       { font-size: 2.5rem; }
    .top-nome    { color: #ccd6f6; font-size: 1rem; font-weight: 700; margin: 0.4rem 0 0.2rem; word-break: break-word; }
    .top-pontos  { color: #64ffda; font-size: 1.7rem; font-weight: 800; }
    .top-detalhe { color: #8892b0; font-size: 0.78rem; margin-top: 0.3rem; }

    /* ── Botões ──────────────────────────────────────────────────────── */
    button[kind="secondary"], button[kind="primary"] {
        min-height: 44px !important; font-size: 0.9rem !important;
    }

    /* ── Misc ────────────────────────────────────────────────────────── */
    hr { border-color: #2d3250; margin: 1.5rem 0; }
    section[data-testid="stSidebar"] { background-color: #13151f; }
    section[data-testid="stSidebar"] *:not(button):not(button *) { color: #ccd6f6; }
    section[data-testid="stSidebar"] button {
        background-color: #0077b6; color: #ffffff !important;
        border: none; border-radius: 8px; min-height: 44px !important;
    }
    section[data-testid="stSidebar"] button:hover {
        background-color: #00b4d8; color: #ffffff !important;
    }
    section[data-testid="stSidebar"] table {
        font-size: 0.82rem; width: 100%; overflow-x: auto; display: block;
    }
    [data-testid="stDataFrame"] > div { overflow-x: auto !important; }
    [data-testid="stHorizontalBlock"],
    [data-testid="stColumns"] { flex-wrap: wrap !important; gap: 0.5rem !important; }

    /* ── Responsividade ──────────────────────────────────────────────── */
    @media screen and (max-width: 900px) {
        .block-container { padding: 3rem 1rem 1.5rem 1rem !important; }
        .main-title { font-size: 2.2rem !important; }
        .kpi-grid { grid-template-columns: repeat(3, 1fr) !important; }
        .kpi-value { font-size: 1.6rem !important; }
        [data-testid="stHorizontalBlock"] > div[data-testid="stColumn"],
        [data-testid="stColumn"] {
            flex: 1 1 calc(33% - 0.5rem) !important;
            min-width: calc(33% - 0.5rem) !important;
        }
    }
    @media screen and (max-width: 640px) {
        .block-container { padding: 2rem 0.5rem 1rem 0.5rem !important; }
        .main-title  { font-size: 1.75rem !important; }
        .subtitulo   { font-size: 0.82rem !important; }
        .kpi-grid { grid-template-columns: repeat(2, 1fr) !important; gap: 0.6rem !important; }
        .kpi-card { padding: 1rem 1rem 0.85rem !important; }
        .kpi-value { font-size: 1.4rem !important; }
        .kpi-label { font-size: 0.65rem !important; }
        .top-card   { padding: 1rem 0.75rem !important; margin: 0.2rem 0 !important; }
        .medal      { font-size: 2rem !important; }
        .top-nome   { font-size: 0.9rem !important; }
        .top-pontos { font-size: 1.4rem !important; }
        .top-detalhe { font-size: 0.7rem !important; }
        [data-testid="stHorizontalBlock"] > div[data-testid="stColumn"]:has(.js-plotly-plot),
        [data-testid="stColumn"]:has(.js-plotly-plot) {
            flex: 1 1 100% !important; min-width: 100% !important;
        }
    }
    @media screen and (max-width: 420px) {
        .block-container { padding: 1.5rem 0.25rem 0.75rem 0.25rem !important; }
        .main-title { font-size: 1.4rem !important; }
        .kpi-grid { grid-template-columns: 1fr !important; }
        .top-pontos { font-size: 1.2rem !important; }
    }
</style>
""", unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
#  Inicialização (cached)
# --------------------------------------------------------------------------- #

def _get_db_path() -> Path:
    """Lê DB_PATH de st.secrets (Streamlit Cloud) ou variável de ambiente (local)."""
    import os
    try:
        db_name = st.secrets.get("DB_PATH", os.getenv("DB_PATH", "linkedin_engagement.db"))
    except Exception:
        db_name = os.getenv("DB_PATH", "linkedin_engagement.db")
    return ROOT / db_name


@st.cache_resource(show_spinner=False)
def _init_analytics() -> tuple[AnalyticsService | None, str | None]:
    """Inicializa o AnalyticsService uma única vez por sessão."""
    try:
        db        = DatabaseManager(_get_db_path())
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


@st.cache_data(ttl=300, show_spinner=False)
def _carregar_dados_filtrado(data_inicio: date, data_fim: date):
    """Carrega dados filtrados por período (cache por combinação de datas)."""
    analytics, erro = _init_analytics()
    if erro or analytics is None:
        return None, erro

    try:
        dados = analytics.obter_dados_filtrados(data_inicio, data_fim)
        return dados, None
    except Exception as e:
        logger.error("Erro ao carregar dados filtrados: %s", e, exc_info=True)
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
            st.cache_resource.clear()
            st.session_state["_dados_atualizados"] = True
            st.rerun()

        if st.session_state.pop("_dados_atualizados", False):
            st.toast("Dados atualizados com sucesso!", icon="✅")

        st.markdown("---")
        st.caption("Dados desde 01/03/2026")


# --------------------------------------------------------------------------- #
#  Cabeçalho
# --------------------------------------------------------------------------- #

def _render_header(data_min: date, data_max: date) -> tuple[date, date]:
    """Renderiza o cabeçalho com título e filtro de data. Retorna (inicio, fim) aplicados."""
    st.markdown(
        '<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0">',
        unsafe_allow_html=True,
    )

    # Se reset foi solicitado no ciclo anterior, aplica ANTES de criar os widgets
    if st.session_state.pop("_reset_filtro_pending", False):
        st.session_state["filtro_inicio_widget"]   = data_min
        st.session_state["filtro_fim_widget"]      = data_max
        st.session_state["filtro_inicio_aplicado"] = data_min
        st.session_state["filtro_fim_aplicado"]    = data_max

    # Datas dos inputs (podem mudar sem aplicar)
    if "filtro_inicio_widget" not in st.session_state:
        st.session_state["filtro_inicio_widget"] = data_min
    if "filtro_fim_widget" not in st.session_state:
        st.session_state["filtro_fim_widget"] = data_max

    # Datas efetivamente aplicadas (usadas para carregar dados)
    if "filtro_inicio_aplicado" not in st.session_state:
        st.session_state["filtro_inicio_aplicado"] = data_min
    if "filtro_fim_aplicado" not in st.session_state:
        st.session_state["filtro_fim_aplicado"] = data_max

    col_titulo, col_filtro = st.columns([3, 2], vertical_alignment="center")

    with col_titulo:
        st.markdown('<h1 class="main-title">LinkedIn Engagement Tracker</h1>', unsafe_allow_html=True)
        st.markdown('<p class="subtitulo">Ranking de engajamento da página corporativa — 2026</p>', unsafe_allow_html=True)

    with col_filtro:
        st.markdown(
            '<p style="font-size:0.7rem; font-weight:700; color:#0077b6; '
            'text-transform:uppercase; letter-spacing:0.1em; margin:0 0 0.4rem 0;">📅 Filtrar por Período</p>',
            unsafe_allow_html=True,
        )

        col_de, col_ate = st.columns(2)
        with col_de:
            st.date_input("De", min_value=data_min, max_value=data_max, key="filtro_inicio_widget", format="DD/MM/YYYY")
        with col_ate:
            st.date_input("Até", min_value=data_min, max_value=data_max, key="filtro_fim_widget", format="DD/MM/YYYY")

        col_aplicar, col_reset = st.columns(2)
        with col_aplicar:
            if st.button("✔ Aplicar", use_container_width=True, key="btn_aplicar_filtro", type="primary"):
                inicio = st.session_state["filtro_inicio_widget"]
                fim    = st.session_state["filtro_fim_widget"]
                if inicio > fim:
                    fim = inicio
                st.session_state["filtro_inicio_aplicado"] = inicio
                st.session_state["filtro_fim_aplicado"]    = fim
                st.rerun()
        with col_reset:
            if st.button("↺ Resetar", use_container_width=True, key="btn_reset_filtro_global"):
                st.session_state["_reset_filtro_pending"] = True
                st.rerun()

        inicio_ap = st.session_state["filtro_inicio_aplicado"]
        fim_ap    = st.session_state["filtro_fim_aplicado"]
        is_filtrado = (inicio_ap != data_min or fim_ap != data_max)
        if is_filtrado:
            st.markdown(
                f'<p style="font-size:0.72rem; color:#00b4d8; margin:0.3rem 0 0 0;">'
                f'🔵 {inicio_ap.strftime("%d/%m/%Y")} → {fim_ap.strftime("%d/%m/%Y")}</p>',
                unsafe_allow_html=True,
            )

    return st.session_state["filtro_inicio_aplicado"], st.session_state["filtro_fim_aplicado"]


# --------------------------------------------------------------------------- #
#  KPIs
# --------------------------------------------------------------------------- #

def _render_kpis(kpis: dict) -> None:
    GRUPOS = [
        ("Resumo Geral", [
            ("💬", "Interações",   kpis["total_interacoes"], "#0077b6"),
            ("⭐", "Pontos Totais", kpis["pontos_totais"],    "#f4c430"),
            ("📄", "Posts",        kpis["total_posts"],      "#00b4d8"),
            ("👤", "Usuários",     kpis["total_usuarios"],   "#48cae4"),
        ]),
        ("Engajamento", [
            ("👍", "Reações",           kpis["total_reactions"],   "#06d6a0"),
            ("💬", "Comentários",       kpis["total_comentarios"], "#a855f7"),
            ("🔄", "Compartilhamentos", kpis["total_shares"],      "#f97316"),
        ]),
    ]

    html = ""
    for titulo, items in GRUPOS:
        html += f'<div class="kpi-section-title">{titulo}</div><div class="kpi-grid">'
        for icon, label, value, accent in items:
            formatted = f"{value:,}".replace(",", ".")
            html += f"""
            <div class="kpi-card" style="--accent:{accent};">
                <span class="kpi-icon">{icon}</span>
                <div class="kpi-value">{formatted}</div>
                <div class="kpi-label">{label}</div>
            </div>"""
        html += "</div>"

    st.markdown(html, unsafe_allow_html=True)


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

    # Gera HTML de todos os cards de uma vez para melhor controle mobile
    cards_html = '<div style="display:flex; flex-wrap:wrap; gap:0.5rem; justify-content:center;">'
    for rank_idx in range(len(top3)):
        u = top3[rank_idx]
        medalha, classe = medalhas[rank_idx]
        cards_html += f"""
        <div class="top-card {classe}" style="flex:1 1 200px; max-width:320px;">
            <div class="medal">{medalha}</div>
            <div class="top-nome">{u.usuario}</div>
            <div class="top-pontos">{u.pontos} pts</div>
            <div class="top-detalhe">
                👍 {u.reactions} &nbsp;|&nbsp;
                💬 {u.comentarios} &nbsp;|&nbsp;
                🔄 {u.shares}
            </div>
        </div>"""
    cards_html += "</div>"
    st.markdown(cards_html, unsafe_allow_html=True)


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
    col1, col2 = st.columns([1, 1])

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
                margin=dict(t=80, b=80, l=20, r=20),
            )
            fig.update_traces(
                textinfo="percent+label",
                textfont_size=13,
                hovertemplate="<b>%{label}</b><br>Quantidade: %{value}<br>Participação: %{percent}<extra></extra>",
            )
            st.plotly_chart(fig, use_container_width=True, height=500)
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

    # Converter data e ordenar do mais antigo ao mais recente
    if "data_post" in df.columns:
        df["data_post"] = pd.to_datetime(df["data_post"])
        df = df.sort_values("data_post", ascending=True).reset_index(drop=True)

    if "url_post" in df.columns:
        df["Link"] = df["url_post"].where(df["url_post"].notna(), other=None)
        df = df.drop(columns=["url_post"])

    if "data_post" in df.columns:
        df["data_post"] = df["data_post"].dt.strftime("%d/%m/%Y")

    df = df.rename(columns={
        "post_id":          "Post ID",
        "data_post":        "Data",
        "reactions":        "👍 Reações",
        "comentarios":      "💬 Comentários",
        "shares":           "🔄 Compartilhamentos",
        "total_interacoes": "Total",
        "pontos":           "⭐ Pontos",
    })

    # Reordenar colunas: Link antes de Post ID
    cols = list(df.columns)
    if "Link" in cols and "Post ID" in cols:
        cols.remove("Link")
        idx_id = cols.index("Post ID")
        cols.insert(idx_id, "Link")
        df = df[cols]

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
    _inject_calendario_pt()

    # Carrega dados completos (para obter min/max de datas e cache)
    with st.spinner("Carregando dados..."):
        dados_completos, erro = _carregar_dados()

    if erro or dados_completos is None:
        st.error(f"Erro ao carregar dados: {erro}")
        st.info(
            "Verifique se:\n"
            "1. O banco de dados `linkedin_engagement.db` está presente no repositório.\n"
            "2. No Streamlit Cloud: configure `DB_PATH` em **App Settings → Secrets** (se necessário).\n"
            "3. Localmente: o arquivo `.env` está configurado corretamente."
        )
        return

    # Determina o intervalo de datas disponível
    df_posts_full = dados_completos["df_posts"]
    if not df_posts_full.empty and "data_post" in df_posts_full.columns:
        datas_validas = pd.to_datetime(df_posts_full["data_post"]).dropna()
        data_min_global = datas_validas.min().date()
        data_max_global = datas_validas.max().date()
    else:
        data_min_global = date(2026, 1, 6)
        data_max_global = date.today()

    # Renderiza cabeçalho com filtro de data
    data_inicio, data_fim = _render_header(data_min_global, data_max_global)

    # Usa dados filtrados se o período for diferente do intervalo completo
    is_filtrado = (data_inicio != data_min_global or data_fim != data_max_global)
    if is_filtrado:
        with st.spinner("Aplicando filtro..."):
            dados, erro_f = _carregar_dados_filtrado(data_inicio, data_fim)
        if erro_f or dados is None:
            st.warning("Erro ao filtrar dados — exibindo período completo.")
            dados = dados_completos
    else:
        dados = dados_completos

    kpis    = dados["kpis"]
    ranking = dados["ranking"]

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
    st.caption("LinkedIn Engagement Tracker | Dados desde 01/03/2026 | Uso interno")


if __name__ == "__main__":
    main()
