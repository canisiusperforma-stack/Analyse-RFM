"""Client du modèle de langage.

Transport HTTP réalisé avec la bibliothèque standard (`urllib`), exécuté dans
un fil d'exécution pour ne pas bloquer la boucle d'événements. Aucune
dépendance supplémentaire n'est introduite : l'API visée est le format
« chat completions » compatible OpenAI, ce qui couvre Ollama, vLLM, LM Studio,
vLLM auto-hébergé ainsi que les API distantes compatibles.

Le rôle de ce module est strictement technique : transmettre des messages et
rendre le texte produit. Il n'a aucune connaissance métier et ne valide rien —
c'est le rôle de `app.ai.response_validator`.

La température par défaut est nulle : une génération déterministe est la
stratégie la plus sûr pour un contexte où l'exactitude des chiffres prime sur
la variété rédactionnelle.
"""

from __future__ import annotations

import asyncio
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Optional

from app.config import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


class ErreurLLM(Exception):
    """Erreur générique du client LLM."""


class LLMIndisponible(ErreurLLM):
    """Le service de modèle de langage est injoignable ou désactivé."""


class LLMRefus(ErreurLLM):
    """Le service a répondu sans contenu exploitable."""


@dataclass
class ReponseLLM:
    """Résultat d'un appel au modèle."""

    texte: str
    modele: str
    fournisseur: str = "inconnu"
    duree_ms: int = 0
    tokens_entree: Optional[int] = None
    tokens_sortie: Optional[int] = None
    brut: dict[str, Any] = field(default_factory=dict)

    def resume(self) -> dict[str, Any]:
        return {
            "modele": self.modele,
            "fournisseur": self.fournisseur,
            "duree_ms": self.duree_ms,
            "tokens_entree": self.tokens_entree,
            "tokens_sortie": self.tokens_sortie,
        }


def llm_actif() -> bool:
    """Indique si un appel au modèle est autorisé par la configuration."""
    return bool(settings.LLM_ENABLED and settings.LLM_BASE_URL)


def _url_completion() -> str:
    base = settings.LLM_BASE_URL.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return f"{base}/chat/completions"


def _fournisseur() -> str:
    base = settings.LLM_BASE_URL.lower()
    if "11434" in base or "ollama" in base:
        return "ollama"
    if "openai.com" in base:
        return "openai"
    return "compatible-openai"


def _entetes() -> dict[str, str]:
    entetes = {"Content-Type": "application/json"}
    if settings.LLM_API_KEY:
        entetes["Authorization"] = f"Bearer {settings.LLM_API_KEY}"
    return entetes


def _extraire_texte(payload: dict[str, Any]) -> str:
    choix = payload.get("choices") or []
    if not choix:
        raise LLMRefus("Réponse du modèle sans choix exploitable.")
    message = choix[0].get("message") or {}
    contenu = message.get("content")
    if contenu is None:
        contenu = choix[0].get("text")
    if not isinstance(contenu, str) or not contenu.strip():
        raise LLMRefus("Réponse du modèle vide.")
    return contenu.strip()


def _extraire_usage(payload: dict[str, Any]) -> tuple[Optional[int], Optional[int]]:
    usage = payload.get("usage") or {}
    entree = usage.get("prompt_tokens")
    sortie = usage.get("completion_tokens")
    return (
        int(entree) if isinstance(entree, (int, float)) else None,
        int(sortie) if isinstance(sortie, (int, float)) else None,
    )


def _appeler_synchronicement(
    messages: list[dict[str, str]],
    temperature: float,
    tokens_max: int,
) -> dict[str, Any]:
    corps = json.dumps(
        {
            "model": settings.LLM_MODELE,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": tokens_max,
            "stream": False,
        },
        ensure_ascii=False,
    ).encode("utf-8")

    requete = urllib.request.Request(
        _url_completion(),
        data=corps,
        headers=_entetes(),
        method="POST",
    )

    try:
        with urllib.request.urlopen(
            requete, timeout=settings.LLM_DELAI_MAX
        ) as reponse:
            contenu = reponse.read().decode("utf-8")
    except urllib.error.HTTPError as erreur:
        detail = ""
        try:
            detail = erreur.read().decode("utf-8", "replace")[:500]
        except Exception:  # noqa: BLE001
            detail = ""
        raise LLMIndisponible(
            f"Le modèle a renvoyé une erreur HTTP {erreur.code} : {detail}"
        ) from erreur
    except (urllib.error.URLError, TimeoutError, OSError) as erreur:
        raise LLMIndisponible(
            f"Service de modèle de langage injoignable ({_url_completion()}) : "
            f"{erreur}"
        ) from erreur

    try:
        return json.loads(contenu)
    except json.JSONDecodeError as erreur:
        raise LLMRefus("Réponse du modèle illisible (JSON invalide).") from erreur


async def completer(
    messages: list[dict[str, str]],
    temperature: Optional[float] = None,
    tokens_max: Optional[int] = None,
) -> ReponseLLM:
    """Appelle le modèle et renvoie sa réponse textuelle.

    Lève `LLMIndisponible` si le LLM est désactivé ou injoignable, et
    `LLMRefus` si la réponse est vide. L'appelant doit prévoir un repli
    déterministe dans les deux cas.
    """
    if not llm_actif():
        raise LLMIndisponible(
            "Assistant IA désactivé (LLM_ENABLED=false) : la réponse est "
            "produite directement par le backend."
        )
    if not messages:
        raise LLMRefus("Aucun message à transmettre au modèle.")

    debut = time.perf_counter()
    try:
        payload = await asyncio.to_thread(
            _appeler_synchronicement,
            messages,
            settings.LLM_TEMPERATURE if temperature is None else temperature,
            settings.LLM_TOKENS_MAX if tokens_max is None else tokens_max,
        )
    except (LLMIndisponible, LLMRefus) as erreur:
        logger.warning("Appel LLM échoué : %s", erreur)
        raise

    duree_ms = int((time.perf_counter() - debut) * 1000)
    texte = _extraire_texte(payload)
    tokens_entree, tokens_sortie = _extraire_usage(payload)

    logger.info(
        "Appel LLM réussi (modèle=%s, durée=%s ms, tokens sortie=%s)",
        settings.LLM_MODELE,
        duree_ms,
        tokens_sortie,
    )
    return ReponseLLM(
        texte=texte,
        modele=payload.get("model") or settings.LLM_MODELE,
        fournisseur=_fournisseur(),
        duree_ms=duree_ms,
        tokens_entree=tokens_entree,
        tokens_sortie=tokens_sortie,
        brut=payload,
    )


async def verifier_disponibilite() -> dict[str, Any]:
    """État du service de modèle, pour la route de diagnostic."""
    etat: dict[str, Any] = {
        "actif": llm_actif(),
        "base_url": settings.LLM_BASE_URL if settings.LLM_ENABLED else None,
        "modele": settings.LLM_MODELE if settings.LLM_ENABLED else None,
        "fournisseur": _fournisseur() if settings.LLM_ENABLED else None,
        "joignable": False,
    }
    if not llm_actif():
        etat["raison"] = "LLM désactivé : réponses produites par le backend."
        return etat
    try:
        await completer(
            [
                {
                    "role": "user",
                    "content": "Réponds uniquement par le mot : PRET",
                }
            ],
            tokens_max=8,
        )
    except ErreurLLM as erreur:
        etat["raison"] = str(erreur)
        return etat
    etat["joignable"] = True
    return etat
