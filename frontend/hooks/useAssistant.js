"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { getApiErrorText } from "@/lib/errors";
import {
  poserRequete,
  recupererExercices,
  recupererReferentiel,
} from "@/services/iaService";

/**
 * Nombre de tours envoyés au backend comme historique.
 *
 * L'historique est tronqué par tours entiers et non par taille : le backend
 * n'en retient qu'un nombre limité (`LLM_TOURS_HISTORIQUE`), et un échange coupé
 * au milieu entre l'utilisateur et l'assistant embarrasserait le modèle plus
 * qu'il ne l'aiderait.
 */
const TOURS_ENVOYES = 8;

let compteurMessage = 0;

function creerMessage(role, texte, extra = {}) {
  compteurMessage += 1;
  return { id: `msg-${compteurMessage}`, role, texte, ...extra };
}

/**
 * État de la conversation avec l'assistant.
 *
 * Le message de l'utilisateur est ajouté immédiatement, avant l'appel réseau :
 * la question posée ne doit pas disparaître si la requête échoue. Dans ce cas
 * l'erreur est exposée à part, et la question reste rejouable.
 *
 * Aucun calcul n'est effectué ici. Le hook ne fait qu'empiler des tours et
 * transporter le compte rendu du backend jusqu'au rendu.
 */
export default function useAssistant() {
  const [messages, setMessages] = useState([]);
  const [chargement, setChargement] = useState(false);
  const [erreur, setErreur] = useState(null);

  const [referentiel, setReferentiel] = useState(null);
  const [exercices, setExercices] = useState([]);
  const [exercice, setExercice] = useState(null);
  const [document, setDocument] = useState(null);

  // Les suggestions ne sont proposées qu'une fois le référentiel connu : sans
  // lui, l'interface afficherait des questions dont l'assistant ignore la
  // réponse.
  const pret = referentiel !== null;

  const historiqueRef = useRef([]);

  useEffect(() => {
    let annule = false;
    (async () => {
      try {
        const [referentielData, exercicesDisponibles] = await Promise.all([
          recupererReferentiel(),
          recupererExercices(),
        ]);
        if (annule) return;
        setReferentiel(referentielData);
        setExercices(exercicesDisponibles);
      } catch (erreurInitiale) {
        if (!annule) setErreur(erreurInitiale);
      }
    })();
    return () => {
      annule = true;
    };
  }, []);

  const envoyer = useCallback(
    async (question) => {
      const texte = String(question ?? "").trim();
      if (!texte || chargement) return;

      setErreur(null);
      setChargement(true);
      setMessages((precedents) => [
        ...precedents,
        creerMessage("user", texte),
      ]);

      try {
        // Le chemin d'orchestration est emprunté par défaut : c'est lui qui
        // décide si la question relève des données, des documents, des deux, ou
        // d'aucun. Le document sélectionné, s'il y en a un, restreint la
        // recherche sans jamais élargir les droits de l'utilisateur.
        const compte_rendu = await poserRequete({
          question: texte,
          exercice,
          documents: document ? [document] : [],
          historique: historiqueRef.current.slice(-TOURS_ENVOYES * 2),
        });

        const texteReponse = compte_rendu?.reponse || "";

        // Une demande de précision n'est pas une réponse : la conserver dans
        // l'historique ferait croire que l'assistant a répondu, et le routeur
        // perdrait le contexte de ce qu'il attend.
        const estReponse = !compte_rendu?.clarification;
        if (estReponse) {
          historiqueRef.current = [
            ...historiqueRef.current,
            { role: "user", content: texte },
            { role: "assistant", content: texteReponse },
          ].slice(-TOURS_ENVOYES * 2);
        }

        setMessages((precedents) => [
          ...precedents,
          creerMessage("assistant", texteReponse, {
            compteRendu: compte_rendu,
          }),
        ]);
        return compte_rendu;
      } catch (erreurRequete) {
        setErreur(erreurRequete);
        return null;
      } finally {
        setChargement(false);
      }
    },
    [chargement, exercice, document]
  );

  const reinitialiser = useCallback(() => {
    historiqueRef.current = [];
    setMessages([]);
    setErreur(null);
  }, []);

  /** Rejoue une question d'amorce sans attendre la saisie. */
  const poserSuggestion = useCallback(
    (question) => envoyer(question),
    [envoyer]
  );

  return {
    pret,
    messages,
    chargement,
    erreur,
    texteErreur: erreur ? getApiErrorText(erreur) : null,
    referentiel,
    exercices,
    exercice,
    setExercice,
    document,
    setDocument,
    envoyer,
    poserSuggestion,
    reinitialiser,
  };
}
