"""Routes de la base documentaire et du chatbot documentaire.

Ce routeur est le **seul** point d'entrée du RAG. Il rend joignables des
fonctions qui existent déjà dans `app.rag` sans en réécrire aucune, et porte
trois responsabilités :

1. **Valider** le contrat d'entrée (`app.schemas.document`).
2. **Autoriser** — deux barrières distinctes et cumulatives :
   - la *permission* (`documents:voir`, `documents:televerser`,
     `documents:indexer`, `documents:acces`, `documents:telecharger`) règle
     l'accès à la **fonction** ;
   - la *confidentialité* (`app.models.document.document_visible`) règle l'accès
     au **document**. Elle est revérifiée ici, sur chaque route qui touche un
     document identifié, alors que la recherche l'applique déjà au niveau de
     chaque extrait.
3. **Traduire** en HTTP : `ErreurDocumentaire` (échec imputable au fichier
   déposé) devient `422`, un identifiant absent ou non lisible devient `404`.

Indiscernabilité
    Un document auquel l'utilisateur n'a pas droit renvoie `404`, jamais `403`.
    Un `403` confirmerait qu'il existe, ce qui suffit à cartographier la base
    documentaire : il suffit de tester des titres probables. La différence
    entre « absent » et « interdit » n'a aucune utilité pour l'appelant
    légitime, qui ne doit pas agir sur ce document de toute façon.

Confidentialité à l'import
    Un document déposé sans classification est `interne` : c'est la valeur la
    plus **ouverte**, et un dépôt ne peut donc pas contourner un classement.
    Inversement, déposer un document `restreinte` ou `confidentielle` exige la
    permission `documents:acces`, réservée à `ADMIN` : sans cela, n'importe quel
    rôle disposant de `documents:televerser` pourrait rendre confidentiel un
    fichier destiné à tous, puis le retirer aux autres en changeant sa
    classification — ou, à l'inverse, le publier en déposant un document
    confidentiel comme `interne`. Le dépôt et le classement sont deux actes
    distincts, et le second est réservé à l'administrateur.

Activation
    `RAG_ENABLED=false` suspend tout ce qui atteint le contenu des documents —
    indexation, recherche, chatbot — sans interdire d'administrer la base
    (dépôt, liste, suppression, reclassification). L'interface reste
    consultable, mais aucun texte n'est découpé, vectorisé ni transmis à un
    modèle. Le motif est alors un indisponible (`503`) et non une absence : il
    signale une fonctionnalité volontairement coupée, pas une information
    manquante.
"""

from __future__ import annotations

from typing import Annotated, Any, Optional
from urllib.parse import quote

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile

from app.config import settings
from app.models.document import (
    NIVEAUX_CONFIDENTIALITE,
    STATUTS_INDEXATION,
    construire_document,
    document_visible,
    extension_de_nom,
    filtre_acces_documents,
    normaliser_niveau,
    peut_gerer_acces,
    resumer,
    type_mime_de_extension,
)
from app.rag import document_loader, embeddings, prompt_builder, rag_service, vector_store
from app.rag.erreurs import ErreurDocumentaire
from app.rag.retriever import construire_sources
from app.repositories import document_repository
from app.schemas.document import AccesDocument, QuestionDocumentaire
from app.security.permissions import exiger_permission
from app.services.permission_service import ROLES
from app.utils.errors import (
    ErreurConflict,
    ErreurForbidden,
    ErreurIndisponible,
    ErreurNotFound,
    ErreurValidation,
)
from app.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()

_PERMISSION_VOIR = "documents:voir"
_PERMISSION_TELEVERSER = "documents:televerser"
_PERMISSION_TELECHARGER = "documents:telecharger"
_PERMISSION_SUPPRIMER = "documents:supprimer"
_PERMISSION_INDEXER = "documents:indexer"
_PERMISSION_ACCES = "documents:acces"


# --- Garde-fous ------------------------------------------------------------


def exiger_rag_actif() -> None:
    """Suspend toute opération atteignant le contenu des documents.

    Dépendance FastAPI. N'interdit ni l'administration de la base (liste,
    suppression, reclassification) ni le dépôt : ce sont des opérations sur des
    métadonnées. Seules celles qui lisent, découpent, vectorisent ou transmettent
    le texte exigent que la recherche documentaire soit active.
    """
    if not settings.RAG_ENABLED:
        raise ErreurIndisponible(
            "La recherche documentaire est désactivée (RAG_ENABLED=false). "
            "Aucun document n'est indexé ni transmis à un modèle. Réactivez-la "
            "dans la configuration pour utiliser l'assistant documentaire."
        )


def _identifiant(valeur: str) -> ObjectId:
    """Convertit un identifiant de document, ou échoue par `404`.

    Un identifiant mal formé ne peut désigner aucun document ; le traiter comme
    absent évite de distinguer une saisie invalide d'un document réellement
    supprimé, distinction sans aucun intérêt pour l'appelant.
    """
    try:
        return ObjectId(valeur)
    except (InvalidId, TypeError):
        raise ErreurNotFound("Document introuvable.")


async def _document_visible(identifiant: ObjectId, utilisateur: dict) -> dict:
    """Charge un document après avoir vérifié que l'utilisateur peut le lire.

    Applique `filtre_acces_documents` **dans la requête**, et non sur le
    résultat : un document interdit n'est jamais chargé, donc jamais présent en
    mémoire, jamais affichable par erreur de projection, jamais journalisable.
    `document_visible` est ensuite recontrôlé sur l'objet obtenu, pour que la
    route ne dépende pas de la seule correction de la requête.
    """
    document = await document_repository.recuperer_document_accessible(
        identifiant, filtre_acces_documents(utilisateur)
    )
    if document is None or not document_visible(document, utilisateur):
        raise ErreurNotFound("Document introuvable.")
    return document


def _analyser_liste(valeurs: Optional[list[str]]) -> list[str]:
    """Accepte `champ=a&champ=b` comme `champ=a,b`.

    Un `FormData` de navigateur produit naturellement des champs répétés, mais
    une sélection multiple dans un formulaire produit une chaîne unique séparée
    par des virgules. Accepter les deux évite que l'interface doive choisir, et
    donc qu'un oubli vide la liste — un document `restreinte` sans rôle deviendrait
    confidentiel pour personne, silencieusement.
    """
    if not valeurs:
        return []
    elements: list[str] = []
    for valeur in valeurs:
        elements.extend(part.strip() for part in str(valeur).split(","))
    return [element for element in elements if element]


def _verifier_roles(roles: list[str]) -> None:
    inconnus = sorted({role for role in roles if role not in ROLES})
    if inconnus:
        raise ErreurValidation({
            "roles_autorises": (
                f"Rôle(s) inconnu(s) : {', '.join(inconnus)}. "
                f"Rôles valides : {', '.join(ROLES)}."
            )
        })


def _verifier_identifiants(identifiants: list[str]) -> list[str]:
    """Valide la liste blanche d'utilisateurs d'un document confidentiel."""
    invalides = [i for i in identifiants if not ObjectId.is_valid(i)]
    if invalides:
        raise ErreurValidation({
            "utilisateurs_autorises": (
                f"Identifiant(s) d'utilisateur invalide(s) : {', '.join(invalides[:5])}."
            )
        })
    return identifiants


async def _lire_fichier_borne(fichier: UploadFile) -> bytes:
    """Lit le fichier déposé sans jamais dépasser la taille autorisée.

    La lecture est bornée à `RAG_TAILLE_MAX_OCTETS + 1` octets. Lire le fichier
    entier puis vérifier sa taille — le réflexe naturel — laisserait un dépôt
    de plusieurs gigaoctets charger la mémoire du serveur avant d'être refusé, ce
    qui transforme une vérification en porte d'entrée pour un déni de service.
    Un octet de marge suffit à savoir que la limite est dépassée, sans jamais
    charger le fichier entier.
    """
    limite = settings.RAG_TAILLE_MAX_OCTETS
    contenu = await fichier.read(limite + 1)

    if len(contenu) > limite:
        raise ErreurValidation({
            "fichier": (
                f"Fichier trop volumineux : maximum "
                f"{limite // (1024 * 1024)} Mo par document."
            )
        })
    if not contenu:
        raise ErreurValidation({"fichier": "Le fichier déposé est vide."})

    return contenu


def _en_tete_telechargement(nom_fichier: str) -> dict[str, str]:
    """En-tête `Content-Disposition` tolérant aux accents de nom de fichier.

    Un nom administratif contient accents et apostrophes ; sans la forme
    `filename*=UTF-8''…`, l'en-tête est illisible ou tronqué selon le client.
    """
    return {
        "Content-Disposition": (
            f'attachment; filename="document"; filename*=UTF-8\'\'{quote(nom_fichier)}'
        )
    }


# --- Importation -----------------------------------------------------------


@router.post(
    "",
    summary="Déposer un document",
    description=(
        "Dépose un fichier dans la base documentaire, l'archive en GridFS et "
        "l'indexe lorsque `RAG_EXTRACTION_AUTO` est actif.\n\n"
        "**Formats acceptés** : "
        + ", ".join(f"`.{item}`" for item in document_loader.formats_acceptes())
        + f" — taille maximale {settings.RAG_TAILLE_MAX_OCTETS // (1024 * 1024)} Mo.\n\n"
        "Le dépôt crée un document `interne`. Le classer `restreinte` ou "
        "`confidentielle` exige la permission `documents:acces` (ADMIN) : un "
        "dépôt ne peut ni restreindre ni publier un fichier par le seul fait "
        "d'exister.\n\n"
        "Un contenu déjà présent (même empreinte SHA-256) est refusé en `409`, "
        "y compris lorsque le document d'origine n'est pas visible : le "
        "contrôle de doublon ne peut pas être borné aux documents accessibles, "
        "sinon un contenu confidentiel pourrait être republié en `interne` par un "
        "second dépôt.\n\n"
        "Un document dont l'extraction échoue (PDF numérisé, format illisible) "
        "est **quand même enregistré**, avec le motif de l'échec : il reste "
        "listable et supprimable, seulement pas interrogeable."
    ),
    response_description="Document déposé, avec le compte rendu d'indexation.",
    status_code=201,
)
async def televerser_document(
    fichier: Annotated[UploadFile, File(description="Fichier à déposer.")],
    utilisateur: dict = Depends(exiger_permission(_PERMISSION_TELEVERSER)),
    description: Annotated[Optional[str], Form()] = None,
    confidentialite: Annotated[str, Form()] = "interne",
    roles_autorises: Annotated[Optional[list[str]], Form()] = None,
    utilisateurs_autorises: Annotated[Optional[list[str]], Form()] = None,
) -> dict[str, Any]:
    nom_fichier = (fichier.filename or "").strip()
    if not nom_fichier:
        raise ErreurValidation({"fichier": "Nom de fichier absent."})

    contenu = await _lire_fichier_borne(fichier)

    # L'extension est validée **avant** toute écriture : refuser un format
    # inextrayable après coup laisserait dans GridFS un fichier sans usage et
    # sans moyen de le supprimer depuis l'interface.
    extension = extension_de_nom(nom_fichier)
    formats = document_loader.formats_acceptes()
    if extension not in formats:
        raise ErreurValidation({
            "fichier": (
                f"Format « .{extension or 'inconnu'} » non pris en charge. "
                f"Formats acceptés : {', '.join('.' + f for f in formats)}."
            )
        })
    if extension not in settings.rag_extensions:
        raise ErreurValidation({
            "fichier": (
                f"Le format « .{extension} » n'est pas autorisé par la "
                f"configuration (RAG_EXTENSIONS). Formats autorisés : "
                f"{', '.join('.' + f for f in settings.rag_extensions)}."
            )
        })

    if confidentialite and confidentialite not in NIVEAUX_CONFIDENTIALITE:
        raise ErreurValidation({
            "confidentialite": (
                f"Niveau inconnu « {confidentialite} ». Niveaux valides : "
                f"{', '.join(NIVEAUX_CONFIDENTIALITE)}."
            )
        })
    niveau = normaliser_niveau(confidentialite)

    roles = _analyser_liste(roles_autorises)
    utilisateurs = _analyser_liste(utilisateurs_autorises)

    # Le dépôt est le moment où la classification est décidée : le vérifier
    # ici, et non seulement à la reclassification, empêche qu'un document
    # confidentiel existe avec un déposant qui ne pourrait pas le gérer.
    if niveau != "interne" and not peut_gerer_acces(utilisateur):
        raise ErreurForbidden(
            "Déposer un document classé exige la permission « documents:acces », "
            "réservée à l'administrateur. Déposez-le comme « interne » puis "
            "demandez sa classification."
        )
    _verifier_roles(roles)
    _verifier_identifiants(utilisateurs)

    try:
        document = construire_document(
            nom_fichier=nom_fichier,
            contenu=contenu,
            type_mime=fichier.content_type or type_mime_de_extension(extension),
            description=description,
            confidentialite=niveau,
            roles_autorises=roles,
            utilisateurs_autorises=utilisateurs,
            cree_par=utilisateur.get("_id"),
        )
    except ValueError as erreur:
        raise ErreurValidation({"confidentialite": str(erreur)}) from erreur

    # La recherche de doublon est **délibérément** faite sans clause d'accès.
    #
    # La borner aux documents visibles laisserait un contournement : un contenu
    # confidentiel dont l'on détient les octets pourrait être redéposé comme
    # `interne` — le doublon invisible n'étant pas trouvé — et la base
    # contiendrait alors une copie ouverte d'un document que l'on vient de
    # restreindre. Le refus ne dit rien de plus que ce que l'appelant sait
    # déjà, puisqu'il possède le contenu : ni nom, ni identifiant du document
    # masqué.
    doublon = await document_repository.lister_documents(
        filtre={"sha256": document["sha256"]},
        limite=1,
    )
    if doublon:
        existant = doublon[0]
        if document_visible(existant, utilisateur):
            raise ErreurConflict(
                "Ce contenu est déjà déposé sous le nom « "
                f"{existant.get('nom_fichier')} » (identifiant {existant.get('_id')}). "
                "Réindexez-le si sa classification a changé."
            )
        raise ErreurConflict(
            "Ce contenu est déjà présent dans la base documentaire, sous une "
            "classification à laquelle vous n'avez pas accès. Adressez-vous à "
            "l'administrateur pour le distinguer ou le faire reclasser."
        )

    file_id = await document_repository.sauvegarder_fichier(
        contenu, nom_fichier, document["type_mime"]
    )
    document["file_id"] = file_id

    try:
        identifiant = await document_repository.inserer_document(document)
    except Exception:
        # L'archivage a réussi, l'insertion non : le fichier resterait orphelin,
        # invisible dans la liste et donc impossible à supprimer par
        # l'interface. On le retire avant de propager l'erreur.
        try:
            await document_repository.supprimer_fichier(file_id)
        except Exception:  # noqa: BLE001
            logger.exception("Nettoyage GridFS impossible pour %s", file_id)
        raise

    logger.info(
        "Document « %s » (%s) déposé par %s, niveau %s.",
        nom_fichier, identifiant, utilisateur.get("role"), niveau,
    )

    indexation: Optional[dict[str, Any]] = None
    indexation_demandee = bool(settings.RAG_ENABLED and settings.RAG_EXTRACTION_AUTO)
    if indexation_demandee:
        resultat = await rag_service.indexer(identifiant)
        indexation = resultat.to_dict()

    enregistre = await document_repository.recuperer_document(identifiant)
    return {
        "document": resumer(enregistre or document),
        "indexation": indexation,
        "indexation_demandee": indexation_demandee,
    }


# --- Consultation ----------------------------------------------------------


@router.get(
    "",
    summary="Lister les documents accessibles",
    description=(
        "Documents que l'utilisateur est autorisé à lire, du plus récent au "
        "plus ancien.\n\n"
        "Le filtrage est appliqué en base : un document `restreinte` ou "
        "`confidentielle` non autorisé n'est pas renvoyé, et son existence "
        "n'est pas révélée."
    ),
)
async def lister(
    utilisateur: dict = Depends(exiger_permission(_PERMISSION_VOIR)),
    limite: int = Query(50, ge=1, le=200, description="Documents par page."),
    saut: int = Query(0, ge=0, description="Documents ignorés."),
) -> dict[str, Any]:
    filtre = filtre_acces_documents(utilisateur)
    documents = await document_repository.lister_documents(
        filtre=filtre, limite=limite, saut=saut
    )
    return {
        "documents": [resumer(document) for document in documents],
        "total": await document_repository.compter_documents(filtre),
        "limite": limite,
        "saut": saut,
    }


@router.get(
    "/referentiel",
    summary="Périmètre et garanties de l'assistant documentaire",
    description=(
        "Expose le pipeline tel qu'il est réellement configuré : étapes, "
        "formats acceptés, modèle d'embeddings, seuil de pertinence, règle "
        "d'ancrage et volume accessible à l'appelant.\n\n"
        "Sert à documenter *pourquoi* une question reste sans réponse, et à "
        "alimenter les suggestions de l'interface sans lui faire annoncer des "
        "capacités que le système n'a pas."
    ),
)
async def referentiel(
    utilisateur: dict = Depends(exiger_permission(_PERMISSION_VOIR)),
) -> dict[str, Any]:
    return {
        "actif": settings.RAG_ENABLED,
        "regles": [
            "Les réponses proviennent exclusivement des extraits indexés.",
            "Les connaissances générales du modèle ne sont jamais utilisées.",
            "Faute de source autorisée, l'information est déclarée introuvable "
            "sans appel au modèle.",
            "Chaque affirmation doit porter un marqueur de source [S1], [S2]…",
            "Une réponse non fondée est rejetée au profit des extraits.",
            "Un document interdit n'est jamais lu, vectorisé ni cité.",
        ],
        "pipeline": [
            "Extraction", "Nettoyage", "Découpage", "Embeddings", "Vector Store",
            "Recherche", "Contexte", "LLM", "Réponse + sources",
        ],
        "formats_acceptes": document_loader.formats_acceptes(),
        "formats_autorises": list(settings.rag_extensions),
        "taille_max_octets": settings.RAG_TAILLE_MAX_OCTETS,
        "niveaux_confidentialite": list(NIVEAUX_CONFIDENTIALITE),
        "statuts_indexation": list(STATUTS_INDEXATION),
        "seuil_pertinence": settings.RAG_SEUIL_PERTINENCE,
        "ponderation_dense": settings.RAG_PONDERATION_DENSE,
        "citations_exigees": settings.RAG_CITATIONS_EXIGEES,
        "recherche": {
            "top_k": settings.RAG_RECHERCHE_TOP_K,
            "candidats": settings.RAG_RECHERCHE_CANDIDATS,
            "sources_min": settings.RAG_SOURCES_MIN,
            "contexte_caracteres_max": settings.RAG_CONTEXTE_CARACTERES_MAX,
        },
        "decoupage": {
            "taille": settings.RAG_CHUNK_TAILLE,
            "taille_min": settings.RAG_CHUNK_TAILLE_MIN,
            "recouvrement": settings.RAG_CHUNK_RECOUVREMENT,
        },
        "embeddings": embeddings.decrire(),
        "prompt": prompt_builder.resume_prompt(),
        "morceaux_accessibles": await vector_store.compter_autorises(utilisateur),
    }


@router.get(
    "/statistiques",
    summary="État de la base documentaire",
    description=(
        "Volume de la base et des extraits, **restreint aux documents "
        "accessibles à l'appelant** : un total brut révélerait l'existence de "
        "documents qu'il n'a pas le droit de lire."
    ),
)
async def statistiques(
    utilisateur: dict = Depends(exiger_permission(_PERMISSION_VOIR)),
) -> dict[str, Any]:
    filtre = filtre_acces_documents(utilisateur)
    return {
        "documents_visibles": await document_repository.compter_documents(filtre),
        "documents_indexes": await document_repository.compter_documents(
            {**filtre, "statut_indexation": "indexe"}
        ),
        "morceaux_visibles": await vector_store.compter_autorises(utilisateur),
        "actif": settings.RAG_ENABLED,
    }


@router.get(
    "/recherche",
    summary="Rechercher des extraits (sans modèle)",
    description=(
        "Recherche les extraits correspondant à une question et renvoie les "
        "morceaux retenus, avec leur provenance et leur score.\n\n"
        "**Aucun modèle n'est appelé.** Cette route sert à explorer la base, à "
        "vérifier ce que le chatbot voit réellement, et à diagnostiquer une "
        "question qui resterait sans réponse.\n\n"
        "Une recherche dont le meilleur score reste sous le seuil renvoie une "
        "liste vide : mieux vaut signaler une absence que présenter un extrait "
        "sans rapport."
    ),
    dependencies=[Depends(exiger_rag_actif)],
)
async def rechercher(
    q: str = Query(
        ...,
        min_length=1,
        max_length=settings.RAG_QUESTION_MAX,
        description="Question ou termes recherchés.",
        examples=["modalités d'octroi de la subvention"],
    ),
    utilisateur: dict = Depends(exiger_permission(_PERMISSION_VOIR)),
    nombre: int = Query(
        default=0, ge=0, le=20, description="Extraits à renvoyer (0 = défaut)."
    ),
    documents: Optional[list[str]] = Query(
        default=None, description="Restreint la recherche à ces documents."
    ),
) -> dict[str, Any]:
    resultat = await rag_service.rechercher(
        question=q,
        utilisateur=utilisateur,
        nombre=nombre or None,
        documents=documents,
    )
    sources = construire_sources(resultat) if resultat.suffisant else []

    return {
        "question": resultat.question,
        "sources": [source.resume() for source in sources],
        "nb_sources": len(sources),
        "trouve": bool(sources),
        "seuil": resultat.seuil,
        "score_max": resultat.score_max,
        "recherche": resultat.resume(),
    }


# --- Chatbot documentaire --------------------------------------------------


@router.post(
    "/question",
    summary="Poser une question sur les documents",
    description=(
        "Répond à une question à partir des **seuls** documents autorisés.\n\n"
        "Le chemin est imposé : recherche des extraits autorisés au-dessus du "
        "seuil, puis — et seulement s'il y en a — constitution du contexte, "
        "appel du modèle, contrôle d'ancrage.\n\n"
        "**Aucune source, aucun appel au modèle.** Si aucun extrait autorisé "
        "n'atteint le seuil, la réponse indique que l'information n'a pas été "
        "trouvée dans les documents disponibles, et `mode` vaut `absence`.\n\n"
        "**Aucune connaissance extérieure.** Le modèle ne reçoit que les "
        "extraits fournis ; s'il cite une source inexistante ou avance un "
        "chiffre absent des extraits, sa réponse est rejetée (`mode` : "
        "`repli_controle_echoue`) au profit d'une restitution des extraits "
        "produite par le code.\n\n"
        "`mode` indique le chemin réellement parcouru : `llm`, `absence`, "
        "`repli_modele_indisponible`, `repli_controle_echoue` ou "
        "`sans_question`."
    ),
    response_description="Réponse, sources citées et traçabilité du contrôle.",
    dependencies=[Depends(exiger_rag_actif)],
)
async def poser_question(
    requete: QuestionDocumentaire,
    utilisateur: dict = Depends(exiger_permission(_PERMISSION_VOIR)),
) -> dict[str, Any]:
    reponse = await rag_service.repondre(
        question=requete.question,
        utilisateur=utilisateur,
        historique=[tour.model_dump() for tour in requete.historique],
        nombre=requete.nombre,
        documents=requete.documents,
    )
    return reponse.to_dict()


# --- Un document -----------------------------------------------------------


@router.get(
    "/{document_id}",
    summary="Consulter un document",
    description=(
        "Métadonnées d'un document, avec son état d'indexation et le motif "
        "d'un éventuel échec.\n\n"
        "Un document auquel l'appelant n'a pas droit renvoie `404` : un `403` "
        "confirmerait son existence."
    ),
)
async def consulter(
    document_id: str,
    utilisateur: dict = Depends(exiger_permission(_PERMISSION_VOIR)),
) -> dict[str, Any]:
    document = await _document_visible(_identifiant(document_id), utilisateur)
    return {
        "document": resumer(document),
        "erreur_indexation": document.get("erreur_indexation"),
    }


@router.get(
    "/{document_id}/telecharger",
    summary="Télécharger le fichier d'origine",
    description=(
        "Retourne le fichier déposé, tel qu'il a été reçu : le pipeline "
        "n'en conserve aucune version modifiée."
    ),
    response_class=Response,
)
async def telecharger(
    document_id: str,
    utilisateur: dict = Depends(exiger_permission(_PERMISSION_TELECHARGER)),
) -> Response:
    document = await _document_visible(_identifiant(document_id), utilisateur)

    file_id = document.get("file_id")
    if not isinstance(file_id, ObjectId):
        raise ErreurNotFound("Fichier d'origine introuvable pour ce document.")

    try:
        contenu = await document_repository.lire_fichier(file_id)
    except Exception as erreur:  # noqa: BLE001
        logger.error("Lecture du fichier %s impossible : %s", file_id, erreur)
        raise ErreurNotFound("Fichier d'origine introuvable pour ce document.")

    return Response(
        content=contenu,
        media_type=document.get("type_mime") or "application/octet-stream",
        headers=_en_tete_telechargement(str(document.get("nom_fichier") or "document")),
    )


@router.post(
    "/{document_id}/indexer",
    summary="(Ré)indexer un document",
    description=(
        "Relance le pipeline complet — extraction, nettoyage, découpage, "
        "vectorisation, écriture — sur un document.\n\n"
        "L'opération est **idempotente** : les extraits précédents sont "
        "remplacés, jamais doublés. `force=false` n'indexe que si le document "
        "ne l'est pas déjà.\n\n"
        "Un échec n'interrompt rien : le document est marqué en erreur, reste "
        "listable et supprimable, et le motif figure dans la réponse."
    ),
    dependencies=[Depends(exiger_rag_actif)],
)
async def indexer(
    document_id: str,
    utilisateur: dict = Depends(exiger_permission(_PERMISSION_INDEXER)),
    force: bool = Query(True, description="Réindexer même si déjà indexé."),
) -> dict[str, Any]:
    identifiant = _identifiant(document_id)
    await _document_visible(identifiant, utilisateur)

    try:
        resultat = await rag_service.indexer(identifiant, force=force)
    except ErreurDocumentaire as erreur:
        raise ErreurValidation({"document": erreur.message}) from erreur

    document = await document_repository.recuperer_document(identifiant)
    return {**resultat.to_dict(), "document": resumer(document) if document else None}


@router.patch(
    "/{document_id}/acces",
    summary="Fixer la confidentialité d'un document",
    description=(
        "Modifie le niveau de diffusion et la liste des autorisés "
        "(`documents:acces`, **ADMIN uniquement**).\n\n"
        "Le changement est **répercuté sur les extraits déjà indexés**. Sans "
        "cela, un document promu de `interne` à `confidentielle` continuerait de "
        "répondre par des extraits portant encore l'ancienne classification, "
        "donc de rester lisible par ceux qui ne devraient plus le voir.\n\n"
        "Aucun passe-droit n'est accordé à `ADMIN` : c'est l'administrateur "
        "lui-même qui doit figurer dans la liste blanche d'un document "
        "confidentiel, ce qui évite qu'un compte administrateur compromis "
        "expose par défaut l'ensemble de la base.\n\n"
        "Classer un document ne donne pas le droit de le lire. L'administrateur "
        "peut corriger une classification erronée sans être autorisé à ouvrir "
        "le document ; s'il ne l'est pas, la réponse ne lui renvoie que la "
        "classification appliquée, sans nom de fichier, empreinte ni "
        "description."
    ),
)
async def modifier_acces(
    document_id: str,
    acces: AccesDocument,
    utilisateur: dict = Depends(exiger_permission(_PERMISSION_ACCES)),
) -> dict[str, Any]:
    identifiant = _identifiant(document_id)

    # Le contrôle d'accès est ici **volontairement** absent : la route est
    # réservée à l'administrateur, qui doit pouvoir classer un document sans
    # être déjà autorisé à le lire — sans quoi un document confidentiel
    # deviendrait impossible à corriger par quiconque.
    #
    # Ce qui ne doit pas suivre, en revanche, c'est la divulgation : la
    # permission de classer n'est pas une permission de lire. Si l'administrateur
    # n'a pas accès au document, la réponse se limite à la classification qu'il
    # vient de poser, sans nom de fichier, empreinte ni description — ce qu'il
    # n'aurait pas pu obtenir par `GET /{document_id}`, qui renvoie `404`.
    document = await document_repository.recuperer_document(identifiant)
    if document is None:
        raise ErreurNotFound("Document introuvable.")

    lisible = document_visible(document, utilisateur)

    donnees = acces.normalise()
    _verifier_identifiants(donnees["utilisateurs_autorises"])

    await document_repository.modifier_document(identifiant, donnees)
    synchronises = await document_repository.synchroniser_acces_document(identifiant)

    if synchronises:
        logger.info(
            "Classification de %s mise à jour, %s extrait(s) resynchronisé(s).",
            identifiant, synchronises,
        )

    mis_a_jour = (await document_repository.recuperer_document(identifiant)) or document
    return {
        "document": resumer(mis_a_jour) if lisible else None,
        "classification": {
            "document_id": str(identifiant),
            "confidentialite": mis_a_jour.get("confidentialite"),
            "roles_autorises": mis_a_jour.get("roles_autorises") or [],
            "utilisateurs_autorises": mis_a_jour.get("utilisateurs_autorises") or [],
        },
        "morceaux_synchronises": synchronises,
    }


@router.delete(
    "/{document_id}",
    summary="Supprimer un document",
    description=(
        "Supprime le document, ses extraits indexés et son fichier d'origine.\n\n"
        "L'opération est irréversible : le document disparaît de toutes les "
        "réponses futures."
    ),
)
async def supprimer(
    document_id: str,
    utilisateur: dict = Depends(exiger_permission(_PERMISSION_SUPPRIMER)),
) -> dict[str, Any]:
    identifiant = _identifiant(document_id)
    document = await _document_visible(identifiant, utilisateur)

    if not await document_repository.supprimer_document(identifiant):
        raise ErreurNotFound("Document introuvable.")

    logger.info(
        "Document « %s » (%s) supprimé par %s.",
        document.get("nom_fichier"), identifiant, utilisateur.get("role"),
    )
    return {
        "supprime": True,
        "document_id": str(identifiant),
        "nom_fichier": document.get("nom_fichier"),
    }
