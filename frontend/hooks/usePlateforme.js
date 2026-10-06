"use client";

import { useCallback, useEffect, useState } from "react";

import { referentielDocuments } from "@/services/documentService";
import { verifierSante } from "@/services/systemeService";
import { usePermissions } from "@/hooks/usePermissions";

/**
 * État de la plateforme, tel que le backend le déclare.
 *
 * `/api/sante` est interrogée sanspermission : c'est une route publique, faite
 * pour être appelée même quand plus rien d'autre ne répond. Son échec distingue
 * donc deux pannes que l'interface ne peut pas distinguer seule — l'API
 * injoignable, et l'API vivante mais la base perdue. Le mode dégradé du
 * démarrage de FastAPI fait que le second cas est réel : l'API répond, et toutes
 * les routes métier échouent.
 *
 * Le périmètre documentaire est une source distincte, avec ses propres droits
 * (`documents:voir`). Son absence n'est pas une panne : un RAG coupé se
 * signale par `actif: false`, pas par une erreur.
 */
export default function usePlateforme() {
  const { has, ready } = usePermissions();

  const [sante, setSante] = useState(null);
  const [santeErreur, setSanteErreur] = useState(null);
  const [referentiel, setReferentiel] = useState(null);
  const [loading, setLoading] = useState(false);

  const verifier = useCallback(async () => {
    setLoading(true);
    setSanteErreur(null);
    try {
      const donnees = await verifierSante();
      setSante(donnees);
      return donnees;
    } catch (erreur) {
      setSante(null);
      setSanteErreur(erreur);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    verifier();
  }, [verifier]);

  const litReferentiel = has("documents:voir");

  useEffect(() => {
    if (!ready || !litReferentiel) return undefined;
    let annule = false;
    referentielDocuments()
      .then((donnees) => {
        if (!annule) setReferentiel(donnees);
      })
      .catch(() => {
        if (!annule) setReferentiel(null);
      });
    return () => {
      annule = true;
    };
  }, [litReferentiel, ready]);

  return {
    sante,
    santeErreur,
    referentiel,
    loading,
    verifier,
    /** Base perdue alors que l'API répond : le mode dégradé du démarrage. */
    degrade: sante != null && sante.mongodb !== "ok",
    ragActif: referentiel?.actif === true,
  };
}
