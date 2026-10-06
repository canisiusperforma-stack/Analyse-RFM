"use client";

import { ChevronDown, Database, FileSearch, Route, ShieldCheck } from "lucide-react";

import { libelleIntent, raisonChemin } from "@/lib/assistant";

/**
 * Détail du calcul d'une réponse.
 *
 * Ce panneau est replié par défaut mais toujours présent : la réponse d'un
 * assistant doit pouvoir être contrôlée sans quitter l'écran. Il expose les
 * éléments qui rendent la réponse vérifiable — le chemin suivi par la question,
 * les fonctions backend interrogées, les documents lus, et le verdict du
 * rapprochement des chiffres.
 *
 * Le panneau ne réaudite rien : il ne fait que restituer le compte rendu du
 * backend, qui est seul à avoir vu les faits. Un contrôle effectué ici serait
 * un second avis partial, et donnerait une assurance que l'interface ne peut
 * pas fournir.
 */

/**
 * Étapes du chemin données.
 *
 * Decrivant l'ancienne chaîne, elles sont complétées plus bas par les étapes
 * propres au chemin documentaire : la liste affichée est toujours un extrait du
 * pipeline réellement suivi, afin qu'un utilisateur puisse vérifier ce qui a
 * été fait plutôt que lire une description générique.
 */
const ETAPES = [
  { cle: "question", libelle: "Question utilisateur", icone: null },
  { cle: "analyse", libelle: "Analyse de la question", icone: "code" },
  { cle: "indicateur", libelle: "Identification de l'indicateur", icone: "code" },
  { cle: "source", libelle: "Requête backend", icone: null },
  { cle: "calcul", libelle: "Calcul exact", icone: "code" },
  { cle: "resultat", libelle: "Résultat structuré", icone: null },
  { cle: "generation", libelle: "Génération par le modèle", icone: null },
  { cle: "controle", libelle: "Explication contrôlée", icone: null },
];

/** Étapes ajoutées lorsqu'une recherche documentaire a eu lieu. */
const ETAPES_DOCUMENTS = [
  { cle: "recherche", libelle: "Recherche documentaire", icone: "code" },
  { cle: "extraits", libelle: "Extraits retenus", icone: null },
];

export default function SourceReference({ compteRendu }) {
  if (!compteRendu) return null;

  const {
    analyse,
    intent,
    resultat,
    sources,
    documents,
    controle,
    regle,
    modele,
    reponse_rejetee: rejet,
  } = compteRendu;

  const sourcesListe = Array.isArray(sources) ? sources : [];
  const documentsListe = Array.isArray(documents) ? documents : [];
  const chemin = libelleIntent(intent);
  const raison = raisonChemin(compteRendu);

  // Le chemin documentaire n'est listé que s'il a été emprunté, et le chemin
  // données que s'il a produit quelque chose. Afficher les deux systématiquement
  // ferait croire que toute question a interrogé la base *et* les documents.
  const aDesDocuments = documentsListe.length > 0;
  const etapes = aDesDocuments ? [...ETAPES, ...ETAPES_DOCUMENTS] : ETAPES;

  const realisees = {
    question: Boolean(compteRendu.question),
    analyse: Boolean(analyse),
    indicateur: Boolean(resultat?.indicateur),
    source: sourcesListe.length > 0,
    calcul: Boolean(resultat?.mesures?.length),
    resultat: Boolean(resultat),
    generation: compteRendu.generee_par === "llm",
    controle: Boolean(controle),
    recherche: aDesDocuments,
    extraits: aDesDocuments,
  };

  return (
    <details className="source-ref">
      <summary className="source-ref__summary">
        <ChevronDown size={14} className="source-ref__chevron" aria-hidden="true" />
        Détail du calcul
      </summary>

      <div className="source-ref__corps">
        <section className="source-ref__section">
          <h4 className="source-ref__titre">
            <Route size={13} aria-hidden="true" />
            Chemin suivi
          </h4>
          {chemin && (
            <p className="source-ref__chemin">
              <strong>{chemin}</strong>
              {raison ? ` — ${raison}` : ""}
            </p>
          )}
          <ol className="source-ref__etapes">
            {etapes.map((etape) => (
              <li
                key={etape.cle}
                className={`source-ref__etape${
                  realisees[etape.cle] ? " source-ref__etape--faite" : ""
                }`}
              >
                <span className="source-ref__etape-point" aria-hidden="true" />
                <span className="source-ref__etape-libelle">
                  {etape.libelle}
                </span>
                <span className="source-ref__etape-auteur">
                  {etape.icone === "code" ? "code" : "backend"}
                </span>
              </li>
            ))}
          </ol>
        </section>

        {analyse && (
          <section className="source-ref__section">
            <h4 className="source-ref__titre">Analyse de la question</h4>
            <dl className="source-ref__faits">
              <div>
                <dt>Intention</dt>
                <dd>{analyse.libelle || analyse.intention || "—"}</dd>
              </div>
              {analyse.agregation && (
                <div>
                  <dt>Agrégation</dt>
                  <dd>{analyse.agregation}</dd>
                </div>
              )}
              {typeof analyse.confiance === "number" && (
                <div>
                  <dt>Confiance du classement</dt>
                  <dd>{Math.round(analyse.confiance * 100)} %</dd>
                </div>
              )}
              {analyse.exercice != null && (
                <div>
                  <dt>Exercice demandé</dt>
                  <dd>{analyse.exercice}</dd>
                </div>
              )}
              {analyse.situations?.length > 0 && (
                <div>
                  <dt>Situation visée</dt>
                  <dd>{analyse.situations.join(", ")}</dd>
                </div>
              )}
              {analyse.communes?.length > 0 && (
                <div>
                  <dt>Communes citées</dt>
                  <dd>{analyse.communes.join(", ")}</dd>
                </div>
              )}
            </dl>
          </section>
        )}

        <section className="source-ref__section">
          <h4 className="source-ref__titre">
            <Database size={13} aria-hidden="true" />
            Fonctions interrogées
          </h4>
          {sourcesListe.length === 0 ? (
            <p className="source-ref__vide">
              Aucune fonction de calcul interrogée : la question ne porte sur
              aucune donnée, ou hors du périmètre de la plateforme.
            </p>
          ) : (
            <ul className="source-ref__sources">
              {sourcesListe.map((source, index) => (
                <li key={`${source.fonction}-${index}`}>
                  <code className="source-ref__code">{source.fonction}</code>
                  <span className="source-ref__module">{source.module}</span>
                  {source.exercice != null && (
                    <span className="source-ref__exercice">
                      exercice {source.exercice}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>

        {aDesDocuments && (
          <section className="source-ref__section">
            <h4 className="source-ref__titre">
              <FileSearch size={13} aria-hidden="true" />
              Documents consultés
            </h4>
            <ul className="source-ref__documents">
              {documentsListe.map((document) => (
                <li key={document.etiquette}>
                  <span className="source-ref__etiquette">{document.etiquette}</span>
                  <span className="source-ref__module">{document.document}</span>
                  <span
                    className={`source-ref__statut${
                      document.cite ? " source-ref__statut--cite" : ""
                    }`}
                  >
                    {document.cite ? "cité" : "non cité"}
                  </span>
                </li>
              ))}
            </ul>
          </section>
        )}

        <section className="source-ref__section">
          <h4 className="source-ref__titre">
            <ShieldCheck size={13} aria-hidden="true" />
            Contrôle des chiffres
          </h4>
          <p className="source-ref__note">{controle?.note || "—"}</p>
          {rejet && (
            <p className="source-ref__rejet">
              Modèle écarté : la réponse affichée est celle du backend.
            </p>
          )}
          {regle && <p className="source-ref__regle">{regle}</p>}
          {modele && (
            <p className="source-ref__modele">
              Modèle : {modele.actif ? modele.nom : "non configuré"}
            </p>
          )}
        </section>
      </div>
    </details>
  );
}
