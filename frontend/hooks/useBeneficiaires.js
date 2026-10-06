"use client";

import { useCallback, useEffect, useState } from "react";

import {
  recupererBeneficiaires,
  recupererExercices,
  recupererStatistiques,
} from "@/services/beneficiairesService";

const FILTRES_INITIAUX = {
  recherche: "",
  situation: "",
  rfm: "",
  tri: "nom",
  ordre: "asc",
};

export default function useBeneficiaires() {
  const [exercices, setExercices] = useState([]);
  const [exercice, setExercice] = useState(null);
  const [statistiques, setStatistiques] = useState(null);
  const [liste, setListe] = useState(null);
  const [filtres, setFiltres] = useState(FILTRES_INITIAUX);
  const [saut, setSaut] = useState(0);
  const [limite, setLimite] = useState(25);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const modifieFiltres = useCallback((patch) => {
    setFiltres((precedents) => ({ ...precedents, ...patch }));
    setSaut(0);
  }, []);

  const reinitialiserFiltres = useCallback(() => {
    setFiltres(FILTRES_INITIAUX);
    setSaut(0);
  }, []);

  const recharger = useCallback(
    () => {
      if (exercice == null) return;
      setLoading(true);
      setError(null);
      Promise.all([
        recupererStatistiques(exercice),
        recupererBeneficiaires({ exercice, ...filtres, limite, saut }),
      ])
        .then(([stats, lignes]) => {
          setStatistiques(stats);
          setListe(lignes);
        })
        .catch((erreur) => setError(erreur))
        .finally(() => setLoading(false));
    },
    [exercice, filtres, limite, saut]
  );

  useEffect(() => {
    let annule = false;
    (async () => {
      try {
        const disponibles = await recupererExercices();
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
    statistiques,
    liste,
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
  };
}