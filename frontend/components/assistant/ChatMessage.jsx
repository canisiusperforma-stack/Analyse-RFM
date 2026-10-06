"use client";

import { AlertTriangle, Bot, CheckCircle2, Clock3, HelpCircle, User } from "lucide-react";

import Badge from "@/components/ui/Badge";
import DocumentReference from "@/components/assistant/DocumentReference";
import SourceReference from "@/components/assistant/SourceReference";
import {
  avertissementModeleEcarte,
  avertissementsVisibles,
  blocDonnees,
  clarification,
  confiancePourcent,
  documentsAffichables,
  exerciceUtilise,
  libelleIntent,
  libelleIntention,
  libelleProvenance,
  libelleStatut,
  limitesVisibles,
  mesuresDonnees,
  mesuresSecondaires,
  paragraphes,
  resumeReponse,
  tableauAffichable,
  tableauDonnees,
  varianteProvenance,
  varianteStatut,
} from "@/lib/assistant";

/**
 * Rendu de la valeur d'une mesure.
 *
 * `valeur_affichee` est la chaîne produite par le backend : elle est affichée
 * telle quelle, sans reformatage. C'est la garantie que l'écran montre les
 * chiffres que le serveur a calculés et validés, et non une relecture faite
 * par le navigateur.
 */
function ValeurMesure({ mesure }) {
  return (
    <span className="chat-message__mesure-valeur">
      {mesure.valeur_affichee ?? "—"}
    </span>
  );
}

/** Tableau structuré, lorsque le calcul en produit un. */
function TableauResultat({ tableau }) {
  return (
    <div className="chat-message__tableau">
      <table className="table">
        <thead>
          <tr>
            {tableau.colonnes.map((colonne) => (
              <th key={colonne} scope="col">
                {colonne}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {tableau.lignes.map((ligne, index) => (
            <tr key={`${index}-${ligne[0]}`}>
              {ligne.map((cellule, colonne) =>
                colonne === 0 ? (
                  <th key={colonne} scope="row">
                    {cellule}
                  </th>
                ) : (
                  <td key={colonne}>{cellule}</td>
                )
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/**
 * Bloc de données structurées, sur le chemin de fusion.
 *
 * Il est distinct du bloc de mesures de l'en-tête parce qu'il répond à une
 * autre question : l'en-tête montre les chiffres, celui-ci montre ce que le
 * backend a pu calculer et, surtout, ce qu'il n'a pas pu calculer. La ligne
 * d'absence est donc affichée dès qu'un statut n'est pas « disponible » —
 * c'est le cas le plus important de cet écran, et le seul qui interdit de
 * conclure.
 */
function BlocDonneesStructurees({ compteRendu }) {
  const bloc = blocDonnees(compteRendu);
  if (!bloc) return null;

  const mesuresListe = mesuresDonnees(compteRendu);
  const tableau = tableauDonnees(compteRendu);
  const absent = bloc.statut !== "disponible";

  return (
    <section className="chat-message__donnees">
      <h4 className="chat-message__donnees-titre">
        {bloc.libelle || "Données calculées"}
      </h4>
      {absent && (
        <p className="chat-message__absence">
          <AlertTriangle size={14} aria-hidden="true" />
          {bloc.absence || "La donnée nécessaire n'a pas pu être calculée."}
        </p>
      )}
      {mesuresListe.length > 0 && (
        <ul className="chat-message__mesures">
          {mesuresListe.map((mesure) => (
            <li key={mesure.cle} className="chat-message__mesure">
              <span className="chat-message__mesure-libelle">{mesure.libelle}</span>
              <ValeurMesure mesure={mesure} />
            </li>
          ))}
        </ul>
      )}
      {tableau && <TableauResultat tableau={tableau} />}
      {bloc.note && <p className="chat-message__note">{bloc.note}</p>}
    </section>
  );
}

/** Message de l'utilisateur. */
function BulleUtilisateur({ texte }) {
  return (
    <div className="chat-message chat-message--user">
      <span className="chat-message__avatar" aria-hidden="true">
        <User size={15} />
      </span>
      <div className="chat-message__bulle chat-message__bulle--user">
        {paragraphes(texte).map((paragraphe, index) => (
          // eslint-disable-next-line react/no-array-index-key
          <p key={index}>{paragraphe}</p>
        ))}
      </div>
    </div>
  );
}

/** Réponse de l'assistant, avec sa traçabilité. */
function BulleAssistant({ texte, compteRendu }) {
  const resume = resumeReponse(compteRendu);
  const intention = compteRendu?.analyse?.intention;
  const exerciceUtiliseValeur = exerciceUtilise(compteRendu);
  const secondaire = mesuresSecondaires(compteRendu);
  const tableau = tableauAffichable(compteRendu);
  const avertissements = avertissementsVisibles(compteRendu);
  const rejet = avertissementModeleEcarte(compteRendu);
  const indisponible = resume?.statut === "absent";

  // Chemin d'orchestration : présent sur `/query`, absent sur `/question`.
  const chemin = libelleIntent(compteRendu?.intent);
  const demande = clarification(compteRendu);
  const limites = limitesVisibles(compteRendu);
  const donnees = blocDonnees(compteRendu);
  const confiance = confiancePourcent(compteRendu);

  return (
    <div className="chat-message chat-message--assistant">
      <span className="chat-message__avatar" aria-hidden="true">
        <Bot size={15} />
      </span>

      <div className="chat-message__bulle chat-message__bulle--assistant">
        <header className="chat-message__entete">
          {chemin ? (
            <span className="chat-message__indicateur">{chemin}</span>
          ) : (
            resume?.libelle && (
              <span className="chat-message__indicateur">{resume.libelle}</span>
            )
          )}
          {chemin && resume?.libelle && (
            <span className="chat-message__sous-titre">{resume.libelle}</span>
          )}
          {intention && (
            <Badge variant="neutral">{libelleIntention(intention)}</Badge>
          )}
          {chemin && resume?.statut && (
            <Badge variant={varianteStatut(resume.statut)} dot>
              {libelleStatut(resume.statut)}
            </Badge>
          )}
          {typeof compteRendu?.duree_ms === "number" && (
            <span className="chat-message__duree" title="Durée du traitement">
              <Clock3 size={12} aria-hidden="true" />
              {compteRendu.duree_ms} ms
            </span>
          )}
        </header>

        {demande && (
          <p className="chat-message__clarification">
            <HelpCircle size={14} aria-hidden="true" />
            {demande}
          </p>
        )}

        {indisponible && !demande && (
          <p className="chat-message__absence">
            <AlertTriangle size={14} aria-hidden="true" />
            {compteRendu?.resultat?.absence ||
              "La donnée nécessaire n'est pas disponible."}
          </p>
        )}

        <div className="chat-message__texte">
          {paragraphes(texte).map((paragraphe, index) => (
            // eslint-disable-next-line react/no-array-index-key
            <p key={index}>{paragraphe}</p>
          ))}
        </div>

        {secondaire.length > 0 && (
          <ul className="chat-message__mesures">
            {secondaire.map((mesure) => (
              <li
                key={mesure.cle}
                className="chat-message__mesure"
              >
                <span className="chat-message__mesure-libelle">
                  {mesure.libelle}
                </span>
                <ValeurMesure mesure={mesure} />
              </li>
            ))}
          </ul>
        )}

        {donnees ? (
          <BlocDonneesStructurees compteRendu={compteRendu} />
        ) : (
          tableau && <TableauResultat tableau={tableau} />
        )}

        {documentsAffichables(compteRendu) && (
          <DocumentReference compteRendu={compteRendu} />
        )}

        {limites.length > 0 && (
          <ul className="chat-message__limites">
            {limites.map((limite) => (
              <li key={limite}>{limite}</li>
            ))}
          </ul>
        )}

        {rejet && (
          <p className="chat-message__rejet">
            <AlertTriangle size={14} aria-hidden="true" />
            {rejet}
          </p>
        )}

        {avertissements.map((avertissement) => (
          <p
            key={avertissement}
            className="chat-message__avertissement"
          >
            <AlertTriangle size={13} aria-hidden="true" />
            {avertissement}
          </p>
        ))}

        {!donnees && resume?.note && (
          <p className="chat-message__note">{resume.note}</p>
        )}

        <footer className="chat-message__pied">
          <Badge variant={varianteProvenance(compteRendu)}>
            {libelleProvenance(compteRendu)}
          </Badge>
          {exerciceUtiliseValeur != null && (
            <span className="chat-message__exercice">
              Exercice {exerciceUtiliseValeur}
            </span>
          )}
          {confiance != null && (
            <span
              className="chat-message__confiance"
              title="Confiance du choix de chemin par le routeur"
            >
              Confiance {confiance} %
            </span>
          )}
          <SourceReference compteRendu={compteRendu} />
        </footer>
      </div>
    </div>
  );
}

/**
 * Un tour de conversation.
 *
 * Le message de l'utilisateur est une bulle simple ; celui de l'assistant porte
 * au contraire la réponse, le statut du calcul et le détail des sources. Cette
 * dissymétrie est voulue : elle matérialise que le texte affiché n'est pas du
 * même ordre que la question posée, puisqu'il est adossé à un calcul.
 */
export default function ChatMessage({ message }) {
  if (message.role === "user") {
    return <BulleUtilisateur texte={message.texte} />;
  }

  if (!message.compteRendu) {
    return (
      <div className="chat-message chat-message--assistant">
        <span className="chat-message__avatar" aria-hidden="true">
          <CheckCircle2 size={15} />
        </span>
        <div className="chat-message__bulle chat-message__bulle--assistant">
          <p className="chat-message__texte">{message.texte}</p>
        </div>
      </div>
    );
  }

  return (
    <BulleAssistant texte={message.texte} compteRendu={message.compteRendu} />
  );
}
