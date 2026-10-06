"use client";

import { useEffect, useRef } from "react";

import {
  AlertCircle,
  RotateCcw,
  ShieldCheck,
  Sparkles,
  TriangleAlert,
} from "lucide-react";

import Button from "@/components/ui/Button";
import EmptyState from "@/components/ui/EmptyState";
import Badge from "@/components/ui/Badge";
import ChatInput from "@/components/assistant/ChatInput";
import ChatMessage from "@/components/assistant/ChatMessage";
import { QUESTIONS_EXEMPLES, QUESTIONS_HORS_PERIMETRE } from "@/lib/assistant";

/**
 * Panneau d'accueil, avant la première question.
 *
 * Il pose le cadre avant de proposer quoi que ce soit : ce que l'assistant sait
 * calculer, qu'il peut aussi lire les textes réglementaires, et qu'il ne produit
 * aucun chiffre de son propre chef. Un utilisateur qui pose une question à un
 * outil administratif doit savoir d'avance ce qu'il obtiendra — un chiffre
 * calculé et traçable, une citation, ou une déclaration d'absence.
 */
function Accueil({ referentiel, exercice, exercices, onProposer }) {
  const indicateurs = referentiel?.indicateurs ?? [];
  const garanties = referentiel?.garanties ?? [];
  const modeleActif = Boolean(referentiel?.modele?.actif);

  return (
    <div className="chat-window__accueil">
      <div className="chat-window__presentation">
        <span className="chat-window__presentation-icone" aria-hidden="true">
          <Sparkles size={22} />
        </span>
        <h2 className="chat-window__titre">
          Interrogez les données et les textes de la plateforme
        </h2>
        <p className="chat-window__texte">
          Chaque réponse est calculée par le backend avant d’être rédigée : les
          chiffres affichés proviennent d’une source identifiée, les règles
          invoquées portent la citation de leur texte, et une donnée absente vous
          est signalée comme telle plutôt qu’estimée.
        </p>
        <div className="chat-window__pastilles">
          <Badge variant="success" dot>
            Calcul backend exact
          </Badge>
          <Badge variant="success" dot>
            Textes cités
          </Badge>
          <Badge variant="success" dot>
            Chiffres contrôlés
          </Badge>
          <Badge variant={modeleActif ? "primary" : "neutral"} dot>
            {modeleActif
              ? `Rédaction assistée (${referentiel.modele.nom})`
              : "Rédaction backend"}
          </Badge>
        </div>
      </div>

      {indicateurs.length > 0 && (
        <section className="chat-window__bloc">
          <h3 className="chat-window__bloc-titre">Questions d’exemple</h3>
          <ul className="chat-window__suggestions">
            {QUESTIONS_EXEMPLES.map((question) => (
              <li key={question}>
                <button
                  type="button"
                  className="chat-window__suggestion"
                  onClick={() => onProposer(question)}
                >
                  {question}
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      {garanties.length > 0 && (
        <section className="chat-window__bloc">
          <h3 className="chat-window__bloc-titre">
            <ShieldCheck size={14} aria-hidden="true" />
            Ce que garantit cet assistant
          </h3>
          <ul className="chat-window__garanties">
            {garanties.slice(0, 4).map((garantie) => (
              <li key={garantie}>{garantie}</li>
            ))}
          </ul>
        </section>
      )}

      <section className="chat-window__bloc">
        <h3 className="chat-window__bloc-titre">Hors périmètre</h3>
        <ul className="chat-window__hors-perimetre">
          {QUESTIONS_HORS_PERIMETRE.map((question) => (
            <li key={question}>
              <button
                type="button"
                className="chat-window__suggestion chat-window__suggestion--discrete"
                onClick={() => onProposer(question)}
              >
                {question}
              </button>
            </li>
          ))}
        </ul>
        <p className="chat-window__note">
          {exercices.length > 0
            ? `Exercices disponibles : ${exercices
                .slice(0, 6)
                .join(", ")}${exercices.length > 6 ? "…" : ""}. Sans exercice imposé, l’assistant vous demandera la période plutôt que d’en choisir une à votre place.`
            : `Aucun exercice n’a été détecté dans les sources. L’assistant répondra qu’il n’a pas de données.`}
          {exercice != null && ` Exercice imposé : ${exercice}.`}
        </p>
      </section>
    </div>
  );
}

/**
 * Fenêtre de conversation.
 *
 * Le fil défile automatiquement à chaque nouveau message, sans jamais faire
 * défiler la page entière : la zone de saisie et l'en-tête restent en place,
 * ce qui permet de poser une question suivante sans revenir en haut.
 */
export default function ChatWindow({
  pret,
  messages,
  chargement,
  texteErreur,
  referentiel,
  exercices,
  exercice,
  onEnvoyer,
  onProposer,
  onReinitialiser,
}) {
  const basRef = useRef(null);

  useEffect(() => {
    basRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, chargement]);

  const vide = messages.length === 0;

  return (
    <section className="chat-window card">
      <header className="chat-window__barre">
        <div className="chat-window__identite">
          <span className="chat-window__pastille" aria-hidden="true" />
          <div>
            <h2 className="chat-window__nom">Assistant analytique</h2>
            <p className="chat-window__etat">
              {pret
                ? `${referentiel?.indicateurs?.length ?? 0} indicateurs — réponses calculées par le backend`
                : "Chargement du périmètre…"}
            </p>
          </div>
        </div>
        {!vide && (
          <Button
            variant="ghost"
            size="sm"
            onClick={onReinitialiser}
            disabled={chargement}
          >
            <RotateCcw size={14} aria-hidden="true" />
            Nouvelle conversation
          </Button>
        )}
      </header>

      <div className="chat-window__fil">
        {!pret ? (
          <EmptyState
            icon={Sparkles}
            title="Préparation de l’assistant"
            description="Chargement du périmètre et des indicateurs disponibles."
          />
        ) : vide ? (
          <Accueil
            referentiel={referentiel}
            exercice={exercice}
            exercices={exercices}
            onProposer={onProposer}
          />
        ) : (
          <div className="chat-window__messages">
            {messages.map((message) => (
              <ChatMessage key={message.id} message={message} />
            ))}
            {chargement && (
              <div className="chat-window__en-cours">
                <span className="chat-window__points" aria-hidden="true">
                  <span />
                  <span />
                  <span />
                </span>
                Calcul et rédaction en cours…
              </div>
            )}
          </div>
        )}
        <div ref={basRef} />
      </div>

      {texteErreur && (
        <div className="chat-window__erreur alert alert--error" role="alert">
          <AlertCircle size={16} className="alert__icon" aria-hidden="true" />
          <div>
            <strong>La question n’a pas pu être traitée.</strong>
            <p>{texteErreur}</p>
            <p className="chat-window__erreur-note">
              <TriangleAlert size={13} aria-hidden="true" />
              Aucune valeur n’a été affichée : l’assistant ne produit jamais de
              chiffre lorsqu’il n’a pas pu calculer.
            </p>
          </div>
        </div>
      )}

      <ChatInput onEnvoyer={onEnvoyer} desactive={!pret || chargement} />
    </section>
  );
}
