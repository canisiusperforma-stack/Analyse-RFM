"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ChevronDown, ShieldCheck } from "lucide-react";

import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import Input from "@/components/ui/Input";
import Modal from "@/components/ui/Modal";
import Select from "@/components/ui/Select";
import {
  MODULES,
  ROLE_BADGE_VARIANTS,
  ROLE_DEFAUT,
  ROLE_LABELS,
  ROLES,
} from "@/lib/permissions";
import {
  ROLES_INTENTS,
  actionsRoleModule,
  descriptionModule,
  libelleAction,
  libelleModule,
  nomComplet,
} from "@/lib/administration";
import { formatDateTime } from "@/lib/formatters";
import {
  combineErrors,
  email as validerEmail,
  maxLength,
  minLength,
  required,
} from "@/lib/validators";

const LONGUEUR_MIN_MOT_DE_PASSE = 8;

const VIDE = {
  prenom: "",
  nom: "",
  email: "",
  motDePasse: "",
  role: ROLE_DEFAUT,
  actif: "true",
};

/**
 * Création et édition d'un compte.
 *
 * Un seul formulaire pour les deux, mais pas un seul jeu de champs : à la
 * création l'e-mail, le mot de passe et le rôle sont demandés ; en édition ils
 * sont hors d'atteinte. Le backend ne sait pas les modifier — réécrire
 * l'identité d'un compte, ou son mot de passe sans jamais l'afficher, ne sont
 * pas des opérations qu'un écran d'administration doit rendre banales. Le rôle,
 * lui, se change ailleurs, dans une modale dédiée : c'est un acte à part, avec
 * sa propre permission.
 *
 * Le mot de passe est dit « provisoire » : il est stocké haché et n'est jamais
 * renvoyé par l'API. Personne, pas même l'administrateur, ne pourra le
 * retrouver — il devra être changé par l'intéressé.
 */
export default function UtilisateurFormModal({
  open = false,
  mode = "creation",
  utilisateur = null,
  onClose,
  onSubmit,
  submitting = false,
}) {
  const [formulaire, setFormulaire] = useState(VIDE);
  const [erreurs, setErreurs] = useState({});
  const [details, setDetails] = useState(false);

  const creation = mode === "creation";

  useEffect(() => {
    if (!open) return;
    setErreurs({});
    setDetails(false);
    setFormulaire(
      creation
        ? VIDE
        : {
            prenom: utilisateur?.prenom ?? "",
            nom: utilisateur?.nom ?? "",
            email: utilisateur?.email ?? "",
            motDePasse: "",
            role: utilisateur?.role ?? ROLE_DEFAUT,
            actif: utilisateur?.actif ? "true" : "false",
          }
    );
  }, [creation, open, utilisateur]);

  const change = useCallback((champ, valeur) => {
    setFormulaire((precedents) => ({ ...precedents, [champ]: valeur }));
  }, []);

  const valide = useMemo(() => {
    const trouvees = {
      prenom: combineErrors(
        required(formulaire.prenom, "Le prénom"),
        maxLength(formulaire.prenom, 100, "Le prénom")
      ),
      nom: combineErrors(
        required(formulaire.nom, "Le nom"),
        maxLength(formulaire.nom, 100, "Le nom")
      ),
    };
    if (creation) {
      trouvees.email = combineErrors(
        required(formulaire.email, "L'adresse e-mail"),
        validerEmail(formulaire.email)
      );
      trouvees.motDePasse = combineErrors(
        required(formulaire.motDePasse, "Le mot de passe"),
        minLength(
          formulaire.motDePasse,
          LONGUEUR_MIN_MOT_DE_PASSE,
          "Le mot de passe"
        )
      );
      trouvees.role = required(formulaire.role, "Le rôle");
    }
    return trouvees;
  }, [creation, formulaire]);

  const valideGlobalement = Object.values(valide).every((erreur) => !erreur);

  const soumettre = async (evenement) => {
    evenement.preventDefault();
    if (!valideGlobalement || submitting) {
      setErreurs(valide);
      return;
    }
    setErreurs({});
    if (creation) {
      await onSubmit({
        prenom: formulaire.prenom.trim(),
        nom: formulaire.nom.trim(),
        email: formulaire.email.trim().toLowerCase(),
        motDePasse: formulaire.motDePasse,
        role: formulaire.role,
      });
      return;
    }
    await onSubmit({
      prenom: formulaire.prenom.trim(),
      nom: formulaire.nom.trim(),
      actif: formulaire.actif === "true",
    });
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      size={creation ? "md" : "lg"}
      title={creation ? "Nouveau compte" : `Fiche de ${nomComplet(utilisateur)}`}
      description={
        creation
          ? "Le compte est créé actif, avec le rôle choisi. Aucun jeton n'est émis : l'intéressé se connectera avec le mot de passe provisoire."
          : "Identité et état du compte. L'e-mail, le mot de passe et le rôle ne sont pas modifiables depuis cet écran."
      }
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={submitting}>
            Annuler
          </Button>
          <Button type="submit" form="utilisateur-form" loading={submitting}>
            {creation ? "Créer le compte" : "Enregistrer"}
          </Button>
        </>
      }
    >
      <form id="utilisateur-form" onSubmit={soumettre} noValidate>
        <div className="admin-form">
          <Input
            label="Prénom"
            required
            value={formulaire.prenom}
            onChange={(e) => change("prenom", e.target.value)}
            error={erreurs.prenom}
            maxLength={100}
            autoComplete="given-name"
            disabled={submitting}
          />
          <Input
            label="Nom"
            required
            value={formulaire.nom}
            onChange={(e) => change("nom", e.target.value)}
            error={erreurs.nom}
            maxLength={100}
            autoComplete="family-name"
            disabled={submitting}
          />

          {creation ? (
            <>
              <Input
                label="Adresse e-mail"
                required
                type="email"
                value={formulaire.email}
                onChange={(e) => change("email", e.target.value)}
                error={erreurs.email}
                hint="Identifiant de connexion, unique sur la plateforme."
                autoComplete="off"
                disabled={submitting}
              />
              <Input
                label="Mot de passe provisoire"
                required
                type="password"
                value={formulaire.motDePasse}
                onChange={(e) => change("motDePasse", e.target.value)}
                error={erreurs.motDePasse}
                hint={`${LONGUEUR_MIN_MOT_DE_PASSE} caractères minimum. Communiqué à l'intéressé : il ne sera plus jamais lisible, même ici.`}
                autoComplete="new-password"
                disabled={submitting}
              />
              <Select
                label="Rôle"
                required
                value={formulaire.role}
                onChange={(e) => change("role", e.target.value)}
                error={erreurs.role}
                hint={ROLES_INTENTS[formulaire.role]}
                disabled={submitting}
                options={ROLES.map((nomRole) => ({
                  value: nomRole,
                  label: ROLE_LABELS[nomRole] ?? nomRole,
                }))}
              />
              <div className="admin-form__apercu">
                <div className="admin-form__apercu-entete">
                  <ShieldCheck size={15} aria-hidden="true" />
                  <span>Ce que ce rôle ouvre</span>
                  <Badge
                    variant={ROLE_BADGE_VARIANTS[formulaire.role] ?? "neutral"}
                  >
                    {ROLE_LABELS[formulaire.role] ?? formulaire.role}
                  </Badge>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setDetails((precedent) => !precedent)}
                  aria-expanded={details}
                >
                  <ChevronDown
                    size={14}
                    aria-hidden="true"
                    style={{
                      transform: details ? "rotate(180deg)" : "none",
                      transition: "transform var(--transition-fast)",
                    }}
                  />
                  {details
                    ? "Masquer le détail"
                    : "Détail des habilitations accordées"}
                </Button>
                {details && <ApercuHabilitations role={formulaire.role} />}
              </div>
            </>
          ) : (
            <>
              <div className="field">
                <span className="field__label">Adresse e-mail</span>
                <span className="meta-list__value">{formulaire.email}</span>
                <span className="field__hint">
                  Non modifiable depuis cet écran.
                </span>
              </div>
              <Select
                label="État du compte"
                value={formulaire.actif}
                onChange={(e) => change("actif", e.target.value)}
                hint="Un compte désactivé ne peut plus se connecter ; les jetons déjà émis restent valables jusqu'à leur expiration."
                disabled={submitting}
                options={[
                  { value: "true", label: "Actif" },
                  { value: "false", label: "Désactivé" },
                ]}
              />
              <div className="meta-list admin-form__meta">
                <div className="meta-list__item">
                  <span className="meta-list__label">Rôle</span>
                  <span className="meta-list__value">
                    <Badge
                      variant={ROLE_BADGE_VARIANTS[utilisateur?.role] ?? "neutral"}
                    >
                      {ROLE_LABELS[utilisateur?.role] ?? utilisateur?.role ?? "—"}
                    </Badge>
                  </span>
                </div>
                <div className="meta-list__item">
                  <span className="meta-list__label">Créé le</span>
                  <span className="meta-list__value">
                    {formatDateTime(utilisateur?.created_at)}
                  </span>
                </div>
                <div className="meta-list__item">
                  <span className="meta-list__label">Dernière connexion</span>
                  <span className="meta-list__value">
                    {utilisateur?.derniere_connexion
                      ? formatDateTime(utilisateur.derniere_connexion)
                      : "Jamais connecté"}
                  </span>
                </div>
              </div>
            </>
          )}
        </div>
      </form>
    </Modal>
  );
}

/** Modules et actions réellement accordés par un rôle. */
function ApercuHabilitations({ role }) {
  const modules = useMemo(
    () =>
      MODULES.map((nomModule) => ({
        nomModule,
        actions: actionsRoleModule(role, nomModule),
      })).filter((entree) => entree.actions.length > 0),
    [role]
  );

  return (
    <ul className="admin-apercu">
      {modules.map(({ nomModule, actions }) => (
        <li key={nomModule} className="admin-apercu__item">
          <span className="admin-apercu__module">
            {libelleModule(nomModule)}
            <small>{descriptionModule(nomModule)}</small>
          </span>
          <span className="admin-apercu__actions">
            {actions.map((permission) => (
              <span key={permission} className="admin-perm">
                {libelleAction(permission)}
              </span>
            ))}
          </span>
        </li>
      ))}
    </ul>
  );
}
