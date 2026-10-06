"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import { connexion as serviceConnexion } from "@/services/authService";
import { inscription as serviceInscription } from "@/services/authService";
import { recupererMoi } from "@/services/authService";

const TOKEN_KEY = "rfm_token";
const USER_KEY = "rfm_user";
const PERMISSIONS_KEY = "rfm_permissions";
const EXPIRES_KEY = "rfm_token_expires_at";

function sessionExpiree(expiresAt) {
  if (!expiresAt) return false;
  const expiration = new Date(expiresAt).getTime();
  return Number.isFinite(expiration) && expiration <= Date.now();
}

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(null);
  const [permissions, setPermissions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [sessionError, setSessionError] = useState(null);

  const nettoyerSession = useCallback(() => {
    if (typeof window === "undefined") return;
    window.localStorage.removeItem(TOKEN_KEY);
    window.localStorage.removeItem(USER_KEY);
    window.localStorage.removeItem(PERMISSIONS_KEY);
    window.localStorage.removeItem(EXPIRES_KEY);
    setToken(null);
    setUser(null);
    setPermissions([]);
    setSessionError(null);
  }, []);

  const restaurerSession = useCallback(async () => {
    if (typeof window === "undefined") {
      setLoading(false);
      return;
    }
    setLoading(true);
    setSessionError(null);

    const jeton = window.localStorage.getItem(TOKEN_KEY);
    if (!jeton) {
      setLoading(false);
      return;
    }

    const expiration = window.localStorage.getItem(EXPIRES_KEY);
    if (sessionExpiree(expiration)) {
      nettoyerSession();
      setSessionError(
        "Votre session a expiré. Veuillez vous reconnecter."
      );
      setLoading(false);
      return;
    }

    // Le contexte ne fait jamais confiance à l'utilisateur en cache :
    // la session est revalidée côté serveur via /auth/me.
    try {
      let cache = null;
      let permissionsCache = [];
      try {
        cache = JSON.parse(window.localStorage.getItem(USER_KEY) || "null");
        permissionsCache = JSON.parse(
          window.localStorage.getItem(PERMISSIONS_KEY) || "[]"
        );
      } catch {
        window.localStorage.removeItem(USER_KEY);
        window.localStorage.removeItem(PERMISSIONS_KEY);
      }
      if (cache) setUser(cache);
      if (permissionsCache.length > 0) setPermissions(permissionsCache);
      setToken(jeton);

      const donnees = await recupererMoi();
      const utilisateur = donnees?.utilisateur ?? null;
      const permissionsServeur = Array.isArray(donnees?.permissions)
        ? donnees.permissions
        : [];
      setUser(utilisateur);
      setPermissions(permissionsServeur);
      if (utilisateur) {
        window.localStorage.setItem(USER_KEY, JSON.stringify(utilisateur));
      }
      if (permissionsServeur.length > 0) {
        window.localStorage.setItem(
          PERMISSIONS_KEY,
          JSON.stringify(permissionsServeur)
        );
      }
    } catch (erreur) {
      nettoyerSession();
      if (erreur?.status === 401) {
        setSessionError(
          "Votre session a expiré. Veuillez vous reconnecter."
        );
      }
    } finally {
      setLoading(false);
    }
  }, [nettoyerSession]);

  useEffect(() => {
    restaurerSession();
  }, [restaurerSession]);

  // Session invalidée en cours d'utilisation (réponse 401 de l'API).
  useEffect(() => {
    const gererExpiration = () => {
      nettoyerSession();
      setSessionError(
        "Votre session a expiré. Veuillez vous reconnecter."
      );
    };
    window.addEventListener("auth:expired", gererExpiration);
    return () => window.removeEventListener("auth:expired", gererExpiration);
  }, [nettoyerSession]);

  const login = useCallback(async (email, motDePasse) => {
    const donnees = await serviceConnexion({ email, motDePasse });
    const permissionsServeur = Array.isArray(donnees.permissions)
      ? donnees.permissions
      : [];
    if (typeof window !== "undefined") {
      window.localStorage.setItem(TOKEN_KEY, donnees.access_token);
      window.localStorage.setItem(
        USER_KEY,
        JSON.stringify(donnees.utilisateur || {})
      );
      window.localStorage.setItem(
        PERMISSIONS_KEY,
        JSON.stringify(permissionsServeur)
      );
      if (donnees.expires_at) {
        window.localStorage.setItem(EXPIRES_KEY, donnees.expires_at);
      }
    }
    setToken(donnees.access_token);
    setUser(donnees.utilisateur ?? null);
    setPermissions(permissionsServeur);
    setSessionError(null);
    return donnees;
  }, []);

  const register = useCallback(async (infos) => {
    const donnees = await serviceInscription(infos);
    const permissionsServeur = Array.isArray(donnees.permissions)
      ? donnees.permissions
      : [];
    if (typeof window !== "undefined") {
      window.localStorage.setItem(TOKEN_KEY, donnees.access_token);
      window.localStorage.setItem(
        USER_KEY,
        JSON.stringify(donnees.utilisateur || {})
      );
      window.localStorage.setItem(
        PERMISSIONS_KEY,
        JSON.stringify(permissionsServeur)
      );
      if (donnees.expires_at) {
        window.localStorage.setItem(EXPIRES_KEY, donnees.expires_at);
      }
    }
    setToken(donnees.access_token);
    setUser(donnees.utilisateur ?? null);
    setPermissions(permissionsServeur);
    setSessionError(null);
    return donnees;
  }, []);

  const logout = useCallback(() => {
    nettoyerSession();
  }, [nettoyerSession]);

  const recharger = useCallback(async () => {
    const donnees = await recupererMoi();
    const utilisateur = donnees?.utilisateur ?? null;
    const permissionsServeur = Array.isArray(donnees?.permissions)
      ? donnees.permissions
      : [];
    setUser(utilisateur);
    setPermissions(permissionsServeur);
    if (utilisateur && typeof window !== "undefined") {
      window.localStorage.setItem(USER_KEY, JSON.stringify(utilisateur));
    }
    if (permissionsServeur.length > 0 && typeof window !== "undefined") {
      window.localStorage.setItem(
        PERMISSIONS_KEY,
        JSON.stringify(permissionsServeur)
      );
    }
    return donnees;
  }, []);

  const value = useMemo(
    () => ({
      user,
      token,
      permissions,
      loading,
      sessionError,
      isAuthenticated: Boolean(token),
      login,
      register,
      logout,
      recharger,
    }),
    [
      user,
      token,
      permissions,
      loading,
      sessionError,
      login,
      register,
      logout,
      recharger,
    ]
  );

  return <AuthContext value={value}>{children}</AuthContext>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth doit être utilisé à l'intérieur de <AuthProvider>");
  }
  return ctx;
}