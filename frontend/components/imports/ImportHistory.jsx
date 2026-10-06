"use client";

import { Database, RefreshCw } from "lucide-react";

import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import EmptyState from "@/components/ui/EmptyState";
import Table from "@/components/ui/Table";
import { formatDateTime, formatBytes } from "@/lib/formatters";
import { courtIdentifiant, statutImportation } from "@/lib/imports";

const columns = [
  {
    key: "nom_fichier",
    header: "Fichier",
    render: (ligne) => (
      <span title={ligne.nom_fichier}>{ligne.nom_fichier}</span>
    ),
  },
  {
    key: "importe_le",
    header: "Date",
    render: (ligne) => formatDateTime(ligne.importe_le),
  },
  {
    key: "importe_par",
    header: "Importé par",
    render: (ligne) => courtIdentifiant(ligne.importe_par),
  },
  {
    key: "taille_octets",
    header: "Taille",
    render: (ligne) => formatBytes(ligne.taille_octets),
  },
  {
    key: "statut",
    header: "Statut",
    render: (ligne) => {
      const statut = statutImportation(ligne.statut);
      return (
        <Badge variant={statut.variant} dot>
          {statut.label}
        </Badge>
      );
    },
  },
  {
    key: "nb_lignes_total",
    header: "Total",
    render: (ligne) => ligne.nb_lignes_total,
  },
  {
    key: "nb_lignes_importees",
    header: "Importées",
    render: (ligne) => <strong>{ligne.nb_lignes_importees}</strong>,
  },
  {
    key: "nb_lignes_rejetees",
    header: "Rejetées",
    render: (ligne) => (
      <span className={ligne.nb_lignes_rejetees > 0 ? "text-secondary" : undefined}>
        {ligne.nb_lignes_rejetees}
      </span>
    ),
  },
  {
    key: "nb_doublons",
    header: "Doublons",
    render: (ligne) => ligne.nb_doublons,
  },
  {
    key: "id",
    header: "",
    render: (ligne) => (
      <Button
        variant="ghost"
        size="sm"
        onClick={(event) => {
          event.stopPropagation();
          ligne?.onSelection?.();
        }}
      >
        Détails
      </Button>
    ),
  },
];

export default function ImportHistory({
  importations = [],
  loading = false,
  onSelect,
  onRefresh,
  refreshLoading = false,
}) {
  const rows = importations.map((importation) => ({
    ...importation,
    onSelection: () => onSelect?.(importation),
  }));

  return (
    <section className="card report-section">
      <div className="card__header">
        <div>
          <h3 className="card__title">Historique des importations</h3>
          <p className="text-muted">
            Qui a importé, quand, quel fichier, combien de lignes ont été
            conservées ou rejetées.
          </p>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={onRefresh}
          loading={refreshLoading}
          aria-label="Actualiser"
          title="Actualiser"
        >
          <RefreshCw size={16} aria-hidden="true" />
          Actualiser
        </Button>
      </div>
      <Table
        columns={columns}
        data={rows}
        rowKey="id"
        loading={loading}
        empty={{
          icon: Database,
          title: "Aucune importation",
          description:
            "Importez un premier fichier CSV ou Excel pour voir l'historique apparaître ici.",
        }}
      />
    </section>
  );
}