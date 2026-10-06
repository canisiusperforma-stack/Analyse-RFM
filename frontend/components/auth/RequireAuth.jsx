"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import Loading from "@/components/ui/Loading";

export default function RequireAuth({ children }) {
  const { isAuthenticated, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !isAuthenticated) {
      router.replace("/connexion");
    }
  }, [loading, isAuthenticated, router]);

  if (loading) {
    return <Loading variant="page" label="Vérification de la session…" />;
  }

  if (!isAuthenticated) {
    return null;
  }

  return children;
}