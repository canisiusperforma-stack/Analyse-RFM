"use client";

import { useCallback, useEffect, useState } from "react";

import {
  genererPrevision,
  recupererDonneesPrevisions,
  recupererMetaPrevisions,
} from "@/services/previsionService";

const PARAMETRES_INITIAUX = {
  phase: "paiement",
  horizon: 6,
  methode: "",
};

export default function usePrevisions() {
  const [referentiel, setReferentiel] = useState(null);
  const [donnees, setDonnees] = useState(null);
  const [resultat, setResultat] = useState(null);
  const [parametres, setParametres] = useState(PARAMETRES_INITIAUX);
  const [loadingDonnees, setLoadingDonnees] = useState(false);
  const [generationLoading, setGenerationLoading] = useState(false);
  const [error, setError] = useState(null);
  const [generationError, setGenerationError] = useState(null);

  const modifieParametres = useCallback((patch) => {
    setParametres((precedents) => ({ ...precedents, ...patch }));
  }, []);

  useEffect(() => {
    let annule = false;
    recupererMetaPrevisions()
      .then((referentielData) => {
        if (!annule) setReferentiel(referentielData);
      })
      .catch((erreur) => {
        if (!annule) setError(erreur);
      });
    return () => {
      annule = true;
    };
  }, []);

  const chargerDonnees = useCallback((phase) => {
    setLoadingDonnees(true);
    setError(null);
    return recupererDonneesPrevisions({ phase })
      .then((donneesData) => {
        setDonnees(donneesData);
        return donneesData;
      })
      .catch((erreur) => {
        setError(erreur);
        throw erreur;
      })
      .finally(() => setLoadingDonnees(false));
  }, []);

  useEffect(() => {
    chargerDonnees(parametres.phase).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [parametres.phase]);

  const lancerGeneration = useCallback(
    async (options = {}) => {
      setGenerationLoading(true);
      setGenerationError(null);
      try {
        const resultatGenere = await genererPrevision({
          phase: options.phase ?? parametres.phase,
          horizon: options.horizon ?? parametres.horizon,
          testSize: options.testSize ?? 4,
          methode: options.methode ?? parametres.methode,
        });
        setResultat(resultatGenere);
        if (resultatGenere.phase && resultatGenere.phase !== parametres.phase) {
          modifieParametres({ phase: resultatGenere.phase });
        }
        return resultatGenere;
      } catch (erreur) {
        setGenerationError(erreur);
        throw erreur;
      } finally {
        setGenerationLoading(false);
      }
    },
    [parametres, modifieParametres]
  );

  return {
    referentiel,
    donnees,
    resultat,
    parametres,
    modifieParametres,
    chargerDonnees,
    loadingDonnees,
    generationLoading,
    error,
    generationError,
    lancerGeneration,
    setResultat,
  };
}