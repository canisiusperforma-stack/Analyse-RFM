"""Service des rapports : données consolidées par exercice.

Agrège les synthèses existantes (tableau de bord + budget) pour dresser un
rapport RFM complet et reproductible **par exercice**. Aucun chiffre n'est
écrit en dur : tout provient des collections métier, via les services déjà
en place (`dashboard_service`, `budget_service`).

Le rapport est ensuite sérialisé en Excel par `app.reports.excel_generator`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from app.services import budget_service, dashboard_service


async def exercices_disponibles() -> list[int]:
    """Exercices pour lesquels un rapport peut être dressé (décroissant).

    Reprise de la résolution du tableau de bord : exercices présents dans les
    crédits votés et/ou dans les demandes de remboursement.
    """
    return await dashboard_service.analyser_exercices()


async def collecter_rapport(exercice: Optional[int] = None) -> dict[str, Any]:
    """Consolide les indicateurs d'un exercice pour le rapport.

    Si `exercice` est absent, l'exercice le plus récent présent en base est
    utilisé (sinon l'année courante).
    """
    if exercice is None:
        disponibles = await exercices_disponibles()
        exercice = disponibles[0] if disponibles else datetime.now(timezone.utc).year
    exercice = int(exercice)

    synthese = await dashboard_service.calculer_synthese(exercice)
    budget = await budget_service.calculer_synthese(exercice)

    return {
        "exercice": exercice,
        "calcule_le": datetime.now(timezone.utc).isoformat(),
        "population": synthese["population"],
        "budget": {
            "total": budget["total"],
            "lignes": budget["lignes"],
            "serie_mensuelle": budget["serie_mensuelle"],
            "repartition_par_type": budget["repartition_par_type"],
        },
        "remboursements": synthese["remboursements"],
        "analytique": synthese["analytique"],
    }