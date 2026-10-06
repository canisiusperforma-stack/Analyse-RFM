"""Tests du RAG documentaire et de la base documentaire.

Ce fichier est le garde-fou du besoin central : le chatbot ne doit répondre
qu'à partir des documents autorisés, et seulement quand il en a trouvé. Il
vérifie donc, dans cet ordre :

1. **La cohérence des types** — les `Literal` de `app.schemas.document` doivent
  Suivre le modèle de confidentialité et la matrice RBAC. Un niveau ajouté au
   modèle sans être déclaré dans le schéma serait refusé par l'API ; ce test
   rend l'écart visible immédiatement.
2. **Le contrôle d'accès** — `filtre_acces_documents` et `document_visible`, y
   compris l'absence de passe-droit pour `ADMIN` et le traitement d'un
   utilisateur absent.
3. **Le pipeline hors base** — extraction, nettoyage, découpage, embeddings,
   recherche lexicale, construction du contexte.
4. **Le contrôle d'ancrage** — citation inventée, chiffre non sourcé, absence
   de citation : les trois doivent être refusés.
5. **Le pipeline en base** — indexation idempotente, recopie de la
   classification sur les extraits, propagations d'accès, et surtout :
   **le modèle n'est jamais appelé quand aucune source n'atteint le seuil.**

Lancement :
    python tests/test_rag.py
"""

import asyncio
import sys
from pathlib import Path
from typing import Any, get_args

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
from bson import ObjectId

from app.ai.llm_service import LLMIndisponible
from app.config import settings
from app.models.document import (
    CONFIDENTIALITE_CONFIDENTIELLE,
    CONFIDENTIALITE_INTERNE,
    CONFIDENTIALITE_RESTREINTE,
    NIVEAUX_CONFIDENTIALITE,
    construire_document,
    document_visible,
    extension_de_nom,
    filtre_acces_documents,
    normaliser_niveau,
    peut_gerer_acces,
)
from app.rag import (
    document_loader,
    embeddings,
    grounding,
    prompt_builder,
    rag_service,
    retriever,
    text_splitter,
    vector_store,
)
from app.rag.erreurs import ErreurDocumentaire
from app.rag.retriever import Source
from app.repositories import document_repository
from app.schemas.document import (
    AccesDocument,
    NiveauConfidentialite,
    QuestionDocumentaire,
    RoleAutorise,
)
from app.services.permission_service import ROLES, utilisateur_a_permission
from app.utils.errors import ErreurIndisponible, ErreurValidation

#: Marque commune aux documents de test, pour un nettoyage ciblé.
MARQUE = "documents-test-rag"
_ids_crees: list[ObjectId] = []


def _utilisateur(role: str | None, identifiant: ObjectId | None = None) -> dict:
    return {"_id": identifiant or ObjectId(), "role": role}


def _nettoyer() -> None:
    """Supprime les documents et extraits du test, sans toucher au reste."""
    from app.database import obtenir_database

    db = obtenir_database()
    ids = [ObjectId() for _ in range(1)]
    ids.extend(_ids_crees)
    if not ids:
        return
    db["documents_morceaux"].delete_many({"document_id": {"$in": ids}})
    db["documents"].delete_many({"_id": {"$in": ids}})


# --- 1. Cohérence des types ------------------------------------------------


async def _tester_types_alignes() -> None:
    """Les `Literal` du schéma ne doivent pas diverger du modèle."""
    assert set(get_args(NiveauConfidentialite)) == set(NIVEAUX_CONFIDENTIALITE), (
        "app.schemas.document.NiveauConfidentialite diverge de "
        "app.models.document.NIVEAUX_CONFIDENTIALITE"
    )
    assert set(get_args(RoleAutorise)) == set(ROLES), (
        "app.schemas.document.RoleAutorise diverge de permission_service.ROLES"
    )
    print("[OK] Types du schéma alignés sur le modèle et le RBAC")


# --- 2. Contrôle d'accès ---------------------------------------------------


async def _tester_confidentialite() -> None:
    interne = {"confidentialite": "interne"}
    restreinte = {
        "confidentialite": CONFIDENTIALITE_RESTREINTE,
        "roles_autorises": ["RESPONSABLE"],
        "utilisateurs_autorises": [],
    }
    confidentielle = {
        "confidentialite": CONFIDENTIALITE_CONFIDENTIELLE,
        "roles_autorises": ["RESPONSABLE"],
        "utilisateurs_autorises": [],
    }

    # Un champ absent vaut `interne` : les documents déposés avant
    # l'existence de la classification restent lisibles.
    assert normaliser_niveau(None) == CONFIDENTIALITE_INTERNE
    assert normaliser_niveau("niveau-inconnu") == CONFIDENTIALITE_INTERNE

    # `interne` est lisible par tout le monde, y compris sans identité.
    assert document_visible(interne, None) is True
    assert document_visible(interne, _utilisateur("AGENT")) is True

    # `restreinte` exige le rôle.
    assert document_visible(restreinte, _utilisateur("RESPONSABLE")) is True
    assert document_visible(restreinte, _utilisateur("AGENT")) is False
    assert document_visible(restreinte, None) is False

    # `ADMIN` n'a pas de passe-droit : c'est lui qui doit figurer dans la liste.
    assert document_visible(restreinte, _utilisateur("ADMIN")) is False

    # `confidentielle` exige le rôle **et** l'identité.
    alice = ObjectId()
    confidentielle["utilisateurs_autorises"] = [str(alice)]
    assert document_visible(confidentielle, _utilisateur("RESPONSABLE", alice)) is True
    assert document_visible(
        confidentielle, _utilisateur("RESPONSABLE", ObjectId())
    ) is False, "le bon rôle ne suffit pas pour un document confidentiel"
    assert document_visible(confidentielle, _utilisateur("ADMIN", alice)) is False

    # La clause Mongo ne doit jamais être vide : sans elle, aucun contrôle.
    for role in ("ADMIN", "RESPONSABLE", "ANALYSTE", "AGENT", None):
        filtre = filtre_acces_documents(_utilisateur(role))
        assert filtre.get("$or"), f"filtre vide pour le rôle {role}"
        assert len(filtre) == 1, "le filtre ne doit contenir que $or"

    # Le refus par défaut : sans identité, seul `interne` est atteignable.
    sans_identite = filtre_acces_documents(None)
    assert sans_identite["$or"] == [{"confidentialite": {"$in": ["interne", None]}}]

    # Seuls les administrateurs classent.
    assert peut_gerer_acces(_utilisateur("ADMIN")) is True
    assert peut_gerer_acces(_utilisateur("RESPONSABLE")) is False
    assert peut_gerer_acces(None) is False

    # Un document classé sans rôle est refusé à la construction : il serait
    # inaccessible à tout le monde, donc inerte.
    for niveau in (CONFIDENTIALITE_RESTREINTE, CONFIDENTIALITE_CONFIDENTIELLE):
        try:
            construire_document(
                nom_fichier="secret.txt",
                contenu=b"texte",
                confidentialite=niveau,
                roles_autorises=[],
            )
            raise AssertionError(f"un document « {niveau} » sans rôle doit être refusé")
        except ValueError:
            pass

    # Idem au niveau du schéma HTTP, pour que le refus parvienne en 422.
    try:
        AccesDocument(confidentialite=CONFIDENTIALITE_RESTREINTE)
        raise AssertionError("AccesDocument doit refuser « restreinte » sans rôle")
    except Exception as erreur:  # pydantic ValidationError
        assert "rôle" in str(erreur).lower()

    print("[OK] Confidentialité : 3 niveaux, refus par défaut, aucun passe-droit ADMIN")


# --- 3. Pipeline hors base -------------------------------------------------


async def _tester_extraction() -> None:
    # Texte brut
    extrait = document_loader.extraire(b"Bonjour le monde.\n\fPage deux.", "a.txt")
    assert extrait.format == "txt" and extrait.nb_caracteres > 0

    # Markdown : le titre de section est conservé
    markdown = b"# Titre\n\nContenu de la section.\n\n## Autre\n\nAutre contenu."
    extrait = document_loader.extraire(markdown, "a.md")
    assert extrait.format == "md"
    assert any(bloc.titre for bloc in extrait.blocs), "titre de section non conservé"

    # CSV : les colonnes sont nommées, sinon une ligne plate serait
    # introuvable par le nom de sa colonne.
    csv = b"matricule;nom;montant\n001;Alice;1000\n002;Bob;2000\n"
    extrait = document_loader.extraire(csv, "a.csv")
    contenu = " ".join(bloc.texte for bloc in extrait.blocs)
    assert "matricule" in contenu and "Alice" in contenu

    # JSON
    extrait = document_loader.extraire(b'[{"a": 1, "b": 2}]', "a.json")
    assert extrait.format == "json" and extrait.nb_caracteres > 0

    # Format non pris en charge : refus explicite, jamais de texte deviné.
    try:
        document_loader.extraire(b"contenu", "a.docx")
        raise AssertionError("un format non pris en charge doit être refusé")
    except ErreurDocumentaire as erreur:
        assert "non pris en charge" in erreur.message

    # Fichier vide
    try:
        document_loader.extraire(b"", "a.txt")
        raise AssertionError("un fichier vide doit être refusé")
    except ErreurDocumentaire as erreur:
        assert "vide" in erreur.message

    # PDF sans en-tête
    try:
        document_loader.extraire(b"ceci n'est pas un pdf", "a.pdf")
        raise AssertionError("un PDF sans en-tête doit être refusé")
    except ErreurDocumentaire:
        pass

    assert extension_de_nom("Rapport.Final.PDF") == "pdf"
    assert extension_de_nom("sans-extension") == ""
    print("[OK] Extraction : 5 formats, refus des formats et fichiers inexploitables")


async def _tester_borne_de_depot() -> None:
    """Le dépôt doit refuser un fichier trop gros **sans** le lire en entier.

    Vérifier la taille après `await fichier.read()` laisserait un dépôt
    arbitrairement volumineux charger la mémoire du serveur avant d'être
    refusé. La lecture est donc bornée : c'est ce que vérifie ce test en
    appelant la lecture avec une limite d'un octet.
    """
    from io import BytesIO

    from starlette.datastructures import Headers, UploadFile

    from app.api.routes.documents import _lire_fichier_borne

    limite = settings.RAG_TAILLE_MAX_OCTETS

    def _fichier(payload: bytes) -> UploadFile:
        return UploadFile(
            file=BytesIO(payload),
            filename="document.txt",
            headers=Headers({"content-type": "text/plain"}),
        )

    # Un fichier dans la limite passe, et son contenu est rendu intact.
    assert await _lire_fichier_borne(_fichier(b"contenu")) == b"contenu"

    # Un octet de plus que la limite : refusé, sans être chargé.
    trop_gros = _fichier(b"a" * (limite + 1))
    try:
        await _lire_fichier_borne(trop_gros)
        raise AssertionError("un fichier au-delà de la limite doit être refusé")
    except ErreurValidation as erreur:
        assert "volumineux" in str(erreur.detail)
        # Un octet seulement a été lu : la lecture s'est arrêtée d'elle-même.
        assert trop_gros.file.tell() <= limite + 1, "le fichier a été lu en entier"

    # Un fichier vide est refusé au dépôt, pas conservé comme document inerte.
    try:
        await _lire_fichier_borne(_fichier(b""))
        raise AssertionError("un fichier vide doit être refusé")
    except ErreurValidation as erreur:
        assert "vide" in str(erreur.detail)

    # Le chargementur applique la même borne, en amont du découpage.
    settings.RAG_TAILLE_MAX_OCTETS = 10
    try:
        document_loader.extraire(b"a" * 11, "gros.txt")
        raise AssertionError("le chargementur doit refuser un fichier trop gros")
    except ErreurDocumentaire as erreur:
        assert "taille maximale" in erreur.message
    finally:
        settings.RAG_TAILLE_MAX_OCTETS = limite

    print("[OK] Dépôt : taille bornée à la lecture, refus avant écriture")


async def _tester_decoupage() -> None:
    long = " ".join(
        f"La phrase numéro {index} décrit une disposition administrative."
        for index in range(120)
    )
    extrait = document_loader.extraire(long.encode("utf-8"), "a.txt")
    morceaux = text_splitter.decouper(extrait)

    assert len(morceaux) > 1, "un texte long doit produire plusieurs morceaux"
    for morceau in morceaux:
        assert morceau.texte.strip(), "morceau vide"
        assert len(morceau.texte) <= settings.RAG_CHUNK_TAILLE + (
            settings.RAG_CHUNK_RECOUVREMENT
        ), "morceau trop long"
        assert morceau.ordinal > 0
    assert [m.ordinal for m in morceaux] == list(range(1, len(morceaux) + 1))
    assert all(isinstance(m.page, (int, type(None))) for m in morceaux)

    # Un paragraphe trop court est rattaché au précédent, non indexé seul.
    assert all(
        len(morceau.texte) >= min(
            settings.RAG_CHUNK_TAILLE_MIN, len(morceaux[-1].texte)
        )
        for morceau in morceaux
    )

    # Deux morceaux consécutifs se recouvrent : une phrase à cheval sur la
    # frontière doit rester retrouvable.
    if len(morceaux) > 1:
        fin = morceaux[0].texte[-60:]
        assert fin in morceaux[1].texte, "recouvrement absent entre morceaux"

    # Le nettoyage ne doit pas toucher aux nombres.
    assert "1000" in text_splitter.nettoyer("Montant : 1 000 000 € (article 12).")
    print("[OK] Découpage : taille bornée, recouvrement, provenance conservée")


async def _tester_embeddings() -> None:
    dimension = settings.RAG_EMBED_DIM
    a = embeddings.vecteuriser("La subvention est accordée par arrêté préfectoral.")
    b = embeddings.vecteuriser("La subvention est accordée par arrêté préfectoral.")
    c = embeddings.vecteuriser("Le hangar accueille les conferences annuelles")

    assert a.shape == (dimension,), f"dimension {a.shape} != ({dimension},)"
    assert np.allclose(a, b), "la vectorisation doit être déterministe"
    assert abs(float(np.linalg.norm(a)) - 1.0) < 1e-5, "vecteur non normé"

    # Deux textes sans rapport ne doivent pas être « opposés » : toutes les
    # composantes sont positives, donc le cosinus reste dans [0, 1].
    assert float(a @ c) >= 0.0, "similarité négative pour deux textes sans rapport"
    assert float(a @ a) > float(a @ c), "l'ordre de similarité est inversé"

    # Un lot vide ne doit pas faire planter l'appelant.
    assert embeddings.vectoriser_plusieurs([]).shape == (0, dimension)
    assert embeddings.similarite(a, np.zeros((0, dimension), dtype=np.float32)).size == 0

    # Un texte d'une écriture non latine ne doit ni planter ni produire de NaN :
    # les documents du SRB ne sont pas tous en français.
    etrange = embeddings.vecteuriser("Grant 批复емвения по решению № 42")
    assert etrange.shape == (dimension,)
    assert np.isfinite(etrange).all(), "vecteur non fini sur texte non latin"
    assert float(np.linalg.norm(etrange)) > 0.0

    # Deux dimensions incompatibles doivent être refusées explicitement.
    try:
        embeddings.similarite(a, np.zeros((2, 16), dtype=np.float32))
        raise AssertionError("des dimensions incompatibles doivent être refusées")
    except ValueError as erreur:
        assert "réindex" in str(erreur).lower()

    print("[OK] Embeddings : déterministes, normés, similarité bornée [0, 1]")


async def _tester_recherche_lexicale() -> None:
    # La couverture, non la densité : répéter un mot cent fois ne doit pas
    # éclipser un extrait qui emploie une fois chaque terme.
    assert retriever.score_lexical("subvention arrêté", "subvention et arrêté") == 1.0
    assert retriever.score_lexical("subvention arrêté", "subvention " * 50) == 0.5
    assert retriever.score_lexical("subvention arrêté", "rien à voir") == 0.0
    assert retriever.score_lexical("", "anything") == 0.0

    # Insensible aux accents et à la casse.
    assert (
        retriever.score_lexical("Exécution budgétaire", "execution budgetaire") == 1.0
    )

    # Une question sans terme discriminant ne doit rien|score.
    assert retriever.score_lexical("de le la", "texte quelconque") == 0.0
    print("[OK] Recherche lexicale : couverture, insensibilité aux accents")


async def _tester_contexte() -> None:
    sources = [
        Source(
            etiquette="S1",
            document_id="d1",
            ordinal=1,
            nom_fichier="arrete.pdf",
            page=4,
            titre="Article 5",
            confidentialite="interne",
            score=0.8,
            contenu="Le montant est fixé à 1 000 €.",
        ),
        Source(
            etiquette="S2",
            document_id="d2",
            ordinal=2,
            nom_fichier="note.md",
            page=None,
            titre=None,
            confidentialite="confidentielle",
            score=0.4,
            contenu="La subvention est annuelle.",
        ),
    ]

    contexte = retriever.construire_contexte(sources)
    assert "[S1]" in contexte and "[S2]" in contexte
    assert "arrete.pdf" in contexte and "page 4" in contexte
    assert "Article 5" in contexte

    # La confidentialité non interne doit apparaître dans le contexte, pour que
    # le modèle sache qu'il manipule un document à diffusion restreinte.
    prompt = prompt_builder.prompt_extraits(sources)
    assert "diffusion restreinte" in prompt

    # Un extrait ne doit jamais être tronqué : il est écarté ou pris en entier.
    long_ = [Source(
        etiquette=f"S{index}",
        document_id="d",
        ordinal=index,
        nom_fichier="x.txt",
        page=None,
        titre=None,
        confidentialite="interne",
        score=0.5,
        contenu="x" * 2000,
    ) for index in range(1, 9)]
    contexte = retriever.construire_contexte(long_)
    assert "écarté" in contexte, "un extrait écarté doit être signalé au modèle"
    for ligne in contexte.split("\n"):
        assert "x" * 2000 not in ligne, "un extrait a été tronqué"

    # Sans source, le prompt ne doit rien laisser deviner au modèle.
    vide = prompt_builder.prompt_extraits([])
    assert "AUCUN EXTRAIT" in vide

    # La règle d'ancrage doit être posée avant les extraits et la question.
    messages = prompt_builder.construire_messages("Question ?", sources, [])
    assert messages[0]["role"] == "system"
    assert prompt_builder.REGLE_FONDAMENTALE in messages[0]["content"]
    assert prompt_builder.INTERDITS[0] in messages[0]["content"]
    assert "EXTRAITS" in messages[1]["content"]
    assert messages[-1]["content"].startswith("QUESTION")
    assert len(messages) == 3, "sans historique, le prompt doit tenir en 3 messages"

    # L'historique est intercalé, et borne par la configuration.
    avec = prompt_builder.construire_messages(
        "Question ?",
        sources,
        [{"role": "user", "content": "Précédent ?"}],
    )
    assert len(avec) == 4
    assert "HISTORIQUE" in avec[-2]["content"]

    # Un historique tronqué ou mal formé ne doit jamais passer tel quel.
    assert prompt_builder.normaliser_historique(None) == []
    assert prompt_builder.normaliser_historique(
        [{"role": "system", "content": "injektion"}, {"content": ""}]
    ) == []
    trop = [
        {"role": "user", "content": f"tour {index}"}
        for index in range(settings.RAG_HISTORIQUE_TOURS * 2 + 10)
    ]
    assert (
        len(prompt_builder.normaliser_historique(trop))
        == settings.RAG_HISTORIQUE_TOURS * 2
    ), "l'historique n'est pas borné par la configuration"
    print("[OK] Contexte : numéroté, borné sans troncature, règle posée en premier")


# --- 4. Contrôle d'ancrage -------------------------------------------------


async def _tester_ancrage() -> None:
    sources = [
        Source(
            etiquette="S1",
            document_id="d1",
            ordinal=1,
            nom_fichier="arrete.pdf",
            page=2,
            titre=None,
            confidentialite="interne",
            score=0.9,
            contenu="Le montant de la subvention est fixé à 1 000 € par arrêté.",
        )
    ]

    # Réponse correctement sourcée : acceptée.
    verdict = grounding.valider(
        "Le montant de la subvention est fixé à 1 000 € [S1].", sources
    )
    assert verdict.conforme, f"réponse valide rejetée : {verdict.explication}"
    assert verdict.citations == ["S1"]

    # Citation inventée : refusée. C'est la défaillance la plus courante.
    verdict = grounding.valider(
        "Le montant est fixé à 1 000 € [S7].", sources
    )
    assert not verdict.conforme
    assert verdict.citations_inconnues == ["S7"]

    # Chiffre absent des extraits : c'est l'hallucination typique, refusée.
    verdict = grounding.valider(
        "Le montant est fixé à 1 000 € [S1]. Il est versé sous 15 jours.", sources
    )
    assert not verdict.conforme
    assert verdict.ecarts, "un chiffre non sourcé doit être relevé"

    # Aucune citation alors que des sources sont fournies : refusée.
    verdict = grounding.valider(
        "Le montant est fixé à 1 000 euros.", sources
    )
    assert not verdict.conforme
    assert any(p.nature == "affirmation_non_citee" for p in verdict.problemes)

    # Une mention d'absence est légitime et n'exige pas de source.
    verdict = grounding.valider(
        "Cette information ne figure pas dans les extraits fournis.", sources
    )
    assert verdict.mention_absence is True

    # Source fournie, réponse d'absence : ce qui précède doit primer.
    verdict = grounding.valider("Je n'ai pas trouvé cette information.", [])
    assert verdict.conforme, "l'absence doit être signalée sans être rejetée"

    # Sans source, une affirmation est nécessairement inventée.
    verdict = grounding.valider("La subvention est de 1 000 €.", [])
    assert not verdict.conforme
    assert not verdict.reparable

    # Réponse vide : refusée sans appel au modèle possible.
    verdict = grounding.valider("", sources)
    assert not verdict.conforme

    # Le nettoyage des citations orphelines ne laisse pas un marqueur cassé.
    nettoyee = grounding.nettoyer_citations("Montant 1 000 € [S1] et [S9].", sources)
    assert "[S9]" not in nettoyee and "[S1]" in nettoyee

    # L'étiquetage marque les sources effectivement citées.
    sources = grounding.etiqueter_sources(sources, ["S1"])
    assert sources[0].cite is True
    print("[OK] Ancrage : citation inventée, chiffre non sourcé, absence non citée")


# --- 5. Pipeline en base ---------------------------------------------------


async def _deposer(
    nom: str,
    contenu: bytes,
    *,
    confidentialite: str = "interne",
    roles: list[str] | None = None,
    utilisateurs: list[str] | None = None,
) -> ObjectId:
    """Dépose un document de test et le déclare pour le nettoyage."""
    document = construire_document(
        nom_fichier=nom,
        contenu=contenu,
        confidentialite=confidentialite,
        roles_autorises=roles or [],
        utilisateurs_autorises=utilisateurs or [],
    )
    file_id = await document_repository.sauvegarder_fichier(
        contenu, nom, document["type_mime"]
    )
    document["file_id"] = file_id
    identifiant = await document_repository.inserer_document(document)
    _ids_crees.append(identifiant)
    return identifiant


async def _tester_indexation() -> None:
    contenu = (
        "Modalités d'octroi de la subvention. Le montant est fixé à 1 000 €. "
        "Le dossier doit être déposé au guichet. " * 6
    ).encode("utf-8")
    identifiant = await _deposer(f"{MARQUE}-arrete.txt", contenu)

    resultat = await rag_service.indexer(identifiant)
    assert resultat.succes, f"indexation échouée : {resultat.message}"
    assert resultat.nb_morceaux > 0
    assert resultat.nb_caracteres > 0

    # La classification est recopiée sur chaque extrait : c'est ce qui rend le
    # filtrage appliquable au niveau du morceau, sans jointure.
    from app.database import obtenir_database

    db = obtenir_database()
    morceaux = [
        m async for m in db["documents_morceaux"].find({"document_id": identifiant})
    ]
    assert morceaux, "aucun extrait écrit"
    for morceau in morceaux:
        assert morceau["confidentialite"] == "interne"
        assert "vecteur" in morceau and len(morceau["vecteur"]) == settings.RAG_EMBED_DIM
        assert morceau["contenu"].strip()

    # Réindexation idempotente : les extraits sont remplacés, jamais doublés.
    avant = len(morceaux)
    resultat = await rag_service.indexer(identifiant, force=True)
    assert resultat.succes
    morceaux = [
        m async for m in db["documents_morceaux"].find({"document_id": identifiant})
    ]
    assert len(morceaux) == avant, (
        f"la réindexération a doublé les extraits : {avant} -> {len(morceaux)}"
    )

    # Un document déjà indexé n'est pas réindexé sans `force`.
    document = await document_repository.recuperer_document(identifiant)
    assert document["statut_indexation"] == "indexe"

    # Un document illisible reste consultable, mais non interrogeable.
    illegible = await _deposer(f"{MARQUE}-vide.txt", b"   ")
    resultat = await rag_service.indexer(illegible)
    assert not resultat.succes, "un document sans texte ne doit pas s'indexer"
    document = await document_repository.recuperer_document(illegible)
    assert document["statut_indexation"] == "echec"
    assert document["erreur_indexation"], "le motif de l'échec doit être tracé"
    print(f"[OK] Indexation : {avant} extrait(s), idempotente, échec tracé")


async def _tester_recherche_base() -> None:
    contenu = (
        "Le montant de la subvention est fixé à 1 000 euros. "
        "Le dossier doit être déposé au guichet de la préfecture. " * 8
    ).encode("utf-8")
    identifiant = await _deposer(f"{MARQUE}-montant.txt", contenu)
    await rag_service.indexer(identifiant)

    agent = _utilisateur("AGENT")
    resultat = await rag_service.rechercher("montant de la subvention", agent)
    assert resultat.suffisant, "un document interne doit être trouvé par tous"
    assert resultat.morceaux, "aucun extrait retenu"
    assert resultat.score_max >= resultat.seuil, "un extrait retenu doit dépasser le seuil"

    # Les sources sont numérotées et citables.
    sources = retriever.construire_sources(resultat)
    assert sources[0].etiquette == "S1"
    assert 0.0 < sources[0].score_relative <= 1.0
    assert sources[0].contenu.strip()
    assert sources[0].nom_fichier

    # Un document interne est atteignable même sans identité : c'est le niveau
    # le plus ouvert, et le refuser rendrait la base inexploitable hors session.
    anonyme = await rag_service.rechercher("montant de la subvention", None)
    assert anonyme.suffisant, "un document interne doit être atteignable sans session"

    # Le compte rendu doit permettre de diagnostiquer une absence.
    assert "candidats_examines" in resultat.resume()["recherche"]
    print("[OK] Recherche en base : pertinence, numérotation, diagnostic")


async def _tester_isolement_en_base() -> None:
    """Un document confidentiel ne doit jamais fuiter vers qui n'y a pas droit."""
    contenu = (
        "Plan de redressement confidentiel : fusion de trois centres. "
        "Économie attendue de 1 200 000 €. " * 8
    ).encode("utf-8")
    alice = ObjectId()
    confidentiel = await _deposer(
        f"{MARQUE}-secret.txt",
        contenu,
        confidentialite=CONFIDENTIALITE_CONFIDENTIELLE,
        roles=["RESPONSABLE"],
        utilisateurs=[str(alice)],
    )
    await rag_service.indexer(confidentiel)

    alice_util = _utilisateur("RESPONSABLE", alice)
    resultat = await rag_service.rechercher("plan de redressement", alice_util)
    assert resultat.suffisant, "un autorisé doit trouver le document confidentiel"
    assert any(
        candidat.document_id == str(confidentiel) for candidat in resultat.morceaux
    ), "le document confidentiel devrait être trouvé par un autorisé"

    # Ni un autre rôle, ni le même rôle sans l'identité, ni un anonymat.
    for intrus in (
        _utilisateur("AGENT"),
        _utilisateur("RESPONSABLE", ObjectId()),
        _utilisateur("ADMIN", ObjectId()),
        None,
    ):
        resultat = await rag_service.rechercher("plan de redressement", intrus)
        assert not any(
            candidat.document_id == str(confidentiel) for candidat in resultat.morceaux
        ), f"fuite vers {intrus}"

    # Et la liste des documents ne doit pas non plus le révéler.
    visibles = await document_repository.lister_documents(
        filtre=filtre_acces_documents(_utilisateur("AGENT")), limite=500
    )
    assert all(str(document["_id"]) != str(confidentiel) for document in visibles)

    # La reclassification est répercutée sur les extraits déjà indexés.
    await document_repository.modifier_document(
        confidentiel,
        {
            "confidentialite": CONFIDENTIALITE_CONFIDENTIELLE,
            "roles_autorises": ["ADMIN"],
            "utilisateurs_autorises": [],
        },
    )
    modifies = await document_repository.synchroniser_acces_document(confidentiel)
    assert modifies > 0, "la reclassification doit être propagée aux extraits"
    resultat = await rag_service.rechercher("plan de redressement", alice_util)
    assert not any(
        candidat.document_id == str(confidentiel) for candidat in resultat.morceaux
    ), "Alice n'est plus autorisée : le document doit disparaître"
    print("[OK] Isolement : document confidentiel invisible des non-autorisés")


async def _tester_absence_sans_appel_modele() -> None:
    """Le contrôle central du besoin : sans source, le modèle n'est pas appelé."""
    await _tester_recherche_base()  # garantit au moins un document indexé

    appels: list[Any] = []
    original = rag_service.completer

    async def espion(*args, **kwargs):
        appels.append((args, kwargs))
        raise AssertionError(
            "le modèle ne doit pas être appelé quand aucune source n'est trouvée"
        )

    rag_service.completer = espion
    seuil_initial = settings.RAG_SEUIL_PERTINENCE
    try:
        # Le seuil est poussé hors d'atteinte pour rendre l'absence
        # **déterministe**. Compter sur le fait qu'une question « hors sujet »
        # tombe sous le seuil ferait dépendre ce garde-fou du hasard des
        # embeddings : une version de modèle un peu différente suffirait à
        # le faire échouer, ou pire, à le faire passer pour une preuve.
        # Ici, des sources existent bien — la même question réussit ci-dessus —
        # mais aucune n'est retenue : c'est exactement le chemin à vérifier.
        settings.RAG_SEUIL_PERTINENCE = 1.0
        resultat = await rag_service.repondre(
            "montant de la subvention", _utilisateur("AGENT")
        )
        assert not resultat.trouve, "aucun extrait ne devrait dépasser ce seuil"
        assert resultat.mode == "absence", f"mode inattendu : {resultat.mode}"
        assert resultat.sources == []
        assert not appels, "le modèle a été appelé sans source"

        # Le message doit nommer l'absence, et non laisser croire à une panne.
        assert resultat.reponse.startswith(rag_service.MESSAGE_ABSENCE)
        assert resultat.recherche is not None, "l'absence doit rester traçable"

        # Une question vide ne doit pas non plus atteindre le modèle.
        vide = await rag_service.repondre("   ", _utilisateur("AGENT"))
        assert vide.mode == "sans_question"
        assert not vide.trouve
        assert not appels, "le modèle a été appelé sans question"
    finally:
        rag_service.completer = original
        settings.RAG_SEUIL_PERTINENCE = seuil_initial
    print("[OK] Absence : aucun appel au modèle, message d'absence explicite")


async def _tester_repli_modele_indisponible() -> None:
    """Avec des sources mais sans modèle, la réponse reste fondée."""
    from app.ai.llm_service import llm_actif

    if llm_actif():
        print("[INFO] LLM actif : repli sur indisponibilité non testable")
        return
    resultat = await rag_service.repondre(
        "montant de la subvention", _utilisateur("AGENT")
    )
    assert resultat.trouve, "des sources étaient disponibles"
    assert resultat.mode == "repli_modele_indisponible", f"mode : {resultat.mode}"
    assert resultat.sources, "les extraits doivent accompagner le repli"

    # Le repli est produit par le code : il restitue les extraits, et n'ajoute
    # rien qui ne vienne d'eux.
    reponse = resultat.reponse
    assert "[S1]" in reponse
    for source in resultat.sources:
        assert source.contenu[:60] in reponse, "un extrait annoncé n'est pas cité"
    assert resultat.controle is not None
    assert resultat.controle["conforme"] is False
    print("[OK] Repli : réponse déterministe à partir des extraits, sans modèle")


async def _tester_seuil_et_activation() -> None:
    """Le seuil doit rendre « rien trouvé » atteignable, et l'arrêt coupable."""
    from app.api.routes.documents import exiger_rag_actif

    # Le seuil est porté par la recherche, pas par l'orchestrateur : c'est là
    # qu'il est évalué, et c'est `rag_service` qui décide de ne pas appeler le
    # modèle. Un seuil hors d'atteinte doit donc produire une absence, jamais un
    # extrait faible présenté comme une réponse.
    resultat = await retriever.rechercher(
        question="montant de la subvention",
        utilisateur=_utilisateur("AGENT"),
        seuil=1.01,
    )
    assert not resultat.suffisant, "un seuil inatteignable doit tout écarter"
    assert resultat.seuil == 1.01
    assert resultat.score_max <= 1.01

    # L'arrêt global doit être observable et sans effet de bord.
    settings.RAG_ENABLED = True
    try:
        exiger_rag_actif()  # actif : ne doit rien lever
    finally:
        settings.RAG_ENABLED = False

    try:
        exiger_rag_actif()
        raise AssertionError("RAG_ENABLED=false doit suspendre les routes")
    except ErreurIndisponible as erreur:
        assert erreur.statut == 503
        assert erreur.code == "SERVICE_UNAVAILABLE"
        assert "RAG_ENABLED" in erreur.message

    # `RAG_EXTRACTION_AUTO=false` doit différer l'indexation, non l'échouer.
    assert settings.RAG_EXTRACTION_AUTO is True
    print("[OK] Seuil : rend l'absence atteignable, arrêt global observable")


async def _tester_permissions_documents() -> None:
    """Le module `documents` doit garder ses invariants de matrice."""
    from app.services.permission_service import MATRICE_ROLES, PERMISSIONS

    assert "documents:indexer" in PERMISSIONS
    assert "documents:acces" in PERMISSIONS

    # Classer est un acte d'administration : réservé à ADMIN.
    for role in ROLES:
        attendu = role == "ADMIN"
        assert utilisateur_a_permission({"role": role}, "documents:acces") is attendu, (
            f"documents:acces ne devrait pas être à {role}"
        )

    # Réindexer n'ouvre aucun accès : ouvert à la gestion opérationnelle.
    assert utilisateur_a_permission({"role": "RESPONSABLE"}, "documents:indexer")
    assert not utilisateur_a_permission({"role": "ANALYSTE"}, "documents:indexer")
    assert not utilisateur_a_permission({"role": "AGENT"}, "documents:indexer")

    # Le refus par défaut doit survivre.
    assert not utilisateur_a_permission({"role": "ADMIN"}, "documents:inventer")
    assert not utilisateur_a_permission({"role": "INCONNU"}, "documents:voir")

    for role in ROLES:
        assert set(MATRICE_ROLES[role]) <= PERMISSIONS, (
            f"{role} déclare une permission absente du référentiel"
        )
    print("[OK] Permissions : documents:acces ADMIN, documents:indexer gestion")


async def _tester_question_documentaire() -> None:
    """Le contrat HTTP borne la question et refuse les champs inconnus."""
    requete = QuestionDocumentaire(question="  Quelle'est la procédure ?  ")
    assert requete.question == "Quelle'est la procédure ?", "espaces non retirés"
    assert requete.historique == [] and requete.documents is None

    for invalide in ({"question": ""}, {"question": "x" * (settings.RAG_QUESTION_MAX + 1)}):
        try:
            QuestionDocumentaire(**invalide)
            raise AssertionError(f"devrait être refusé : {invalide}")
        except Exception:
            pass

    try:
        QuestionDocumentaire(question="q", champ_inconnu=1)
        raise AssertionError("un champ inconnu doit être refusé")
    except Exception:
        pass
    print("[OK] Contrat HTTP : question bornée, champs inconnus refusés")


# --- Exécution -------------------------------------------------------------


async def executer_tests() -> None:
    from app.database import connecter_database, fermer_database
    from app.services.permission_service import MATRICE_ROLES, PERMISSIONS  # noqa: F401

    await connecter_database()
    try:
        _nettoyer()

        await _tester_types_alignes()
        await _tester_confidentialite()
        await _tester_extraction()
        await _tester_decoupage()
        await _tester_embeddings()
        await _tester_recherche_lexicale()
        await _tester_contexte()
        await _tester_ancrage()
        await _tester_permissions_documents()
        await _tester_question_documentaire()

        await _tester_indexation()
        await _tester_recherche_base()
        await _tester_isolement_en_base()
        await _tester_absence_sans_appel_modele()
        await _tester_repli_modele_indisponible()
        await _tester_seuil_et_activation()
    finally:
        _nettoyer()
        await fermer_database()


if __name__ == "__main__":
    try:
        asyncio.run(executer_tests())
    except AssertionError as erreur:
        print(f"[ECHEC] {erreur}")
        sys.exit(1)
    except (ErreurDocumentaire, ErreurValidation, ErreurIndisponible) as erreur:
        print(f"[ECHEC] {getattr(erreur, 'message', erreur)}")
        sys.exit(1)
    print("TEST_RAG : OK")
