"use client";

import {
  Activity,
  Bot,
  Database,
  FileSearch,
  RefreshCw,
  ServerCog,
} from "lucide-react";

import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import { usePermissions } from "@/hooks/usePermissions";
import { formatDateTime, formatNumber } from "@/lib/formatters";
import { getApiErrorText } from "@/lib/errors";

/**
 * État de la plateforme.
 *
 * Trois sondes, trois questions distinctes : l'API répond-elle, la base est-elle
 * là, la recherche documentaire est-elle active. La troisième n'est interrogée
 * que si l'appelant a `documents:voir` — son absence vaut « inconnu », pas
 * « cassé », et l'écran ne comble pas le trou par une supposition.
 *
 * Le mode dégradé mérite son cas : FastAPI démarre même quand MongoDB est
 * injoignable. L'API répond alors 200 sur `/api/sante` et échoue sur tout le
 * reste. Afficher « opérationnel » sur la seule foi de l'API disponible
 * envoyerait l'administrateur chercher une panne de données qui est en réalité
 * une panne de base.
 */
export default function EtatPlateforme({ sante, santeErreur, referentiel, loading, onVerifier }) {
  const { has } = usePermissions();
  const litDocuments = has("documents:voir");

  const apiOk = sante != null;
  const mongoOk = apiOk && sante.mongodb === "ok";

  const sondes = [
    {
      cle: "api",
      label: "API",
      Icone: ServerCog,
      ok: apiOk,
      valeur: apiOk ? "Opérationnelle" : "Injoignable",
      detail: apiOk
        ? `Version ${sante.version ?? "—"} · ${sante.environnement ?? "—"}`
        : santeErreur
          ? getApiErrorText(santeErreur)
          : "Aucune réponse",
    },
    {
      cle: "mongodb",
      label: "Base de données",
      Icone: Database,
      ok: mongoOk,
      valeur: !apiOk
        ? "Inconnue"
        : mongoOk
          ? "Connectée"
          : "Injoignable",
      detail: mongoOk
        ? "Collectionnel et index opérationnels."
        : apiOk
          ? sante.detail
            ? String(sante.detail)
            : "L'API répond en mode dégradé : toutes les routes métier échoueront."
          : "Vérifiable seulement si l'API répond.",
    },
    {
      cle: "rag",
      label: "Recherche documentaire",
      Icone: FileSearch,
      ok: referentiel?.actif === true,
      valeur: !litDocuments
        ? "Non consultable"
        : referentiel?.actif === true
          ? "Active"
          : referentiel
            ? "Désactivée"
            : "Inconnue",
      detail: !litDocuments
        ? "Votre rôle ne permet pas d'interroger le pipeline documentaire."
        : referentiel?.actif === true
          ? `${formatNumber(referentiel?.morceaux_accessibles ?? 0)} extrait(s) accessible(s) · seuil ${referentiel?.seuil_pertinence ?? "—"}`
          : referentiel
            ? "RAG désactivé par la configuration : l'assistant ne répondra que par des extraits, sans modèle."
            : "Périmètre indisponible.",
    },
  ];

  return (
    <section className="card" id="plateforme">
      <div className="card__header">
        <span className="conv-section__icon">
          <Activity size={18} />
        </span>
        <div>
          <h3 className="card__title">État de la plateforme</h3>
          <p className="text-muted">
            Sonde déclarée par l&apos;API elle-même, sans permission requise —
            elle reste donc joignable même quand plus rien d&apos;autre ne
            répond.
          </p>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={onVerifier}
          loading={loading}
          aria-label="Revérifier l'état de la plateforme"
        >
          {!loading && <RefreshCw size={16} aria-hidden="true" />}
          Revérifier
        </Button>
      </div>

      <div className="card__body">
        <div className="admin-sondes">
          {sondes.map(({ cle, label, Icone, ok, valeur, detail }) => (
            <div
              key={cle}
              className={`admin-sonde admin-sonde--${ok ? "ok" : "hs"}`}
            >
              <span className="admin-sonde__icone" aria-hidden="true">
                <Icone size={16} />
              </span>
              <div className="admin-sonde__corps">
                <div className="admin-sonde__entete">
                  <span className="admin-sonde__label">{label}</span>
                  <Badge variant={ok ? "success" : "danger"} dot>
                    {valeur}
                  </Badge>
                </div>
                <p className="admin-sonde__detail">{detail}</p>
              </div>
            </div>
          ))}
        </div>

        {sante?.horodatage && (
          <p className="text-muted admin-sonde__horodatage">
            <Bot size={13} aria-hidden="true" /> Sonde du{" "}
            {formatDateTime(sante.horodatage)}.
          </p>
        )}
      </div>
    </section>
  );
}
