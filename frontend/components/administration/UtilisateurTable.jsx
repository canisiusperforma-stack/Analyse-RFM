"use client";

import { useMemo } from "react";
import {
  KeyRound,
  LogIn,
  Pencil,
  RefreshCw,
  Search,
  Trash2,
  UserCog,
  Users,
} from "lucide-react";

import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import Table from "@/components/ui/Table";
import Input from "@/components/ui/Input";
import Select from "@/components/ui/Select";
import { usePermissions } from "@/hooks/usePermissions";
import { useAuth } from "@/context/AuthContext";
import { ROLE_BADGE_VARIANTS, ROLE_LABELS, ROLES } from "@/lib/permissions";
import { nomComplet } from "@/lib/administration";
import { formatDateTime, initials } from "@/lib/formatters";

const FILTRES_ETAT = [
  { value: "", label: "Tous les états" },
  { value: "actif", label: "Actifs" },
  { value: "inactif", label: "Désactivés" },
];

/**
 * Liste des comptes.
 *
 * Deux protections contre l'auto-sabotage, toutes deux visibles avant le clic :
 * le backend interdit de changer son propre rôle et de supprimer son propre
 * compte, et il interdit de désactiver le dernier administrateur via la
 * console… ce qu'il ne peut pas voir. Le tableau ne prétend donc pas le
 * deviner — il désactive l'action sur soi-même, ce qu'il sait avec certitude,
 * et laisse le reste au refus du serveur.
 *
 * Le filtre par mot-clé s'applique à la page affichée, pas à la population :
 * le backend n'expose pas de recherche sur les comptes, et le faire croire
 * reviendrait à annoncer une exhaustivité qui n'existe pas.
 */
export default function UtilisateurTable({
  comptes = [],
  loading = false,
  filtres,
  onFiltres,
  recherche,
  onRecherche,
  onReinitialiser,
  filtresActifs = false,
  actionEnCours = null,
  onRefresh,
  onOuvrir,
  onModifier,
  onChangerRole,
  onSupprimer,
}) {
  const { has } = usePermissions();
  const { user: utilisateurCourant } = useAuth();

  const peutCreer = has("utilisateurs:creer");
  const peutModifier = has("utilisateurs:modifier");
  const peutChangerRole = has("utilisateurs:changer_role");
  const peutSupprimer = has("utilisateurs:supprimer");

  const visibles = useMemo(() => {
    const terme = recherche.trim().toLowerCase();
    if (!terme) return comptes;
    return comptes.filter((utilisateur) =>
      [utilisateur.prenom, utilisateur.nom, utilisateur.email, utilisateur.role]
        .filter(Boolean)
        .some((champ) => String(champ).toLowerCase().includes(terme))
    );
  }, [comptes, recherche]);

  const colonnes = useMemo(
    () => [
      {
        key: "identite",
        header: "Utilisateur",
        render: (utilisateur) => (
          <div className="admin-identite">
            <span className="avatar" aria-hidden="true">
              {initials(nomComplet(utilisateur))}
            </span>
            <div style={{ minWidth: 0 }}>
              <div className="tableau__nom">{nomComplet(utilisateur)}</div>
              <span className="tableau__sous-texte" style={{ display: "block" }}>
                {utilisateur.email}
              </span>
            </div>
          </div>
        ),
      },
      {
        key: "role",
        header: "Rôle",
        width: "150px",
        render: (utilisateur) => (
          <Badge variant={ROLE_BADGE_VARIANTS[utilisateur.role] ?? "neutral"}>
            {ROLE_LABELS[utilisateur.role] ?? utilisateur.role}
          </Badge>
        ),
      },
      {
        key: "actif",
        header: "État",
        width: "130px",
        render: (utilisateur) => (
          <Badge variant={utilisateur.actif ? "success" : "neutral"} dot>
            {utilisateur.actif ? "Actif" : "Désactivé"}
          </Badge>
        ),
      },
      {
        key: "derniere_connexion",
        header: "Dernière connexion",
        render: (utilisateur) =>
          utilisateur.derniere_connexion ? (
            <span title={formatDateTime(utilisateur.derniere_connexion)}>
              {formatDateTime(utilisateur.derniere_connexion)}
            </span>
          ) : (
            <span className="text-muted">Jamais connecté</span>
          ),
      },
      {
        key: "created_at",
        header: "Créé le",
        render: (utilisateur) => formatDateTime(utilisateur.created_at),
      },
      {
        key: "actions",
        header: "",
        width: "220px",
        render: (utilisateur) => {
          const enCours = actionEnCours === utilisateur.id;
          const soiMeme =
            utilisateur.id != null && utilisateur.id === utilisateurCourant?.id;
          return (
            <div
              style={{ display: "flex", gap: 6, justifyContent: "flex-end" }}
            >
              {peutModifier && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => onOuvrir?.(utilisateur)}
                  aria-label={`Ouvrir la fiche de ${nomComplet(utilisateur)}`}
                >
                  <Pencil size={14} aria-hidden="true" />
                  Fiche
                </Button>
              )}
              {peutChangerRole && (
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={soiMeme}
                  title={
                    soiMeme
                      ? "Le backend interdit de modifier son propre rôle : cela pourrait verrouiller la plateforme."
                      : `Changer le rôle de ${nomComplet(utilisateur)}`
                  }
                  onClick={() => onChangerRole?.(utilisateur)}
                  aria-label={`Changer le rôle de ${nomComplet(utilisateur)}`}
                >
                  <UserCog size={14} aria-hidden="true" />
                </Button>
              )}
              {peutSupprimer && (
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={soiMeme}
                  title={
                    soiMeme
                      ? "Le backend interdit de supprimer son propre compte."
                      : `Supprimer ${nomComplet(utilisateur)}`
                  }
                  loading={enCours}
                  onClick={() => onSupprimer?.(utilisateur)}
                  aria-label={`Supprimer ${nomComplet(utilisateur)}`}
                >
                  {!enCours && <Trash2 size={14} aria-hidden="true" />}
                </Button>
              )}
            </div>
          );
        },
      },
    ],
    [actionEnCours, onChangerRole, onOuvrir, onSupprimer, peutChangerRole, peutModifier, peutSupprimer, utilisateurCourant]
  );

  return (
    <section className="card">
      <div className="card__header">
        <div>
          <h3 className="card__title">Comptes</h3>
          <p className="text-muted">
            {recherche.trim()
              ? `${visibles.length} résultat(s) sur cette page`
              : "Recherche limitée à la page affichée — le backend n'expose pas de recherche sur les comptes."}
          </p>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={onRefresh}
          loading={loading}
          aria-label="Actualiser la liste des comptes"
        >
          {!loading && <RefreshCw size={16} aria-hidden="true" />}
          Actualiser
        </Button>
      </div>

      <div className="filtres-bar admin-filtres">
        <div className="filtres-bar__champ--recherche">
          <Input
            label="Rechercher"
            type="search"
            value={recherche}
            onChange={(evenement) => onRecherche(evenement.target.value)}
            placeholder="Nom ou e-mail, sur la page affichée"
          />
        </div>
        <Select
          label="Rôle"
          value={filtres.role}
          onChange={(evenement) => onFiltres({ role: evenement.target.value })}
          placeholder="Tous les rôles"
          options={ROLES.map((role) => ({
            value: role,
            label: ROLE_LABELS[role] ?? role,
          }))}
        />
        <Select
          label="État"
          value={filtres.actif}
          onChange={(evenement) => onFiltres({ actif: evenement.target.value })}
          options={FILTRES_ETAT}
        />
        {filtresActifs && (
          <Button
            variant="ghost"
            size="sm"
            className="filtres-bar__reinitialiser"
            onClick={onReinitialiser}
          >
            Réinitialiser
          </Button>
        )}
      </div>

      <Table
        columns={colonnes}
        data={visibles}
        rowKey="id"
        loading={loading}
        empty={{
          icon: Users,
          title:
            comptes.length > 0
              ? "Aucun compte ne correspond aux filtres"
              : "Aucun compte",
          description:
            comptes.length > 0
              ? "Modifiez la recherche, le rôle ou l'état pour élargir la sélection."
              : peutCreer
                ? "Créez le premier compte pour ouvrir l'accès à la plateforme."
                : "Aucun compte n'est enregistré sur la plateforme.",
          action:
            comptes.length === 0 && peutCreer ? (
              <Badge variant="info">
                <KeyRound size={13} aria-hidden="true" /> Bouton « Nouveau
                compte » ci-dessus
              </Badge>
            ) : undefined,
        }}
      />

      <p className="text-muted admin-tableau__pied">
        <LogIn size={13} aria-hidden="true" /> La dernière connexion n&apos;est
        renseignée qu&apos;à la connexion : un compte actif qui n&apos;a jamais
        de date n&apos;a jamais ouvert la plateforme.
      </p>
    </section>
  );
}
