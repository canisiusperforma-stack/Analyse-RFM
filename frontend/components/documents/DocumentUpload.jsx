"use client";

import { useCallback, useMemo, useRef, useState } from "react";
import { AlertCircle, CheckCircle2, Info, UploadCloud } from "lucide-react";

import Button from "@/components/ui/Button";
import Input from "@/components/ui/Input";
import Select from "@/components/ui/Select";
import {
  NIVEAUX_CONFIDENTIALITE,
  libellesFormats,
} from "@/lib/documents";
import { getApiErrorText } from "@/lib/errors";
import { formatBytes } from "@/lib/formatters";
import { ROLES, ROLE_LABELS } from "@/lib/permissions";
import { cn } from "@/lib/utils";
import { televerserDocument } from "@/services/documentService";
import { usePermissions } from "@/hooks/usePermissions";

const OPTIONS_NIVEAU = NIVEAUX_CONFIDENTIALITE.map((niveau) => ({
  value: niveau.valeur,
  label: niveau.label,
}));

/**
 * Dépôt d'un document dans la base documentaire.
 *
 * Deux règles de sécurité gouvernent ce formulaire, et l'interface les
 * accompagne plutôt que de les laisser découvrir par un refus.
 *
 * Le dépôt crée un document `interne`. Classer `restreinte` ou `confidentielle`
 * exige la permission `documents:acces`, réservée à l'administrateur : sans
 * elle, le sélecteur de niveau n'est pas proposé. Rendre confidentiel un
 * fichier destiné à tous, puis le retirer aux autres en changeant sa
 * classification, reviendrait à laisser quiconque peut déposer décider de ce
 * que les autres verront.
 *
 * Un contenu déjà présent est refusé par le backend (`409`), y compris lorsque
 * le document d'origine n'est pas visible : borner la détection de doublon aux
 * documents accessibles permettrait de republier en `interne` un contenu
 * confidentiel dont on détient les octets. Le refus est donc restitué tel quel,
 * sans suggérer qu'un doublon n'existe pas.
 *
 * La liste blanche nominative n'est pas demandée ici : elle suppose de connaître
 * des identifiants d'utilisateurs, ce que l'écran de dépôt ne permet pas. Elle
 * se complète depuis la fiche du document, une fois le fichier archivé.
 */
export default function DocumentUpload({ onDepose, referentiel }) {
  const inputRef = useRef(null);
  const { has } = usePermissions();

  const [fichier, setFichier] = useState(null);
  const [description, setDescription] = useState("");
  const [confidentialite, setConfidentialite] = useState("interne");
  const [rolesAutorises, setRolesAutorises] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [erreur, setErreur] = useState(null);
  const [succes, setSucces] = useState(null);
  const [dragging, setDragging] = useState(false);

  const peutClasser = has("documents:acces");
  const classe = confidentialite !== "interne";

  const formatsAutorises = referentiel?.formats_autorises ?? [];
  const formatsListes =
    formatsAutorises.length > 0
      ? formatsAutorises
      : (referentiel?.formats_acceptes ?? []);
  const formatsAcceptes = useMemo(
    () => formatsListes.map((format) => `.${format}`).join(","),
    [formatsListes]
  );

  const tailleMax = referentiel?.taille_max_octets ?? null;

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

      const extension = (choisi.name || "").toLowerCase().split(".").pop();
      if (formatsAutorises.length > 0 && !formatsAutorises.includes(extension)) {
        setErreur(
          `Format « .${extension} » non pris en charge. Formats acceptés : ${libellesFormats(
            formatsAutorises
          )}.`
        );
        setFichier(null);
        return;
      }
      if (tailleMax && choisi.size > tailleMax) {
        setErreur(
          `Fichier trop volumineux (${formatBytes(choisi.size)}). Taille maximale : ${formatBytes(tailleMax)}.`
        );
        setFichier(null);
        return;
      }

      setFichier(choisi);
    },
    [formatsAutorises, tailleMax]
  );

  const basculerRole = useCallback((role) => {
    setRolesAutorises((precedents) =>
      precedents.includes(role)
        ? precedents.filter((item) => item !== role)
        : [...precedents, role]
    );
  }, []);

  const soumettre = async (event) => {
    event.preventDefault();
    if (!fichier || uploading) return;

    setUploading(true);
    setErreur(null);
    setSucces(null);
    try {
      const resultat = await televerserDocument({
        fichier,
        description: description.trim() || null,
        confidentialite,
        rolesAutorises: classe ? rolesAutorises : [],
      });

      const nom = resultat?.document?.nom_fichier ?? fichier.name;
      const indexation = resultat?.indexation;

      if (resultat?.indexation_demandee) {
        setSucces(
          indexation?.succes
            ? `« ${nom} » déposé et indexé — ${indexation.nb_morceaux} extrait(s), ${indexation.nb_caracteres} caractères.`
            : `« ${nom} » déposé, mais l'extraction a échoué : ${
                indexation?.message || "motif non précisé"
              }. Le document reste consultable et supprimable, seulement pas interrogeable.`
        );
      } else {
        setSucces(
          `« ${nom} » déposé. L'indexation n'a pas été demandée : la recherche documentaire étant désactivée, aucun texte n'a été découpé ni vectorisé.`
        );
      }

      setFichier(null);
      setDescription("");
      setConfidentialite("interne");
      setRolesAutorises([]);
      if (inputRef.current) inputRef.current.value = "";
      onDepose?.(resultat);
    } catch (errorDepot) {
      setErreur(getApiErrorText(errorDepot));
    } finally {
      setUploading(false);
    }
  };

  return (
    <form className="card card__padding" onSubmit={soumettre}>
      <h3 className="card__title">Déposer un document</h3>
      <p className="text-muted">
        Le fichier est archivé tel qu&apos;il est reçu, puis découpé et vectorisé
        pour la recherche documentaire. Un contenu déjà présent est refusé.
      </p>

      <input
        ref={inputRef}
        type="file"
        accept={formatsAcceptes || undefined}
        className="sr-only"
        onChange={(event) => selectionner(event.target.files)}
        id="document-fichier"
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
        <span className="dropzone__hint">
          {fichier
            ? `${formatBytes(fichier.size)} — cliquer pour changer`
            : `ou cliquez pour parcourir — ${libellesFormats(formatsListes)}${
                tailleMax ? `, ${formatBytes(tailleMax)} maximum` : ""
              }`}
        </span>
      </div>

      <div className="import-options" style={{ marginTop: 14 }}>
        <Input
          label="Description"
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          placeholder="Objet du document, date, référence administrative…"
          hint="Facultatif. Sert à la traçabilité, pas à la recherche."
        />

        {peutClasser ? (
          <Select
            label="Confidentialité"
            value={confidentialite}
            onChange={(event) => {
              setConfidentialite(event.target.value);
              setRolesAutorises([]);
            }}
            options={OPTIONS_NIVEAU}
            hint="Réservé à l'administrateur"
          />
        ) : (
          <div className="field">
            <span className="field__label">Confidentialité</span>
            <span
              className="input"
              style={{ background: "var(--color-surface-alt)", color: "var(--color-text-muted)" }}
            >
              Interne
            </span>
            <span className="field__hint">
              Le dépôt crée toujours un document interne
            </span>
          </div>
        )}
      </div>

      {peutClasser && classe && (
        <div
          className="filtres-bar"
          style={{ marginTop: 12, gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))" }}
        >
          {ROLES.map((role) => (
            <label
              key={role}
              className="filtres-bar__champ"
              style={{ display: "flex", gap: 8, alignItems: "center" }}
            >
              <input
                type="checkbox"
                checked={rolesAutorises.includes(role)}
                onChange={() => basculerRole(role)}
              />
              <span className="tableau__sous-texte">{ROLE_LABELS[role] ?? role}</span>
            </label>
          ))}
          <p
            className="text-muted"
            style={{ gridColumn: "1 / -1", margin: 0 }}
          >
            Rôles autorisés à lire ce document. Un niveau classé sans aucun rôle
            autorisé serait inaccessible à tout le monde : le backend le refuse.
          </p>
        </div>
      )}

      {!peutClasser && (
        <p className="text-muted" style={{ marginTop: 10 }}>
          <Info size={13} aria-hidden="true" /> Le dépôt crée un document{" "}
          <strong>interne</strong>. Sa classification se fixe ensuite par
          l&apos;administrateur, depuis la fiche du document.
        </p>
      )}

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

      <div style={{ marginTop: 12 }}>
        <Button
          type="submit"
          loading={uploading}
          disabled={!fichier}
          title={fichier ? undefined : "Sélectionnez d'abord un fichier"}
        >
          {uploading ? "Dépôt en cours…" : "Déposer le document"}
        </Button>
      </div>
    </form>
  );
}
