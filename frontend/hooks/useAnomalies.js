"use client";

import { useCallback, useEffect, useState } from "react";

import {
  lancerDetectionAnomalies,
  recupererAnomalies,
  recupererExercicesAnomalies,
  recupererReferentielAnomalies,
} from "@/services/anomalieService";

const FILTRES_INITIAUX = {
  recherche: "",
  statut_verification: "",
  niveau: "",
  methode: "",
  variable: "",
  tri: "detecte_le",
  ordre: "desc",
};

export default function useAnomalies() {
  const [exercices, setExercices] = useState([]);
  const [exercice, setExercice] = useState(null);
  const [referentiel, setReferentiel] = useState(null);
  const [liste, setListe] = useState(null);
  const [filtres, setFiltres] = useState(FILTRES_INITIAUX);
  const [saut, setSaut] = useState(0);
  const [limite, setLimite] = useState(25);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const [detection, setDetection] = useState(null);
  const [detectionLoading, setDetectionLoading] = useState(false);
  const [detectionError, setDetectionError] = useState(null);

  const modifieFiltres = useCallback((patch) => {
    setFiltres((precedents) => ({ ...precedents, ...patch }));
    setSaut(0);
  }, []);

  const reinitialiserFiltres = useCallback(() => {
    setFiltres(FILTRES_INITIAUX);
    setSaut(0);
  }, []);

  const recharger = useCallback(() => {
    setLoading(true);
    setError(null);
    recupererAnomalies({
      exercice,
      ...filtres,
      limite,
      saut,
    })
      .then(setListe)
      .catch(setError)
      .finally(() => setLoading(false));
  }, [exercice, filtres, limite, saut]);

  useEffect(() => {
    let annule = false;
    (async () => {
      try {
        const [exercicesDisponibles, referentielData] = await Promise.all([
          recupererExercicesAnomalies(),
          recupererReferentielAnomalies(),
        ]);
        if (annule) return;
        setExercices(exercicesDisponibles);
        setReferentiel(referentielData);
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

  const lancerDetection = useCallback(
    async (options = {}) => {
      setDetectionLoading(true);
      setDetectionError(null);
      try {
        const resultat = await lancerDetectionAnomalies({
          exercice: options.exercice ?? exercice ?? undefined,
          stocker: true,
        });
        setDetection(resultat);
        if (resultat.exercice != null) {
          setExercices((disponibles) =>
            disponibles.includes(resultat.exercice)
              ? disponibles
              : [...disponibles, resultat.exercice].sort((a, b) => b - a)
          );
          setExercice(resultat.exercice);
        }
        recharger();
        return resultat;
      } catch (erreur) {
        setDetectionError(erreur);
        throw erreur;
      } finally {
        setDetectionLoading(false);
      }
    },
    [exercice, recharger]
  );

  const fermerDetection = useCallback(() => {
    setDetection(null);
    setDetectionError(null);
  }, []);

  return {
    exercices,
    exercice,
    setExercice,
    referentiel,
    liste,
    setListe,
    filtres,
    modifieFiltres,
    reinitialiserFiltres,
    saut,
    setSaut,
    limite,
    setLimite,
    loading,
    error,
    recharger,
    detection,
    detectionLoading,
    detectionError,
    lancerDetection,
    fermerDetection,
  };
}