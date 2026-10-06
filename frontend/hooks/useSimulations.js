"use client";

import { useCallback, useEffect, useState } from "react";

import {
  calculerSimulation,
  recupererScenariosSimulation,
} from "@/services/simulationService";

const HYPOTHESES_INITIALES = {
  budgetHypothetique: "",
  nombreDossiers: "",
  montantMoyen: "",
  ecartDossiersPct: 10,
  ecartMontantPct: 5,
};

export default function useSimulations() {
  const [referentiel, setReferentiel] = useState(null);
  const [hypotheses, setHypotheses] = useState(HYPOTHESES_INITIALES);
  const [resultat, setResultat] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    let annule = false;
    recupererScenariosSimulation()
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

  const modifieHypotheses = useCallback((patch) => {
    setHypotheses((precedentes) => ({ ...precedentes, ...patch }));
  }, []);

  const calculer = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resultatCalcule = await calculerSimulation({
        budgetHypothetique: Number(hypotheses.budgetHypothetique),
        nombreDossiers: Number(hypotheses.nombreDossiers),
        montantMoyen: Number(hypotheses.montantMoyen),
        ecartDossiersPct: Number(hypotheses.ecartDossiersPct),
        ecartMontantPct: Number(hypotheses.ecartMontantPct),
      });
      setResultat(resultatCalcule);
      return resultatCalcule;
    } catch (erreur) {
      setError(erreur);
      throw erreur;
    } finally {
      setLoading(false);
    }
  }, [hypotheses]);

  const reinitialiser = useCallback(() => {
    setHypotheses(HYPOTHESES_INITIALES);
    setResultat(null);
    setError(null);
  }, []);

  const hypothesesValides =
    Number(hypotheses.budgetHypothetique) > 0 &&
    Number(hypotheses.nombreDossiers) > 0 &&
    Number(hypotheses.montantMoyen) > 0;

  return {
    referentiel,
    hypotheses,
    modifieHypotheses,
    resultat,
    loading,
    error,
    calculer,
    reinitialiser,
    hypothesesValides,
  };
}