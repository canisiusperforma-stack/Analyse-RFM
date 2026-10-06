# Le canal documentaire (RAG)

> **Le modèle n'est jamais consulté sans sources, et une réponse non fondée
> n'est jamais renvoyée.**

Cette règle est tenue par la structure du pipeline, pas par une consigne donnée
au modèle. Chaque étape below rend l'étape suivante impossible à contourner.

## 1. Vue d'ensemble

```
   Document (pdf, txt, md, csv, json, xlsx)
        │
        ▼
   document_loader ── extraction du texte          ← échec = document marqué
        │                                              en erreur, reste
        ▼                                              téléchargeable
   text_splitter ── nettoyage + découpage           ← ne change jamais le sens
        │                                              (900 car., recouvr. 150)
        ▼
   embeddings ────── vecteurs de n-grammes hachés   ← sans modèle, sans réseau
        │
        ▼
   vector_store ──── MongoDB + filtre d'accès       ← l'ACL entre dans la
        │                                              requête, pas après
        ▼
   retriever ─────── hybride dense + lexical         ← seuil de pertinence
        │                                              + diversité
        ▼
   [S1] [S2] [S3] ── contexte numéroté              ← jamais tronqué
        │
        ▼
   prompt_builder ── consignes d'ancrage
        │
        ▼
   LLM (optionnel) ── rédaction
        │
        ▼
   grounding ─────── citations et chiffres contrôlés
        │
        ├── conforme ──▶ réponse
        └── rejet ─────▶ extraits bruts, tels quels  ← jamais une régénération
```

## 2. Étapes « Indexation » et « Recherche »

### `document_loader` — extraction

Formats : `pdf`, `txt`, `md`, `csv`, `json`, `xlsx` (`RAG_EXTENSIONS`). Taille
maximale 20 Mo (`RAG_TAILLE_MAX_OCTETS`). Le binaire est conservé dans GridFS ;
seule l'empreinte sert au dossier.

Un échec d'extraction **n'interrompt rien** : le document est marqué en erreur et
reste consultable et téléchargeable, lisiblement indisponible pour la recherche.

### `text_splitter` — nettoyage et découpage

Ces deux opérations sont ici parce qu'elles obéissent à la même contrainte : **ne
rien changer au sens**. Un texte administratif est dense en nombres, en références
d'articles et en sigles ; toute normalisation hasardeuse y détruit une
information.

Nettoyage : Unicode NFC, espaces insécables ramenés à des espaces ordinaires,
caractères de contrôle supprimés, groupes de milliers assemblés (« 1 000 000 » →
« 1000000 »), césures recollées (« phenomè- » + saut de ligne + « ne » →
« phénomène »). Les nombres, montants et références d'articles ne sont **pas**
touchés.

Découpage : 900 caractères (`RAG_CHUNK_TAILLE`), minimum 180
(`RAG_CHUNK_TAILLE_MIN`), recouvrement 150 (`RAG_CHUNK_RECOUVREMENT`).

`construire_contexte()` **ne tronque jamais un morceau** : au-delà de
`RAG_CONTEXTE_CARACTERES_MAX`, il retire des morceaux entiers. Un extrait coupé
en plein milieu d'une phrase devient une source citable mais fausse.

### `embeddings` — vecteurs comparables

Deux vecteurs doivent être comparables d'un appel à l'autre, d'un processus à
l'autre, et après un redémarrage. Cette contrainte dirige tout le choix : la
fonction de vectorisation ne dépend d'aucun état mémorisé, d'aucun modèle
téléchargé, d'aucun appel réseau.

Le texte est découpé en **n-grammes de mots (1–2) et de caractères (3–5)**, chaque
n-gramme est envoyé dans une case d'un vecteur de `RAG_EMBED_DIM` (2048)
dimensions par hachage, la fréquence est comprimée logarithmiquement, puis le
vecteur est normalisé. La similarité est le produit scalaire, soit le cosinus.

`scikit-learn` est déjà une dépendance du projet (`app.ml`) et son
`HashingVectorizer` ne s'entraîne pas.

> **Ce n'est pas un modèle sémantique.** Un vecteur de n-grammes mesure une
> proximité de forme. Le registre `embeddings.FONCTIONS` est le point de
> remplacement prévu : `RAG_EMBED_MODELE` sélectionne la fonction, et un modèle
> réel peut y être ajouté sans toucher au reste du pipeline. Changer de modèle
> impose de réindexer tous les documents — les dimensions et la sémantique
> changent.

### `vector_store` — dépôt et barrière de sécurité

MongoDB sert à la fois de dépôt des vecteurs et de **point d'application du
filtrage d'accès**. C'est délibéré : la clause `$or` construite par
`app.models.document.filtre_acces_documents` entre dans la requête, si bien
qu'un morceau interdit n'est jamais transmis au processus qui classe les
résultats. Le classement s'exécute sur des candidats **déjà autorisés** — il ne
peut pas « remonter » vers un document interdit, puisqu'il ne le voit pas. Un
deuxième contrôle par résultat complète la défense en profondeur.

Sélection des candidats, deux régimes :

| Volume de corpus autorisé | Régime |
|---|---|
| ≤ `RAG_RECHERCHE_CANDIDATS` (200) | tous les morceaux sont chargés — **classement exact** |
| > 200 | présélection lexicale MongoDB (`$text`) puis classement — `preselection_exhaustive: false` est signalé dans le compte rendu |

L'index texte porte sur `(contenu, titre)` avec `default_language="none"` : le
corpus est en français, et l'analyseur par défaut dégraderait les élisions.

Les vecteurs de dimension incohérente avec `RAG_EMBED_DIM` sont écartés plutôt
que d'être tronqués ou projetés : un vecteur tronqué ressemblerait à un document
plutôt qu'à un autre.

### `retriever` — recherche hybride

Similarité vectorielle combinée à un score lexical, pondérée par
`RAG_PONDERATION_DENSE` (0.7).

Ce n'est pas un raffinement décoratif, c'est ce qui rend le seuil de pertinence
exploitable. Un extrait qui partage beaucoup de mots avec la question sans la
traiter peut obtenir un score vectoriel honorable, tandis qu'une référence exacte
(localité, numéro d'article, matricule) mérite d'être pesée davantage. Inversement,
le score lexical seul remonterait des morceaux qui reprennent les mots de la
question sans y répondre.

**Diversité.** Deux morceaux consécutifs d'un même document se recouvrent, et les
mettre tous deux dans le contexte n'apporte rien. Un extrait d'un autre document
est préféré à la suite du même texte.

### `grounding` — le troisième rempart

Le prompt dit ce qu'il faut faire ; ce module **vérifie** que la réponse obtenue
le fait. Un modèle peut ignorer ses consignes, notamment pour satisfaire
l'utilisateur : il n'est pas rare de le voir compléter un extrait par un chiffre
connu du domaine, ou citer une page qui n'a pas été fournie. Ces deux
défaillances sont détectables mécaniquement.

| Contrôle | Détecte |
|---|---|
| `citations` | un marqueur `[S7]` alors qu'il n'y a que trois sources |
| `chiffres` | un nombre absent des extraits fournis |
| `absence` | « je n'ai rien trouvé » alors que des extraits ont été fournis |

## 3. Réponse : un chemin unique, sans exception

1. recherche des extraits autorisés au-dessus du seuil ;
2. **s'il n'y en a aucun, retour immédiat** d'un message d'absence, sans appel
   au modèle — le modèle n'a rien à quoi répondre ;
3. constitution du contexte et du prompt ;
4. appel du modèle ;
5. contrôle d'ancrage ;
6. en cas de rejet, repli sur les extraits.

Le repli est **déterministe** : il est produit par le code, à partir des extraits
réellement retenus. C'est ce qui garantit qu'un incident du modèle se traduit
par une réponse plus pauvre, jamais par une réponse fausse.

## 4. Absence de sources : deux causes à ne pas confondre

`_collecter_documents` renvoie un couple, pas une simple liste, parce que
l'absence a deux origines qui ne se ressemblent pas :

| Cause | Message |
|---|---|
| recherche menée sans succès | « 12 document(s) autorisé(s) ont été consultés ; aucun extrait ne correspond » |
| recherche **non** menée | « Les documents ne sont pas accessibles à votre rôle » / « La recherche documentaire est désactivée » |

Les confondre laisserait croire que les documents ne traitent pas du sujet alors
qu'ils n'ont pas été consultés.

## 5. Contrôle d'accès

`app/models/document.py` définit les niveaux de confidentialité et construit le
filtre. La classification est **dénormalisée sur chaque morceau** —
`confidentialite`, `roles_autorises`, `utilisateurs_autorises` — ce qui permet au
filtre de vivre dans la requête MongoDB.

`synchroniser_acces_document()` propage un changement de classification à tous
les morceaux d'un document. Oublier cette propagation est le scénario
d'échec le plus grave du système : un document reclassifié continuerait d'être
servi à partir de morceaux portant l'ancienne classification.

Index composé `(confidentialite, roles_autorises)` : c'est lui qui permet au tri
des candidats de servir le filtrage d'accès au lieu de le subir. Sans lui, chaque
recherche parcourt tous les extraits — le confidentialiel compris — pour n'en
garder qu'une fraction.

## 6. API

| Route | Rôle |
|---|---|
| `POST /api/v1/documents` | dépôt d'un document (GridFS + indexation) |
| `GET /api/v1/documents/recherche` | recherche, sans appel au modèle |
| `POST /api/v1/documents/question` | réponse documentaire complète |
| `POST /api/v1/documents/{id}/indexer` | réindexation manuelle |
| `PATCH /api/v1/documents/{id}/acces` | reclassification |
| `GET /api/v1/documents/{id}/telecharger` | binaire d'origine |
| `DELETE /api/v1/documents/{id}` | suppression (morceaux purgés) |
| `GET /api/v1/documents/referentiel`, `/statistiques` | inventaire |

`RAG_ENABLED=false` renvoie **503** sur `/question`, `/recherche` et
`/{id}/indexer`. Le dépôt, la liste, le téléchargement, la reclassification et la
suppression restent disponibles : un déploiement sans RAG doit pouvoir gérer son
corpus.

## 7. Réglages

| Réglage | Défaut | Rôle |
|---|---|---|
| `RAG_ENABLED` | `false` | master switch du canal documentaire |
| `RAG_EMBED_MODELE` | `local-hash` | fonction de vectorisation |
| `RAG_EMBED_DIM` | `2048` | dimension des vecteurs |
| `RAG_SEUIL_PERTINENCE` | `0.25` | seuil de pertinence des extraits |
| `RAG_PONDERATION_DENSE` | `0.7` | part du dense dans le score hybride |
| `RAG_RECHERCHE_TOP_K` | `6` | extraits retournés |
| `RAG_RECHERCHE_CANDIDATS` | `200` | bascule scan exhaustif / présélection |
| `RAG_CITATIONS_EXIGEES` | `true` | citations obligatoires |
| `RAG_EXTRACTION_AUTO` | `true` | indexation au dépôt |
| `RAG_CONTEXTE_CARACTERES_MAX` | `12000` | plafond de contexte |
| `RAG_TAILLE_MAX_OCTETS` | 20 Mo | taille maximale d'un document |

## 8. Limites connues

- **Pas de vrai modèle d'embeddings.** La recherche est lexicale, pas sémantique.
  Une question formulée avec des mots absents du document ne le trouvera pas.
  C'est la première limitation à lever si la qualité de retrieval devient
  insuffisante ; le point d'entrée est `embeddings.FONCTIONS`.
- **Un seul tenant, une seule langue.** Pas de recherche multilingue, pas de
  détection de langue.
- **Le seuil est global.** `RAG_SEUIL_PERTINENCE` ne varie pas selon la nature de
  la question : une recherche de référence exacte (numéro d'article) et une
  recherche de principe général mériteraient des seuils différents.
- **La présélection `$text` au-delà de 200 morceaux n'est pas exhaustive.** Le
  compte rendu le signale (`preselection_exhaustive: false`), mais rien n'oblige
  un appelant à le lire.
- **Pas de réindexation en masse.** Changer `RAG_EMBED_MODELE` n'a pas d'outil
  dédié : il faut reindexer document par document via
  `POST /{id}/indexer`.
- **Le CSV et le JSON sont indexés comme du texte.** Une feuille de calcul à
  plusieurs colonnes produit des morceaux dont la structure tabulaire est perdue.

## Voir aussi

- [`ia.md`](ia.md) — le routage et l'orchestration
- [`architecture.md`](architecture.md) — l'ensemble du système
- [`securite.md`](securite.md) — RBAC et confidentialité
