"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import {
  consulterDocument,
  indexerDocument,
  listerDocuments,
  modifierAccesDocument,
  referentielDocuments,
  statistiquesDocuments,
  supprimerDocument,
  telechargerDocument,
} from "@/services/documentService";
import { telechargerBlob } from "@/lib/imports";

/**
 * État de la page « Documents ».
 *
 * Le hook regroupe ce qui est partagé par toute la page — la liste, les
 * statistiques, le référentiel du pipeline — et les actions qui les modifient.
 * Chaque action renvoie la donnée fraîche renvoyée par le backend plutôt que
 * de la reconstruire localement : l'indexation, la reclassification et la
 * suppression ont des effets que le client ne peut pas deviner (extraits
 * resynchronisés, nombre de morceaux réellement produit), et un état optimiste
 * afficherait un résultat qui n'a pas eu lieu.
 *
 * Une action qui échoue **ne** recharge pas la liste et **ne** touche pas
 * `error` : elle remonte l'échec à l'appelant, qui en fait un message ciblé.
 * Écraser `error` afficherait « impossible de charger la base documentaire » en
 * tête d'une page dont la liste s'affiche parfaitement — un échec d'indexation
 * décrit comme un chargement raté.
 */
export default function useDocuments() {
  const [documents, setDocuments] = useState([]);
  const [total, setTotal] = useState(0);
  const [statistiques, setStatistiques] = useState(null);
  const [referentiel, setReferentiel] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Une action en cours porte son propre état : sans cela, recharger la liste
  // pendant une indexation afficherait un chargement global et masquerait la
  // ligne concernée, qui est précisément ce que l'agent veut surveiller.
  const [actionEnCours, setActionEnCours] = useState(null);

  const recharger = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [liste, etat] = await Promise.all([
        listerDocuments({ limite: 100 }),
        statistiquesDocuments(),
      ]);
      setDocuments(liste.documents ?? []);
      setTotal(liste.total ?? 0);
      setStatistiques(etat);
      return liste;
    } catch (erreur) {
      setError(erreur);
      throw erreur;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    recharger().catch(() => {
      // l'erreur est exposée via `error`
    });
  }, [recharger]);

  useEffect(() => {
    let annule = false;
    referentielDocuments()
      .then((donnees) => {
        if (!annule) setReferentiel(donnees);
      })
      .catch(() => {
        // Le référentiel est un complément : son absence (RAG coupé, droits
        // insuffisants) ne doit pas empêcher l'administration de la base, qui
        // reste entièrement fonctionnelle sans lui.
        if (!annule) setReferentiel(null);
      });
    return () => {
      annule = true;
    };
  }, []);

  /** Remplace un document dans la liste, à partir de sa version fraîche. */
  const remplacer = useCallback((document) => {
    if (!document?.id) return;
    setDocuments((precedents) =>
      precedents.some((item) => item.id === document.id)
        ? precedents.map((item) => (item.id === document.id ? document : item))
        : [document, ...precedents]
    );
  }, []);

  const rafraichirStatistiques = useCallback(async () => {
    try {
      setStatistiques(await statistiquesDocuments());
    } catch {
      // Compteur secondaire : son échec ne doit pas masquer une action réussie.
    }
  }, []);

  const ouvrir = useCallback(async (identifiant) => {
    const donnees = await consulterDocument(identifiant);
    return donnees;
  }, []);

  const telecharger = useCallback(async (document) => {
    const blob = await telechargerDocument(document.id);
    telechargerBlob(blob, document.nom_fichier);
  }, []);

  const indexer = useCallback(
    async (identifiant, { force = true } = {}) => {
      setActionEnCours(identifiant);
      try {
        const resultat = await indexerDocument(identifiant, { force });
        if (resultat?.document) remplacer(resultat.document);
        await rafraichirStatistiques();
        return resultat;
      } finally {
        setActionEnCours(null);
      }
    },
    [rafraichirStatistiques, remplacer]
  );

  const classer = useCallback(
    async (identifiant, acces) => {
      setActionEnCours(identifiant);
      try {
        const resultat = await modifierAccesDocument(identifiant, acces);
        // La route ne renvoie le document que si l'administrateur est
        // autorisé à le lire : dans le cas contraire elle ne renvoie que la
        // classification appliquée. Remplacer la ligne par `null` effacerait
        // donc l'affichage d'un document parfaitement consultable.
        if (resultat?.document) remplacer(resultat.document);
        await rafraichirStatistiques();
        return resultat;
      } finally {
        setActionEnCours(null);
      }
    },
    [rafraichirStatistiques, remplacer]
  );

  const supprimer = useCallback(
    async (identifiant) => {
      setActionEnCours(identifiant);
      try {
        const resultat = await supprimerDocument(identifiant);
        setDocuments((precedents) =>
          precedents.filter((item) => item.id !== identifiant)
        );
        setTotal((precedent) => Math.max(0, precedent - 1));
        await rafraichirStatistiques();
        return resultat;
      } finally {
        setActionEnCours(null);
      }
    },
    [rafraichirStatistiques]
  );

  const apresDepot = useCallback(
    async (resultat) => {
      if (resultat?.document) remplacer(resultat.document);
      await rafraichirStatistiques();
      return resultat;
    },
    [rafraichirStatistiques, remplacer]
  );

  const ragActif = referentiel?.actif === true;
  const peutIndexer = ragActif;

  const compte = useMemo(() => {
    return {
      total: total || documents.length,
      indexes: documents.filter((item) => item.statut_indexation === "indexe")
        .length,
      echecs: documents.filter((item) => item.statut_indexation === "echec")
        .length,
      classes: documents.filter(
        (item) => item.confidentialite && item.confidentialite !== "interne"
      ).length,
    };
  }, [documents, total]);

  return {
    documents,
    total,
    statistiques,
    referentiel,
    loading,
    error,
    compte,
    ragActif,
    peutIndexer,
    actionEnCours,
    recharger,
    ouvrir,
    telecharger,
    indexer,
    classer,
    supprimer,
    apresDepot,
  };
}
