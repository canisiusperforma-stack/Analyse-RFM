"use client";

import { useMemo, useState } from "react";
import {
  Eye,
  FolderOpen,
  RefreshCw,
  Search,
  Trash2,
} from "lucide-react";

import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import Table from "@/components/ui/Table";
import { usePermissions } from "@/hooks/usePermissions";
import { iconeDocument, niveauConfidentialite, statutIndexation } from "@/lib/documents";
import { formatBytes, formatDateTime, formatNumber } from "@/lib/formatters";
import { courtIdentifiant } from "@/lib/imports";

/** Filtres appliqués côté affichage, pas côté serveur. */
const FILTRES = [
  { valeur: "tous", libelle: "Tous" },
  { valeur: "indexe", libelle: "Indexés" },
  { valeur: "en_attente", libelle: "En attente" },
  { valeur: "echec", libelle: "Échecs" },
  { valeur: "classes", libelle: "Classés" },
];

/**
 * Liste des documents accessibles.
 *
 * Le filtrage par mot-clé et par état est fait ici, sur la liste déjà
 * restreinte par le backend : le client ne connaît que ce qu'il a le droit de
 * voir, et ne peut donc pas élargir la recherche au-delà. Aucun indicateur ne
 * laisse croire qu'il existe des documents masqués — un compte total serait
 * le meilleur moyen de cartographier la base.
 */
export default function DocumentTable({
  documents = [],
  loading = false,
  onRefresh,
  onOpen,
  onDelete,
  actionEnCours = null,
  ragActif = true,
}) {
  const { has } = usePermissions();
  const [recherche, setRecherche] = useState("");
  const [filtre, setFiltre] = useState("tous");

  const peutSupprimer = has("documents:supprimer");

  const filtres = useMemo(() => {
    const terme = recherche.trim().toLowerCase();
    return documents.filter((document) => {
      if (filtre === "indexe" && document.statut_indexation !== "indexe") {
        return false;
      }
      if (
        filtre === "en_attente" &&
        document.statut_indexation !== "en_attente"
      ) {
        return false;
      }
      if (filtre === "echec" && document.statut_indexation !== "echec") {
        return false;
      }
      if (
        filtre === "classes" &&
        !(
          document.confidentialite === "restreinte" ||
          document.confidentialite === "confidentielle"
        )
      ) {
        return false;
      }
      if (!terme) return true;
      return [document.nom_fichier, document.description]
        .filter(Boolean)
        .some((champ) => champ.toLowerCase().includes(terme));
    });
  }, [documents, filtre, recherche]);

  const columns = useMemo(
    () => [
      {
        key: "nom_fichier",
        header: "Document",
        render: (document) => {
          const Icone = iconeDocument(document.extension);
          const niveau = niveauConfidentialite(document.confidentialite);
          return (
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <Icone size={18} aria-hidden="true" style={{ flexShrink: 0 }} />
              <div style={{ minWidth: 0 }}>
                <div className="tableau__nom">{document.nom_fichier}</div>
                {document.description && (
                  <span
                    className="tableau__sous-texte"
                    style={{ display: "block" }}
                  >
                    {document.description}
                  </span>
                )}
                <span
                  className="doc-ref__non-cite"
                  title={niveau.description}
                  style={{ display: "inline-block", marginTop: 2 }}
                >
                  {niveau.label}
                </span>
              </div>
            </div>
          );
        },
      },
      {
        key: "statut_indexation",
        header: "Indexation",
        render: (document) => {
          const statut = statutIndexation(document.statut_indexation);
          return (
            <Badge variant={statut.variante} dot={statut.pastille}>
              {statut.label}
            </Badge>
          );
        },
      },
      {
        key: "nb_morceaux",
        header: "Extraits",
        render: (document) => formatNumber(document.nb_morceaux ?? 0),
      },
      {
        key: "taille_octets",
        header: "Taille",
        render: (document) => formatBytes(document.taille_octets),
      },
      {
        key: "created_at",
        header: "Déposé le",
        render: (document) => formatDateTime(document.created_at),
      },
      {
        key: "cree_par",
        header: "Par",
        render: (document) => courtIdentifiant(document.cree_par),
      },
      {
        key: "actions",
        header: "",
        render: (document) => {
          const enCours = actionEnCours === document.id;
          return (
            <div
              style={{ display: "flex", gap: 6, justifyContent: "flex-end" }}
            >
              <Button
                variant="ghost"
                size="sm"
                onClick={(event) => {
                  event.stopPropagation();
                  onOpen?.(document);
                }}
              >
                <Eye size={14} aria-hidden="true" />
                Fiche
              </Button>
              {peutSupprimer && (
                <Button
                  variant="ghost"
                  size="sm"
                  loading={enCours}
                  onClick={(event) => {
                    event.stopPropagation();
                    onDelete?.(document);
                  }}
                  aria-label={`Supprimer ${document.nom_fichier}`}
                >
                  {!enCours && <Trash2 size={14} aria-hidden="true" />}
                </Button>
              )}
            </div>
          );
        },
      },
    ],
    [actionEnCours, onDelete, onOpen, peutSupprimer]
  );

  return (
    <section className="card">
      <div className="card__header">
        <div>
          <h3 className="card__title">Documents</h3>
          <p className="text-muted">
            {filtres.length === documents.length
              ? `${formatNumber(documents.length)} document(s) accessible(s)`
              : `${formatNumber(filtres.length)} sur ${formatNumber(documents.length)} document(s)`}
            {!ragActif && " — indexation et recherche suspendues"}
          </p>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <div style={{ minWidth: 220 }}>
            <input
              type="search"
              className="input"
              value={recherche}
              onChange={(event) => setRecherche(event.target.value)}
              placeholder="Filtrer par nom ou description"
              aria-label="Filtrer les documents"
            />
          </div>
          <select
            className="select"
            value={filtre}
            onChange={(event) => setFiltre(event.target.value)}
            aria-label="Filtrer par état"
          >
            {FILTRES.map((item) => (
              <option key={item.valeur} value={item.valeur}>
                {item.libelle}
              </option>
            ))}
          </select>
          <Button
            variant="ghost"
            size="sm"
            onClick={onRefresh}
            loading={loading}
            aria-label="Actualiser"
            title="Actualiser"
          >
            {!loading && <RefreshCw size={16} aria-hidden="true" />}
            Actualiser
          </Button>
        </div>
      </div>

      <Table
        columns={columns}
        data={filtres}
        rowKey="id"
        loading={loading}
        empty={{
          icon: documents.length > 0 ? Search : FolderOpen,
          title:
            documents.length > 0
              ? "Aucun document ne correspond au filtre"
              : "Base documentaire vide",
          description:
            documents.length > 0
              ? "Modifiez le filtre d'état ou le mot-clé pour retrouver vos documents."
              : "Déposez un premier document pour alimenter la base et rendre l'assistant documentaire interrogeable.",
        }}
      />
    </section>
  );
}
