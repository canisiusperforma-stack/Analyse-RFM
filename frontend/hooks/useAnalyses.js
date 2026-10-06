"use client";

import { useCallback, useEffect, useState } from "react";

import {
  recupererAnalyseTemporelle,
  recupererExercicesAnalyses,
} from "@/services/analyseService";

export default function useAnalyses() {
  const [exercices, setExercices] = useState([]);
  const [exercice, setExercice] = useState(null);
  const [donnees, setDonnees] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const recharger = useCallback(() => {
    if (exercice == null) return;
    setLoading(true);
    setError(null);
    recupererAnalyseTemporelle(exercice)
      .then(setDonnees)
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
    donnees,
    loading,
    error,
    recharger,
  };
}