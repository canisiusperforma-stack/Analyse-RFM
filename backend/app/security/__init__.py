"""Sécurité : authentification (JWT, mots de passe) et RBAC.

Sous-modules :
- `app.security.jwt`          — création et vérification des jetons ;
- `app.security.password`     — hashage bcrypt des mots de passe ;
- `app.security.dependencies` — dépendance d'authentification ;
- `app.security.permissions`  — dépendances RBAC (permission, module, rôle).
"""