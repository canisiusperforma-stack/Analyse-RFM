"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import {
  changerRoleUtilisateur,
  creerUtilisateur,
  listerUtilisateurs,
  modifierUtilisateur,
  supprimerUtilisateur,
} from "@/services/utilisateursService";
import { ROLES } from "@/lib/permissions";

const FILTRES_INITIAUX = { role: "", actif: "" };
const LIMITE_PAGE = 20;

/** Le backend plafonne `limite` à 500 : c'est la fenêtre d'un coup de regard. */
const LIMITE_CENSUS = 500;

/**
 * État de la page « Utilisateurs ».
 *
 * Deux chargements distincts, et non un seul.
 *
 * `liste` respecte les filtres et la pagination : c'est la vue de travail. Le
 * backend ne propose ni recherche textuelle ni statistiques sur les comptes, or
 * une barre de répartition par rôles calculée sur la page courante afficherait
 * « 3 administrateurs » là où il y en a peut-être douze. `census` charge donc
 * l'ensemble des comptes une fois, sans filtre, et sert uniquement aux
 * compteurs. Quand la population dépasse la fenêtre, il est dit explicitement
 * que le décompte porte sur les premiers comptes — un indicateur approximatif
 * annoncé comme exact est pire qu'un indicateur absent.
 *
 * Chaque action renvoie la version fraîche renvoyée par le backend : la
 * désactivation d'un compte, le changement de rôle et la suppression ont des
 * effets que le client ne peut pas deviner, et un état optimiste afficherait un
 * résultat qui n'a pas eu lieu.
 */
export default function useUtilisateurs() {
  const [liste, setListe] = useState(null);
  const [census, setCensus] = useState(null);
  const [filtres, setFiltres] = useState(FILTRES_INITIAUX);
  const [saut, setSaut] = useState(0);
  const [recherche, setRecherche] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [actionEnCours, setActionEnCours] = useState(null);

  const modifieFiltres = useCallback((patch) => {
    setFiltres((precedents) => ({ ...precedents, ...patch }));
    setSaut(0);
  }, []);

  const reinitialiserFiltres = useCallback(() => {
    setFiltres(FILTRES_INITIAUX);
    setRecherche("");
    setSaut(0);
  }, []);

  const recharger = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const donnees = await listerUtilisateurs({
        limite: LIMITE_PAGE,
        saut,
        role: filtres.role || null,
        actif: filtres.actif === "" ? null : filtres.actif === "actif",
      });
      setListe(donnees);
      return donnees;
    } catch (erreur) {
      setError(erreur);
      throw erreur;
    } finally {
      setLoading(false);
    }
  }, [filtres.actif, filtres.role, saut]);

  const rechargerCensus = useCallback(async () => {
    try {
      setCensus(await listerUtilisateurs({ limite: LIMITE_CENSUS }));
    } catch {
      // Les compteurs sont un complément : leur absence ne doit pas empêcher
      // d'administrer les comptes, qui reste entièrement fonctionnel sans eux.
      setCensus(null);
    }
  }, []);

  useEffect(() => {
    recharger().catch(() => {
      // l'erreur est exposée via `error`
    });
  }, [recharger]);

  useEffect(() => {
    rechargerCensus();
  }, [rechargerCensus]);

  /** Remplace un compte dans la page courante, à partir de sa version fraîche. */
  const remplacer = useCallback((utilisateur) => {
    if (!utilisateur?.id) return;
    setListe((precedents) => {
      if (!precedents) return precedents;
      return {
        ...precedents,
        utilisateurs: precedents.utilisateurs.map((item) =>
          item.id === utilisateur.id ? utilisateur : item
        ),
      };
    });
  }, []);

  const creer = useCallback(
    async (compte) => {
      const utilisateur = await creerUtilisateur(compte);
      await Promise.all([recharger().catch(() => {}), rechargerCensus()]);
      return utilisateur;
    },
    [recharger, rechargerCensus]
  );

  const modifier = useCallback(
    async (identifiant, changements) => {
      setActionEnCours(identifiant);
      try {
        const utilisateur = await modifierUtilisateur(identifiant, changements);
        remplacer(utilisateur);
        await rechargerCensus();
        return utilisateur;
      } finally {
        setActionEnCours(null);
      }
    },
    [remplacer, rechargerCensus]
  );

  const changerRole = useCallback(
    async (identifiant, role) => {
      setActionEnCours(identifiant);
      try {
        const utilisateur = await changerRoleUtilisateur(identifiant, role);
        remplacer(utilisateur);
        await rechargerCensus();
        return utilisateur;
      } finally {
        setActionEnCours(null);
      }
    },
    [remplacer, rechargerCensus]
  );

  const supprimer = useCallback(
    async (identifiant) => {
      setActionEnCours(identifiant);
      try {
        await supprimerUtilisateur(identifiant);
        // La suppression est définitive : la page courante est rechargée pour
        // combler le trou laissé, plutôt que décalee optimistement.
        await Promise.all([recharger().catch(() => {}), rechargerCensus()]);
      } finally {
        setActionEnCours(null);
      }
    },
    [recharger, rechargerCensus]
  );

  const comptes = useMemo(() => census?.utilisateurs ?? [], [census]);

  const compte = useMemo(() => {
    const population = census?.total ?? 0;
    const parRole = ROLES.map((role) => ({
      role,
      total: comptes.filter((utilisateur) => utilisateur.role === role).length,
    }));
    const actifs = comptes.filter((utilisateur) => utilisateur.actif).length;
    return {
      population,
      actifs,
      inactifs: comptes.length - actifs,
      parRole,
      // `derniere_connexion` n'est renseigné qu'à la connexion : un compte actif
      // qui n'y figure jamais n'a jamais ouvert la plateforme.
      jamaisConnectes: comptes.filter(
        (utilisateur) => utilisateur.actif && !utilisateur.derniere_connexion
      ).length,
      // La fenêtre de census est bornée : au-delà, les compteurs sont partiels
      // et le tableau le signale plutôt que de présenter un faux total.
      partiel: population > comptes.length,
      observe: comptes.length,
    };
  }, [census, comptes]);

  const filtresActifs =
    filtres.role !== "" || filtres.actif !== "" || recherche.trim() !== "";

  return {
    liste,
    comptes: liste?.utilisateurs ?? [],
    census,
    compte,
    filtres,
    modifieFiltres,
    reinitialiserFiltres,
    recherche,
    setRecherche,
    filtresActifs,
    saut,
    setSaut,
    limite: LIMITE_PAGE,
    loading,
    error,
    actionEnCours,
    recharger,
    rechargerCensus,
    creer,
    modifier,
    changerRole,
    supprimer,
  };
}
