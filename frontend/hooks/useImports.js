"use client";

import { useCallback, useEffect, useState } from "react";

import { listerImportations } from "@/services/importService";

export default function useImports() {
  const [importations, setImportations] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const recharger = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const donnees = await listerImportations();
      setImportations(donnees.importations ?? []);
    } catch (erreur) {
      setError(erreur);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    recharger();
  }, [recharger]);

  return { importations, loading, error, recharger, setImportations };
}