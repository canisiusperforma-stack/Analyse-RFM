"""Schémas de la base documentaire et du chatbot documentaire.

Ce module ne décrit que les **contrats d'entrée** des routes
`/api/v1/documents`. La logique d'indexation, de recherche et de contrôle
d'ancrage vit dans `app.rag` et `app.models.document` ; les routes ne font que
valider, autoriser et traduire en code HTTP.

Les bornes ne sont pas décoratives : elles reprennent la configuration
(`RAG_QUESTION_MAX`, `RAG_HISTORIQUE_TOURS`, `RAG_TAILLE_MAX_OCTETS`) plutôt que
des valeurs en dur, afin que le contrat HTTP et le traitement interne ne puissent
pas diverger. Un client qui envoie une question de 2 000 caractères est refusé
ici, pas Trimée puis acceptée.

`Literal` et constantes
    `NiveauConfidentialite` et `RoleAutorise` dupliquent
    respectivement `app.models.document.NIVEAUX_CONFIDENTIALITE` et
    `app.services.permission_service.ROLES` : `Literal` est evaluated au
    chargement du module, il ne peut donc pas être construit à partir d'une
    variable. Cette duplication est contrôlée par
    `tests/test_rag.py::test_types_document_alignes_sur_le_rbac`, qui échoue si
    les deux listes divergent — un niveau ajouté au modèle sans être déclaré ici
    serait rejeté par l'API, ce que le test rend visible immédiatement.

Réponses
    Aucun schéma de sortie n'est déclaré, comme pour l'assistant analytique. La
    forme d'une réponse de `rag_service` dépend du chemin parcouru — absence de
    source, modèle indisponible, contrôle d'ancrage rejeté, réponse acceptée — et
    un modèle figé contraindrait cet audit au lieu de le décrire. Les routes
    renvoient donc le dictionnaire produit par le service, comme le reste de
    l'API.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.config import settings
from app.schemas.assistant import TourConversation

#: Doit rester aligné sur `app.models.document.NIVEAUX_CONFIDENTIALITE`.
NiveauConfidentialite = Literal["interne", "restreinte", "confidentielle"]

#: Doit rester aligné sur `app.services.permission_service.ROLES`.
RoleAutorise = Literal["ADMIN", "RESPONSABLE", "ANALYSTE", "AGENT"]


class AccesDocument(BaseModel):
    """Corps de la requête de reclassification d'un document.

    Réservé à `ADMIN` (`documents:acces`). Le changement est répercuté sur les
    extraits déjà indexés : sans cela, un document promu de `interne` à
    `confidentielle` continuerait de répondre par des extraits portant encore
    l'ancienne classification.

    Un document `restreinte` ou `confidentielle` doit désigner au moins un rôle.
    La règle est répétée ici, et non laissée au modèle, pour que le refus
    parvienne au client en `422` avec le détail du champ fautif, plutôt qu'en
    `500` depuis une couche plus profonde.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    confidentialite: NiveauConfidentialite = Field(
        description=(
            "Niveau de diffusion. `interne` : tout utilisateur disposant de "
            "`documents:voir`. `restreinte` : rôles listés. `confidentielle` : "
            "rôles **et** utilisateurs listés."
        ),
    )
    roles_autorises: list[RoleAutorise] = Field(
        default_factory=list,
        max_length=4,
        description="Rôles autorisés à lire le document.",
        examples=[["RESPONSABLE"]],
    )
    utilisateurs_autorises: list[str] = Field(
        default_factory=list,
        max_length=500,
        description=(
            "Identifiants d'utilisateurs nommément autorisés. N'a d'effet qu'au "
            "niveau `confidentielle`, où il s'ajoute à la liste des rôles."
        ),
        examples=[["665f1b2c3d4e5f6a7b8c9d0e"]],
    )

    @model_validator(mode="after")
    def _verifier_role_obligatoire(self) -> "AccesDocument":
        if self.confidentialite != "interne" and not self.roles_autorises:
            raise ValueError(
                f"Un document « {self.confidentialite} » doit désigner au moins "
                "un rôle autorisé, sans quoi il serait inaccessible à tous."
            )
        return self

    def normalise(self) -> dict:
        """Données à écrire sur le document, sans champ vide ni doublon."""
        return {
            "confidentialite": self.confidentialite,
            "roles_autorises": sorted(set(self.roles_autorises)),
            "utilisateurs_autorises": sorted(
                {identifiant for identifiant in self.utilisateurs_autorises if identifiant}
            ),
        }


class QuestionDocumentaire(BaseModel):
    """Corps de la requête « poser une question sur les documents ».

    `documents` restreint la recherche à un sous-ensemble de la base. Ce
    périmètre est **combiné** à la clause d'accès, jamais substitué à elle
    (`app.rag.vector_store.construire_filtre`) : un document listé ici mais non
    autorisé reste donc inaccessible.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    question: str = Field(
        min_length=1,
        max_length=settings.RAG_QUESTION_MAX,
        description=(
            "Question en langage naturel. Le modèle n'est appelé que si un "
            "extrait autorisé dépasse le seuil de pertinence."
        ),
        examples=["Quelles sont les modalités d'octroi de la subvention ?"],
    )
    historique: list[TourConversation] = Field(
        default_factory=list,
        max_length=settings.RAG_HISTORIQUE_TOURS * 2,
        description=(
            "Tours précédents. Assurent la continuité de conversation ; ne sont "
            "jamais une source, et leurs chiffres ne sont pas réutilisables."
        ),
    )
    documents: Optional[list[str]] = Field(
        default=None,
        max_length=50,
        description=(
            "Restreint la recherche à ces documents. Ignoré si absent. Ne "
            "confère aucun accès supplémentaire."
        ),
    )
    nombre: Optional[int] = Field(
        default=None,
        ge=1,
        le=20,
        description=(
            "Nombre maximal d'extraits retenus (défaut : "
            f"`RAG_RECHERCHE_TOP_K` = {settings.RAG_RECHERCHE_TOP_K})."
        ),
    )
