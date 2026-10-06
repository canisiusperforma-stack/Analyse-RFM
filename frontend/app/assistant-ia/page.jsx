"use client";

import PageContainer from "@/components/layout/PageContainer";
import Select from "@/components/ui/Select";
import ChatWindow from "@/components/assistant/ChatWindow";
import useAssistant from "@/hooks/useAssistant";

/**
 * Page de l'assistant conversationnel.
 *
 * Elle ne fait que câbler le hook d'état au composant de rendu et porter le
 * sélecteur d'exercice, conformément aux autres pages de l'application. Toute
 * la logique — analyse, calcul, contrôle des chiffres — reste côté backend :
 * cette page n'a pas à savoir comment une réponse est obtenue, seulement la
 * présenter et remonter la question.
 *
 * Aucun export de `metadata` : la page est un composant client, le titre
 * campagne étant porté par le layout, comme pour les autres pages
 * interactives.
 */
export default function AssistantIaPage() {
  const {
    pret,
    messages,
    chargement,
    texteErreur,
    referentiel,
    exercices,
    exercice,
    setExercice,
    document,
    setDocument,
    envoyer,
    poserSuggestion,
    reinitialiser,
  } = useAssistant();

  return (
    <PageContainer
      title="Assistant IA"
      subtitle="Interrogez les données RFM et les textes réglementaires en langage naturel"
      className="page-container--chat"
      actions={
        exercices.length > 0 ? (
          <Select
            label="Exercice"
            hint="Laissez vide pour que l'assistant demande la période"
            value={exercice ?? ""}
            disabled={chargement}
            onChange={(evenement) =>
              setExercice(
                evenement.target.value
                  ? Number(evenement.target.value)
                  : null
              )
            }
            options={[
              { value: "", label: "Préciser la période" },
              ...exercices.map((annee) => ({
                value: annee,
                label: `Exercice ${annee}`,
              })),
            ]}
          />
        ) : null
      }
    >
      {document && (
        <div className="page-container__filtre" role="status">
          <span>
            Document ciblé : <strong>{document}</strong>
          </span>
          <button
            type="button"
            className="page-container__filtre-retrait"
            onClick={() => setDocument(null)}
            disabled={chargement}
          >
            Retirer le filtre
          </button>
        </div>
      )}

      <ChatWindow
        pret={pret}
        messages={messages}
        chargement={chargement}
        texteErreur={texteErreur}
        referentiel={referentiel}
        exercices={exercices}
        exercice={exercice}
        document={document}
        onEnvoyer={envoyer}
        onProposer={poserSuggestion}
        onReinitialiser={reinitialiser}
      />
    </PageContainer>
  );
}
