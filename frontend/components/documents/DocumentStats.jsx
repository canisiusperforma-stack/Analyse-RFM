"use client";

import { useMemo } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  FileStack,
  FolderOpen,
  Search,
  ShieldAlert,
} from "lucide-react";

import StatCard from "@/components/dashboard/StatCard";
import Badge from "@/components/ui/Badge";
import { formatNumber } from "@/lib/formatters";
import { libellesFormats } from "@/lib/documents";

/**
 * État de la base documentaire.
 *
 * Les compteurs affichés sont ceux de `/documents/statistiques`, déjà restreints
 * aux documents accessibles à l'appelant : aucun total brut n'est présenté, car
 * il révélerait l'existence de documents que l'utilisateur n'a pas le droit
 * de lire.
 *
 * L'indexation et le RAG sont deux choses distinctes, et l'interface le dit.
 * Un document `en attente` sur une base active signifie « pas encore
 * réindexé » ; sur une base désactivée, il signifie « l'extraction est
 * suspendue ». Présenter le même badge dans les deux cas ferait croire à une
 * anomalie là où il n'y a qu'une configuration.
 */
export default function DocumentStats({ statistiques, referentiel, compte }) {
  const formats = useMemo(
    () => libellesFormats(referentiel?.formats_autorises),
    [referentiel]
  );

  const actif = referentiel?.actif === true;
  const enAttente = Math.max(
    0,
    (statistiques?.documents_visibles ?? compte.total) -
      (statistiques?.documents_indexes ?? compte.indexes) -
      compte.echecs
  );

  return (
    <section className="conv-section">
      <div className="conv-section__header">
        <span className="conv-section__icon">
          <FolderOpen size={18} />
        </span>
        <div>
          <h2 className="conv-section__title">État de la base</h2>
          <p className="conv-section__subtitle">
            Volumétrie calculée sur les seuls documents que vous êtes autorisé à
            consulter. Formats acceptés&nbsp;: {formats}.
          </p>
        </div>
      </div>

      {!actif && (
        <div className="notice" role="status">
          <AlertTriangle size={16} aria-hidden="true" />
          <span>
            La recherche documentaire est <strong>désactivée</strong>{" "}
            (<code>RAG_ENABLED=false</code>). Le dépôt, la consultation, la
            reclassification et la suppression restent disponibles — ce sont des
            opérations sur des métadonnées — mais aucun texte n&apos;est
            découpé, vectorisé ni transmis à un modèle. L&apos;indexation et la
            recherche renverront une erreur d&apos;indisponibilité.
          </span>
        </div>
      )}

      <div className="stats-grid">
        <StatCard
          icon={FolderOpen}
          label="Documents accessibles"
          value={formatNumber(statistiques?.documents_visibles ?? compte.total)}
          sub="base documentaire"
        />
        <StatCard
          icon={CheckCircle2}
          label="Indexés"
          value={formatNumber(statistiques?.documents_indexes ?? compte.indexes)}
          sub="interrogeables par l'assistant"
          variant={actif ? "success" : "default"}
        />
        <StatCard
          icon={FileStack}
          label="Extraits accessibles"
          value={formatNumber(statistiques?.morceaux_visibles ?? compte.total)}
          sub="morceaux vectorisés"
          variant={actif ? "info" : "default"}
        />
        <StatCard
          icon={Search}
          label="Recherche documentaire"
          value={actif ? "Active" : "Désactivée"}
          sub={
            actif
              ? `seuil de pertinence ${referentiel?.seuil_pertinence ?? "—"}`
              : "aucun texte indexé"
          }
          variant={actif ? "success" : "warning"}
        />
        <StatCard
          icon={ShieldAlert}
          label="Documents classés"
          value={formatNumber(compte.classes)}
          sub="restreints ou confidentiels"
          variant={compte.classes > 0 ? "warning" : "default"}
        />
        <StatCard
          icon={AlertTriangle}
          label="Échecs d'extraction"
          value={formatNumber(compte.echecs)}
          sub={
            enAttente > 0
              ? `${formatNumber(enAttente)} en attente d'indexation`
              : "aucun en attente"
          }
          variant={compte.echecs > 0 ? "danger" : "default"}
        />
      </div>

      {compte.echecs > 0 && (
        <p className="text-muted">
          Un document dont l&apos;extraction échoue reste déposé, consultable et
          supprimable&nbsp;: seul l&apos;interrogation par l&apos;assistant lui
          est refusée. Le motif figure dans sa fiche.
        </p>
      )}

      {!actif && (
        <Badge variant="warning" dot>
          Canal documentaire suspendu
        </Badge>
      )}
    </section>
  );
}
