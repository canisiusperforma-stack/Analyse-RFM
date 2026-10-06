"""Étape « Extraction » du pipeline RAG : fichier binaire → texte structuré.

Un document déposé arrive sous forme d'octets. Ce module en tire des **blocs de
texte** portant chacun leur provenance (page pour un PDF, section pour un
tableau ou un document structuré), provenance que le découpage et la citation
reprennent ensuite. Aucun texte n'est inventé ici : un fichier dont le contenu
ne peut pas être lu est refusé, jamais deviné.

Formats pris en charge, sans dépendance externe pour les formats texte :

| Format | Extracteur                          | Provenance      |
|--------|-------------------------------------|-----------------|
| `pdf`  | flux PDF (stdlib) ou `pypdf` si présent | page       |
| `txt`  | décodage direct                     | section          |
| `md`   | sections délimitées par un titre    | titre de section |
| `csv`  | `csv` stdlib, délimiteur détecté    | feuille / bloc   |
| `json` | `json` stdlib, à plat               | section          |
| `xlsx` | `openpyxl` (déjà dépendance)        | feuille          |

Choix de ne dépendre d'aucune bibliothèque PDF
    `pypdf` est utilisé lorsqu'il est installé, car il gère mieux les
    variantes de la norme. En son absence, un extracteur fondé sur la
    bibliothèque standard est employé : les flux de contenu sont localisés,
    les filtres `FlateDecode` décompressés, et les opérateurs de dessin de
    texte (`Tj`, `TJ`, `'`, `"`) interprétés. Cela couvre les PDF produits
    numériquement, qui sont le cas des documents produits par l'administration.

Limite assumée
    Un PDF **numérisé** (image sans couche texte) ne produit aucun caractère :
    `extraire_pdf` le signale par un avertissement et l'étape échoue, plutôt que
    d'indexer un document vide qui aurait l'air correctement traité. Une passe
    de reconnaissance optique est alors nécessaire en amont.
"""

from __future__ import annotations

import csv
import io
import json
import re
import zlib
from dataclasses import dataclass, field
from typing import Any, Optional

from app.config import settings
from app.models.document import extension_de_nom
from app.rag.erreurs import ErreurDocumentaire
from app.utils.logging import get_logger

logger = get_logger(__name__)

try:  # Facultatif : améliore l'extraction quand il est présent.
    from pypdf import PdfReader  # type: ignore
except Exception:  # noqa: BLE001
    PdfReader = None  # type: ignore[assignment]

#: Nombre maximal de lignes rendues pour un tableau, par feuille.
LIGNES_TABLEAU_MAX = 5000

#: Nombre de lignes de données regroupées dans un même bloc.
LIGNES_PAR_BLOC = 20

#: Profondeur d'aplatissement d'un JSON.
PROFONDEUR_JSON_MAX = 6

DELIMITEURS_CSV = (";", ",", "\t", "|")


@dataclass
class Bloc:
    """Fragment de texte extrait, avec l'endroit dont il provient."""

    texte: str
    page: Optional[int] = None
    titre: Optional[str] = None

    def resume(self) -> dict[str, Any]:
        return {"page": self.page, "titre": self.titre}


@dataclass
class DocumentExtrait:
    """Résultat de l'extraction, prêt pour le nettoyage et le découpage."""

    blocs: list[Bloc] = field(default_factory=list)
    format: str = ""
    nb_caracteres: int = 0
    avertissements: list[str] = field(default_factory=list)

    def est_vide(self) -> bool:
        return self.nb_caracteres == 0

    def resume(self) -> dict[str, Any]:
        return {
            "format": self.format,
            "nb_blocs": len(self.blocs),
            "nb_caracteres": self.nb_caracteres,
            "avertissements": list(self.avertissements),
        }


# --- Décodage --------------------------------------------------------------

_ENCODAGES = ("utf-8-sig", "utf-8", "cp1252", "latin-1")


def decoder(contenu: bytes) -> str:
    """Décode en essayant les encodages courants, du plus strict au plus large.

    `latin-1` ne peut pas échouer : il sert de repli, ce qui garantit qu'un
    document mal encodé produit du texte approximatif plutôt qu'une erreur. Un
    `cp1252` est tenté avant lui, car c'est l'encodage courant des documents
    administratifs francophones.
    """
    for encodage in _ENCODAGES:
        try:
            return contenu.decode(encodage)
        except (UnicodeDecodeError, LookupError):
            continue
    return contenu.decode("latin-1", "replace")


def _verifier_taille(contenu: bytes, nom_fichier: str) -> None:
    if not contenu:
        raise ErreurDocumentaire("Le fichier déposé est vide.", etapa="extraction")
    if len(contenu) > settings.RAG_TAILLE_MAX_OCTETS:
        limite = settings.RAG_TAILLE_MAX_OCTETS // (1024 * 1024)
        raise ErreurDocumentaire(
            f"Le fichier « {nom_fichier} » dépasse la taille maximale autorisée "
            f"({limite} Mo).",
            etapa="extraction",
        )


# --- PDF -------------------------------------------------------------------

_STREAM = re.compile(rb"stream\r?\n")
_FIN_STREAM = re.compile(rb"endstream")
_FILTRE = re.compile(rb"/Filter\s*(?:\[\s*)?/(FlateDecode|LZWDecode|ASCII85Decode|None)")
_TITRE_PDF = re.compile(rb"/Title\s*\(([^)]*)\)", re.DOTALL)

#: Un « mot » au sens de la typographie PDF est séparé par un kerning négatif ;
#: en dessous de ce seuil (millièmes de cadratin), une espace est insérée.
SEUIL_KERNING_MOT = -100.0
SEUIL_SAUT_LIGNE = 0.5


def _flux_decompresses(contenu: bytes) -> list[bytes]:
    """Tous les flux du PDF, décompressés lorsqu'ils le sont."""
    flux: list[bytes] = []
    for debut in _STREAM.finditer(contenu):
        fin = _FIN_STREAM.search(contenu, debut.end())
        if fin is None:
            continue
        donnees = contenu[debut.end() : fin.start()]
        dictionnaire = contenu[max(0, debut.start() - 400) : debut.start()]

        filtre = _FILTRE.search(dictionnaire)
        nom_filtre = filtre.group(1) if filtre else b""

        if nom_filtre == b"FlateDecode":
            try:
                flux.append(zlib.decompress(donnees))
                continue
            except zlib.error:
                try:
                    flux.append(zlib.decompressobj().decompress(donnees))
                    continue
                except zlib.error:
                    continue
        elif nom_filtre in (b"", b"None"):
            flux.append(donnees)
    return flux


def _lire_chaine_litterale(texte: str, position: int) -> tuple[str, int]:
    """Lit une chaîne littérale `(...)` en gérant les échappements et imbrications."""
    profondeur = 1
    position += 1
    morceaux: list[str] = []
    taille = len(texte)

    while position < taille and profondeur:
        caractere = texte[position]
        if caractere == "\\":
            position += 1
            if position >= taille:
                break
            suivant = texte[position]
            if suivant in "nrtbf":
                morceaux.append({"n": "\n", "r": "\r", "t": "\t", "b": "\b", "f": "\f"}[suivant])
            elif suivant in "()\\":
                morceaux.append(suivant)
            elif suivant in "\n\r":
                pass
            elif suivant.isdigit():
                chiffres = suivant
                for _ in range(2):
                    if position + 1 < taille and texte[position + 1].isdigit():
                        position += 1
                        chiffres += texte[position]
                    else:
                        break
                morceaux.append(chr(int(chiffres, 8) & 0xFF))
            else:
                morceaux.append(suivant)
            position += 1
            continue
        if caractere == "(":
            profondeur += 1
        elif caractere == ")":
            profondeur -= 1
            if profondeur == 0:
                position += 1
                break
        morceaux.append(caractere)
        position += 1

    return "".join(morceaux), position


def _lire_chaine_hex(texte: str, position: int) -> tuple[str, int]:
    """Lit une chaîne hexadécimale `<48656C6C6F>`."""
    fin = texte.find(">", position)
    if fin == -1:
        return "", len(texte)
    chiffres = re.sub(r"[^0-9A-Fa-f]", "", texte[position + 1 : fin])
    if len(chiffres) % 2:
        chiffres += "0"
    try:
        octets = bytes.fromhex(chiffres)
    except ValueError:
        return "", fin + 1
    return _decodage_pdf(octets), fin + 1


def _decodage_pdf(octets: bytes) -> str:
    """Interprète les chaînes PDF en UTF-16 puis en octets simples.

    Les documents administratifs sont souvent produits par Word : leurs
    chaînes sont en UTF-16 avec BOM. Le comptage des octets nuls permet de
    distinguer les deux écritures sans table de correspondance.
    """
    if octets[:2] in (b"\xfe\xff", b"\xff\xfe"):
        return octets.decode("utf-16", "replace")
    if len(octets) % 2 == 0 and octets.count(b"\x00") >= len(octets) // 4:
        return octets.decode("utf-16-be", "replace")
    return octets.decode("latin-1", "replace")


def _texte_dun_flux(flux: bytes) -> str:
    """Interprète les opérateurs de dessin de texte d'un flux de contenu."""
    texte = flux.decode("latin-1", "replace")
    taille = len(texte)
    position = 0

    sortie: list[str] = []
    morceaux: list[str] = []
    separation = False
    position_y = 0.0

    def vider(saut: bool) -> None:
        contenu = "".join(morceaux)
        if contenu or saut:
            if sortie and not sortie[-1].endswith("\n") and not saut:
                sortie.append(" ")
            if separation and contenu and not contenu.startswith(" "):
                contenu = " " + contenu
            sortie.append(contenu)
            if saut:
                sortie.append("\n")
        morceaux.clear()

    while position < taille:
        caractere = texte[position]

        if caractere == "(":
            valeur, position = _lire_chaine_litterale(texte, position)
            morceaux.append(valeur)
            continue
        if caractere == "<" and position + 1 < taille and texte[position + 1] != "<":
            valeur, position = _lire_chaine_hex(texte, position)
            morceaux.append(valeur)
            continue
        if caractere in "<>[]":
            position += 1
            continue
        if caractere.isspace():
            position += 1
            continue
        if caractere == "/":
            fin = position + 1
            while fin < taille and not texte[fin].isspace() and texte[fin] not in "()<>[]/":
                fin += 1
            position = fin
            continue
        if caractere in "+-.0123456789":
            fin = position
            while fin < taille and (texte[fin].isdigit() or texte[fin] in "+-.eE"):
                fin += 1
            jeton = texte[position:fin]
            try:
                nombre = float(jeton)
            except ValueError:
                nombre = 0.0
            if nombre <= SEUIL_KERNING_MOT:
                separation = True
            position = fin
            continue

        fin = position
        while fin < taille and not texte[fin].isspace() and texte[fin] not in "()<>[]/":
            fin += 1
        operateur = texte[position:fin]
        position = fin if fin > position else position + 1

        if operateur in ("Tj", "TJ", "'", '"'):
            if operateur in ("'", '"'):
                morceaux.append("\n")
            vider(False)
            separation = False
        elif operateur in ("Td", "TD"):
            nombres = re.findall(r"[-+]?\d*\.?\d+", texte[max(0, position - 40) : position])
            decalage = float(nombres[-1]) if nombres else 0.0
            position_y += decalage
            if abs(decalage) > SEUIL_SAUT_LIGNE:
                vider(True)
        elif operateur == "Tm":
            nombres = re.findall(r"[-+]?\d*\.?\d+", texte[max(0, position - 60) : position])
            if len(nombres) >= 6:
                nouvelle_y = float(nombres[-1])
                if abs(nouvelle_y - position_y) > SEUIL_SAUT_LIGNE:
                    vider(True)
                position_y = nouvelle_y
        elif operateur == "T*":
            vider(True)
        elif operateur == "ET":
            vider(True)
            position_y = 0.0
        else:
            separation = False

    vider(False)
    return "".join(sortie)


def extraire_pdf(contenu: bytes) -> DocumentExtrait:
    """Extrait le texte d'un PDF, page par page."""
    if contenu[:5] != b"%PDF-":
        raise ErreurDocumentaire(
            "Le fichier ne commence pas par l'en-tête PDF attendu.",
            etapa="extraction",
        )
    if b"/Encrypt" in contenu:
        raise ErreurDocumentaire(
            "Le PDF est chiffré : le déverrouiller est nécessaire avant indexation.",
            etapa="extraction",
        )

    avertissements: list[str] = []

    if PdfReader is not None:
        document = extraire_pdf_pypdf(contenu)
        if document is not None:
            return document
        avertissements.append(
            "Lecture PDF native (pypdf) sans texte exploitable ; lecture de secours utilisée."
        )

    flux = _flux_decompresses(contenu)
    if not flux:
        raise ErreurDocumentaire(
            "Aucun flux de contenu lisible dans ce PDF. S'il a été numérisé, "
            "une reconnaissance optique est nécessaire avant indexation.",
            etapa="extraction",
        )

    blocs: list[Bloc] = []
    for numero, donnees in enumerate(flux, start=1):
        texte = _texte_dun_flux(donnees)
        if texte.strip():
            blocs.append(Bloc(texte=texte, page=numero))

    if not blocs:
        raise ErreurDocumentaire(
            "Ce PDF ne contient aucune couche texte (PDF numérisé probable). "
            "Une reconnaissance optique est nécessaire avant indexation.",
            etapa="extraction",
        )

    return _finaliser(blocs, "pdf", avertissements)


def extraire_pdf_pypdf(contenu: bytes) -> Optional[DocumentExtrait]:
    """Lecture via `pypdf` si la bibliothèque est installée."""
    if PdfReader is None:
        return None
    try:
        lecteur = PdfReader(io.BytesIO(contenu))
        blocs = [
            Bloc(texte=page.extract_text() or "", page=numero)
            for numero, page in enumerate(lecteur.pages, start=1)
        ]
    except Exception as erreur:  # noqa: BLE001
        logger.warning("Lecture PDF via pypdf impossible : %s", erreur)
        return None

    blocs = [bloc for bloc in blocs if bloc.texte.strip()]
    if not blocs:
        return None
    return _finaliser(blocs, "pdf", [])


# --- Texte, Markdown -------------------------------------------------------

_TITRE_MD = re.compile(r"^(#{1,6})\s+(.+?)\s*#*$")
_SAUT_PAGE = "\f"


def extraire_texte(contenu: bytes) -> DocumentExtrait:
    """Extrait un document texte brut, en conservant les sauts de page."""
    texte = decoder(contenu).replace("\r\n", "\n").replace("\r", "\n")
    if _SAUT_PAGE not in texte:
        return _finaliser([Bloc(texte=texte)], "txt", [])

    blocs: list[Bloc] = []
    for numero, portion in enumerate(texte.split(_SAUT_PAGE), start=1):
        if portion.strip():
            blocs.append(Bloc(texte=portion, page=numero))
    return _finaliser(blocs, "txt", [])


def extraire_markdown(contenu: bytes) -> DocumentExtrait:
    """Extrait un Markdown en conservant le titre de section de chaque bloc."""
    texte = decoder(contenu).replace("\r\n", "\n").replace("\r", "\n")
    lignes = texte.split("\n")

    blocs: list[Bloc] = []
    titre_courant: Optional[str] = None
    tampon: list[str] = []
    page = 1

    def vider() -> None:
        if any(ligne.strip() for ligne in tampon):
            blocs.append(Bloc(texte="\n".join(tampon).strip(), page=page, titre=titre_courant))
        tampon.clear()

    for ligne in lignes:
        if _SAUT_PAGE in ligne:
            vider()
            page += ligne.count(_SAUT_PAGE) + 1
            reste = ligne.split(_SAUT_PAGE)[-1]
            if reste.strip():
                tampon.append(reste)
            continue
        correspondance = _TITRE_MD.match(ligne)
        if correspondance:
            vider()
            titre_courant = correspondance.group(2).strip()
            continue
        tampon.append(ligne)
    vider()

    return _finaliser(blocs, "md", [])


# --- Tableaux --------------------------------------------------------------


def _valeur_cellule(valeur: Any) -> str:
    if valeur is None:
        return ""
    if isinstance(valeur, float) and valeur.is_integer():
        return str(int(valeur))
    return str(valeur).strip()


def _rendre_lignes(
    entetes: list[str],
    lignes: list[list[str]],
    titre: Optional[str],
) -> list[Bloc]:
    """Rend chaque ligne de données sous forme « colonne : valeur ».

    Un tableau aplati (`a;b;c` / `1;2;3`) n'est pas interrogeable par
    recherche sémantique : aucun mot de la colonne n'apparaît dans la cellule.
    En préfixant chaque valeur par son en-tête, le contenu indexé porte les
    mots du schéma, ce qui rend la ligne retrouvable par le nom de sa colonne.
    """
    if not entetes:
        return []

    blocs: list[Bloc] = []
    tampon: list[str] = []

    for ligne in lignes:
        morceaux = [
            f"{entete.strip()} : {_valeur_cellule(valeur)}"
            for entete, valeur in zip(entetes, ligne)
            if entete.strip() and _valeur_cellule(valeur)
        ]
        if not morceaux:
            continue
        tampon.append(" ; ".join(morceaux))
        if len(tampon) >= LIGNES_PAR_BLOC:
            blocs.append(Bloc(texte="\n".join(tampon), titre=titre))
            tampon = []
    if tampon:
        blocs.append(Bloc(texte="\n".join(tampon), titre=titre))

    return blocs


def _detecter_delimiteur(contenu: str) -> str:
    premiere = contenu.split("\n", 1)[0] if "\n" in contenu else contenu
    meilleur = ","
    meilleur_score = -1
    for delimiteur in DELIMITEURS_CSV:
        score = premiere.count(delimiteur)
        if score > meilleur_score:
            meilleur = delimiteur
            meilleur_score = score
    return meilleur


def extraire_csv(contenu: bytes) -> DocumentExtrait:
    """Extrait un CSV en détectant son délimiteur et en nommant ses colonnes."""
    texte = decoder(contenu)
    if not texte.strip():
        return _finaliser([], "csv", [])

    lecteur = csv.reader(io.StringIO(texte), delimiter=_detecter_delimiteur(texte))
    toutes = [ligne for ligne in lecteur][:LIGNES_TABLEAU_MAX + 1]
    avertissements: list[str] = []
    if len(toutes) > LIGNES_TABLEAU_MAX:
        toutes = toutes[:LIGNES_TABLEAU_MAX]
        avertissements.append(
            f"Feuille tronquée à {LIGNES_TABLEAU_MAX} lignes pour l'indexation."
        )
    if not toutes:
        return _finaliser([], "csv", avertissements)

    entetes = [cellule.strip() for cellule in toutes[0]]
    if not any(entetes):
        entetes = [f"colonne {index + 1}" for index in range(len(toutes[0]))]
        lignes = toutes
    else:
        lignes = toutes[1:]

    blocs = _rendre_lignes(entetes, lignes, titre="Tableau")
    return _finaliser(blocs, "csv", avertissements)


def extraire_xlsx(contenu: bytes) -> DocumentExtrait:
    """Extrait chaque feuille d'un classeur Excel."""
    try:
        from openpyxl import load_workbook
    except ImportError as erreur:  # pragma: no cover
        raise ErreurDocumentaire(
            "La lecture des classeurs Excel requiert openpyxl.",
            etapa="extraction",
        ) from erreur

    try:
        classeur = load_workbook(io.BytesIO(contenu), read_only=True, data_only=True)
    except Exception as erreur:  # noqa: BLE001
        raise ErreurDocumentaire(
            f"Classeur Excel illisible : {erreur}", etapa="extraction"
        ) from erreur

    blocs: list[Bloc] = []
    avertissements: list[str] = []
    try:
        for feuille in classeur.worksheets:
            iterateur = feuille.iter_rows(values_only=True)
            entetes: list[str] = []
            lignes: list[list[str]] = []
            for index, ligne in enumerate(iterateur):
                if index == 0:
                    entetes = [_valeur_cellule(valeur) for valeur in ligne]
                    continue
                lignes.append([_valeur_cellule(valeur) for valeur in ligne])
                if len(lignes) >= LIGNES_TABLEAU_MAX:
                    avertissements.append(
                        f"Feuille « {feuille.title} » tronquée à "
                        f"{LIGNES_TABLEAU_MAX} lignes pour l'indexation."
                    )
                    break
            if not any(entetes):
                entetes = [f"colonne {position + 1}" for position in range(len(lignes[0]))] if lignes else []
            blocs.extend(_rendre_lignes(entetes, lignes, titre=f"Feuille {feuille.title}"))
    finally:
        classeur.close()

    return _finaliser(blocs, "xlsx", avertissements)


# --- JSON ------------------------------------------------------------------


def _aplatir(valeur: Any, prefixe: str = "", profondeur: int = 0) -> list[str]:
    """Aplatit une structure JSON en lignes « chemin : valeur »."""
    if profondeur > PROFONDEUR_JSON_MAX:
        return []

    lignes: list[str] = []
    if isinstance(valeur, dict):
        for cle, sous_valeur in valeur.items():
            chemin = f"{prefixe}.{cle}" if prefixe else str(cle)
            lignes.extend(_aplatir(sous_valeur, chemin, profondeur + 1))
    elif isinstance(valeur, list):
        for index, sous_valeur in enumerate(valeur[:LIGNES_TABLEAU_MAX]):
            chemin = f"{prefixe}[{index}]" if prefixe else f"[{index}]"
            lignes.extend(_aplatir(sous_valeur, chemin, profondeur + 1))
    elif valeur is None:
        return []
    else:
        lignes.append(f"{prefixe} : {valeur}" if prefixe else str(valeur))
    return lignes


def extraire_json(contenu: bytes) -> DocumentExtrait:
    """Extrait un JSON, en privilégiant une liste d'objets homogènes.

    Une liste d'objets aux clés communes est rendue comme un tableau
    (en-têtes + valeurs), pour bénéficier du même nommage de colonnes qu'un
    CSV. Les autres formes sont simplement aplaties.
    """
    texte = decoder(contenu).strip()
    if not texte:
        return _finaliser([], "json", [])

    try:
        donnees = json.loads(texte)
    except json.JSONDecodeError as erreur:
        raise ErreurDocumentaire(
            f"JSON illisible : {erreur}", etapa="extraction"
        ) from erreur

    if isinstance(donnees, list) and donnees and all(
        isinstance(element, dict) for element in donnees
    ):
        entetes: list[str] = []
        for element in donnees:
            for cle in element:
                if cle not in entetes:
                    entetes.append(cle)
        lignes = [
            [_valeur_cellule(element.get(entete)) for entete in entetes]
            for element in donnees[:LIGNES_TABLEAU_MAX]
        ]
        blocs = _rendre_lignes(entetes, lignes, titre="Données")
        return _finaliser(blocs, "json", [])

    lignes = _aplatir(donnees)
    blocs = [
        Bloc(texte="\n".join(lignes[position : position + LIGNES_PAR_BLOC]), titre="Données")
        for position in range(0, len(lignes), LIGNES_PAR_BLOC)
    ]
    return _finaliser(blocs, "json", [])


# --- Point d'entrée --------------------------------------------------------

EXTRACTEURS = {
    "pdf": extraire_pdf,
    "txt": extraire_texte,
    "md": extraire_markdown,
    "csv": extraire_csv,
    "json": extraire_json,
    "xlsx": extraire_xlsx,
}


def _finaliser(
    blocs: list[Bloc],
    format_nom: str,
    avertissements: list[str],
) -> DocumentExtrait:
    """Écarte les blocs vides et calcule le volume de texte retenu."""
    retenus = [bloc for bloc in blocs if bloc.texte and bloc.texte.strip()]
    total = sum(len(bloc.texte) for bloc in retenus)
    return DocumentExtrait(
        blocs=retenus,
        format=format_nom,
        nb_caracteres=total,
        avertissements=avertissements,
    )


def formats_acceptes() -> list[str]:
    return sorted(EXTRACTEURS)


def extraire(contenu: bytes, nom_fichier: str) -> DocumentExtrait:
    """Extrait le texte d'un document, en dispatchant sur son format.

    Le format est retenu à partir de l'extension, seule information fiable
    disponible avant l'analyse. Un format non pris en charge est refusé
    explicitement, afin que l'utilisateur sache quoi convertir.
    """
    _verifier_taille(contenu, nom_fichier)

    extension = extension_de_nom(nom_fichier)
    if extension not in EXTRACTEURS:
        autorisees = ", ".join(f".{item}" for item in formats_acceptes())
        raise ErreurDocumentaire(
            f"Format « .{extension or 'inconnu'} » non pris en charge pour "
            f"l'indexation. Formats acceptés : {autorisees}.",
            etapa="extraction",
        )

    if not settings.rag_extensions or extension not in settings.rag_extensions:
        autorisees = ", ".join(f".{item}" for item in settings.rag_extensions)
        raise ErreurDocumentaire(
            f"Le format « .{extension} » n'est pas autorisé par la "
            f"configuration (RAG_EXTENSIONS). Formats autorisés : {autorisees}.",
            etapa="extraction",
        )

    document = EXTRACTEURS[extension](contenu)

    if document.est_vide():
        raise ErreurDocumentaire(
            f"Aucun texte exploitable n'a été extrait de « {nom_fichier} ». "
            "Le document ne peut donc pas être indexé.",
            etapa="extraction",
        )

    logger.info(
        "Extraction « %s » : format=%s, %s bloc(s), %s caractère(s)",
        nom_fichier,
        document.format,
        len(document.blocs),
        document.nb_caracteres,
    )
    return document
