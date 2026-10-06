"use client";

import { useState } from "react";
import { ChevronDown, FileCog, ShieldCheck } from "lucide-react";

import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import Loading from "@/components/ui/Loading";
import { descriptionEmbeddings, libellesFormats } from "@/lib/documents";
import { formatBytes, formatNumber, formatScore } from "@/lib/formatters";

/**
 * Périmètre réel de la recherche documentaire.
 *
 * Ce panneau expose ce que le pipeline fait *effectivement* — formats
 * autorisés, modèle d'embeddings, découpage, seuil, nombre d'extraits — et non
 * une description wishful. C'est la contrepartie visuelle de la recherche « sans
 * modèle » : si une question reste sans réponse, l'agent doit pouvoir lire ici
 * *pourquoi* (seuil trop haut, format refusé, RAG coupé) sans avoir à deviner.
 *
 * Les garanties affichées sont celles du backend, restituées telles quelles. Les
 * réécrire ici créerait un second jeu de règles, susceptible de diverger de
 * celui qui s'applique réellement.
 */
export default function DocumentReferentiel({ referentiel, loading }) {
  const [ouvert, setOuvert] = useState(false);

  if (loading) return <Loading label="Chargement du référentiel…" />;
  if (!referentiel) return null;

  const {
    actif,
    regles = [],
    pipeline = [],
    formats_acceptes: formatsAcceptes = [],
    formats_autorises: formatsAutorises = [],
    taille_max_octets: tailleMax,
    niveaux_confidentialite: niveaux = [],
    statuts_indexation: statuts = [],
    seuil_pertinence: seuil,
    ponderation_dense: ponderation,
    citations_exigees: citations,
    recherche: reglages = {},
    decoupage = {},
    embeddings,
  } = referentiel;

  const entrees = [
    {
      label: "Formats extraits",
      valeur: `${libellesFormats(formatsAcceptes)} — autorisés : ${libellesFormats(formatsAutorises)}`,
    },
    {
      label: "Taille maximale",
      valeur: tailleMax ? formatBytes(tailleMax) : "—",
    },
    {
      label: "Découpage",
      valeur: decoupage.taille
        ? `${formatNumber(decoupage.taille)} caractères (minimum ${formatNumber(decoupage.taille_min)}, recouvrement ${formatNumber(decoupage.recouvrement)})`
        : "—",
    },
    {
      label: "Seuil de pertinence",
      valeur:
        seuil != null
          ? `${formatScore(seuil)} — pondération vectorielle ${formatScore(ponderation)}`
          : "—",
    },
    {
      label: "Recherche",
      valeur: reglages.top_k
        ? `${formatNumber(reglages.top_k)} extraits retenus, ${formatNumber(reglages.candidats)} candidats examinés, ${formatNumber(reglages.sources_min)} sources minimum`
        : "—",
    },
    {
      label: "Contexte",
      valeur: reglages.contexte_caracteres_max
        ? `${formatNumber(reglages.contexte_caracteres_max)} caractères maximum`
        : "—",
    },
    {
      label: "Embeddings",
      valeur: descriptionEmbeddings(embeddings),
    },
    {
      label: "Citations",
      valeur: citations
        ? "Obligatoires — chaque affirmation doit porter un marqueur de source"
        : "Non exigées par la configuration",
    },
    {
      label: "Niveaux de confidentialité",
      valeur: niveaux.length > 0 ? niveaux.join(", ") : "—",
    },
    {
      label: "États d'indexation",
      valeur: statuts.length > 0 ? statuts.join(", ") : "—",
    },
  ];

  return (
    <section className="card">
      <div className="card__header">
        <span className="conv-section__icon">
          <FileCog size={18} />
        </span>
        <div>
          <h3 className="card__title">Périmètre du pipeline</h3>
          <p className="text-muted">
            Configuration réellement appliquée — c&apos;est elle qui explique
            pourquoi une question reste sans réponse.
          </p>
        </div>
        <Badge variant={actif ? "success" : "warning"} dot>
          {actif ? "Recherche active" : "Recherche désactivée"}
        </Badge>
      </div>

      <div className="card__body">
        {pipeline.length > 0 && (
          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              gap: 6,
              marginBottom: 16,
            }}
          >
            {pipeline.map((etape) => (
              <span key={etape} className="badge badge--neutral">
                {etape}
              </span>
            ))}
          </div>
        )}

        <div className="meta-list">
          {entrees.map(({ label, valeur }) => (
            <div key={label} className="meta-list__item">
              <span className="meta-list__label">{label}</span>
              <span className="meta-list__value">{valeur}</span>
            </div>
          ))}
        </div>

        {regles.length > 0 && (
          <>
            <div style={{ marginTop: 16 }}>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setOuvert((precedent) => !precedent)}
                aria-expanded={ouvert}
              >
                <ChevronDown
                  size={14}
                  aria-hidden="true"
                  style={{
                    transform: ouvert ? "rotate(180deg)" : "none",
                    transition: "transform var(--transition-fast)",
                  }}
                />
                {ouvert
                  ? "Masquer les garanties"
                  : `Afficher les ${regles.length} garanties`}
              </Button>
            </div>

            {ouvert && (
              <ul
                className="placeholder-list"
                style={{ marginTop: 12, listStyle: "none" }}
              >
                {regles.map((regle) => (
                  <li
                    key={regle}
                    style={{ display: "flex", gap: 8, alignItems: "flex-start" }}
                  >
                    <ShieldCheck
                      size={13}
                      aria-hidden="true"
                      style={{ flexShrink: 0, marginTop: 3 }}
                    />
                    <span>{regle}</span>
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </div>
    </section>
  );
}
