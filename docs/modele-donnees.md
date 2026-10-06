# Modèle de données MongoDB — RFM SRB Vatovavy

> **Statut : PROPOSITION à valider.** Rédigé à partir de l'inventaire réel du projet
> et du périmètre fonctionnel déclaré. À re-confronter aux données réelles RFM 2025
> dès qu'elles seront disponibles.

---

## 1. Méthode et constat d'inventaire

### 1.1 Aucune donnée métier n'existe dans le projet

Inventaire exhaustif vérifié (extensions `csv`, `xlsx`, `xls`, `parquet`, `json`,
`sqlite`, `dta`, etc., hors `venv`/`node_modules`/`.next`) :

| Emplacement | Contenu | Conclusion |
|---|---|---|
| `backend/data/raw/` | vide | aucune donnée source |
| `backend/data/processed/` | vide | aucun jeu traité |
| `backend/data/exports/` | vide | aucun export |
| `database/seed/` | README vide | aucun script d'amorçage |
| `scripts/` | uniquement 3 `.bat` | aucun script d'import Python |
| `backend/scripts/import_data.py`, `seed.py` | 0 octet | pipeline d'import non implémenté |
| `backend/app/{models,schemas,repositories,services,ml,analytics}` | 0 octet | modèle non défini |
| MongoDB `rfm_srb_vatovavy` | seule collection `test` (1 doc `{_id, message}`) | aucunement des données RFM |

**Conclusion : il n'existe aucune colonne réelle à analyser.** Par conséquent, ni les
statuts, ni les catégories, ni la liste exacte des montants ne peuvent être **déterminés**
à partir de données. Tout ce qui suit est une **proposition fondée sur le périmètre
fonctionnel** (voir 1.2) et sur les pratiques standards du domaine, **sans jamais prétendre
provenir d'un fichier de données**.

### 1.2 Signaux fonctionnels vérifiables dans le projet

Seul matériau réellement présent : le périmètre déclaré dans le frontend et la config.

| Module (frontend) | Capacités déclarées | Implications de données |
|---|---|---|
| Bénéficiaires | « Liste et recherche », « actifs, pensionnés, catégories », « fiche détaillée » | entité `beneficiaires`, champ situation/statut, catégorie, fiche individuelle |
| Remboursements | « Statuts et états des demandes », « Montants, délais et circuits » | entité `remboursements`, dossier par bénéficiaire, statut de workflow, montants |
| Budget | « Crédits votés par exercice », « Taux d'exécution budgétaire », « Consommation mensuelle » | entité `budgets_rfm` (annuel) + `executions` (mensuel), taux calculés |
| Prévisions | « Sélection du modèle », « Horizon », « Intervalles de confiance » | entité `previsions` → sorties ML persistées |
| Simulations | « Scénarios : tendance, prudent, optimiste » | entité `simulations` → scénario + paramètres + résultats |
| Anomalies | « observations atypiques », « valeurs à vérifier », « seuils paramétrables » | entité `anomalies` → détections persistées + workflow de vérification |
| Documents | module « Documents » | entité `documents` (sources RAG, GridFS) |
| Rapports | « PDF et Excel », « modèles réutilisables » | entité `rapports` (métadonnées de génération) |
| Assistant IA | « RAG », « sources identifiables » | appuie sur `documents` (+ extraits) |
| Utilisateurs | JWT, `prenom`, `nom`, `email`, `role` | entité `utilisateurs` |
| Monnaie | `formatCurrency` → « Ar » (ariary), arrondi entier pour affichage | montants en ariary |

---

## 2. Déterminations

- **Granularité** : 3 niveaux — **individu** (bénéficiaire / dossier de remboursement),
  **mois** (exécution, prévision, indicateurs), **exercice** (budget, année civile).
- **Données temporelles** : exercice budgétaire (année, ex. 2025) ; séries mensuelles
  (`YYYY-MM`) pour consommation et prévisions ; horodatage UTC pour les événements
  (dépôt, décision, génération).
- **Données budgétaires** : crédit voté par ligne budgétaire et par exercice ;
  exécution = consommation mensuelle par ligne.
- **Données bénéficiaires** : identité, situation (actif/pensionné), catégorie, rattachement.
- **Données remboursements** : dossier, demandeur, montant demandé/accordé, dates, statut, circuit.
- **Statuts** : *listes proposées en §3, à confirmer sur données réelles — aucun statut ne
  provient d'une donnée observée.*
- **Catégories** : idem, propositions génériques.
- **Montants** : type **Decimal128** (ariary), jamais de flottants binaires.

---

## 3. Modèle MongoDB proposé

### 3.0 Principes transverses

| Règle | Valeur |
|---|---|
| Identifiant | `_id` : `ObjectId`, sauf exception signalée |
| Montants | `Decimal128` (BSON) via `Decimal` pydantic — jamais `double` |
| Dates | `date` (BSON), UTC ; les dates « mois » sont stockées en `string "YYYY-MM"` |
| Horodatages | `created_at` / `updated_at` : `datetime` UTC |
| Noms | collections au pluriel snake_case, champs en français du projet |
| Références | par `ObjectId` de la collection liée (pas d'embedding de documents métier) |

### 3.1 Collections retenues vs écartées

| Collection | Retenue | Justification |
|---|---|---|
| `utilisateurs` | ✅ | authentification JWT, rôles, traçabilité des actes |
| `beneficiaires` | ✅ | module fiche bénéficiaire, filtres actifs/pensionnés/catégories |
| `budgets_rfm` | ✅ | crédits votés par exercice (donnée maîtresse budgétaire) |
| `remboursements` | ✅ | cœur du domaine (statuts, montants, délais, circuits) |
| `executions` | ✅ | consommation mensuelle par ligne → taux d'exécution |
| `anomalies` | ✅ | sorties de détection + workflow « valeur à vérifier » |
| `previsions` | ✅ | sorties ML persistées (horizon, intervalles de confiance) |
| `simulations` | ✅ | scénarios tendance/prudent/optimiste et leurs résultats |
| `documents` | ✅ | module Documents + sources RAG (contenu dans GridFS) |
| `rapports` | ✅ | métadonnées des rapports PDF/Excel générés |
| `indicateurs` | ❌ | indicateurs/taux = calculs à la volée (agrégations) ; une collection ne sera créée que si un historique/instantané est exigé (cf. §7) |
| `previsions` vs `simulations` | distinctes | les unes sont des sorties de modèles ML, les autres des scénarios manuels — ne pas fusionner |

> La collection `test` présente dans la base (résidu) est à supprimer :
> `db.test.drop()`.

### 3.2 `utilisateurs`

**Champs**

| Champ | Type | Contrainte |
|---|---|---|
| `_id` | ObjectId | clé |
| `prenom` | string | requis |
| `nom` | string | requis |
| `email` | string | requis, **unique**, validé |
| `mot_de_passe_hash` | string (bcrypt) | requis, jamais restitué |
| `role` | string | énum : `administrateur` \| `gestionnaire` \| `validateur` \| `consultant` |
| `actif` | boolean | défaut `true` |
| `email_verifie` | boolean | défaut `false` |
| `derniere_connexion` | datetime | nullable |
| `created_at`, `updated_at` | datetime | remplis automatiquement |
| `created_by` | ObjectId → `utilisateurs` | nullable (traçabilité) |

**Index** : `{ email: 1 }` unique ; `{ actif: 1, role: 1 }`.

**Relations** : `created_by` → soi-même ; référence par `remboursements.valide_par`,
`anomalies.traite_par`, `previsions.generateur`, `rapports.generateur`.

**Exemple fictif**
```json
{
  "_id": "672a…",
  "prenom": "Hery",
  "nom": "RAKOTO",
  "email": "h.rakoto@exemple.mg",
  "mot_de_passe_hash": "$2b$12$…",
  "role": "gestionnaire",
  "actif": true,
  "email_verifie": true,
  "derniere_connexion": "2026-01-05T08:12:00Z",
  "created_at": "2025-11-02T09:00:00Z",
  "updated_at": "2025-11-02T09:00:00Z",
  "created_by": null
}
```

### 3.3 `beneficiaires`

**Champs**

| Champ | Type | Contrainte |
|---|---|---|
| `_id` | ObjectId | clé |
| `matricule` | string | requis, **unique** (identifiant métier) |
| `nom`, `prenom` | string | requis |
| `date_naissance` | date | nullable |
| `genre` | string | `M` \| `F` \| nullable |
| `situation` | string | énum : `actif` \| `pensionne` (proposition) |
| `categorie` | string | proposition, ex. `fonctionnaire` \| `contractuel` \| `retraite` — à valider |
| `direction` | string | proposition : rattachement administratif |
| `cin` | string | nullable, index |
| `telephone`, `email` | string | nullable |
| `adresse` | object | `{ region, district, commune }` — nullable |
| `statut_dossier` | string | énum : `actif` \| `suspendu` \| `clos` (proposition) |
| `created_at`, `updated_at` | datetime | remplis automatiquement |

**Index** : `{ matricule: 1 }` unique ; `{ situation: 1, categorie: 1 }` ;
`{ "adresse.region": 1 }` ; `{ nom: 1, prenom: 1 }`.

**Relations** : référencé par `remboursements.beneficiaire_id`, `anomalies.beneficiaire_id`.

**Exemple fictif**
```json
{
  "_id": "672a…",
  "matricule": "RFM-2025-00142",
  "nom": "RAHELISOA",
  "prenom": "Voahangy",
  "date_naissance": "1978-04-12",
  "genre": "F",
  "situation": "actif",
  "categorie": "fonctionnaire",
  "direction": "Direction Régionale de l'Éducation — Vatovavy",
  "cin": "123456789012",
  "telephone": "+261 34 00 000 00",
  "email": "v.rahelisoa@exemple.mg",
  "adresse": { "region": "Vatovavy", "district": "Ifanadiana", "commune": "Ifanadiana" },
  "statut_dossier": "actif",
  "created_at": "2025-01-10T07:30:00Z",
  "updated_at": "2025-01-10T07:30:00Z"
}
```

### 3.4 `budgets_rfm`

**Champs**

| Champ | Type | Contrainte |
|---|---|---|
| `_id` | ObjectId | clé |
| `exercice` | int | requis (ex. `2025`) |
| `chapitre` | string | requis (nomenclature budgétaire) |
| `ligne_budgetaire` | string | requis |
| `libelle` | string | requis |
| `type` | string | énum : `fonctionnement` \| `investissement` (proposition) |
| `montant_vote` | Decimal128 | requis, ≥ 0 |
| `created_at`, `updated_at` | datetime | remplis automatiquement |

**Contrainte d'unicité** : `{ exercice, chapitre, ligne_budgetaire }` unique.

**Index** : unique `{ exercice, chapitre, ligne_budgetaire }` ; `{ exercice, type }`.

**Relations** : référencé par `executions.budget_id`. Le taux d'exécution d'une ligne =
`Σ executions.montant_execute / montant_vote`.

**Exemple fictif**
```json
{
  "_id": "672a…",
  "exercice": 2025,
  "chapitre": "31-07",
  "ligne_budgetaire": "31-07-42",
  "libelle": "Remboursements de frais de soins — pensionnés",
  "type": "fonctionnement",
  "montant_vote": { "$numberDecimal": "250000000" }
}
```

### 3.5 `remboursements`

**Champs**

| Champ | Type | Contrainte |
|---|---|---|
| `_id` | ObjectId | clé |
| `numero_dossier` | string | requis, **unique** (ex. `RM-2025-00481`) |
| `beneficiaire_id` | ObjectId → `beneficiaires` | requis |
| `type_prestation` | string | proposition : `soins` \| `pharmacie` \| `hospitalisation` \| `prothese` \| `autre` — à valider |
| `circuit` | string | proposition : ex. `circuit_normal` \| `circuit_accelere` |
| `date_demande` | date | requis |
| `date_decision` | date | nullable |
| `montant_demande` | Decimal128 | requis, ≥ 0 |
| `montant_accordee` | Decimal128 | nullable, ≥ 0 |
| `montant_paye` | Decimal128 | nullable, ≥ 0 |
| `statut` | string | énum : `soumis` \| `a_completer` \| `en_cours` \| `valide` \| `refuse` \| `paye` \| `annule` (proposition de workflow) |
| `motif_refus` | string | nullable |
| `pieces` | array<string> | identifiants des justificatifs (`documents`) |
| `valide_par` | ObjectId → `utilisateurs` | nullable |
| `created_at`, `updated_at` | datetime | remplis automatiquement |

**Index** : `{ numero_dossier: 1 }` unique ; `{ beneficiaire_id: 1, date_demande: -1 }` ;
`{ statut: 1 }` ; `{ date_decision: 1 }` ; `{ type_prestation: 1, date_demande: -1 }`.

**Relations** : `beneficiaire_id` → `beneficiaires` ; `pieces` → `documents` ;
`valide_par` → `utilisateurs` ; type de dépense → `executions` pour la consommation.

**Exemple fictif**
```json
{
  "_id": "672a…",
  "numero_dossier": "RM-2025-00481",
  "beneficiaire_id": "672a…",
  "type_prestation": "hospitalisation",
  "circuit": "circuit_normal",
  "date_demande": "2025-03-20",
  "date_decision": "2025-04-02",
  "montant_demande": { "$numberDecimal": "1850000" },
  "montant_accordee": { "$numberDecimal": "1700000" },
  "montant_paye": { "$numberDecimal": "1700000" },
  "statut": "paye",
  "motif_refus": null,
  "pieces": ["672a…"],
  "valide_par": "672a…",
  "created_at": "2025-03-20T08:05:00Z",
  "updated_at": "2025-04-02T15:40:00Z"
}
```

### 3.6 `executions`

**Champs**

| Champ | Type | Contrainte |
|---|---|---|
| `_id` | ObjectId | clé |
| `budget_id` | ObjectId → `budgets_rfm` | requis |
| `mois` | string `YYYY-MM` | requis |
| `montant_execute` | Decimal128 | requis, ≥ 0 |
| `created_at`, `updated_at` | datetime | remplis automatiquement |

**Contrainte d'unicité** : `{ budget_id, mois }` unique.

**Index** : unique `{ budget_id, mois }` ; `{ mois: 1 }`.

**Relations** : `budget_id` → `budgets_rfm`. Le cumul exercice = somme par exercice via
`budget_id.exercice` (agrégation, pas de stockage du cumul).

**Exemple fictif**
```json
{
  "_id": "672a…",
  "budget_id": "672a…",
  "mois": "2025-06",
  "montant_execute": { "$numberDecimal": "24300000" }
}
```

### 3.7 `anomalies`

**Champs**

| Champ | Type | Contrainte |
|---|---|---|
| `_id` | ObjectId | clé |
| `type_anomalie` | string | énum : `montant_atypique` \| `delai_atypique` \| `volume_atypique` \| `ecart_budget` (proposition) |
| `remboursement_id` | ObjectId → `remboursements` | nullable |
| `beneficiaire_id` | ObjectId → `beneficiaires` | nullable |
| `budget_id` | ObjectId → `budgets_rfm` | nullable (anomalie sur ligne budgétaire) |
| `periode` | string `YYYY-MM` | nullable |
| `valeur` | Decimal128 | requis |
| `seuil` | Decimal128 | requis (seuil paramétrable) |
| `ecart` | Decimal128 | requis (valeur − seuil) |
| `statut` | string | énum : `nouvelle` \| `a_verifier` \| `confirmee` \| `ecartee` (workflow « valeur à vérifier ») |
| `commentaire` | string | nullable |
| `detecte_le` | datetime | requis |
| `traite_par` | ObjectId → `utilisateurs` | nullable |
| `created_at`, `updated_at` | datetime | remplis automatiquement |

**Index** : `{ statut: 1 }` ; `{ type_anomalie: 1, periode: 1 }` ; `{ remboursement_id: 1 }`.

**Relations** : 3 références optionnelles selon le périmètre de l'anomalie.

**Exemple fictif**
```json
{
  "_id": "672a…",
  "type_anomalie": "montant_atypique",
  "remboursement_id": "672a…",
  "beneficiaire_id": null,
  "budget_id": null,
  "periode": "2025-07",
  "valeur": { "$numberDecimal": "12500000" },
  "seuil": { "$numberDecimal": "8000000" },
  "ecart": { "$numberDecimal": "4500000" },
  "statut": "a_verifier",
  "commentaire": null,
  "detecte_le": "2025-08-01T06:00:00Z",
  "traite_par": null,
  "created_at": "2025-08-01T06:00:00Z",
  "updated_at": "2025-08-01T06:00:00Z"
}
```

### 3.8 `previsions`

**Champs**

| Champ | Type | Contrainte |
|---|---|---|
| `_id` | ObjectId | clé |
| `type_indicateur` | string | énum : `montant_rembourse` \| `nombre_dossiers` \| `consommation_budget` (proposition) |
| `exercice` | int | requis |
| `mois` | string `YYYY-MM` | requis |
| `valeur_prevue` | Decimal128 | requis |
| `borne_inf`, `borne_sup` | Decimal128 | requis (intervalles de confiance) |
| `modele` | string | nom du modèle ML (ex. `prophet`, `sarimax`, `gbm` — à préciser) |
| `parametres` | object | hyperparamètres utilisés |
| `date_generation` | datetime | requis |
| `generateur` | ObjectId → `utilisateurs` | nullable |
| `created_at` | datetime | rempli automatiquement |

**Index** : unique `{ exercice, mois, type_indicateur, modele }` ; `{ date_generation: -1 }`.

**Relations** : `generateur` → `utilisateurs`.

**Exemple fictif**
```json
{
  "_id": "672a…",
  "type_indicateur": "montant_rembourse",
  "exercice": 2025,
  "mois": "2025-11",
  "valeur_prevue": { "$numberDecimal": "185000000" },
  "borne_inf": { "$numberDecimal": "161000000" },
  "borne_sup": { "$numberDecimal": "209000000" },
  "modele": "prophet",
  "parametres": { "saisonnalite_mensuelle": true, "horizon": 6 },
  "date_generation": "2025-10-01T10:00:00Z",
  "generateur": "672a…",
  "created_at": "2025-10-01T10:00:00Z"
}
```

### 3.9 `simulations`

**Champs**

| Champ | Type | Contrainte |
|---|---|---|
| `_id` | ObjectId | clé |
| `nom` | string | requis |
| `scenario` | string | énum : `tendance` \| `prudent` \| `optimiste` (proposition) |
| `parametres` | object | hypothèses (volumes, taux, montants) |
| `resultats` | array | série mensuelle : `[{ mois, valeur }]` |
| `date_creation` | datetime | requis |
| `created_by` | ObjectId → `utilisateurs` | nullable |

**Index** : `{ createe_par: 1, date_creation: -1 }` ; `{ scenario: 1 }`.

**Relations** : `created_by` → `utilisateurs`.

**Exemple fictif**
```json
{
  "_id": "672a…",
  "nom": "Scénario prudent 2026",
  "scenario": "prudent",
  "parametres": { "croissance_dossiers": 0.02, "montant_moyen": 1650000 },
  "resultats": [
    { "mois": "2026-01", "valeur": { "$numberDecimal": "188000000" } },
    { "mois": "2026-02", "valeur": { "$numberDecimal": "190000000" } }
  ],
  "date_creation": "2026-01-15T09:30:00Z",
  "created_by": "672a…"
}
```

### 3.10 `documents`

**Champs**

| Champ | Type | Contrainte |
|---|---|---|
| `_id` | ObjectId | clé |
| `nom_fichier` | string | requis |
| `type_mime` | string | requis |
| `taille_octets` | long | ≥ 0 |
| `description` | string | nullable |
| `source` | string | énum : `televersement` \| `import` \| `lien` |
| `file_id` | ObjectId → GridFS | requis si contenu stocké (`storage.fs.files`) |
| `statut_indexation` | string | énum : `en_attente` \| `indexe` \| `echec` (RAG) |
| `cree_par` | ObjectId → `utilisateurs` | nullable |
| `created_at`, `updated_at` | datetime | remplis automatiquement |

**Index** : `{ nom_fichier: 1 }` ; `{ statut_indexation: 1 }` ; `{ created_at: -1 }`.

**Relations** : référencé par `remboursements.pieces` ; contenu binaire dans GridFS
(bucket `storage`).

**Exemple fictif**
```json
{
  "_id": "672a…",
  "nom_fichier": "justificatif_rm202500481.pdf",
  "type_mime": "application/pdf",
  "taille_octets": 482120,
  "description": "Facture d'hospitalisation — coupure 1",
  "source": "televersement",
  "file_id": "672a…",
  "statut_indexation": "indexe",
  "cree_par": "672a…",
  "created_at": "2025-03-22T09:15:00Z",
  "updated_at": "2025-03-22T09:20:00Z"
}
```

### 3.11 `rapports`

**Champs**

| Champ | Type | Contrainte |
|---|---|---|
| `_id` | ObjectId | clé |
| `titre` | string | requis |
| `type` | string | énum : `pdf` \| `excel` |
| `modele` | string | nom du modèle de rapport |
| `parametres` | object | filtre/périmètre de génération (exercice, période…) |
| `fichier_id` | ObjectId | fichier généré (GridFS) |
| `statut` | string | énum : `genere` \| `echoue` |
| `date_generation` | datetime | requis |
| `generateur` | ObjectId → `utilisateurs` | nullable |

**Index** : `{ date_generation: -1 }` ; `{ type: 1, date_generation: -1 }`.

**Relations** : `generateur` → `utilisateurs` ; contenu dans GridFS.

**Exemple fictif**
```json
{
  "_id": "672a…",
  "titre": "Exécution budgétaire — T1 2025",
  "type": "excel",
  "modele": "execution_budget",
  "parametres": { "exercice": 2025, "debut": "2025-01", "fin": "2025-03" },
  "fichier_id": "672a…",
  "statut": "genere",
  "date_generation": "2025-04-05T14:00:00Z",
  "generateur": "672a…"
}
```

---

## 4. Relations logiques (vue d'ensemble)

```
utilisateurs ──┬── created_by ───────────────────────────────┐
               ├── valide_par ──> remboursements             │
               ├── traite_par ──> anomalies                  │
               ├── generateur ──> previsions, rapports       │
               └── created_by ──> simulations                │

beneficiaires ──┬── beneficiaire_id ──> remboursements
                └── beneficiaire_id ──> anomalies

budgets_rfm ────┬── budget_id ──> executions
                └── budget_id ──> anomalies

remboursements ── pieces ──> documents
rapports ──────── fichier ──> GridFS
documents ─────── file_id ──> GridFS
```

---

## 5. Synthèse des index

| Collection | Index uniques | Index secondaires |
|---|---|---|
| `utilisateurs` | `email` | `(actif, role)` |
| `beneficiaires` | `matricule` | `(situation, categorie)`, `adresse.region`, `(nom, prenom)`, `cin` |
| `budgets_rfm` | `(exercice, chapitre, ligne_budgetaire)` | `(exercice, type)` |
| `remboursements` | `numero_dossier` | `(beneficiaire_id, date_demande)`, `statut`, `date_decision`, `(type_prestation, date_demande)` |
| `executions` | `(budget_id, mois)` | `mois` |
| `anomalies` | — | `statut`, `(type_anomalie, periode)`, `remboursement_id` |
| `previsions` | `(exercice, mois, type_indicateur, modele)` | `date_generation` |
| `simulations` | — | `(created_by, date_creation)`, `scenario` |
| `documents` | — | `nom_fichier`, `statut_indexation`, `created_at` |
| `rapports` | — | `date_generation`, `(type, date_generation)` |

---

## 6. Non créées ou à recycler

- **`indicateurs`** : non créée pour l'instant — les KPI du tableau de bord (taux
  d'exécution, cumuls, moyennes, délais moyens) se calculent par agrégation. Ajouter
  `indicateurs_historique` uniquement si un historique/instantané de KPI est exigé.
- **`test`** : collection parasite dans la base → `db.test.drop()`.
- **Collections métier non justifiées par un périmètre déclaré** : aucune autre.

---

## 7. À valider dès réception des données réelles

1. **Liste exacte des statuts** (remboursements, bénéficiaires) et de leurs transitions.
2. **Nomenclature des catégories** (bénéficiaires) et des **types de prestation**.
3. **Nomenclature budgétaire** (chapitres/lignes) et codification `RPM`/matricules.
4. **Unité et précision des montants** (ariary ; fractions éventuelles).
5. **Circuits de remboursements** et leurs délais normatifs.
6. **Granularité exacte de l'exécution budgétaire** (mensuelle confortée ?).