"use client";

import { useEffect, useState } from "react";
import { AlertCircle } from "lucide-react";

import Modal from "@/components/ui/Modal";
import Loading from "@/components/ui/Loading";
import { getApiErrorText } from "@/lib/errors";
import {
  listerBrutes,
  listerNettoyees,
  listerRejets,
} from "@/services/importService";

const MODES = {
  brutes: {
    titre: "Lignes brutes",
    description:
      "Lignes conservées telles qu'importées, sans aucune modification.",
    fetcher: listerBrutes,
  },
  nettoyees: {
    titre: "Lignes nettoyées",
    description:
      "Lignes après validation et normalisation (montants, dates, types).",
    fetcher: listerNettoyees,
  },
  rejets: {
    titre: "Lignes rejetées",
    description: "Détail complet des lignes rejetées et des motifs de rejet.",
    fetcher: listerRejets,
  },
};

function FormaterValeur({ valeur }) {
  if (valeur == null) return "—";
  return <span>{String(valeur)}</span>;
}

export default function ImportDataModal({
  open,
  onClose,
  mode,
  importationId,
}) {
  const [elements, setElements] = useState([]);
  const [loading, setLoading] = useState(false);
  const [erreur, setErreur] = useState(null);

  const config = MODES[mode] || MODES.brutes;

  useEffect(() => {
    if (!open || !mode) return undefined;

    let actif = true;
    setLoading(true);
    setErreur(null);
    setElements([]);

    const fetcher = MODES[mode]?.fetcher;
    if (!fetcher) {
      setLoading(false);
      return undefined;
    }

    fetcher(importationId)
      .then((donnees) => {
        if (actif) setElements(donnees.lignes ?? []);
      })
      .catch((errorData) => {
        if (actif) setErreur(getApiErrorText(errorData));
      })
      .finally(() => {
        if (actif) setLoading(false);
      });

    return () => {
      actif = false;
    };
  }, [open, mode, importationId]);

  if (mode === "rejets") {
    return (
      <Modal
        open={open}
        onClose={onClose}
        title={config.titre}
        description={config.description}
        size="lg"
      >
        {erreur ? (
          <div className="alert alert--error" role="alert">
            <AlertCircle size={18} className="alert__icon" aria-hidden="true" />
            <span>{erreur}</span>
          </div>
        ) : loading ? (
          <Loading label="Chargement des rejets…" />
        ) : elements.length === 0 ? (
          <p className="text-muted">Aucune ligne rejetée.</p>
        ) : (
          <div className="reject-list">
            {elements.map((rejet, index) => (
              <div
                key={`${rejet.ligne}-${rejet.colonne}-${index}`}
                className={`reject-item reject-item--${rejet.type_erreur || "type"}`}
              >
                <div>
                  <span className="reject-chip">
                    {rejet.type_erreur || "erreur"}
                  </span>
                  <div className="reject-item__col">
                    Ligne {rejet.ligne} · {rejet.colonne}
                  </div>
                </div>
                <div className="reject-item__value">{rejet.valeur}</div>
                <div className="reject-item__reason">{rejet.raison}</div>
              </div>
            ))}
          </div>
        )}
      </Modal>
    );
  }

  const cles = [];
  for (const element of elements) {
    for (const cle of Object.keys(element?.valeurs ?? {})) {
      if (!cles.includes(cle)) cles.push(cle);
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={config.titre}
      description={config.description}
      size="lg"
    >
      {erreur ? (
        <div className="alert alert--error" role="alert">
          <AlertCircle size={18} className="alert__icon" aria-hidden="true" />
          <span>{erreur}</span>
        </div>
      ) : loading ? (
        <Loading label="Chargement des lignes…" />
      ) : elements.length === 0 ? (
        <p className="text-muted">Aucune ligne disponible.</p>
      ) : (
        <div className="lines-table">
          <table>
            <thead>
              <tr>
                <th>N°</th>
                {cles.map((cle) => (
                  <th key={cle}>{cle}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {elements.map((element) => (
                <tr key={element.ligne}>
                  <td>{element.ligne}</td>
                  {cles.map((cle) => {
                    const manquante = element.manquantes?.includes(cle);
                    return (
                      <td
                        key={cle}
                        className={manquante ? "lines-table__missing" : undefined}
                      >
                        <FormaterValeur valeur={element.valeurs?.[cle]} />
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Modal>
  );
}