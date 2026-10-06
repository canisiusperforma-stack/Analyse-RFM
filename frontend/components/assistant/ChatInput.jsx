"use client";

import { useEffect, useRef, useState } from "react";

import { SendHorizontal } from "lucide-react";

import Button from "@/components/ui/Button";
import { MAX_QUESTION } from "@/lib/assistant";

const LIGNES_MAX = 6;
const HAUTEUR_LIGNE = 22;

/**
 * Champ de saisie d'une question.
 *
 * La zone de texte grandit avec la question jusqu'à une hauteur bornée, puis
 * défile : le fil de conversation reste visible pendant la saisie, ce qui
 * importe quand la réponse dépend d'un calcul dont on veut garder la trace.
 *
 * La touche Entrée envoie, Maj+Entrée insère un saut de ligne. Ce choix est
 * explicite parce qu'il n'est pas neutre : la question d'un analyste est une
 * phrase, alors que le retour à la ligne sert surtout à la préparation d'une
 * liste — d'où les deux gestes conservés côte à côte.
 */
export default function ChatInput({
  onEnvoyer,
  desactive = false,
  placeholder = "Posez votre question sur les données de la plateforme…",
}) {
  const [texte, setTexte] = useState("");
  const zoneRef = useRef(null);

  const tropLong = texte.length > MAX_QUESTION;
  // La limite est celle du backend (`LLM_QUESTION_MAX`). L'envoi est bloqué
  // au-delà plutôt que de laisser la requête partir : le refus arriverait en
  // 422, après une attente qui n'aurait rien produit.
  const peutEnvoyer = texte.trim().length > 0 && !desactive && !tropLong;

  // Ajustement de la hauteur après chaque frappe.
  useEffect(() => {
    const zone = zoneRef.current;
    if (!zone) return;
    zone.style.height = "auto";
    zone.style.height = `${Math.min(zone.scrollHeight, LIGNES_MAX * HAUTEUR_LIGNE)}px`;
  }, [texte]);

  const envoyer = () => {
    if (!peutEnvoyer) return;
    const question = texte.trim();
    setTexte("");
    onEnvoyer(question);
  };

  const surTouche = (evenement) => {
    if (evenement.key !== "Enter" || evenement.shiftKey) return;
    // `preventDefault` garde le saut de ligne pour Maj+Entrée, qui n'est pas
    // traité ici et suit le comportement natif du champ.
    evenement.preventDefault();
    envoyer();
  };

  const surChangement = (evenement) => {
    setTexte(evenement.target.value);
  };

  return (
    <form
      className="chat-input"
      onSubmit={(evenement) => {
        evenement.preventDefault();
        envoyer();
      }}
    >
      <div className="chat-input__champ">
        <textarea
          ref={zoneRef}
          className="chat-input__zone"
          value={texte}
          onChange={surChangement}
          onKeyDown={surTouche}
          placeholder={placeholder}
          rows={1}
          disabled={desactive}
          aria-label="Votre question"
          aria-describedby="chat-input-aide"
          maxLength={MAX_QUESTION + 500}
        />
        <Button
          type="submit"
          className="chat-input__envoyer"
          disabled={!peutEnvoyer}
          aria-label="Envoyer la question"
          title="Envoyer (Entrée)"
        >
          <SendHorizontal size={16} aria-hidden="true" />
        </Button>
      </div>

      <div className="chat-input__pied" id="chat-input-aide">
        <span className="chat-input__indice">
          Entrée pour envoyer · Maj+Entrée pour un retour à la ligne
        </span>
        {tropLong ? (
          <span className="chat-input__compteur chat-input__compteur--alerte">
            {texte.length} / {MAX_QUESTION} caractères
          </span>
        ) : null}
      </div>
    </form>
  );
}
