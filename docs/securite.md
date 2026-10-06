# Sécurité — RBAC (rôles, permissions, contrôle d'accès)

## Principe

Le backend est **la seule source d'autorité** pour les permissions :

- `backend/app/services/permission_service.py` — rôles, modules, matrice des
  permissions, vérifications.
- `backend/app/security/permissions.py` — dépendances FastAPI
  (`exiger_permission`, `exiger_module`, `exiger_roles`) appliquées à chaque
  route : sans droit, réponse `403` (`ErreurForbidden`).
- `backend/app/security/jwt.py` — jeton JWT vérifié (signature, expiration,
  émetteur), `sub` = identifiant utilisateur, `role` transporté en charge utile
  mais **jamais utilisé seul** : la permission retenue est celle du document
  `utilisateurs` en base, re-chargé à chaque requête.

Le frontend **masque/affiche uniquement** l'interface selon les permissions :

- `frontend/lib/permissions.js` — référentiel projeté (affichage), généré
  depuis le backend (`python backend/scripts/generer_permissions_frontend.py`).
- `frontend/hooks/usePermissions.js` — hook `usePermissions()`.
- `frontend/components/auth/RequirePermission.jsx` — garde de page (`/403`).
- `frontend/components/auth/PermissionsGate.jsx` — masquage de blocs précis.
- `frontend/components/layout/AppShell.jsx` — garde par module sur chaque route.
- `frontend/components/layout/Sidebar.jsx` — filtrage des entrées de menu.

Le masquage frontend n'est **jamais** une protection suffisante : toute
opération sensible est ré-évaluée côté API.

## Rôles

| Rôle        | Mission                                         |
| ----------- | ----------------------------------------------- |
| `ADMIN`     | Accès total, gestion des utilisateurs et rôles. |
| `RESPONSABLE` | Pilotage et gestion opérationnelle des données. |
| `ANALYSTE`  | Lecture, analyses, prévisions, simulations, rapports. |
| `AGENT`     | Opérationnel quotidien (enregistrements).       |

Rôle par défaut à la création d'un compte : `AGENT`.

## Matrice des permissions

Convention de nommage : `<module>:<action>`.

| Module | Actions | ADMIN | RESPONSABLE | ANALYSTE | AGENT |
| ------ | ------- | :---: | :---------: | :------: | :---: |
| dashboard | voir | ✓ | ✓ | ✓ | ✓ |
| beneficiaires | voir / creer / modifier / supprimer / exporter | ✓ | ✓ | voir+exporter | voir+creer+modifier |
| budget | voir / creer / modifier / supprimer / exporter | ✓ | ✓ | voir+exporter | voir |
| remboursements | voir / creer / modifier / supprimer / valider / exporter | ✓ | ✓ | voir+exporter | voir+creer+modifier |
| analyses | voir / exporter | ✓ | ✓ | ✓ | voir |
| anomalies | voir / traiter | ✓ | ✓ | voir+traiter | voir |
| previsions | voir / creer / exporter | ✓ | ✓ | ✓ | voir |
| simulations | voir / creer / supprimer / exporter | ✓ | ✓ | voir+creer+exporter | voir |
| assistant | utiliser | ✓ | ✓ | ✓ | ✓ |
| documents | voir / televerser / supprimer / telecharger | ✓ | ✓ | voir+telecharger | voir+televerser+telecharger |
| rapports | voir / generer / exporter | ✓ | ✓ | ✓ | voir |
| utilisateurs | voir / creer / modifier / supprimer / changer_role | ✓ | voir | — | — |
| importation | importer / voir_rapport | ✓ | ✓ | voir_rapport | importer |

Règles d'usage :

- Permission inconnue ⇒ refusée.
- Rôle inconnu ou absent ⇒ aucun accès implicite (refus par défaut).
- `utilisateurs:*` hors `utilisateurs:voir` : réservé à `ADMIN`.
- `remboursements:valider` : `ADMIN` et `RESPONSABLE` uniquement.
- `rapports:generer` / `rapports:exporter` : `ADMIN`, `RESPONSABLE`, `ANALYSTE`.

## Utilisation côté backend

```python
from app.security.permissions import exiger_permission, exiger_module

@router.post("", status_code=201)
async def creer(
    donnees: Schema,
    acteur: dict = Depends(exiger_permission("utilisateurs:creer")),
):
    ...
```

## Utilisation côté frontend

```jsx
const { has, hasAny, canAccessModule, role, permissions } = usePermissions();

<PermissionsGate permission="importation:importer">
  <ImportUpload />
</PermissionsGate>

<RequirePermission module="utilisateurs">
  <PageUtilisateurs />
</RequirePermission>
```

## Régénération / synchronisation de la matrice frontend

```
python backend/scripts/generer_permissions_frontend.py
```

Régénère le bloc de données de `frontend/lib/permissions.js` à partir du
backend (source d'autorité). Ne jamais éditer ce bloc à la main.

## Tests

- Backend : `python backend/tests/test_rbac.py` — matrice complète,
  hiérarchies, refus par défaut, dépendances FastAPI, accès par module/par rôle,
  comportement en base (création, connexion, gestion des utilisateurs).
- Frontend : `npm test` (dans `frontend/`) — matrice générée vs valeurs
  attendues pour chaque rôle, helpers et gardes.