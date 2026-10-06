"use client";

import { useCallback, useRef, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  FileSpreadsheet,
  FileText,
  UploadCloud,
} from "lucide-react";

import Button from "@/components/ui/Button";
import Input from "@/components/ui/Input";
import Select from "@/components/ui/Select";
import { getApiErrorText } from "@/lib/errors";
import { formatBytes } from "@/lib/formatters";
import { cn } from "@/lib/utils";
import { importerFichier } from "@/services/importService";

const ENCODAGES = [
  { value: "", label: "Détection automatique" },
  { value: "utf-8-sig", label: "UTF-8 (BOM)" },
  { value: "utf-8", label: "UTF-8" },
  { value: "cp1252", label: "Windows-1252" },
  { value: "latin-1", label: "Latin-1" },
];

const DELIMITEURS = [
  { value: "", label: "Détection automatique" },
  { value: ",", label: "Virgule (,)" },
  { value: ";", label: "Point-virgule (;)" },
  { value: "\t", label: "Tabulation" },
];

const TAILLE_MAX_OCTETS = 50 * 1024 * 1024;
const EXTENSIONS = [".csv", ".xlsx"];

function iconeFichier(nomFichier) {
  return nomFichier?.toLowerCase().endsWith(".xlsx")
    ? FileSpreadsheet
    : FileText;
}

export default function ImportUpload({ onImported }) {
  const inputRef = useRef(null);
  const [fichier, setFichier] = useState(null);
  const [encodage, setEncodage] = useState("");
  const [delimiteur, setDelimiteur] = useState("");
  const [colonnesObligatoires, setColonnesObligatoires] = useState("");
  const [feuille, setFeuille] = useState("0");
  const [deverser, setDeverser] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [erreur, setErreur] = useState(null);
  const [succes, setSucces] = useState(null);
  const [dragging, setDragging] = useState(false);

  const ignorer = useCallback((event) => {
    event.preventDefault();
    event.stopPropagation();
  }, []);

  const selectionner = useCallback(
    (fichiers) => {
      setErreur(null);
      setSucces(null);
      const choisi = fichiers?.[0];
      if (!choisi) return;

      const nom = (choisi.name || "").toLowerCase();
      if (!EXTENSIONS.some((ext) => nom.endsWith(ext))) {
        setErreur(
          "Format non supporté. Formats autorisés : CSV (.csv) et Excel (.xlsx)."
        );
        setFichier(null);
        return;
      }
      if (choisi.size > TAILLE_MAX_OCTETS) {
        setErreur(
          `Fichier trop volumineux (${formatBytes(choisi.size)}). Taille maximale : 50 Mo.`
        );
        setFichier(null);
        return;
      }
      setFichier(choisi);
    },
    []
  );

  const soumettre = async (event) => {
    event.preventDefault();
    if (!fichier || uploading) return;

    setUploading(true);
    setErreur(null);
    setSucces(null);
    try {
      const resultat = await importImportation();
      setSucces(
        `Importation terminée : ${resultat.rapport?.nb_lignes_importees ?? 0} lignes conservées.`
      );
      setFichier(null);
      if (inputRef.current) inputRef.current.value = "";
      onImported?.(resultat);
    } catch (errorImport) {
      setErreur(getApiErrorText(errorImport));
    } finally {
      setUploading(false);
    }
  };

  async function importImportation() {
    let idUtilisateur = null;
    if (typeof window !== "undefined") {
      try {
        const brut = window.localStorage.getItem("rfm_user");
        if (brut) {
          const infos = JSON.parse(brut);
          idUtilisateur = infos?.id || null;
        }
      } catch {
        idUtilisateur = null;
      }
    }
    const colonnes = colonnesObligatoires
      .split(",")
      .map((col) => col.trim())
      .filter(Boolean);

    return importerFichier({
      fichier,
      encodage: encodage || null,
      delimiteur: delimiteur || null,
      feuille: Number(feuille) || 0,
      colonnesObligatoires: colonnes,
      deversement: deverser,
      utilisateurId: idUtilisateur,
    });
  }

  return (
    <form className="card card__padding" onSubmit={soumettre}>
      <input
        ref={inputRef}
        type="file"
        accept=".csv,.xlsx"
        className="sr-only"
        onChange={(event) => selectionner(event.target.files)}
        id="import-fichier"
      />

      <div
        className={cn("dropzone", dragging && "dropzone--dragging")}
        onClick={() => inputRef.current?.click()}
        onDragOver={(event) => {
          ignorer(event);
          setDragging(true);
        }}
        onDragLeave={(event) => {
          ignorer(event);
          setDragging(false);
        }}
        onDrop={(event) => {
          ignorer(event);
          setDragging(false);
          selectionner(event.dataTransfer?.files);
        }}
      >
        <span className="dropzone__icon" aria-hidden="true">
          <UploadCloud size={22} />
        </span>
        <span className="dropzone__title">
          {fichier ? fichier.name : "Glissez un fichier ici"}
        </span>
        {fichier ? (
          <span className="dropzone__hint">
            {fichier.name} — {formatBytes(fichier.size)} (cliquer pour changer)
          </span>
        ) : (
          <span className="dropzone__hint">
            ou cliquez pour parcourir — CSV ou XLSX, 50 Mo maximum
          </span>
        )}
        {fichier && (
          <span className="dropzone__file">
            {(() => {
              const Icone = iconeFichier(fichier.name);
              return <Icone size={16} aria-hidden="true" />;
            })()}
          </span>
        )}
      </div>

      <div className="import-options">
        <Select
          label="Encodage"
          options={ENCODAGES}
          value={encodage}
          onChange={(event) => setEncodage(event.target.value)}
        />
        <Select
          label="Séparateur"
          options={DELIMITEURS}
          value={delimiteur}
          onChange={(event) => setDelimiteur(event.target.value)}
        />
        <Input
          label="Feuille Excel"
          type="number"
          min="0"
          value={feuille}
          onChange={(event) => setFeuille(event.target.value)}
          hint="Index de la feuille (défaut 0)"
        />
        <Input
          label="Colonnes obligatoires"
          value={colonnesObligatoires}
          onChange={(event) => setColonnesObligatoires(event.target.value)}
          hint="Noms normalisés séparés par des virgules"
          placeholder="matricule, exercice"
        />
        <label
          className="import-options__checkbox"
          style={{ display: "flex", gap: 8, alignItems: "flex-start" }}
        >
          <input
            type="checkbox"
            checked={deverser}
            onChange={(event) => setDeverser(event.target.checked)}
          />
          <span>
            Déverser vers les collections métier
            <span className="text-muted" style={{ display: "block", fontSize: 12 }}>
              Insertion ou mise à jour des bénéficiaires, budgets, exécutions et
              remboursements par clé naturelle (réimport possible sans doublon).
            </span>
          </span>
        </label>
      </div>

      {erreur && (
        <div className="alert alert--error" role="alert">
          <AlertCircle size={18} className="alert__icon" aria-hidden="true" />
          <span>{erreur}</span>
        </div>
      )}
      {succes && (
        <div className="alert alert--success" role="status">
          <CheckCircle2 size={18} className="alert__icon" aria-hidden="true" />
          <span>{succes}</span>
        </div>
      )}

      <Button
        type="submit"
        loading={uploading}
        disabled={!fichier}
        title={fichier ? undefined : "Sélectionnez d'abord un fichier"}
      >
        {uploading ? "Importation en cours…" : "Importer et analyser"}
      </Button>
    </form>
  );
}