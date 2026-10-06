# Architecture

## 1. Vue d'ensemble

```
┌──────────────────────────────────────────────────────────────────────┐
│  Navigateur                                                          │
│  Next.js 16 (App Router) · React 19 · Recharts                       │
│  Proxy /api → backend                                               │
└───────────────────────────────┬──────────────────────────────────────┘
                                │ JWT (Bearer, localStorage)
┌───────────────────────────────▼──────────────────────────────────────┐
│  FastAPI — /api                                                     │
│                                                                      │
│   /api/sante              état de l'API et de MongoDB              │
│   /api/v1/auth            authentification, RBAC                    │
│   /api/v1/<domain>        bénéficiaires, budgets, remboursements,  │
│                           analyses, anomalies, prévisions,          │
│                           simulations, dashboard, imports,         │
│                           rapports, documents, utilisateurs       │
│   /api/v1/assistant       routage + orchestration                  │
└──────┬────────────────────────────────────────┬──────────────────────┘
       │                                        │
┌──────▼──────────────────┐          ┌──────────▼──────────────────┐
│  Couches métier         │          │  app/ai                      │
│                         │          │                             │
│  services/  agrégats    │          │  query_analyzer  intention  │
│  ml/        prévision   │          │  query_router    4 chemins  │
│             anomalies    │          │  indicator_service 21 calc. │
│  imports/   ingestion   │          │  context_builder  figeage   │
│  rag/       documents   │          │  llm_service     rédaction  │
│                         │          │  response_validator contrôle│
└──────┬──────────────────┘          └──────────┬──────────────────┘
       │                                        │
┌──────▼────────────────────────────────────────▼──────────────────────┐
│  MongoDB — rfm_srb_vatovavy                                         │
│                                                                      │
│  beneficiaries budgets_rfm executions remboursements anomalies        │
│  documents documents_morceaux (vecteurs + ACL)                       │
│  utilisateurs                                                        │
│  importations _brutes _nettoyees _rejets                             │
│  GridFS: documents (binaires)                                        │
└──────────────────────────────────────────────────────────────────────┘
```

## 2. Couches du backend

Le nommage est français et le sens est strict : une couche ne connaît que celle
du dessous.

| Couche | Chemin | Rôle |
|---|---|---|
| API | `app/api/` | Routes FastAPI, schémas d'entrée-sortie, dépendances d'authentification |
| Services | `app/services/` | Logique métier, accès direct à MongoDB |
| ML | `app/ml/` | Prévision (5 modèles), détection d'anomalies (4 détecteurs) |
| Imports | `app/imports/` | Ingestion CSV/XLSX : lecture → validation → normalisation → stockage |
| IA | `app/ai/` | Routage, indicateurs, orchestration, client LLM |
| RAG | `app/rag/` | Pipeline documentaire complet |
| Repositories | `app/repositories/` | Accès MongoDB |
| Modèles | `app/models/` | Constantes de domaine, confidentialité, ACL |
| Schémas | `app/schemas/` | Modèles Pydantic d'E/S |
| Sécurité | `app/security/` | JWT, mots de passe, RBAC |
| Base | `app/database/` | Client Motor, connexion, cycle de vie |
| Config | `app/config.py` | Réglages `.env` + validateurs de production |

`app/analytics/` et `app/reports/` sont réservés et vides : la logique
d'analyse vit dans `app/services/`, les rapports ne sont pas implémentés.

## 3. Collections

| Collection | Contenu |
|---|---|
| `beneficiaires` | file RFM : matricule, situation, statut |
| `budgets_rfm` | crédits par chapitre / ligne / nature, LFI et LFR |
| `executions` | exécution mensuelle, 4 phases |
| `remboursements` | dossiers de remboursement |
| `anomalies` | anomalies détectées et leur statut de traitement |
| `documents` | métadonnées, classification, statut d'indexation |
| `documents_morceaux` | morceaux + vecteurs + ACL dénormalisée |
| `utilisateurs` | comptes, rôle, permissions |
| `importations` (+ `_brutes`, `_nettoyees`, `_rejets`) | historique d'ingestion en 3 tiers |
| GridFS `documents` | binaires d'origine |

Le détail des champs est dans [`modele-donnees.md`](modele-donnees.md), qui est
explicitement une proposition à valider.

## 4. Conventions

**Argent.** `Decimal128`, en ariary. Jamais de flottant — les arrondis binaires
produiraient des écarts visibles sur des sommes.

**Dates.** UTC. Les mois sont des chaînes `"YYYY-MM"`, pas des dates : un mois
n'est pas un instant.

**Langue.** Interface, code, commentaires et documentation en français. Les noms
de colonnes sont en `snake_case` sans accent.

**Configuration.** Tout passe par `.env`. `config.py` refuse une configuration de
production insecure (URL LLM en HTTP, secret JWT par défaut) plutôt que de
démarrer.

## 5. Sécurité

Quatre rôles — `ADMIN`, `RESPONSABLE`, `ANALYSTE`, `AGENT` — décrits dans
[`securite.md`](securite.md), avec la matrice de permissions.

Deux points structurants :

- Le contrôle d'accès du RAG est appliqué **dans la requête MongoDB**, pas après
  le classement. Un extrait interdit n'est jamais transmis au processus qui
  classe les résultats.
- Les permissions du frontend sont **générées depuis le backend** :
  `python scripts/generer_permissions_frontend.py`. Le backend est l'autorité ;
  éditer `frontend/lib/permissions.js` à la main est futile.

## 6. Le module IA

Détail dans [`ia.md`](ia.md). En résumé : une question est routée vers `DATA`,
`RAG`, `DATA_RAG` ou `INCONNUE` par du code déterministe, les chiffres sont
calculés par le backend, le contexte est figé avant toute génération, et la
réponse est contrôlée avant d'être renvoyée.

Le canal documentaire est détaillé dans [`rag.md`](rag.md).

## 7. Cycle de vie au démarrage

`app/main.py` (`lifespan`) :

1. configuration du journalisation ;
2. `connecter_database()` — **en mode dégradé si MongoDB est indisponible** :
   l'API démarre et le signale, plutôt que de refuser de démarrer ;
3. si `RAG_ENABLED`, `document_repository.assurer_indexes()` — idempotent ; un
   échec est journalisé sans interrompre, la base restant fonctionnelle mais plus
   lente.

Les index métier (`beneficiaires.matricule`, clés composites de budget, etc.) sont
créés par `scripts/seed.py`.

## 8. État d'avancement

| Domaine | État |
|---|---|
| Backend analytique, ML, imports, RBAC, JWT | implémenté |
| Module IA (routage, indicateurs, contrôles) | implémenté |
| RAG documentaire | implémenté |
| Frontend : accueil, connexion, dashboard, bénéficiaires, budget, remboursements, analyses, prévisions, simulations, assistant | implémenté |
| Frontend : documents, rapports, administration, analyses (page hub) | **pages vides** |
| `app/reports/` | **vide** |
| Intégrations, exports | **non implémentées** |

## Voir aussi

- [`ia.md`](ia.md) — architecture de l'assistant
- [`rag.md`](rag.md) — pipeline documentaire
- [`securite.md`](securite.md) — RBAC
- [`modele-donnees.md`](modele-donnees.md) — modèle de données proposé
