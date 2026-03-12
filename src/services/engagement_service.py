"""
engagement_service.py - Serviço de regras de negócio para engajamento.

Responsabilidade: orquestrar a persistência e consulta de engajamentos,
posts e usuários. Não conhece detalhes de banco de dados.
"""

from __future__ import annotations

from datetime import date
from typing import Dict, List, Tuple

import pandas as pd

from src.core.logger import get_logger
from src.models.engagement import Engagement, TipoInteracao
from src.models.post import Post
from src.models.user import User
from src.repository.engagement_repository import IEngagementRepository
from src.repository.post_repository import IPostRepository
from src.repository.user_repository import IUserRepository

logger = get_logger(__name__)


class EngagementService:
    """
    Coordena a persistência de dados coletados pelo scraper
    e fornece consultas para o dashboard e scripts.
    """

    def __init__(
        self,
        engagement_repo: IEngagementRepository,
        post_repo: IPostRepository,
        user_repo: IUserRepository,
    ) -> None:
        self._engagement_repo = engagement_repo
        self._post_repo = post_repo
        self._user_repo = user_repo

    # ------------------------------------------------------------------ #
    #  Persistência
    # ------------------------------------------------------------------ #

    def _resolver_ids_por_nome(self, engagements: List[Engagement]) -> Dict[str, str]:
        """
        Garante que o mesmo nome sempre use o mesmo usuario_id no banco.

        Carrega todos os usuários existentes uma vez, monta um mapa
        nome_normalizado → usuario_id e retorna o mapa completo para os
        nomes presentes nesta lista de engagements.

        Nomes novos mantêm o ID gerado pelo scraper (hash da URL).
        Nomes já existentes recebem o ID já registrado no banco, evitando
        que a mesma pessoa apareça com IDs diferentes em coletas distintas.
        """
        todos = self._user_repo.buscar_todos()
        mapa_existente: Dict[str, str] = {
            u.nome.strip().lower(): u.usuario_id for u in todos
        }

        mapa_resultado: Dict[str, str] = {}
        for e in engagements:
            nome_norm = e.usuario.strip().lower()
            if nome_norm not in mapa_resultado:
                if nome_norm in mapa_existente:
                    mapa_resultado[nome_norm] = mapa_existente[nome_norm]
                else:
                    # Novo usuário: usa o ID gerado pelo scraper e registra
                    mapa_resultado[nome_norm] = e.usuario_id
                    mapa_existente[nome_norm] = e.usuario_id  # evita conflito dentro do lote

        return mapa_resultado

    def registrar_engajamentos_post(
        self,
        post: Post,
        engagements: List[Engagement],
    ) -> Dict[str, int]:
        """
        Persiste os dados de um post, seus engajamentos e os usuários envolvidos.

        Deduplicação de usuários por nome: se o mesmo nome já existir no banco
        com outro ID (de uma coleta anterior), o ID existente é reutilizado
        e o engagement é vinculado ao mesmo registro de usuário.

        Returns:
            {"inseridos": N, "duplicatas": M}
        """
        logger.info("Registrando post %s com %d interações.", post.post_id, len(engagements))

        self._post_repo.salvar(post)

        if not engagements:
            return {"inseridos": 0, "duplicatas": 0}

        # Resolve IDs por nome para evitar duplicatas de usuário entre coletas
        mapa_nome_id = self._resolver_ids_por_nome(engagements)
        for e in engagements:
            e.usuario_id = mapa_nome_id[e.usuario.strip().lower()]

        # Persiste usuários únicos (por nome normalizado)
        usuarios_vistos: set = set()
        users: List[User] = []
        for e in engagements:
            nome_norm = e.usuario.strip().lower()
            if nome_norm not in usuarios_vistos:
                usuarios_vistos.add(nome_norm)
                users.append(User(usuario_id=e.usuario_id, nome=e.usuario))
        if users:
            self._user_repo.salvar_em_lote(users)

        inseridos = self._engagement_repo.salvar_em_lote(engagements)
        duplicatas = len(engagements) - inseridos

        logger.info("Post %s: %d inseridos, %d duplicatas.", post.post_id, inseridos, duplicatas)
        return {"inseridos": inseridos, "duplicatas": duplicatas}

    def registrar_lote_posts(
        self,
        dados: List[Tuple[Post, List[Engagement]]],
    ) -> Dict[str, int]:
        """Registra múltiplos posts e seus engajamentos."""
        total_inseridos = 0
        total_duplicatas = 0

        for post, engagements in dados:
            resultado = self.registrar_engajamentos_post(post, engagements)
            total_inseridos += resultado["inseridos"]
            total_duplicatas += resultado["duplicatas"]

        logger.info(
            "Lote completo: %d posts, %d inseridos, %d duplicatas.",
            len(dados), total_inseridos, total_duplicatas,
        )
        return {
            "posts_processados": len(dados),
            "inseridos": total_inseridos,
            "duplicatas": total_duplicatas,
        }

    # ------------------------------------------------------------------ #
    #  Consultas
    # ------------------------------------------------------------------ #

    def obter_estatisticas_gerais(self) -> Dict[str, int]:
        """Estatísticas gerais para exibição no dashboard."""
        total_interacoes = self._engagement_repo.contar_total()
        total_posts = self._post_repo.contar_total()
        total_usuarios = self._user_repo.contar_total()

        df_tipos = self._engagement_repo.get_engajamento_por_tipo_dataframe()

        reactions = comentarios = shares = 0
        if not df_tipos.empty:
            for _, row in df_tipos.iterrows():
                if row["tipo"] == TipoInteracao.LIKE.value:
                    reactions = int(row["quantidade"])
                elif row["tipo"] == TipoInteracao.COMENTARIO.value:
                    comentarios = int(row["quantidade"])
                elif row["tipo"] == TipoInteracao.SHARE.value:
                    shares = int(row["quantidade"])

        pontos_totais = reactions * 1 + comentarios * 2 + shares * 2

        return {
            "total_interacoes": total_interacoes,
            "total_posts": total_posts,
            "total_usuarios": total_usuarios,
            "total_reactions": reactions,
            "total_comentarios": comentarios,
            "total_shares": shares,
            "pontos_totais": pontos_totais,
        }

    def obter_engajamentos_por_periodo(self, inicio: date, fim: date) -> List[Engagement]:
        return self._engagement_repo.buscar_por_periodo(inicio, fim)

    def obter_todos_posts(self) -> List[Post]:
        return self._post_repo.buscar_todos()

    def get_ranking_dataframe(self) -> pd.DataFrame:
        return self._engagement_repo.get_ranking_dataframe()

    def get_evolucao_temporal_dataframe(self) -> pd.DataFrame:
        return self._engagement_repo.get_evolucao_temporal_dataframe()

    def get_engajamento_por_tipo_dataframe(self) -> pd.DataFrame:
        return self._engagement_repo.get_engajamento_por_tipo_dataframe()

    def get_engajamento_por_post_dataframe(self) -> pd.DataFrame:
        return self._engagement_repo.get_engajamento_por_post_dataframe()