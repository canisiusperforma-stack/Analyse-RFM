# Architecture de l'assistant conversationnel

Ce document décrit le chemin suivi par une question posée à l'assistant, de la
réception à la réponse. Il décrit le code : chaque affirmation renvoie à un
fichier, et les exemples sont des sorties observées, pas des intentions.

## 1. Principe directeur

> **Le modèle de langage ne choisit jamais la source, et ne produit jamais un
> chiffre que le backend n'a pas calculé.**

Tout le reste en découle. Le routeur est du code déterministe, les agrégations
sont calculées par le backend, et la réponse du modèle est confrontée à un index
des valeurs autorisées avant d'être renvoyée. Un modèle indisponible, muet ou
trop inventif dégrade donc la qualité de la forme, jamais l'exactitude du fond.

## 2. Vue d'ensemble

```
                       ┌──────────────────────────┐
   Question ──────────▶│  query_router.classifier │  aucune source
                       │  (déterministe, sans LLM)│  n'est touchée
                       └────────────┬─────────────┘
                                    │ 4 chemins
        ┌───────────────┬───────────┴──────┬─────────────────┐
        ▼               ▼                  ▼                 ▼
      DATA             RAG              DATA_RAG         INCONNUE
        │               │                  │                 │
        ▼               ▼                  ▼                 ▼
   MongoDB        vector_store         les deux        périmètre
   + indicator_   (filtre d'accès       (le calcul      annoncé,
    service        dans la requête)      décide)        aucun chiffre
        │               │                  │
        └───────┬───────┴──────────────────┘
                ▼
     ┌──────────────────────┐   figeage    ┌──────────────────┐
     │  ContexteAssistant   │─────────────▶│  LLM (optionnel) │
     │  (index des valeurs  │              └────────┬─────────┘
     │   autorisées)        │                       ▼
     └──────────────────────┘            ┌─────────────────────┐
                                         │ response_validator  │
                                         │ + rag.grounding     │
                                         └──────────┬──────────┘
                                                    │ rejet ?
                                                    ▼
                                       réponse déterministe (code)
```

## 3. Étape 1 — Le routeur (`app/ai/query_router.py`)

`classifier(question, exercice_impose=None)` renvoie une `Decision` contenant la
route, l'intention analysée et l'indicateur identifié.

### Pourquoi la classification se fait sans modèle

Un routeur nourri d'un LLM ne serait pas auditable : il produirait une étiquette
dont personne ne pourrait dire à quoi elle correspond, et dont l'erreur se
traduirait par une requête inutile — voire par une source manquante. Ici, chaque
décision est la sortie d'une somme de motifs pondérés dont les tables sont dans le
fichier, et le résultat est validé par un schéma Pydantic (`RouteQuery`) qui
refuse toute incohérence entre le chemin annoncé et les sources demandées.

### Les quatre chemins

| Route | Services interrogés | Sens |
|---|---|---|
| `DATA` | `mongodb` | grandeur calculée par la plateforme |
| `RAG` | `vectorstore`, `llm` | ce que disent les documents autorisés |
| `DATA_RAG` | `mongodb`, `vectorstore`, `llm` | un chiffre confronté à un référentiel |
| `INCONNUE` | — | hors périmètre, aucun chiffre produit |

Cette table (`CHEMINS`) est la seule autorité sur ce qu'un chemin coûte ;
l'orchestrateur n'en déduit rien par lui-même.

### Les quatre tables de motifs

La difficulté n'est pas de reconnaître « procédure » comme un mot documentaire.
C'est de reconnaître que **« Quelle est la procédure de remboursement ? » n'est
pas une question de données**, malgré le mot « remboursement » qu'elle contient.
L'inverse est vrai aussi : « le niveau d'exécution observé respecte-t-il les
règles des documents ? » est une question de données *et* de documents, avec les
mêmes mots. Un lexique unique ne distingue pas ces cas ; quatre tables le font.

| Table | Ce qu'elle recognise | Poids |
|---|---|---|
| `NOYAU_DOCUMENTAIRE` | l'objet même de la demande : procédure, règle, critère, instruction, dispositif | 2–4 |
| `REFERENCE_IMPLICITE` | mention de document sans dire lequel (« le document », « note de service ») | 2–3 |
| `CROISEMENT` | le verbe qui **exige** un référentiel : « conforme », « respecte », « prévu par » | 4–5 |
| `DEMANDE_CHIFFRE` | ce qui distingue « quel montant ? » d'une référence | 1–3 |

Le **croisement** est la table décisive. Ces verbes présupposent une norme : ils
sont sans réponse tant que l'observé et la norme n'ont pas été réunis. Leur
présence, combinée à un indicateur identifiable, suffit à produire `DATA_RAG`.

### Saturer l'indice plutôt que le sommer

Les indices sont ramenés par `1 - exp(-poids / 3.0)` et non par une division. Une
somme brute n'est pas comparable à un seuil : « combien de bénéficiaires » et
« procédure de remboursement » contiendraient des scores sans signification
commune. La forme saturante donne 0 à l'absence, tend vers 1 sans jamais
l'atteindre, et est **monotone** : doubler les occurrences d'un motif double
l'indice, ce qui permet de régler le seuil une fois pour toutes. La borne ouverte
vers 1 est volontaire — aucune combinaison de motifs ne doit produire un indice
indiscernable d'une certitude.

### Ambiguïté sur la période

« Quel est le taux d'exécution ? » est une question recevable mais impropre : de
quel exercice ? Le routeur **ne choisit pas d'année à la place de l'utilisateur**.
Il signale `besoin_clarification`, et l'orchestrateur s'interrompt avant toute
source. Choisir 2025 parce que c'est le plus récent reviendrait à répondre à une
autre question que celle posée — une faute silencieuse.

La demande est limitée à `INDICATEURS_BORNES_A_UN_EXERCICE` (modules `budget`,
`analyses`, `previsions`, `anomalies`). Les indicateurs de population décrivent un
état et se lisent sans année ; en exiger une serait une formalité sans
information ajoutée.

## 4. Étape 2 — L'analyse d'intention (`app/ai/query_analyzer.py`)

Le routeur ne réimplémente pas l'analyse : il s'y branche. `analyser_question`
fournit 10 intentions de domaine, le type d'agrégation et les entités.

| Intention | Exemple |
|---|---|
| `synthese_globale`, `population`, `budget`, `remboursements` | « Compare les actifs et les pensionnés » |
| `analyse_temporelle`, `statistiques`, `anomalies`, `previsions`, `simulations` | « Quel mois présente le montant le plus élevé ? » |
| `hors_perimetre` | tout le reste |

**Agrégations** : `total`, `argmax`, `argmin`, `comparaison`. La comparaison
l'emporte sur le superlatif (« le mois le plus élevé *par rapport à* 2024 »).

**Entités extraites** : `exercice` (année absolue et formulations relatives comme
« dernier exercice » → `-1`), `communes`, `situations` (actif / pensionné),
`types_prestation`, `mois` (noms et abréviations françaises).

Le texte est normalisé en NFKD, accents retirés, ponctuation réduite à des
espaces. Le module ne lève jamais : une question illisible donne
`hors_perimetre`.

## 5. Étape 3 — L'identifiant d'indicateur (`app/ai/indicator_service.py`)

21 indicateurs, chacun avec une formule et une unité. Ils constituent le
vocabulaire chiffré de la plateforme.

| Module | Indicateurs |
|---|---|
| `budget` | `taux_execution`, `credits`, `execute`, `disponible`, `solde`, `engagement`, `mois_extremum` |
| `population` | `total`, `actifs`, `pensionnes`, `beneficiaires_rfm`, `croisement`, `comparaison_situations`, `moyenne_age` |
| `remboursements` | `demandes`, `montant_paye`, `taux_execution`, `mois_extremum` |
| `analyses` | `statistiques` |
| `anomalies` | `total` |
| `previsions` | `serie` |

`resoudre()` exécute la formule et renvoie un `ResultatStructure` contenant les
mesures, le mode de calcul, et — lorsque la donnée manque — un **motif
d'absence**. Il ne produit jamais d'estimation à la place d'une valeur absente.

Les calculs exacts que le modèle ne doit pas faire (extrémum d'une série, écart
et parts entre deux populations) sont performed ici, par le code.

> **Argents en `Decimal128`.** Jamais de flottant : les montants sont en ariary et
> les arrondis binaires produiraient des écarts visibles.

## 6. Étape 4 — L'orchestration (`app/ai/assistant_service.orchestrer`)

Chemin d'exécution, identique pour les quatre routes :

1. contrôle d'accès et de longueur ;
2. **routage**, avant toute source sollicitée ;
3. arrêt immédiat sur demande de précision, sans interroger quoi que ce soit ;
4. calcul backend, si le chemin exige des données ;
5. recherche documentaire, si le chemin exige des documents ;
6. **figeage du contexte** — l'objet `ContexteAssistant` est alors complet ;
7. génération, si elle est possible ;
8. contrôle, et repli sur un texte produit par le code en cas de doute.

**L'étape 6 porte la garantie.** Tant qu'elle n'a pas eu lieu, aucune génération
n'est tentée ; une fois qu'elle a eu lieu, le modèle ne peut plus élargir sa
fenêtre, et chaque valeur qu'il écrit est confrontée à l'index de ce contexte
figé.

### Ordre d'exécution

Le routeur est consulté avant toute source, pour qu'aucune requête ne parte vers
un service inutile. Le budget est sollicité **avant** la recherche documentaire :
c'est le calcul qui décide si la comparaison a un objet, et interroger les
documents pour rien coûte une recherche vectorielle dont le résultat sera jeté.
Le modèle est appelé en dernier.

### Dégradation plutôt que refus

Une partie inaccessible n'annule pas l'autre. Un utilisateur qui peut lire les
documents mais pas le budget obtient quand même la partie documentaire, avec la
limite énoncée dans la réponse. Refuser tout aurait été plus simple, et aurait été
une régression fonctionnelle.

Les deux provenances sont composées sans être confondues. `reponse_deterministe_fusion`
juxtapose ce que les données montrent et ce que les documents disent **sans les
rapprocher**, et le dit explicitement. Rapprocher serait dire « 78,4 % est
inférieur au seuil de 80 % » — un énoncé vrai, mais que le code ne peut pas
établir seul : il ignore que le seuil s'applique. Le laisser au modèle laisserait
passer une interprétation non contrôlée.

## 7. Étape 5 — Le contrôle (`app/ai/response_validator.py`, `app/rag/grounding.py`)

Deux contrôles indépendants, qui ne se recouvrent pas :

| Contrôle | Vérifie |
|---|---|
| `grounding.valider` | chaque marqueur `[Sn]` désigne un extrait réellement fourni ; les affirmations d'absence sont cohérentes avec la présence effective d'extraits |
| `valider_reponse` | chaque nombre écrit figure dans l'index des valeurs autorisées, tolérance `LLM_TOLERANCE_NUMERIQUE` |

**L'ordre n'est pas indifférent.** L'index retient le contenu des extraits : une
valeur affirmée sans citation mais présente dans un extrait passerait le contrôle
numérique. Inversement, un marqueur valide ne dit rien des chiffres qu'il
accompagne. Il faut les deux.

En cas de rejet, la réponse n'est **jamais régénérée** : elle est remplacée par le
texte déterministe, produit par le code à partir des sources réellement retenues.
C'est ce qui garantit qu'un incident du modèle se traduit par une réponse plus
pauvre, jamais par une réponse fausse.

## 8. Le modèle de langage (`app/ai/llm_service.py`)

Client HTTP `urllib` vers une API compatible OpenAI. Cible par défaut : Ollama
(`http://127.0.0.1:11434/v1`, `llama3.1`). VLLM, LM Studio et OpenAI
fonctionnent aussi, sans changement de code.

**`LLM_ENABLED=false` par défaut.** L'assistant reste alors pleinement
fonctionnel : toutes les réponses sont produites par le code à partir des
résultats du backend. Le LLM n'améliore que la forme.

| Réglage | Défaut | Rôle |
|---|---|---|
| `LLM_ENABLED` | `false` | court-circuite tout appel au modèle |
| `LLM_TEMPERATURE` | `0.0` | déterminisme de la formulation |
| `LLM_TOKENS_MAX` | `900` | borne la réponse |
| `LLM_DELAI_MAX` | `60` | abandon sur modèle muet |
| `LLM_QUESTION_MAX` | `500` | refus avant traitement |
| `LLM_TOLERANCE_NUMERIQUE` | `0.01` | tolérance du contrôle des chiffres |

## 9. API

| Route | Rôle |
|---|---|
| `POST /api/v1/assistant/query` | **point d'entrée** : route, orchestre, contrôle |
| `POST /api/v1/assistant/question` | chemin `DATA` historique, sans routage |
| `GET /api/v1/assistant/routes` | chemins, seuils et coût de chacun |
| `GET /api/v1/assistant/referentiel` | catalogue d'indicateurs, intentions, garanties |
| `GET /api/v1/assistant/exercices` | exercices disponibles en base |
| `GET /api/v1/assistant/etat` | état du modèle et du RAG |

Toutes exigent la permission `assistant:utiliser`.

## 10. Réglages du routeur

| Réglage | Défaut | Rôle |
|---|---|---|
| `ASSISTANT_FUSION_ENABLED` | `true` | `false` fait retomber le routeur sur le chemin `DATA` seul |
| `ASSISTANT_CLARIFICATION` | `true` | `false` désactive la demande de précision sur l'exercice |
| `ASSISTANT_ROUTEUR_SEUIL_RAG` | `0.34` | indice documentaire au-delà duquel on interroge les documents |
| `ASSISTANT_ROUTEUR_SEUIL_DATA` | `0.30` | indice de données |
| `ASSISTANT_RAG_SEUIL` | *(vide)* | Force le seuil ; vide hérite de `RAG_SEUIL_PERTINENCE` |
| `ASSISTANT_RAG_TOP_K` | `4` | extraits fournis au modèle |

`ASSISTANT_FUSION_ENABLED=false` restaure exactement l'assistant d'avant la
fusion : c'est un repli, pas un refus.

## 11. Exemples vérifiés

Sorties de `query_router.classifier` sur la version courante :

| Question | Route | Indicateur |
|---|---|---|
| Combien de bénéficiaires sont actifs en 2025 ? | `DATA` | `population.actifs` |
| Quel est le taux d'exécution budgétaire en 2025 ? | `DATA` | `budget.taux_execution` |
| Quel est le montant remboursé en 2025 ? | `DATA` | `remboursements.montant_paye` |
| Quelle est la procédure de remboursement ? | `RAG` | — |
| Quelles pièces faut-il fournir pour un dossier ? | `RAG` | — |
| Quelles pièces justificatives sont exigées ? | `RAG` | — |
| Faut-il un agrément pour ouvrir une pharmacie ? | `RAG` | — |
| Le taux d'exécution respecte-t-il les règles prévues par les textes ? | `DATA_RAG` | `budget.taux_execution` |
| Le montant remboursé en 2025 est-il conforme aux dispositions du document ? | `DATA_RAG` | `remboursements.montant_paye` |
| Quelle est la température à Perpignan en juin ? | `INCONNUE` | — |

Cas particuliers :

| Question | Route | Raison |
|---|---|---|
| Quel est le taux d'exécution ? | `DATA` + clarification | exercice absent, l'utilisateur est interrogé |
| Combien de bénéficiaires ? | `DATA` | indicateur de population, se lit sans année |

## 12. Tests

```
python tests/test_assistant.py
```

12 contrôles, sans base de données. Le premier fige le routage des quatre chemins
— c'est le seul point où une question peut partir vers la mauvaise source, et
l'erreur y est silencieuse : une question documentaire envoyée en `DATA` ne
produit aucun signal, seulement une réponse vide.

```
python tests/test_rbac.py     # matrice des permissions
npm test                      # côté frontend
```

## 13. Limites connues

- **Le lexique est énuméré.** Chaque terme est une expression régulière
  maintenance à la main. « Quelles pièces faut-il fournir » a été mal routé
  longtemps parce que le motif attendait « pièces à fournir », sans l'auxiliaire
  que le français insère entre le nom et le verbe. Le test de routage existe pour
  que ces cas reviennent au lieu de disparaître.
- **Les embeddings sont lexiques.** `app/rag/embeddings.py` hache des n-grammes ;
  ce n'est pas un modèle sémantique. Voir `docs/rag.md`.
- **Aucune notion de conversation dans le routage.** Chaque question est routée
  seule ; l'historique est transmis au modèle mais ne sert pas au routeur.
- **`hors_perimetre` n'est pas élargissable.** Aucune source hors plateforme
  n'est autorisée, par construction.

## Voir aussi

- [`rag.md`](rag.md) — le canal documentaire
- [`architecture.md`](architecture.md) — l'ensemble du système
- [`securite.md`](securite.md) — RBAC et permissions
