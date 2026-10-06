"use client";

import { useEffect, useState } from "react";
import { Check, ShieldCheck } from "lucide-react";

import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import Modal from "@/components/ui/Modal";
import Select from "@/components/ui/Select";
import { formaterValeurAlerte } from "@/components/anomalies/AnomalieTable";
import {
  METHODE_LABELS,
  NIVEAU_VARIANTS,
  STATUTS_VERIFICATION,
} from "@/lib/anomalies";
import { getApiErrorText } from "@/lib/errors";
import {
  formatDate,
  formatDateTime,
  formatScore,
} from "@/lib/formatters";
import { mettreAJourVerificationAnomalie } from "@/services/anomalieService";

const STATUT_OPTIONS = Object.entries(STATUTS_VERIFICATION).map(
  ([value, label]) => ({ value, label })
);

function Champ({ label, children }) {
  return (
    <div className="field" style={{ marginBottom: 12 }}>
      <span className="field__label">{label}</span>
      <span style={{ color: "var(--color-text)" }}>{children}</span>
    </div>
  );
}

export default function AnomalieDetailModal({
  anomalie,
  onClose,
  canTraiter,
  onStatutChange,
}) {
  const [statut, setStatut] = useState(anomalie?.statut_verification ?? "a_verifier");
  const [commentaire, setCommentaire] = useState(anomalie?.commentaire ?? "");
  const [saving, setSaving] = useState(false);
  const [erreur, setErreur] = useState(null);
  const [succes, setSucces] = useState(false);

  useEffect(() => {
    setStatut(anomalie?.statut_verification ?? "a_verifier");
    setCommentaire(anomalie?.commentaire ?? "");
    setErreur(null);
    setSucces(false);
  }, [anomalie]);

  if (!anomalie) return null;

  const parMethode = anomalie.par_methode || [];
  const beneficiaire = anomalie.beneficiaire || {};
  const nomBeneficiaire =
    [beneficiaire.prenom, beneficiaire.nom].filter(Boolean).join(" ") || "—";

  const enregistrer = async () => {
    setSaving(true);
    setErreur(null);
    setSucces(false);
    try {
      const miseAJour = await mettreAJourVerificationAnomalie(anomalie.id, {
        statutVerification: statut,
        commentaire,
      });
      setSucces(true);
      onStatutChange?.(miseAJour);
    } catch (e) {
      setErreur(e);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      open
      onClose={onClose}
      size="lg"
      title={`Observation atypique — ${anomalie.numero_dossier || "dossier inconnu"}`}
      description={nomBeneficiaire}
    >
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
          gap: "4px 16px",
          marginBottom: 16,
        }}
      >
        <Champ label="Bénéficiaire">
          {nomBeneficiaire}
          {beneficiaire.matricule ? ` (${beneficiaire.matricule})` : ""}
        </Champ>
        <Champ label="Prestation">{anomalie.type_prestation || "—"}</Champ>
        <Champ label="Statut du remboursement">
          {anomalie.statut_remboursement || "—"}
        </Champ>
        <Champ label="Date de la demande">
          {formatDate(anomalie.date_demande)}
        </Champ>
        <Champ label="Exercice">
          {anomalie.exercice != null ? anomalie.exercice : "—"}
        </Champ>
        <Champ label="Détecté le">{formatDateTime(anomalie.detecte_le)}</Champ>
      </div>

      <Champ label="Valeur">
        <strong style={{ fontWeight: 700 }}>
          {anomalie.libelle_variable} : {formaterValeurAlerte(anomalie)}
        </strong>
      </Champ>

      <div className="card card__padding" style={{ marginBottom: 16 }}>
        <h3 className="chart-card__title">Niveau d'alerte</h3>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <Badge variant={NIVEAU_VARIANTS[anomalie.niveau] || "neutral"} dot>
            {anomalie.label_niveau}
          </Badge>
          <span className="tableau__sous-texte">
            signalé par {anomalie.nombre_methodes} méthode(s) indépendante(s)
          </span>
        </div>
        <p
          className="chart-card__subtitle"
          style={{ marginTop: 12, whiteSpace: "pre-wrap" }}
        >
          {anomalie.justification}
        </p>
      </div>

      <div className="card card__padding" style={{ marginBottom: 16 }}>
        <h3 className="chart-card__title">Comparaison des méthodes</h3>
        <div className="tableau tableau--scroll">
          <table className="tableau__table">
            <thead>
              <tr>
                <th>Méthode</th>
                <th>Score</th>
                <th>Conclusion</th>
              </tr>
            </thead>
            <tbody>
              {parMethode.length === 0 && (
                <tr>
                  <td colSpan={3} className="tableau__sous-texte">
                    Aucun détail par méthode disponible.
                  </td>
                </tr>
              )}
              {parMethode.map((detail) => (
                <tr key={detail.methode}>
                  <td className="tableau__nom">
                    {detail.label || METHODE_LABELS[detail.methode] || detail.methode}
                  </td>
                  <td className="tableau__montant">
                    {formatScore(detail.score)}
                  </td>
                  <td>
                    <p
                      style={{
                        margin: 0,
                        fontSize: 12.5,
                        color: "var(--color-text-secondary)",
                      }}
                    >
                      {detail.justification}
                    </p>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card card__padding">
        <h3 className="chart-card__title">Vérification humaine</h3>
        <p className="chart-card__subtitle">
          Une observation signalée n'est pas automatiquement une fraude : elle
          fait l'objet d'une vérification tracée par un humain.
        </p>
        <div style={{ width: 280, maxWidth: "100%" }}>
          <Select
            label="Statut de vérification"
            value={statut}
            onChange={(evenement) => setStatut(evenement.target.value)}
            options={STATUT_OPTIONS}
            disabled={!canTraiter}
          />
        </div>
        <div className="field">
          <label className="field__label" htmlFor="commentaire-verification">
            Commentaire
          </label>
          <textarea
            id="commentaire-verification"
            className="input"
            rows={3}
            style={{ height: "auto", minHeight: 84, resize: "vertical" }}
            placeholder="Conclusion de la vérification…"
            value={commentaire}
            onChange={(evenement) => setCommentaire(evenement.target.value)}
            disabled={!canTraiter}
          />
        </div>

        {erreur && (
          <p className="field__error">{getApiErrorText(erreur)}</p>
        )}

        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <Button
            onClick={enregistrer}
            loading={saving}
            disabled={!canTraiter || saving}
          >
            <Check size={15} />
            Enregistrer la vérification
          </Button>
          {succes && (
            <Badge variant="success" dot>
              Vérification enregistrée
            </Badge>
          )}
        </div>

        {anomalie.traite_le && (
          <p className="chart-card__subtitle" style={{ marginTop: 12 }}>
            <ShieldCheck size={13} style={{ verticalAlign: "-2px" }} /> Dernière
            mise à jour le {formatDateTime(anomalie.traite_le)} — statut :{" "}
            {anomalie.label_statut_verification}
          </p>
        )}
      </div>
    </Modal>
  );
}