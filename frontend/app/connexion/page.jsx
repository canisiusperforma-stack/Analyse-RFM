"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { AlertCircle, Eye, EyeOff, LogIn, ShieldCheck } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { getApiErrorText } from "@/lib/errors";
import { APP_NAME } from "@/lib/constants";
import Input from "@/components/ui/Input";
import Button from "@/components/ui/Button";
import Loading from "@/components/ui/Loading";

export default function ConnexionPage() {
  const { user, isAuthenticated, loading, sessionError, login } = useAuth();
  const router = useRouter();

  const [email, setEmail] = useState("");
  const [motDePasse, setMotDePasse] = useState("");
  const [showMotDePasse, setShowMotDePasse] = useState(false);
  const [soumission, setSoumission] = useState(false);
  const [erreur, setErreur] = useState(null);

  useEffect(() => {
    if (!loading && isAuthenticated && user) {
      router.replace("/dashboard");
    }
  }, [loading, isAuthenticated, user, router]);

  if (loading) {
    return <Loading variant="page" label="Vérification de la session…" />;
  }

  if (isAuthenticated && user) {
    return null;
  }

  const messageSession = sessionError || erreur;

  const handleSubmit = async (evenement) => {
    evenement.preventDefault();
    setErreur(null);

    if (!email.trim() || !motDePasse) {
      setErreur("Veuillez saisir votre adresse e-mail et votre mot de passe.");
      return;
    }

    setSoumission(true);
    try {
      await login(email.trim(), motDePasse);
      router.replace("/dashboard");
    } catch (e) {
      setErreur(getApiErrorText(e));
    } finally {
      setSoumission(false);
    }
  };

  return (
    <main className="auth-shell__main">
      <div className="auth-card">
        <div className="auth-card__brand">
          <span className="brand-mark" aria-hidden="true">
            <ShieldCheck size={22} />
          </span>
          <div className="auth-card__brand-text">
            <strong>RFM · SRB</strong>
            <small>Vatovavy</small>
          </div>
        </div>

        <h1 className="auth-card__title">Connexion</h1>
        <p className="auth-card__subtitle">
          Accédez à {APP_NAME} avec votre compte institutionnel.
        </p>

        {messageSession && (
          <div className="alert alert--error" role="alert">
            <AlertCircle size={18} className="alert__icon" aria-hidden="true" />
            <span>{messageSession}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} noValidate>
          <Input
            label="Adresse e-mail"
            type="email"
            name="email"
            autoComplete="email"
            placeholder="prenom.nom@srb.gov.mg"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            disabled={soumission}
          />
          <Input
            label="Mot de passe"
            type={showMotDePasse ? "text" : "password"}
            name="mot_de_passe"
            autoComplete="current-password"
            placeholder="••••••••"
            value={motDePasse}
            onChange={(e) => setMotDePasse(e.target.value)}
            required
            disabled={soumission}
          />
          <div className="auth-card__options">
            <button
              type="button"
              className="auth-card__toggle"
              onClick={() => setShowMotDePasse((v) => !v)}
              aria-pressed={showMotDePasse}
            >
              {showMotDePasse ? (
                <>
                  <EyeOff size={15} aria-hidden="true" /> Masquer
                </>
              ) : (
                <>
                  <Eye size={15} aria-hidden="true" /> Afficher
                </>
              )}
            </button>
          </div>
          <Button
            type="submit"
            variant="primary"
            size="lg"
            fullWidth
            loading={soumission}
            disabled={soumission}
          >
            <LogIn size={17} aria-hidden="true" />
            Se connecter
          </Button>
        </form>

        <p className="auth-card__footer">
          Retour à <Link href="/">l&apos;accueil</Link>
        </p>
      </div>
    </main>
  );
}