import Forbidden from "@/components/auth/Forbidden";

export const metadata = { title: "Accès refusé" };

export default function PageInterdite() {
  return <Forbidden />;
}