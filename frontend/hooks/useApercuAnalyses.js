"use client";

import { useCallback, useEffect, useState } from "react";

import {
  recupererAnalyseTemporelle,
  recupererExercicesAnalyses,
  recupererStatistiquesAnalyse,
} from "@/services/analyseService";

/**
 * Charge en une seule requête d'API les deux modules d'analyse descriptive
 * (évolution mensuelle et statistiques) pour un même exercice.
 *
 * La page « Analyses » n'a besoin que d'un aperçu : regrouper les deux appels
 * évite d'exposer deux sélecteurs d'exercice désynchronisés.
 */
export default function useApercuAnalyses() {
  const [exercices, setExercices] = useState([]);
  const [exercice, setExercice] = useState(null);
  const [temporelle, setTemporelle] = useState(null);
  const [statistiques, setStatistiques] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const recharger = useCallback(() => {
    if (exercice == null) return;
    setLoading(true);
    setError(null);
    Promise.all([
      recupererAnalyseTemporelle(exercice),
      recupererStatistiquesAnalyse(exercice),
    ])
      .then(([donneesTemporelle, donneesStatistiques]) => {
        setTemporelle(donneesTemporelle);
        setStatistiques(donneesStatistiques);
      })
      .catch(setError)
      .finally(() => setLoading(false));
  }, [exercice]);

  useEffect(() => {
    let annule = false;
    (async () => {
      try {
        const disponibles = await recupererExercicesAnalyses();
        if (annule) return;
        setExercices(disponibles);
        setExercice((precedent) => {
          if (precedent != null && disponibles.includes(precedent)) {
            return precedent;
          }
          return disponibles[0] ?? null;
        });
      } catch (erreur) {
        if (!annule) setError(erreur);
      }
    })();
    return () => {
      annule = true;
    };
  }, []);

  useEffect(() => {
    recharger();
  }, [recharger]);

  return {
    exercices,
    exercice,
    setExercice,
    temporelle,
    statistiques,
    loading,
    error,
    recharger,
  };
}
