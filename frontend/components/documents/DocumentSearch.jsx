"use client";

import { useCallback, useState } from "react";
import {
  FileSearch,
  Quote,
  Search,
  ShieldAlert,
  X,
} from "lucide-react";

import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import EmptyState from "@/components/ui/EmptyState";
import Input from "@/components/ui/Input";
import { libellesFormats, niveauConfidentialite } from "@/lib/documents";
import { getApiErrorText } from "@/lib/errors";
import { formatNumber, formatScore } from "@/lib/formatters";
import { rechercherExtraits } from "@/services/documentService";

/**
 * Exploration de la base documentaire — sans modèle.
 *
 * Cette recherche n'appelle **aucun** modèle : elle renvoie les extraits que le
 * moteur de similarité retient, avec leur provenance et leur score. Elle sert à
 * trois choses, et c'est ce qui la distingue de l'assistant :
 *
 * - vérifier ce que le chatbot voit réellement, plutôt que ce qu'il affirme
 *   avoir lu ;
 * - diagnostiquer une question qui resterait sans réponse, en voyant si le
 *   meilleur score passe ou non le seuil ;
 * - retrouver une référence précise sans passer par une rédaction.
 *
 * Une recherche qui ne renvoie rien n'est pas une erreur : c'est une réponse.
 * Le meilleur score et le seuil sont affichés dans les deux cas, pour que
 * l'absence soit attribuable à la base et non à l'interface.
 */
export default function DocumentSearch({ documents = [], ragActif, referentiel }) {
  const [question, setQuestion] = useState("");
  const [resultat, setResultat] = useState(null);
  const [loading, setLoading] = useState(false);
  const [erreur, setErreur] = useState(null);
  const [perimetre, setPerimetre] = useState("");

  const referentielFormats =
    referentiel?.formats_autorises?.length > 0
      ? referentiel.formats_autorises
      : (referentiel?.formats_acceptes ?? []);

  const chercher = useCallback(
    async (evenement) => {
      evenement?.preventDefault();
      const requete = question.trim();
      if (!requete || loading) return;

      setLoading(true);
      setErreur(null);
      try {
        setResultat(
          await rechercherExtraits({
            q: requete,
            documents: perimetre ? [perimetre] : [],
          })
        );
      } catch (errorRecherche) {
        setErreur(getApiErrorText(errorRecherche));
        setResultat(null);
      } finally {
        setLoading(false);
      }
    },
    [loading, perimetre, question]
  );

  const reinitialiser = useCallback(() => {
    setResultat(null);
    setErreur(null);
  }, []);

  const sources = resultat?.sources ?? [];
  const trouve = resultat?.trouve === true;

  return (
    <section className="card">
      <div className="card__header">
        <span className="conv-section__icon">
          <FileSearch size={18} />
        </span>
        <div>
          <h3 className="card__title">Explorer les extraits</h3>
          <p className="text-muted">
            Recherche directe dans les extraits indexés, <strong>sans appel à
            un modèle</strong>. Elle montre ce que l&apos;assistant pourrait
            lire, et rien de plus.
          </p>
        </div>
        {ragActif ? null : (
          <Badge variant="warning" dot>
            Recherche désactivée
          </Badge>
        )}
      </div>

      <div className="card__body">
        <form onSubmit={chercher}>
          <div className="filtres-bar">
            <Input
              label="Question ou termes recherchés"
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="modalités d'octroi de la subvention"
              autoComplete="off"
            />
            <div className="filtres-bar__champ">
              <label className="field__label" htmlFor="document-perimetre">
                Restreindre à un document
              </label>
              <select
                id="document-perimetre"
                className="select"
                value={perimetre}
                onChange={(event) => setPerimetre(event.target.value)}
              >
                <option value="">Tous les documents accessibles</option>
                {documents.map((document) => (
                  <option key={document.id} value={document.id}>
                    {document.nom_fichier}
                  </option>
                ))}
              </select>
              <span className="field__hint">
                Ne restreint jamais l&apos;accès : un document non autorisé
                reste exclu.
              </span>
            </div>
            <div className="filtres-bar__champ">
              <Button
                type="submit"
                loading={loading}
                disabled={!question.trim() || !ragActif}
                title={
                  ragActif
                    ? undefined
                    : "La recherche documentaire est désactivée"
                }
              >
                <Search size={15} />
                Rechercher
              </Button>
            </div>
          </div>
        </form>

        {erreur && (
          <div className="alert alert--error" role="alert" style={{ marginTop: 14 }}>
            <span>{erreur}</span>
          </div>
        )}

        {resultat && (
          <div style={{ marginTop: 16 }}>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: 12,
                flexWrap: "wrap",
              }}
            >
              <div
                style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}
              >
                <Badge variant={trouve ? "success" : "neutral"} dot>
                  {trouve
                    ? `${resultat.nb_sources} extrait${resultat.nb_sources > 1 ? "s" : ""} retenu${resultat.nb_sources > 1 ? "s" : ""}`
                    : "Aucun extrait au-dessus du seuil"}
                </Badge>
                <span className="tableau__sous-texte">
                  meilleur score {formatScore(resultat.score_max)} · seuil{" "}
                  {formatScore(resultat.seuil)}
                </span>
              </div>
              <Button variant="ghost" size="sm" onClick={reinitialiser}>
                <X size={14} />
                Effacer
              </Button>
            </div>

            {!trouve ? (
              <EmptyState
                icon={FileSearch}
                title="Information introuvable dans les documents accessibles"
                description={
                  <>
                    Aucun extrait n&apos;atteint le seuil de pertinence. Le
                    modèle n&apos;aurait pas été appelé non plus : la réponse
                    aurait été un refus, pas une formulation. Voir le{" "}
                    <strong>périmètre du pipeline</strong> pour lire le seuil,
                    les formats et le découpage appliqués.
                  </>
                }
              />
            ) : (
              <ol className="doc-ref__liste" style={{ marginTop: 12 }}>
                {sources.map((source) => {
                  const niveau = niveauConfidentialite(source.confidentialite);
                  return (
                    <li key={source.etiquette} className="doc-ref__item">
                      <div className="doc-ref__entete">
                        <span className="doc-ref__etiquette">
                          {source.etiquette}
                        </span>
                        <span className="doc-ref__document">
                          {source.nom_fichier || "document"}
                        </span>
                        {source.page != null && (
                          <span className="source-ref__module">
                            page {source.page}
                          </span>
                        )}
                        {source.titre && (
                          <span className="source-ref__module">
                            {source.titre}
                          </span>
                        )}
                        <span className="doc-ref__non-cite">
                          score {formatScore(source.score)}
                        </span>
                        {source.confidentialite !== "interne" && (
                          <Badge variant={niveau.variante}>
                            <ShieldAlert size={11} aria-hidden="true" />
                            {niveau.label}
                          </Badge>
                        )}
                      </div>
                      <blockquote className="doc-ref__extrait">
                        <Quote size={11} aria-hidden="true" />
                        <span>{source.extrait}</span>
                      </blockquote>
                    </li>
                  );
                })}
              </ol>
            )}

            {resultat.recherche && (
              <p className="text-muted" style={{ marginTop: 12 }}>
                {resultat.recherche.corpus_autorise != null &&
                  `${formatNumber(resultat.recherche.corpus_autorise)} extrait(s) dans le corpus autorisé — `}
                {resultat.recherche.candidats_examines != null &&
                  `${formatNumber(resultat.recherche.candidats_examines)} candidat(s) examiné(s), `}
                {resultat.recherche.candidats_retenus != null &&
                  `${formatNumber(resultat.recherche.candidats_retenus)} retenu(s) après calcul du score`}
                . Le filtrage par classification est appliqué dans la requête,
                avant tout scoring.
              </p>
            )}
          </div>
        )}

        {!resultat && !erreur && (
          <EmptyState
            icon={Search}
            title="Aucune recherche effectuée"
            description={`Posez une question pour voir quels extraits seraient retenus, et à quel score. ${libellesFormats(
              referentielFormats
            )} sont indexables ; seuls les documents autorisés sont interrogeables.`}
          />
        )}
      </div>
    </section>
  );
}
