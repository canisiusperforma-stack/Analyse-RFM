// Tests de la logique d'affichage de l'assistant.
//
// `lib/assistant.js` ne dépend que de lui-même : il peut donc être chargé
// directement, sans résolution de l'alias `@/`. Ces tests pinent les deux
// règles qui font la valeur de cet écran :
//
//   1. aucune valeur n'est rendue autrement que le backend ne l'a rendue —
//      `valeur_affichee` est reprise telle quelle, jamais reformatée ;
//   2. le statut du calcul et la provenance rédactionnelle sont distingués, en
//      particulier quand le modèle a produit une réponse écartée.
//
// Lancement : npm test  (node --test tests/)

import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const source = readFileSync(path.join(__dirname, "..", "lib", "assistant.js"), "utf8");
const {
  MAX_QUESTION,
  QUESTIONS_EXEMPLES,
  avertissementModeleEcarte,
  avertissementsVisibles,
  blocDonnees,
  clarification,
  confiancePourcent,
  documents,
  documentsAffichables,
  estFusion,
  exerciceUtilise,
  libelleIntent,
  libelleProvenance,
  libelleStatut,
  limitesVisibles,
  mesures,
  mesuresDonnees,
  mesuresSecondaires,
  paragraphes,
  raisonChemin,
  resumeReponse,
  tableauAffichable,
  tableauDonnees,
  varianteProvenance,
  varianteStatut,
} = await import(
  "data:text/javascript;base64," + Buffer.from(source).toString("base64")
);

/** Compte rendu minimal, avec les valeurs déjà rendues par le backend. */
function compteRendu(surcharge = {}) {
  return {
    question: "Quel est le taux d'exécution du budget RFM ?",
    reponse: "Taux d'exécution budgétaire - 73,1 %.",
    analyse: { intention: "budget", agregation: "total", confiance: 1 },
    resultat: {
      indicateur: "budget.taux_execution",
      libelle: "Taux d'exécution budgétaire",
      unite: "pourcentage",
      statut: "disponible",
      mesures: [
        {
          cle: "taux_execution",
          libelle: "Taux d'exécution",
          valeur: 0.7314,
          unite: "pourcentage",
          valeur_affichee: "73,1 %",
        },
      ],
      tableau: null,
      absence: null,
      note: "valeur lue dans la synthèse budgétaire",
    },
    sources: [
      {
        module: "budget",
        fonction: "budget_service.calculer_synthese",
        exercice: 2025,
      },
    ],
    controle: { conforme: true, note: "1 chiffre vérifié sur 1" },
    generee_par: "backend",
    modele: null,
    regle: "Les chiffres proviennent du backend.",
    avertissements: [],
    hors_perimetre: false,
    reponse_rejetee: null,
    exercice: 2025,
    duree_ms: 12,
    ...surcharge,
  };
}

describe("rendu des valeurs du backend", () => {
  test("aucune mesure n'est réinterprétée par le client", () => {
    // Une valeur inventée par le client serait un nombre absent du résultat
    // structuré : `valeur_affichee` est donc la seule source de vérité.
    const mesure = mesures(compteRendu())[0];
    assert.equal(mesure.valeur_affichee, "73,1 %");
    // La valeur brute reste disponible, mais le module ne la reformate pas.
    assert.equal(mesure.valeur, 0.7314);
  });

  test("une mesure multiple n'est jamais rendue par le client", () => {
    const rapport = compteRendu();
    rapport.resultat.mesures = [
      rapport.resultat.mesures[0],
      {
        cle: "part",
        libelle: "Part du budget",
        valeur: 0.4021,
        unite: "pourcentage",
        valeur_affichee: "40,2 %",
      },
    ];
    const secondaires = mesuresSecondaires(rapport);
    // La principale est déjà dans le texte rédigé par le backend.
    assert.equal(secondaires.length, 1);
    assert.equal(secondaires[0].valeur_affichee, "40,2 %");
  });

  test("une enveloppe sans résultat ne fait pas échouer le rendu", () => {
    assert.deepEqual(mesures({}), []);
    assert.deepEqual(mesuresSecondaires({}), []);
    // Aucun champ n'est supposé exister : le résumé est neutre, pas une erreur.
    const resume = resumeReponse({});
    assert.equal(resume.indicateur, null);
    assert.equal(resume.statut, null);
    assert.equal(resume.exercice, null);
    assert.equal(resumeReponse(null), null);
  });
});

describe("statut du calcul", () => {
  test("chaque statut a une variante et un libellé", () => {
    assert.equal(varianteStatut("disponible"), "success");
    assert.equal(varianteStatut("partiel"), "warning");
    assert.equal(varianteStatut("absent"), "warning");
    assert.equal(varianteStatut("inconnu"), "neutral");
    assert.equal(libelleStatut("absent"), "Donnée absente");
  });

  test("le motif d'absence est restitué tel quel", () => {
    const rapport = compteRendu();
    rapport.resultat.statut = "absent";
    rapport.resultat.absence = "Aucun crédit voté n'est enregistré.";
    assert.equal(resumeReponse(rapport).absence, rapport.resultat.absence);
  });
});

describe("provenance rédactionnelle", () => {
  test("une réponse backend est neutre", () => {
    const rapport = compteRendu();
    assert.equal(varianteProvenance(rapport), "neutral");
    assert.equal(libelleProvenance(rapport), "Réponse produite par le backend");
  });

  test("une réponse rédigée par le modèle est signalée comme telle", () => {
    const rapport = compteRendu({ generee_par: "llm", modele: { nom: "qwen" } });
    assert.equal(varianteProvenance(rapport), "primary");
    assert.equal(libelleProvenance(rapport), "Réponse rédigée par le modèle");
  });

  test("une réponse écartée est distinguée d'une réponse backend simple", () => {
    // Le cas le plus important : le modèle a parlé, sa réponse a été refusée.
    // L'utilisateur doit le voir plutôt que de croire une rédaction banale.
    const rapport = compteRendu({
      generee_par: "llm",
      reponse_rejetee: { motif: "valeurs non autorisées", ecarts: [{ valeur: 9 }] },
    });
    assert.equal(varianteProvenance(rapport), "warning");
    assert.equal(libelleProvenance(rapport), "Réponse backend (modèle écarté)");
    assert.match(avertissementModeleEcarte(rapport), /1 valeur\(s\)/);
  });

  test("aucun avertissement quand rien n'a été écarté", () => {
    assert.equal(avertissementModeleEcarte(compteRendu()), null);
  });
});

describe("exercice et sources", () => {
  test("l'exercice affiché est celui appliqué par le service", () => {
    // Il peut différer de l'exercice demandé : l'interface annonce le calcul
    // réellement effectué, pas l'intention.
    assert.equal(exerciceUtilise(compteRendu()), 2025);
    assert.equal(exerciceUtilise({}), null);
  });

  test("un tableau vide n'est pas affiché", () => {
    assert.equal(tableauAffichable(compteRendu()), null);
    const rapport = compteRendu();
    rapport.resultat.tableau = { colonnes: ["Situation", "Total"], lignes: [] };
    assert.equal(tableauAffichable(rapport), null);
    rapport.resultat.tableau = { colonnes: ["Situation", "Total"], lignes: [["Pensionnés", 40]] };
    assert.equal(tableauAffichable(rapport).lignes[0][0], "Pensionnés");
  });
});

describe("texte de la réponse", () => {
  test("une réponse multiligne devient plusieurs paragraphes", () => {
    assert.deepEqual(paragraphes("Un.\n\nDeux."), ["Un.", "Deux."]);
    assert.deepEqual(paragraphes(""), []);
  });
});

describe("amorces", () => {
  test("les questions proposées sont dans la limite du backend", () => {
    assert.ok(QUESTIONS_EXEMPLES.length >= 4);
    for (const question of QUESTIONS_EXEMPLES) {
      assert.ok(question.length > 0 && question.length <= MAX_QUESTION);
    }
  });
});

// ---------------------------------------------------------------------------
// Chemin d'orchestration : DATA / RAG / DATA_RAG
// ---------------------------------------------------------------------------

/** Réponse de fusion : un chiffre calculé et un texte cité. */
function reponseFusion(surcharge = {}) {
  return {
    question: "Le taux d'exécution respecte-t-il le seuil du texte ?",
    intent: "DATA_RAG",
    reponse: "Taux d'exécution - 73,1 % [S1].",
    chemin: ["routeur", "mongodb", "vectorstore", "llm", "controle"],
    confidence: 0.87,
    clarification: null,
    donnees: null,
    data: {
      indicateur: "budget.taux_execution",
      libelle: "Taux d'exécution budgétaire",
      statut: "disponible",
      mesures: [
        {
          cle: "taux_execution",
          libelle: "Taux d'exécution",
          valeur: 0.7314,
          unite: "pourcentage",
          valeur_affichee: "73,1 %",
        },
      ],
      tableau: null,
      absence: null,
      note: null,
      source: "MongoDB",
    },
    documents: [
      {
        etiquette: "S1",
        document: "decret-2024-001.pdf",
        extrait: "Le taux d'exécution minimal est fixé à 80 %.",
        page: 4,
        cite: true,
      },
    ],
    limites: ["Le seuil cité provient du document S1."],
    analyse: { intention: "budget", confiance: 1, raison: "croisement" },
    generee_par: "llm",
    regle: "Les chiffres proviennent du backend.",
    exercice: 2025,
    duree_ms: 34,
    ...surcharge,
  };
}

describe("chemin d'orchestration", () => {
  test("chaque chemin a un libellé, et un chemin inconnu n'en invente aucun", () => {
    assert.equal(libelleIntent("DATA"), "Données calculées");
    assert.equal(libelleIntent("RAG"), "Documents");
    assert.equal(libelleIntent("DATA_RAG"), "Données et documents");
    assert.equal(libelleIntent("INCONNUE"), "Hors périmètre");
    // Une réponse d'une version antérieure ne doit pas afficher « undefined ».
    assert.equal(libelleIntent("QUELQUE_CHOSE"), null);
    assert.equal(libelleIntent(undefined), null);
  });

  test("les données et les documents restent deux provenances distinctes", () => {
    const fusion = reponseFusion();
    // Le chiffre vient de `data`, l'extrait de `documents` : jamais l'inverse.
    assert.equal(mesuresDonnees(fusion)[0].valeur_affichee, "73,1 %");
    assert.equal(mesures(fusion).length, 0, "aucune mesure hors du bloc data");
    assert.equal(documents(fusion)[0].document, "decret-2024-001.pdf");
    assert.equal(estFusion(fusion), true);
  });

  test("une réponse de l'ancien chemin ne casse pas le rendu", () => {
    // `compteRendu` du §/question n'a ni `data` ni `documents` : tous les
    // accesseurs doivent rester neutres au lieu de lever.
    const ancien = compteRendu();
    assert.equal(blocDonnees(ancien), null);
    assert.deepEqual(mesuresDonnees(ancien), []);
    assert.deepEqual(documents(ancien), []);
    assert.equal(documentsAffichables(ancien), false);
    assert.equal(clarification(ancien), null);
    assert.deepEqual(limitesVisibles(ancien), []);
    assert.equal(confiancePourcent(ancien), null);
    assert.equal(raisonChemin(ancien), null);
    assert.equal(libelleIntent(ancien.intent), null);
  });

  test("aucun bloc n'est rendu quand il n'a rien à montrer", () => {
    // Une recherche menée sans succès ne doit pas laisser croire qu'elle a eu
    // lieu : le bloc « Documents » est conditionné à l'existence d'extraits.
    const vide = reponseFusion({ documents: [] });
    assert.equal(documentsAffichables(vide), false);
    const sansTableau = reponseFusion();
    sansTableau.data.tableau = { colonnes: ["A"], lignes: [] };
    assert.equal(tableauDonnees(sansTableau), null);
  });

  test("la demande de précision est restituée et la confiance arrondie", () => {
    // Forme réellement émise par le backend : un objet, non une chaîne.
    const demande = reponseFusion({
      intent: "DATA",
      clarification: {
        motif: "Indicateur identifié : Taux d'exécution budgétaire.",
        question: "Taux d'exécution budgétaire : pour quel exercice ?",
        parametres_manquants: ["exercice"],
      },
    });
    // Le composant rend cette valeur comme un enfant React : renvoyer l'objet
    // entier le faisait planter. Seule la question doit ressortir.
    assert.equal(
      clarification(demande),
      "Taux d'exécution budgétaire : pour quel exercice ?",
    );
    assert.equal(typeof clarification(demande), "string");

    // Une chaîne reste acceptée : une réponse ancienne ne doit pas casser le rendu.
    assert.equal(
      clarification({ clarification: "Pour quel exercice ? " }),
      "Pour quel exercice ?",
    );

    // Un objet sans question exploitable ne produit rien à afficher.
    assert.equal(clarification({ clarification: { motif: "x" } }), null);
    assert.equal(clarification({ clarification: { question: "  " } }), null);

    assert.equal(confiancePourcent(demande), 87);
    // Une confiance non numérique ne doit pas produire « NaN % ».
    assert.equal(confiancePourcent({ confidence: "haut" }), null);
    assert.equal(confiancePourcent(reponseFusion({ confidence: 0.5 })), 50);
  });

  test("les limites annoncées sont vidées de leurs entrées vides", () => {
    assert.deepEqual(limitesVisibles(reponseFusion()), [
      "Le seuil cité provient du document S1.",
    ]);
    assert.deepEqual(limitesVisibles({ limites: [null, "", "x"] }), ["x"]);
  });

  // ---------------------------------------------------------------------------

  /**
   * Réponse de clarification capturée sur le backend, non fabriquée ici.
   *
   * Le bug que ce test verrouille avait une cause précise : les tests
   * construisaient eux-mêmes la réponse, sur une forme *devinée*. Le test passait
   * donc, et l'écran plantait sur la réponse réelle, où `clarification` est un
   * objet. Une charge utile écrite à la main ne peut pas détecter la dérive de
   * contrat qu'elle contient ; seule une capture du serveur le peut. Ce fichier
   * est à régénérer avec :
   *
   *   python -c "import asyncio,json,sys; sys.path.insert(0,'backend'); \
   *     from app.ai.assistant_service import orchestrer; \
   *     json.dump(asyncio.run(orchestrer('Quel est le taux d\'execution ?')), \
   *       open('frontend/tests/fixtures/clarification.json','w'), \
   *       ensure_ascii=False, indent=2)"
   */
  const REponseReelle = JSON.parse(
    readFileSync(path.join(__dirname, "fixtures", "clarification.json"), "utf8"),
  );

  test("la demande de précision réelle s'affiche comme du texte", () => {
    assert.equal(REponseReelle.intent, "DATA");
    assert.deepEqual(REponseReelle.chemin, ["routeur", "clarification"]);

    // Le backend renvoie bien un objet, et non une chaîne.
    assert.equal(typeof REponseReelle.clarification, "object");
    assert.ok(REponseReelle.clarification.question);

    // L'accesseur doit en extraire une chaîne affichable.
    const demande = clarification(REponseReelle);
    assert.equal(typeof demande, "string");
    assert.equal(demande, REponseReelle.clarification.question);
    assert.match(demande, /pour quel exercice/i);
  });

  test("aucun accesseur ne renvoie un objet nu sur une réponse réelle", () => {
    // React refuse de rendre un objet. Tout ce que le composant écrit
    // directement dans le JSX doit donc être une chaîne, un nombre ou un
    // tableau. Les accesseurs qui rendent un objet sont tolérés ici seulement
    // parce que le composant les lit par propriété (`resume?.libelle`), jamais
    // comme un enfant — ce test sert à détecter qu'un jour on les rendrait.
    const rendus = [
      ["avertissementModeleEcarte", avertissementModeleEcarte],
      ["avertissementsVisibles", avertissementsVisibles],
      ["blocDonnees", blocDonnees],
      ["clarification", clarification],
      ["confiancePourcent", confiancePourcent],
      ["documents", documents],
      ["documentsAffichables", documentsAffichables],
      ["exerciceUtilise", exerciceUtilise],
      ["limitesVisibles", limitesVisibles],
      ["mesures", mesures],
      ["mesuresDonnees", mesuresDonnees],
      ["mesuresSecondaires", mesuresSecondaires],
      ["paragraphes", paragraphes],
      ["raisonChemin", raisonChemin],
      ["tableauAffichable", tableauAffichable],
      ["tableauDonnees", tableauDonnees],
      ["estFusion", estFusion],
      ["varianteProvenance", varianteProvenance],
      ["varianteStatut", varianteStatut],
    ];

    for (const [nom, accesseur] of rendus) {
      const valeur = accesseur(REponseReelle);
      const nu = valeur !== null && typeof valeur === "object" && !Array.isArray(valeur);
      assert.equal(nu, false, `${nom} renvoie un objet non rendu : ${JSON.stringify(valeur)}`);
    }
  });

  test("la raison du chemin n'est affichée que si elle existe", () => {
    assert.equal(raisonChemin(reponseFusion()), "croisement");
    assert.equal(raisonChemin({ analyse: { raison: "   " } }), null);
    assert.equal(raisonChemin({}), null);
  });
});
