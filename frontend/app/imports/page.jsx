"use client";

import { useCallback, useState } from "react";

import ImportHistory from "@/components/imports/ImportHistory";
import ImportReport from "@/components/imports/ImportReport";
import ImportUpload from "@/components/imports/ImportUpload";
import PermissionsGate from "@/components/auth/PermissionsGate";
import PageContainer from "@/components/layout/PageContainer";
import useImports from "@/hooks/useImports";
import { detailImportation } from "@/services/importService";

export default function ImportsPage() {
  const { importations, loading, error, recharger } = useImports();
  const [detail, setDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const selectionner = useCallback(async (importation) => {
    if (!importation) return;
    setDetailLoading(true);
    try {
      const donnees = await detailImportation(importation.id);
      setDetail(donnees);
    } catch {
      setDetail(importation);
    } finally {
      setDetailLoading(false);
    }
  }, []);

  const apresImport = useCallback(
    async (resultat) => {
      await recharger();
      selectionner(resultat);
    },
    [recharger, selectionner]
  );

  return (
    <PageContainer
      title="Importation de données"
      subtitle="Importez les fichiers de données RFM (CSV ou Excel). Elles sont validées, normalisées et conservées sans jamais altérer le fichier d'origine."
    >
      <div className="import-stack">
        {error && !loading && (
          <div className="alert alert--error" role="alert">
            <span>
              Impossible de charger l'historique des importations :{" "}
              {error?.message || "erreur inconnue"}
            </span>
          </div>
        )}

        <PermissionsGate permission="importation:importer">
          <ImportUpload onImported={apresImport} />
        </PermissionsGate>

        {detailLoading && <div className="text-muted">Chargement du rapport…</div>}
        {detail && !detailLoading && <ImportReport importation={detail} />}

        <ImportHistory
          importations={importations}
          loading={loading}
          onSelect={selectionner}
          onRefresh={recharger}
          refreshLoading={loading}
        />
      </div>
    </PageContainer>
  );
}