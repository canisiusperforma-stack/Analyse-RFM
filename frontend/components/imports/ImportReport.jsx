"use client";

import { useState } from "react";
import {
  CheckCircle2,
  Database,
  Download,
  Eye,
  FileSearch,
  Filter,
} from "lucide-react";

import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import ImportDataModal from "@/components/imports/ImportDataModal";
import TypeChip from "@/components/imports/TypeChip";
import { getApiErrorText } from "@/lib/errors";
import {
  formatBytes,
  formatDateTime,
} from "@/lib/formatters";
import { courtIdentifiant, statutImportation, telechargerBlob, typeErreurLabel } from "@/lib/imports";
import { telechargerFichierOriginal } from "@/services/importService";

export default function ImportReport({ importation }) {
  const [modal, setModal] = useState(null);
  const [telechargement, setTelechargement] = useState(false);
  const [erreur, setErreur] = useState(null);

  const rapport = importation?.rapport || {};
  const statut = statutImportation(importation?.statut);
  const rejets = rapport.rejets || [];
  const colonnes = rapport.colonnes || [];

  const telechargerFichier = async () => {
    setTelechargement(true);
    setErreur(null);
    try {
      const blob = await telechargerFichierOriginal(importation.id);
      telechargerBlob(blob, importation.nom_fichier || "fichier");
    } catch (errorData) {
      setErreur(getApiErrorText(errorData));
    } finally {
      setTelechargement(false);
    }
  };

  return (
    <div className="import-stack">
      {erreur && (
        <div className="alert alert--error" role="alert">
          <span>{erreur}</span>
        </div>
      )}

      <section className="card report-section" style={{ padding: 20 }}>
        <div className="card__header" style={{ padding: 0, borderBottom: "none" }}>
          <div>
            <h3 className="card__title">{importation.nom_fichier}</h3>
            <p className="text-muted">
              Importée le {formatDateTime(importation.importe_le)}
              {importation.importe_par
                ? ` par ${courtIdentifiant(importation.importe_par)}`
                : ""}
            </p>
          </div>
          <Badge variant={statut.variant} dot>
            {statut.label}
          </Badge>
        </div>

        <div className="stats-grid">
          <div className="stat-card">
            <span className="stat-card__value">{rapport.nb_lignes_total ?? "—"}</span>
            <span className="stat-card__label">Lignes totales</span>
          </div>
          <div className="stat-card stat-card--success">
            <span className="stat-card__value">
              {rapport.nb_lignes_importees ?? "—"}
            </span>
            <span className="stat-card__label">Importées</span>
          </div>
          <div className="stat-card stat-card--danger">
            <span className="stat-card__value">
              {rapport.nb_lignes_rejetees ?? "—"}
            </span>
            <span className="stat-card__label">Rejetées</span>
          </div>
          <div className="stat-card stat-card--warning">
            <span className="stat-card__value">{rapport.nb_doublons ?? "—"}</span>
            <span className="stat-card__label">Doublons</span>
          </div>
        </div>

        {rapport.deversement?.active && (
          <div
            className="alert alert--success"
            role="status"
            style={{ marginTop: 16 }}
          >
            <CheckCircle2 size={18} className="alert__icon" aria-hidden="true" />
            <span>
              Déversement : {rapport.deversement.insere ?? 0} ligne(s) insérée(s),{" "}
              {rapport.deversement.mise_a_jour ?? 0} mise(s) à jour et{" "}
              {rapport.deversement.rejetees ?? 0} rejetée(s) dans les collections
              métier ({rapport.deversement.nb_feuilles ?? 0} feuille(s)).
            </span>
          </div>
        )}

        {(rapport.feuilles?.length ?? 0) > 1 && (
          <div className="meta-list" style={{ marginTop: 4 }}>
            <div className="meta-list__item">
              <span className="meta-list__label">Onglets traités</span>
              <div className="table-wrap" style={{ width: "100%" }}>
                <table className="table">
                  <thead>
                    <tr>
                      <th>Onglet</th>
                      <th>Collection</th>
                      <th>Totales</th>
                      <th>Importées</th>
                      <th>Rejetées</th>
                      <th>Déversées</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rapport.feuilles.map((feuille) => (
                      <tr key={`${feuille.index}-${feuille.titre}`}>
                        <td>{feuille.titre}</td>
                        <td style={{ fontFamily: "var(--font-mono)" }}>
                          {feuille.collection || "—"}
                        </td>
                        <td>{feuille.nb_lignes_total ?? "—"}</td>
                        <td>{feuille.nb_lignes_importees ?? "—"}</td>
                        <td>{feuille.nb_lignes_rejetees ?? "—"}</td>
                        <td>{feuille.nb_deversees ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        <div className="meta-list">
          <div className="meta-list__item">
            <span className="meta-list__label">Format</span>
            <span className="meta-list__value">
              {(rapport.format || importation.type_mime || "—").toUpperCase()}
            </span>
          </div>
          <div className="meta-list__item">
            <span className="meta-list__label">Encodage</span>
            <span className="meta-list__value">{rapport.encodage || "—"}</span>
          </div>
          <div className="meta-list__item">
            <span className="meta-list__label">Séparateur</span>
            <span className="meta-list__value">
              {rapport.delimiteur === "\t"
                ? "Tabulation"
                : (rapport.delimiteur || "—")}
            </span>
          </div>
          <div className="meta-list__item">
            <span className="meta-list__label">Taille</span>
            <span className="meta-list__value">
              {formatBytes(importation.taille_octets ?? rapport.taille_octets)}
            </span>
          </div>
          <div className="meta-list__item">
            <span className="meta-list__label">Colonnes</span>
            <span className="meta-list__value">{rapport.nb_colonnes ?? "—"}</span>
          </div>
          <div className="meta-list__item">
            <span className="meta-list__label">Empreinte SHA-256</span>
            <span className="meta-list__value" style={{ fontFamily: "var(--font-mono)" }}>
              {importation.sha256 || rapport.sha256 || "—"}
            </span>
          </div>
        </div>

        <div className="page-header__actions">
          <Button
            variant="secondary"
            size="sm"
            onClick={telechargerFichier}
            loading={telechargement}
          >
            <Download size={16} aria-hidden="true" />
            Fichier original
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setModal("brutes")}
          >
            <Database size={16} aria-hidden="true" />
            Lignes brutes
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setModal("nettoyees")}
          >
            <Eye size={16} aria-hidden="true" />
            Lignes nettoyées
          </Button>
          {(rapport.nb_lignes_rejetees ?? 0) > 0 && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => setModal("rejets")}
            >
              <Filter size={16} aria-hidden="true" />
              Rejets ({rapport.nb_lignes_rejetees})
            </Button>
          )}
        </div>
      </section>

      {importation.statut === "echec" && (
        <div className="alert alert--error" role="alert">
          <span>
            {importation.erreur || "L'importation a échoué en cours de traitement."}
          </span>
        </div>
      )}

      <section className="card report-section">
        <div className="card__header">
          <div>
            <h3 className="card__title">Détection des colonnes</h3>
            <p className="text-muted">
              Types inférés, remplissage et valeurs invalides par colonne.
            </p>
          </div>
        </div>
        <div className="card__body" style={{ paddingTop: 0 }}>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Nom original</th>
                  <th>Nom normalisé</th>
                  <th>Type</th>
                  <th>Vides</th>
                  <th>Non vides</th>
                  <th>Invalides</th>
                  <th>Exemples</th>
                </tr>
              </thead>
              <tbody>
                {colonnes.map((colonne) => (
                  <tr key={colonne.nom_normalise}>
                    <td>{colonne.nom_original}</td>
                    <td style={{ fontFamily: "var(--font-mono)" }}>
                      {colonne.nom_normalise}
                    </td>
                    <td>
                      <TypeChip type={colonne.type_detecte} />
                    </td>
                    <td>{colonne.nb_vides}</td>
                    <td>{colonne.nb_non_vides}</td>
                    <td>{colonne.nb_invalides}</td>
                    <td className="text-muted">
                      {(colonne.exemples || []).slice(0, 2).join(" · ") || "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {(rapport.nb_lignes_rejetees ?? 0) > 0 && (
        <section className="card report-section">
          <div className="card__header">
            <div>
              <h3 className="card__title">Motifs de rejet</h3>
              <p className="text-muted">
                {rapport.nb_lignes_rejetees} ligne(s) rejetée(s) — les fichiers
                originaux restent intacts.
              </p>
            </div>
            <FileSearch size={18} className="text-muted" aria-hidden="true" />
          </div>
          <div className="card__body" style={{ paddingTop: 0 }}>
            <div className="reject-list">
              {rejets.slice(0, 30).map((rejet, index) => (
                <div
                  key={`${rejet.ligne}-${rejet.colonne}-${index}`}
                  className={`reject-item reject-item--${rejet.type_erreur || "type"}`}
                >
                  <div>
                    <span className="reject-chip">
                      {typeErreurLabel(rejet.type_erreur)}
                    </span>
                    <div className="reject-item__col">
                      Ligne {rejet.ligne}
                    </div>
                  </div>
                  <div className="reject-item__col">{rejet.colonne}</div>
                  <div className="reject-item__value">{rejet.valeur}</div>
                  <div className="reject-item__reason">{rejet.raison}</div>
                </div>
              ))}
            </div>
          </div>
        </section>
      )}

      <ImportDataModal
        open={Boolean(modal)}
        onClose={() => setModal(null)}
        mode={modal}
        importationId={importation.id}
      />
    </div>
  );
}