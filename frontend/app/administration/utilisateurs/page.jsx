"use client";

import { useCallback, useState } from "react";
import { AlertCircle, Check, ChevronLeft, ChevronRight, Plus, X } from "lucide-react";

import PageContainer from "@/components/layout/PageContainer";
import PermissionsGate from "@/components/auth/PermissionsGate";
import RepartitionRoles from "@/components/administration/RepartitionRoles";
import RoleModal from "@/components/administration/RoleModal";
import SuppressionModal from "@/components/administration/SuppressionModal";
import UtilisateurFormModal from "@/components/administration/UtilisateurFormModal";
import UtilisateurStats from "@/components/administration/UtilisateurStats";
import UtilisateurTable from "@/components/administration/UtilisateurTable";
import Button from "@/components/ui/Button";
import useUtilisateurs from "@/hooks/useUtilisateurs";
import { getApiErrorText } from "@/lib/errors";
import { formatNumber } from "@/lib/formatters";
import { nomComplet } from "@/lib/administration";

const MODALITE_CREATION = "creation";
const MODALITE_EDITION = "edition";

/**
 * Administration des comptes.
 *
 * Tout ce qui *attribue* un droit est ici, et rien ne l'est ailleurs. La page
 * reflète le référentiel mais n'en tient pas lieu : chaque action passe par le
 * backend, qui seul connaît les interdits — impossible de changer son propre
 * rôle, impossible de supprimer son propre compte, impossible de descendre sous
 * le dernier administrateur.
 *
 * Deux listes cohabitent et ne se confondent jamais. Le tableau paginé est la vue
 * de travail, filtrable côté serveur. Les compteurs et la répartition par rôle
 * portent sur l'ensemble de la population, obtenue par une seconde requête sans
 * filtre : une barre calculée sur les vingt lignes affichées afficherait « trois
 * administrateurs » là où il y en a peut-être douze. Quand la population dépasse
 * la fenêtre de chargement, l'écran le dit plutôt que de présenter un décompte
 * partiel comme exact.
 */
export default function UtilisateursPage() {
  const {
    liste,
    comptes,
    compte,
    filtres,
    modifieFiltres,
    reinitialiserFiltres,
    recherche,
    setRecherche,
    filtresActifs,
    saut,
    setSaut,
    limite,
    loading,
    error,
    actionEnCours,
    recharger,
    creer,
    modifier,
    changerRole,
    supprimer,
  } = useUtilisateurs();

  const [modalite, setModalite] = useState(null);
  const [fiche, setFiche] = useState(null);
  const [cibleRole, setCibleRole] = useState(null);
  const [cibleSuppression, setCibleSuppression] = useState(null);
  const [soumission, setSoumission] = useState(false);
  const [notice, setNotice] = useState(null);

  const signaler = useCallback((texte, variante = "success") => {
    setNotice({ texte, variante });
  }, []);

  const fermer = useCallback(() => {
    setModalite(null);
    setFiche(null);
    setCibleRole(null);
    setCibleSuppression(null);
  }, []);

  const ouvrirCreation = useCallback(() => {
    setFiche(null);
    setModalite(MODALITE_CREATION);
  }, []);

  const ouvrirFiche = useCallback((utilisateur) => {
    setModalite(MODALITE_EDITION);
    setFiche(utilisateur);
  }, []);

  const creerCompte = useCallback(
    async (donnees) => {
      setSoumission(true);
      try {
        const utilisateur = await creer(donnees);
        fermer();
        signaler(
          `Compte créé pour ${nomComplet(utilisateur)}. Aucun jeton n'a été émis : la personne se connectera avec le mot de passe provisoire.`
        );
      } catch (erreur) {
        // La modale reste ouverte et le motif du refus est affiché : l'écran ne
        // ferme pas sur une action qui n'a pas eu lieu. Rethrower ferait une
        // promesse rejetée sans consommateur — les modales n'attendent pas le
        // retour de `onSubmit`.
        signaler(getApiErrorText(erreur), "error");
      } finally {
        setSoumission(false);
      }
    },
    [creer, fermer, signaler]
  );

  const enregistrerFiche = useCallback(
    async (donnees) => {
      if (!fiche) return;
      setSoumission(true);
      try {
        const utilisateur = await modifier(fiche.id, donnees);
        fermer();
        signaler(`Fiche de ${nomComplet(utilisateur)} enregistrée.`);
      } catch (erreur) {
        // La modale reste ouverte et le motif du refus est affiché : l'écran ne
        // ferme pas sur une action qui n'a pas eu lieu. Rethrower ferait une
        // promesse rejetée sans consommateur — les modales n'attendent pas le
        // retour de `onSubmit`.
        signaler(getApiErrorText(erreur), "error");
      } finally {
        setSoumission(false);
      }
    },
    [fiche, fermer, modifier, signaler]
  );

  const attribuerRole = useCallback(
    async (role) => {
      if (!cibleRole) return;
      setSoumission(true);
      try {
        const utilisateur = await changerRole(cibleRole.id, role);
        fermer();
        signaler(
          `${nomComplet(utilisateur)} est désormais ${utilisateur.role}.`
        );
      } catch (erreur) {
        // La modale reste ouverte et le motif du refus est affiché : l'écran ne
        // ferme pas sur une action qui n'a pas eu lieu. Rethrower ferait une
        // promesse rejetée sans consommateur — les modales n'attendent pas le
        // retour de `onSubmit`.
        signaler(getApiErrorText(erreur), "error");
      } finally {
        setSoumission(false);
      }
    },
    [cibleRole, changerRole, fermer, signaler]
  );

  const supprimerCompte = useCallback(async () => {
    if (!cibleSuppression) return;
    const nom = nomComplet(cibleSuppression);
    setSoumission(true);
    try {
      await supprimer(cibleSuppression.id);
      fermer();
      signaler(`Compte de ${nom} supprimé définitivement.`);
    } catch (erreur) {
      // Voir les autres gestionnaires : la modale reste ouverte sur un refus.
      signaler(getApiErrorText(erreur), "error");
    } finally {
      setSoumission(false);
    }
  }, [cibleSuppression, fermer, signaler, supprimer]);

  const total = liste?.total ?? 0;
  const pageCourante = Math.floor(saut / limite) + 1;
  const pages = Math.max(1, Math.ceil(total / limite));
  const debut = total === 0 ? 0 : saut + 1;
  const fin = Math.min(saut + comptes.length, total);

  return (
    <PageContainer
      title="Utilisateurs"
      subtitle="Comptes, rôles et habilitations de la plateforme. Chaque action est soumise au backend, seul juge des interdits."
      actions={
        <PermissionsGate permission="utilisateurs:creer">
          <Button onClick={ouvrirCreation}>
            <Plus size={16} aria-hidden="true" />
            Nouveau compte
          </Button>
        </PermissionsGate>
      }
    >
      <div className="import-stack">
        {error && !loading && (
          <div className="alert alert--error" role="alert">
            <AlertCircle size={18} className="alert__icon" aria-hidden="true" />
            <span>
              Impossible de charger les comptes : {getApiErrorText(error)}
            </span>
          </div>
        )}

        {notice && (
          <div
            className={`alert alert--${notice.variante}`}
            role="status"
            style={{
              borderLeft: `3px solid var(--color-${
                notice.variante === "error" ? "danger" : "success"
              })`,
            }}
          >
            {notice.variante === "error" ? (
              <AlertCircle size={18} className="alert__icon" aria-hidden="true" />
            ) : (
              <Check size={18} className="alert__icon" aria-hidden="true" />
            )}
            <span>{notice.texte}</span>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setNotice(null)}
              aria-label="Fermer le message"
            >
              <X size={14} aria-hidden="true" />
            </Button>
          </div>
        )}

        <UtilisateurStats compte={compte} loading={false} />

        <RepartitionRoles compte={compte} loading={false} />

        <UtilisateurTable
          comptes={comptes}
          loading={loading}
          filtres={filtres}
          onFiltres={modifieFiltres}
          recherche={recherche}
          onRecherche={setRecherche}
          onReinitialiser={reinitialiserFiltres}
          filtresActifs={filtresActifs}
          actionEnCours={actionEnCours}
          onRefresh={recharger}
          onOuvrir={ouvrirFiche}
          onChangerRole={setCibleRole}
          onSupprimer={setCibleSuppression}
        />

        {total > limite && (
          <div className="tableau__pied">
            <span className="tableau__resume">
              {formatNumber(debut)}–{formatNumber(fin)} sur{" "}
              {formatNumber(total)} compte(s) · page {pageCourante} sur {pages}
              {compte?.partiel && (
                <>
                  {" "}
                  — les compteurs ci-dessus couvrent{" "}
                  {formatNumber(compte.observe)} comptes sur{" "}
                  {formatNumber(compte.population)}
                </>
              )}
            </span>
            <span className="tableau__nav">
              <Button
                variant="ghost"
                size="sm"
                disabled={saut === 0}
                onClick={() => setSaut(Math.max(0, saut - limite))}
              >
                <ChevronLeft size={16} aria-hidden="true" />
                Précédent
              </Button>
              <Button
                variant="ghost"
                size="sm"
                disabled={fin >= total}
                onClick={() => setSaut(saut + limite)}
              >
                Suivant
                <ChevronRight size={16} aria-hidden="true" />
              </Button>
            </span>
          </div>
        )}

        <p className="text-muted">
          <AlertCircle size={13} aria-hidden="true" /> Le backend interdit de
          changer son propre rôle et de supprimer son propre compte : ces
          actions sont désactivées sur votre ligne, car l&apos;écran le sait avec
          certitude. Les autres refus — par exemple faire descendre le dernier
          administrateur — ne sont pas prévisibles ici : ils viennent du serveur,
          au moment du clic.
        </p>

        <p className="text-muted">
          <AlertCircle size={13} aria-hidden="true" /> <strong>Lecture.</strong>{" "}
          La liste est paginée par le backend et la recherche porte sur la page
          affichée. Pour un décompte exhaustif par rôle, la répartition ci-dessus
          utilise une requête dédiée, sans filtre.
        </p>
      </div>

      <UtilisateurFormModal
        open={modalite != null}
        mode={modalite ?? MODALITE_CREATION}
        utilisateur={fiche}
        onClose={fermer}
        onSubmit={
          modalite === MODALITE_EDITION ? enregistrerFiche : creerCompte
        }
        submitting={soumission}
      />

      <RoleModal
        open={cibleRole != null}
        utilisateur={cibleRole}
        onClose={fermer}
        onSubmit={attribuerRole}
        submitting={soumission}
      />

      <SuppressionModal
        open={cibleSuppression != null}
        utilisateur={cibleSuppression}
        onClose={fermer}
        onConfirm={supprimerCompte}
        submitting={soumission}
      />
    </PageContainer>
  );
}