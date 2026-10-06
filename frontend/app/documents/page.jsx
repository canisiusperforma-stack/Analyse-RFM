"use client";

import { useCallback, useState } from "react";
import { AlertCircle, Search } from "lucide-react";

import PermissionsGate from "@/components/auth/PermissionsGate";
import PageContainer from "@/components/layout/PageContainer";
import DocumentPreview from "@/components/documents/DocumentPreview";
import DocumentReferentiel from "@/components/documents/DocumentReferentiel";
import DocumentSearch from "@/components/documents/DocumentSearch";
import DocumentStats from "@/components/documents/DocumentStats";
import DocumentTable from "@/components/documents/DocumentTable";
import DocumentUpload from "@/components/documents/DocumentUpload";
import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import useDocuments from "@/hooks/useDocuments";
import { getApiErrorText } from "@/lib/errors";

/**
 * Base documentaire du SRB.
 *
 * La page regroupe ce que le backend expose réellement sur `/v1/documents`, et
 * rien de plus : dépôt, liste, fiche, classification, indexation, et
 * exploration des extraits sans modèle. Elle ne préjuge d'aucune capacité —
 * chaque action est offerte selon les permissions, et le backend reste seul
 * juge de ce qu'un utilisateur voit.
 *
 * Les compteurs affichés ne portent que sur les documents accessibles à
 * l'appelant. C'est délibéré : un total brut révélerait l'existence de
 * documents que l'agent n'a pas le droit de lire, et il suffirait ensuite de
 * tester des noms probables pour cartographier la base.
 */
export default function DocumentsPage() {
  const {
    documents,
    statistiques,
    referentiel,
    loading,
    error,
    compte,
    ragActif,
    actionEnCours,
    recharger,
    ouvrir,
    telecharger,
    indexer,
    classer,
    supprimer,
    apresDepot,
  } = useDocuments();

  const [selection, setSelection] = useState(null);
  const [ficheOuverte, setFicheOuverte] = useState(false);
  const [notice, setNotice] = useState(null);

  const message = useCallback((texte, variante = "success") => {
    setNotice({ texte, variante });
  }, []);

  const ouvrirFiche = useCallback((document) => {
    setSelection(document);
    setFicheOuverte(true);
  }, []);

  const fermerFiche = useCallback(() => {
    setFicheOuverte(false);
    setSelection(null);
  }, []);

  const deposer = useCallback(
    async (resultat) => {
      await apresDepot(resultat);
      await recharger().catch(() => {});
    },
    [apresDepot, recharger]
  );

  const telechargerFichier = useCallback(
    async (document) => {
      try {
        await telecharger(document);
      } catch (erreur) {
        message(getApiErrorText(erreur), "error");
      }
    },
    [message, telecharger]
  );

  const reindexer = useCallback(
    async (document) => {
      try {
        const resultat = await indexer(document.id);
        message(
          resultat?.succes
            ? `« ${document.nom_fichier} » indexé — ${resultat.nb_morceaux} extrait(s) en ${resultat.duree_ms} ms.`
            : `« ${document.nom_fichier} » : ${resultat?.message || "l'extraction n'a pas abouti."}`
        );
        // La fiche reste ouverte pendant l'indexation : sans ce retour, elle
        // afficherait encore l'ancien statut et l'ancien nombre d'extraits.
        return resultat;
      } catch (erreur) {
        message(getApiErrorText(erreur), "error");
        throw erreur;
      }
    },
    [indexer]
  );

  const reclassifier = useCallback(
    async (identifiant, acces) => {
      try {
        const resultat = await classer(identifiant, acces);
        const synchronises = resultat?.morceaux_synchronises ?? 0;
        message(
          `Classification appliquée : ${resultat?.classification?.confidentialite ?? acces.confidentialite}. ${
            synchronises > 0
              ? `${synchronises} extrait(s) resynchronisé(s).`
              : "Aucun extrait à resynchroniser."
          }`
        );
        await recharger().catch(() => {});
        return resultat;
      } catch (erreur) {
        message(getApiErrorText(erreur), "error");
        throw erreur;
      }
    },
    [classer, recharger]
  );

  const supprimerDocument = useCallback(
    async (document) => {
      try {
        await supprimer(document.id);
        fermerFiche();
        message(`« ${document.nom_fichier} » supprimé, ainsi que ses extraits et son fichier d'origine.`);
      } catch (erreur) {
        message(getApiErrorText(erreur), "error");
        throw erreur;
      }
    },
    [fermerFiche, supprimer]
  );

  return (
    <PageContainer
      title="Base documentaire"
      subtitle="Documents autorisés du SRB : dépôt, classification, indexation et recherche dans les extraits. Un document auquel vous n'avez pas droit n'est ni listé, ni lu, ni cité."
      actions={
        <Badge variant={ragActif ? "success" : "warning"} dot>
          {ragActif ? "Recherche documentaire active" : "Recherche documentaire désactivée"}
        </Badge>
      }
    >
      <div className="import-stack">
        {error && !loading && (
          <div className="alert alert--error" role="alert">
            <AlertCircle size={18} className="alert__icon" aria-hidden="true" />
            <span>
              Impossible de charger la base documentaire : {getApiErrorText(error)}
            </span>
          </div>
        )}

        {notice && (
          <div
            className={`alert alert--${notice.variante}`}
            role="status"
            style={{
              borderLeft: `3px solid var(--color-${notice.variante === "error" ? "danger" : "success"})`,
            }}
          >
            <span>{notice.texte}</span>
            <Button variant="ghost" size="sm" onClick={() => setNotice(null)}>
              Fermer
            </Button>
          </div>
        )}

        <DocumentStats
          statistiques={statistiques}
          referentiel={referentiel}
          compte={compte}
        />

        <PermissionsGate permission="documents:televerser">
          <DocumentUpload onDepose={deposer} referentiel={referentiel} />
        </PermissionsGate>

        <DocumentTable
          documents={documents}
          loading={loading}
          onRefresh={recharger}
          onOpen={ouvrirFiche}
          onDelete={supprimerDocument}
          actionEnCours={actionEnCours}
          ragActif={ragActif}
        />

        <DocumentSearch
          documents={documents}
          ragActif={ragActif}
          referentiel={referentiel}
        />

        <DocumentReferentiel referentiel={referentiel} />

        <p className="text-muted">
          <Search size={13} aria-hidden="true" /> Pour une réponse rédigée
          plutôt que des extraits bruts, passer par l&apos;assistant : il
          applique les mêmes règles d&apos;accès et les mêmes citations, mais
          formule la réponse à partir des seuls documents autorisés.
        </p>
      </div>

      <DocumentPreview
        document={selection}
        ouvert={ficheOuverte}
        onClose={fermerFiche}
        onOpen={ouvrir}
        onDownload={telechargerFichier}
        onReindex={reindexer}
        onClassify={reclassifier}
        onDelete={supprimerDocument}
        actionEnCours={actionEnCours}
        ragActif={ragActif}
      />
    </PageContainer>
  );
}
