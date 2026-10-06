# Plateforme RFM — SRB Vatovavy

Système d'analyse, de prévision et d'aide à la décision pour le **Remboursement
des Frais Médicaux** du Service Régional du Budget de la région Vatovavy
(Madagascar).

La plateforme couvre la file des bénéficiaires, l'exécution budgétaire, les
dossiers de remboursement, la prévision de consommation, la détection
d'anomalies, et un assistant conversationnel capable de répondre aussi bien sur
les **données** que sur les **documents** du SRB.

## Ce que fait l'assistant

```
Question statistique          Question documentaire      Question mixte
        │                             │                          │
        ▼                             ▼                          ▼
   MongoDB                     RAG (vector store)         Router IA
        │                             │                          │
        ▼                             ▼              ┌───────────┴───────────┐
  Backend analytique            Documents             Data    RAG    les deux
  (21 indicateurs)           autorisés + ACL
```

Le routage est **déterministe et sans modèle de langage** : chaque chemin est
décidé par des tables de motifs pondérés, et le résultat est auditable. Le
modèle, s'il est activé, ne rédige qu'à partir de résultats déjà calculés et
d'extraits déjà filtrés — il ne choisit jamais la source et n'invente jamais un
chiffre. Détail dans [`docs/ia.md`](docs/ia.md).

## Stack

| Couche | Choix |
|---|---|
| Backend | Python 3.14, FastAPI 0.141, Motor 3.7 (async), Pydantic 2.13 |
| Base | MongoDB — données et vecteurs dans la même base |
| Frontend | Next.js 16 (App Router), React 19, Recharts, JavaScript |
| Prévision | `statsmodels` (ARIMA, saisonnalité), Prophet (optionnel) |
| LLM | API compatible OpenAI — Ollama par défaut, ou vLLM / LM Studio |

Aucune dépendance à un SDK d'IA : le client LLM est écrit sur `urllib`, et les
embeddings sont calculés localement. Le RAG et l'assistant fonctionnent
entièrement **sans modèle**.

## Démarrage

### Prérequis

- Python 3.14
- Node.js 20+
- MongoDB 7 (service local, ou `docker compose up -d mongo`)

### 1. Base de données

```bash
docker compose up -d mongo
```

Ou un service MongoDB local sur `127.0.0.1:27017`.

### 2. Backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --port 8000
```

### 3. Données de démonstration (facultatif)

```bash
python scripts/seed.py --confirm          # jeu déterministe, GRAINE = 2025
python scripts/generate_admin.py          # compte administrateur
```

> `seed.py` **efface les collections métier** avant de les remplir. `--confirm`
> est obligatoire.

### 4. Frontend

```bash
cd frontend
npm install
npm run dev
```

Ouvrir <http://localhost:3000>. L'API est sur <http://127.0.0.1:8000/docs>.

### Scripts Windows

```bash
scripts\demarrer-projet.bat      # backend + frontend dans deux fenêtres
```

## Configuration

Tout passe par `backend/.env`, documenté ligne à ligne dans
`.env.example`. Les valeurs par défaut sont sûres : l'assistant et le RAG sont
**désactivés**, `JWT_SECRET` est un secret de développement, et `config.py`
refuse de démarrer en `production` avec une configuration insecure.

Les deux réglages qui changent le plus le comportement :

| Réglage | Effet |
|---|---|
| `LLM_ENABLED` | `false` → toutes les réponses sont produites par le code. `true` → le modèle ne fait que la formulation |
| `RAG_ENABLED` | `false` → le canal documentaire renvoie 503. Le dépôt et la gestion des documents restent disponibles |

## Tests

Les tests backend sont des scripts autonomes (pas de pytest dans le projet) :

```bash
cd backend
python tests/test_assistant.py    # routage, garanties, contrôles — sans base
python tests/test_rbac.py         # matrice des permissions — sans base
python tests/test_budget.py       # nécessite MongoDB
python tests/test_rag.py          # nécessite MongoDB
```

```bash
cd frontend
npm test                         # runner intégré de Node
```

Les tests qui créent et suppriment des documents (`test_rag.py`) requièrent une
base accessible.

## Structure

```
backend/app/
  api/          routes FastAPI et schémas d'E/S
  services/     logique métier
  ml/           prévision et détection d'anomalies
  imports/      ingestion CSV/XLSX
  ai/           routage, indicateurs, orchestration, client LLM
  rag/          pipeline documentaire
  models/       constantes de domaine, confidentialité, ACL
  repositories/ accès MongoDB
  security/     JWT, RBAC
frontend/app/   pages (App Router)
frontend/components/  composants, dont l'interface de l'assistant
docs/           documentation
```

## Documentation

| Document | Contenu |
|---|---|
| [`docs/architecture.md`](docs/architecture.md) | vue d'ensemble, couches, conventions |
| [`docs/ia.md`](docs/ia.md) | routage, indicateurs, orchestration, contrôles |
| [`docs/rag.md`](docs/rag.md) | indexation, recherche hybride, ACL |
| [`docs/securite.md`](docs/securite.md) | rôles et matrice de permissions |
| [`docs/modele-donnees.md`](docs/modele-donnees.md) | modèle MongoDB proposé, à valider |

## État du projet

Le backend est complet sur ses domaines métier. Restent à faire :

- les pages frontend **documents**, **rapports** et **administration** (fichiers
  vides) ;
- le module `backend/app/reports/` (vide) ;
- `docs/cahier-des-charges.md`, `docs/api.md`, `docs/guide-installation.md` (vides).

## Conventions

- **Argent** : `Decimal128`, en ariary. Jamais de flottant.
- **Dates** : UTC ; les mois sont des chaînes `"YYYY-MM"`.
- **Langue** : interface, code et documentation en français.
- **Permissions frontend** : générées depuis le backend par
  `python scripts/generer_permissions_frontend.py`. Ne pas éditer à la main.
