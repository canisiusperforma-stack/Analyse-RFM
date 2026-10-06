"use client";

import { useCallback, useEffect, useState } from "react";

import {
  recupererExercices,
  recupererSynthese,
} from "@/services/dashboardService";

export default function useDashboard() {
  const [exercices, setExercices] = useState([]);
  const [exercice, setExercice] = useState(null);
  const [synthese, setSynthese] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const recharger = useCallback(async (exerciceCible) => {
    if (exerciceCible == null) return;
    setLoading(true);
    setError(null);
    try {
      const donnees = await recupererSynthese(exerciceCible);
      setSynthese(donnees);
    } catch (erreur) {
      setError(erreur);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let annule = false;
    (async () => {
      try {
        const disponibles = await recupererExercices();
        if (annule) return;
        setExercices(disponibles);
        setExercice(disponibles[0] ?? null);
      } catch (erreur) {
        if (!annule) setError(erreur);
      }
    })();
    return () => {
      annule = true;
    };
  }, []);

  useEffect(() => {
    recharger(exercice);
  }, [exercice, recharger]);

  return {
    exercices,
    exercice,
    setExercice,
    synthese,
    loading,
    error,
    recharger,
  };
}