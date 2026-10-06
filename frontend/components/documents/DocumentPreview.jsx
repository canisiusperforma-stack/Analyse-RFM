"use client";

import { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Download,
  Eye,
  Loader2,
  RefreshCw,
  ShieldCheck,
  Trash2,
} from "lucide-react";

import Button from "@/components/ui/Button";
import Modal from "@/components/ui/Modal";
import Badge from "@/components/ui/Badge";
import { usePermissions } from "@/hooks/usePermissions";
import {
  NIVEAUX_CONFIDENTIALITE,
  estClasse,
  iconeDocument,
  niveauConfidentialite,
  statutIndexation,
} from "@/lib/documents";
import { getApiErrorText } from "@/lib/errors";
import {
  formatBytes,
  formatDateTime,
  formatNumber,
} from "@/lib/formatters";
import { courtIdentifiant } from "@/lib/imports";
import { ROLES, ROLE_LABELS } from "@/lib/permissions";

const OPTIONS_NIVEAU = NIVEAUX_CONFIDENTIALITE.map((niveau) => ({
  value: niveau.valeur,
  label: niveau.label,
}));

/**
 * Fiche d'un document : métadonnées, actions et classification.
 *
 * Ce que la fiche montre est la projection publique du document, plus le motif
 * d'un échec d'indexation. Elle ne montre jamais le texte intégral : la
 * lecture du contenu passe par la recherche dans les extraits, qui applique le
 * seuil de pertinence, ou par le téléchargement du fichier d'origine.
 *
 * Deux contrôles méritent d'être lus, car ils ne vont pas de soi :
 *
 * La reclassification est proposée à l'administrateur **seulement**. Fixer la
 * confidentialité revient à décider de ce que chacun verra ; le confier à
 * quiconque peut déjà déposer reviendrait à laisser chacun arbitrer. Le backend
 * n'accorde d'ailleurs aucun passe-droit : un administrateur doit figurer
 * lui-même dans la liste blanche d'un document confidentiel, pour qu'un compte
 * administrateur compromis n'expose pas toute la base par défaut.
 *
 * La suppression est irréversible : elle emporte le document, ses extraits et
 * le fichier d'origine. Elle demande donc une confirmation explicite, dans
 * laquelle le nom du fichier est rappelé — un clic sur la mauvaise ligne dans
 * un tableau de vingt documents est un accident, pas une intention.
 */
export default function DocumentPreview({
  document: documentActif = null,
  ouvert = false,
  onOpen,
  onClose,
  onDownload,
  onReindex,
  onClassify,
  onDelete,
  actionEnCours = null,
  ragActif = true,
}) {
  const { has } = usePermissions();
  const peutClasser = has("documents:acces");
  const peutTelecharger = has("documents:telecharger");
  const peutIndexer = has("documents:indexer");
  const peutSupprimer = has("documents:supprimer");

  const [erreurIndexation, setErreurIndexation] = useState(null);
  const [chargement, setChargement] = useState(false);
  const [erreur, setErreur] = useState(null);
  const [confirmation, setConfirmation] = useState("");
  const [confirmationOuverte, setConfirmationOuverte] = useState(false);

  const [niveau, setNiveau] = useState("interne");
  const [roles, setRoles] = useState([]);
  const [utilisateurs, setUtilisateurs] = useState("");

  // La fiche affichée vient de la ligne du tableau, le temps que la route
  // `/v1/documents/{id}` réponde. Elle est ensuite tenue à jour localement : une
  // reclassification ou une indexation change le statut et le nombre d'extraits
  // sans que la ligne sélectionnée — un objet figé au moment de l'ouverture —
  // puisse le refléter.
  const [fiche, setFiche] = useState(documentActif);

  // Le formulaire de classification est réaligné sur le document affiché :
  // sans cela, ouvrir une fiche après en avoir classé une autre proposerait la
  // classification de la précédente, et l'appliquerait au mauvais document.
  useEffect(() => {
    if (!documentActif) {
      setFiche(null);
      return;
    }
    setFiche(documentActif);
    setNiveau(documentActif.confidentialite || "interne");
    setRoles(documentActif.roles_autorises || []);
    setUtilisateurs((documentActif.utilisateurs_autorises || []).join(", "));
    setConfirmation("");
    setConfirmationOuverte(false);
    setErreurIndexation(null);
    setErreur(null);
  }, [documentActif]);

  const charger = useCallback(async () => {
    const identifiant = fiche?.id;
    if (!identifiant) return;
    setChargement(true);
    setErreur(null);
    try {
      const donnees = await onOpen(identifiant);
      if (donnees?.document) setFiche(donnees.document);
      setErreurIndexation(donnees?.erreur_indexation ?? null);
    } catch (errorChargement) {
      setErreur(getApiErrorText(errorChargement));
    } finally {
      setChargement(false);
    }
  }, [fiche?.id, onOpen]);

  useEffect(() => {
    if (ouvert && fiche) charger();
    // `charger` se referme sur l'identifiant : le rechargement suit le document
    // affiché, pas la référence de fonction.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ouvert, fiche?.id]);

  if (!fiche) return null;

  const Icone = iconeDocument(fiche.extension);
  const niveauCourant = niveauConfidentialite(fiche.confidentialite);
  const statut = statutIndexation(fiche.statut_indexation);
  const enCours = actionEnCours === fiche.id;
  const classe = niveau !== "interne";

  const basculerRole = (role) =>
    setRoles((precedents) =>
      precedents.includes(role)
        ? precedents.filter((item) => item !== role)
        : [...precedents, role]
    );

  const appliquerClassification = async () => {
    setErreur(null);
    try {
      const resultat = await onClassify(fiche.id, {
        confidentialite: niveau,
        rolesAutorises: classe ? roles : [],
        utilisateursAutorises: classe
          ? utilisateurs
              .split(",")
              .map((item) => item.trim())
              .filter(Boolean)
          : [],
      });
      if (resultat?.document) setFiche(resultat.document);
    } catch (errorClassement) {
      setErreur(getApiErrorText(errorClassement));
    }
  };

  const reindexer = async () => {
    setErreur(null);
    try {
      const resultat = await onReindex(fiche);
      if (resultat?.document) setFiche(resultat.document);
    } catch (errorReindexation) {
      setErreur(getApiErrorText(errorReindexation));
    }
  };

  const confirmerSuppression = async () => {
    setErreur(null);
    try {
      await onDelete(fiche);
    } catch (errorSuppression) {
      setErreur(getApiErrorText(errorSuppression));
    }
  };

  const peutConfirmer = confirmation === fiche.nom_fichier;

  return (
    <Modal
      open={ouvert}
      onClose={onClose}
      size="lg"
      title={fiche.nom_fichier}
      description={`Déposé le ${formatDateTime(fiche.created_at)} par ${
        courtIdentifiant(fiche.cree_par)
      }`}
      footer={
        <div
          style={{
            display: "flex",
            gap: 8,
            flexWrap: "wrap",
            justifyContent: "flex-end",
          }}
        >
          {peutTelecharger && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => onDownload(fiche)}
              disabled={enCours}
            >
              <Download size={15} aria-hidden="true" />
              Télécharger l'original
            </Button>
          )}
          {peutIndexer && (
            <Button
              variant="outline"
              size="sm"
              loading={enCours}
              disabled={!ragActif}
              title={
                ragActif
                  ? undefined
                  : "La recherche documentaire est désactivée"
              }
              onClick={reindexer}
            >
              {!enCours && <RefreshCw size={15} aria-hidden="true" />}
              {fiche.statut_indexation === "indexe"
                ? "Réindexer"
                : "Indexer"}
            </Button>
          )}
          {peutSupprimer &&
            (confirmationOuverte ? (
              <>
                <span className="tableau__sous-texte">
                  Tapez <code>{fiche.nom_fichier}</code> pour confirmer
                </span>
                <input
                  className="input"
                  style={{ maxWidth: 260 }}
                  value={confirmation}
                  onChange={(event) => setConfirmation(event.target.value)}
                  aria-label="Confirmer la suppression"
                  autoComplete="off"
                />
                <Button
                  variant="danger"
                  size="sm"
                  loading={enCours}
                  disabled={!peutConfirmer}
                  onClick={confirmerSuppression}
                >
                  Supprimer définitivement
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    setConfirmationOuverte(false);
                    setConfirmation("");
                  }}
                >
                  Annuler
                </Button>
              </>
            ) : (
              <Button
                variant="danger"
                size="sm"
                onClick={() => setConfirmationOuverte(true)}
              >
                <Trash2 size={15} aria-hidden="true" />
                Supprimer
              </Button>
            ))}
        </div>
      }
    >
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16 }}>
        <Icone size={28} aria-hidden="true" />
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <Badge variant={niveauCourant.variante} dot>
            {niveauCourant.label}
          </Badge>
          <Badge variant={statut.variante} dot={statut.pastille}>
            {statut.label}
          </Badge>
        </div>
        {chargement && (
          <span className="text-muted">
            <Loader2 size={14} className="spinner" aria-hidden="true" /> Chargement…
          </span>
        )}
      </div>

      {erreur && (
        <div className="alert alert--error" role="alert">
          <AlertTriangle size={18} className="alert__icon" aria-hidden="true" />
          <span>{erreur}</span>
        </div>
      )}

      {erreurIndexation && (
        <div className="alert alert--error" role="alert">
          <AlertTriangle size={18} className="alert__icon" aria-hidden="true" />
          <span>
            <strong>Extraction impossible :</strong> {erreurIndexation}. Le
            document reste déposé, consultable et supprimable — seul
            l&apos;interrogation par l&apos;assistant lui est refusée.
          </span>
        </div>
      )}

      {fiche.description && (
        <p className="text-muted" style={{ marginBottom: 16 }}>
          {fiche.description}
        </p>
      )}

      <div className="meta-list">
        <div className="meta-list__item">
          <span className="meta-list__label">Format</span>
          <span className="meta-list__value">
            {fiche.extension
              ? `.${fiche.extension}`
              : "—"}
            {fiche.type_mime ? ` · ${fiche.type_mime}` : ""}
          </span>
        </div>
        <div className="meta-list__item">
          <span className="meta-list__label">Taille</span>
          <span className="meta-list__value">
            {formatBytes(fiche.taille_octets)}
          </span>
        </div>
        <div className="meta-list__item">
          <span className="meta-list__label">Extraits indexés</span>
          <span className="meta-list__value">
            {formatNumber(fiche.nb_morceaux ?? 0)}
          </span>
        </div>
        <div className="meta-list__item">
          <span className="meta-list__label">Déposé le</span>
          <span className="meta-list__value">
            {formatDateTime(fiche.created_at)}
          </span>
        </div>
        <div className="meta-list__item">
          <span className="meta-list__label">Dernière modification</span>
          <span className="meta-list__value">
            {formatDateTime(fiche.updated_at)}
          </span>
        </div>
        <div className="meta-list__item">
          <span className="meta-list__label">Rôles autorisés</span>
          <span className="meta-list__value">
            {estClasse(fiche.confidentialite)
              ? (fiche.roles_autorises || [])
                  .map((role) => ROLE_LABELS[role] ?? role)
                  .join(", ") || "—"
              : "Tous les utilisateurs autorisés"}
          </span>
        </div>
        <div className="meta-list__item">
          <span className="meta-list__label">Utilisateurs nommés</span>
          <span className="meta-list__value">
            {fiche.confidentialite === "confidentielle"
              ? (fiche.utilisateurs_autorises || [])
                  .map((identifiant) => courtIdentifiant(identifiant))
                  .join(", ") || "—"
              : "Sans objet"}
          </span>
        </div>
      </div>

      {peutClasser && (
        <div className="card card__padding" style={{ marginTop: 18 }}>
          <h4 className="card__title" style={{ fontSize: "0.95rem" }}>
            <ShieldCheck
              size={14}
              aria-hidden="true"
              style={{ verticalAlign: "-2px", marginRight: 6 }}
            />
            Classification
          </h4>
          <p className="text-muted">
            Le changement est répercuté sur les extraits déjà indexés. Sans cela,
            un document promu de « interne » à « confidentielle » continuerait de
            répondre par des extraits portant encore l&aposancienne
            classification, donc resterait lisible par ceux qui ne devraient
            plus le voir.
          </p>

          <div className="filtres-bar" style={{ marginTop: 12 }}>
            <div className="filtres-bar__champ">
              <label className="field__label" htmlFor="document-niveau">
                Niveau de diffusion
              </label>
              <select
                id="document-niveau"
                className="select"
                value={niveau}
                onChange={(event) => {
                  setNiveau(event.target.value);
                  setRoles([]);
                }}
              >
                {OPTIONS_NIVEAU.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              <span className="field__hint">
                {niveauConfidentialite(niveau).description}
              </span>
            </div>

            <div className="filtres-bar__champ">
              <label className="field__label" htmlFor="document-utilisateurs">
                Utilisateurs nommés
              </label>
              <input
                id="document-utilisateurs"
                className="input"
                value={utilisateurs}
                onChange={(event) => setUtilisateurs(event.target.value)}
                placeholder="665f1b2c3d4e5f6a…, 665f1b2c3d4e5f6a…"
                disabled={niveau !== "confidentielle"}
              />
              <span className="field__hint">
                Identifiants séparés par des virgules. N&apos;a d&apos;effet
                qu&apos;en « confidentielle ».
              </span>
            </div>
          </div>

          {classe && (
            <div style={{ marginTop: 12 }}>
              <span className="field__label">Rôles autorisés à lire</span>
              <div
                style={{
                  display: "flex",
                  gap: 14,
                  flexWrap: "wrap",
                  marginTop: 6,
                }}
              >
                {ROLES.map((role) => (
                  <label
                    key={role}
                    style={{ display: "flex", gap: 6, alignItems: "center" }}
                  >
                    <input
                      type="checkbox"
                      checked={roles.includes(role)}
                      onChange={() => basculerRole(role)}
                    />
                    <span className="tableau__sous-texte">
                      {ROLE_LABELS[role] ?? role}
                    </span>
                  </label>
                ))}
              </div>
              <p className="text-muted" style={{ marginTop: 6 }}>
                <AlertTriangle size={13} aria-hidden="true" /> Un niveau classé
                sans aucun rôle autorisé serait inaccessible à tout le monde :
                le backend refuse cette combinaison.
              </p>
            </div>
          )}

          <div style={{ marginTop: 14 }}>
            <Button
              size="sm"
              loading={enCours}
              disabled={classe && roles.length === 0}
              title={
                classe && roles.length === 0
                  ? "Désignez au moins un rôle autorisé"
                  : undefined
              }
              onClick={appliquerClassification}
            >
              <CheckCircle2 size={15} aria-hidden="true" />
              Appliquer la classification
            </Button>
          </div>
        </div>
      )}

      {!peutClasser && estClasse(fiche.confidentialite) && (
        <p className="text-muted" style={{ marginTop: 16 }}>
          <Eye size={13} aria-hidden="true" /> Ce document est{" "}
          {niveauCourant.label.toLowerCase()}. Sa classification est réservée à
          l&apos;administrateur.
        </p>
      )}
    </Modal>
  );
}
