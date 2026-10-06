"use client";

import { ChevronDown, FileText, Link2, Quote } from "lucide-react";

import { documents } from "@/lib/assistant";

/**
 * Extraits retenus par la recherche documentaire.
 *
 * Ce composant est la contrepartie visible de `sources` dans la réponse : là où
 * `sources` dit ce que le backend a interrogé pour *calculer*, les extraits
 * ci-dessous disent quels *textes* ont été lus pour *règle*. Les deux listes
 * sont volontairement rendues par des composants distincts, car les confondre
 * ferait croire qu'un chiffre vient d'un document alors qu'il vient d'un calcul.
 *
 * Rien n'est interprété ici. Un extrait n'est affiché que s'il est présent dans
 * `documents`, il est cité tel que le backend l'a rédigé et anonymisé, et la
 * mention « cité » est celle du backend : le client ne décide pas qu'un extrait
 * a soutenu la réponse, il ne fait que la restituer.
 */
export default function DocumentReference({ compteRendu }) {
  const extraits = documents(compteRendu);
  if (!extraits.length) return null;

  return (
    <details className="doc-ref">
      <summary className="doc-ref__summary">
        <ChevronDown size={14} className="doc-ref__chevron" aria-hidden="true" />
        <FileText size={13} aria-hidden="true" />
        {extraits.length} extrait{extraits.length > 1 ? "s" : ""} consult
        {extraits.length > 1 ? "és" : "é"}
      </summary>

      <ol className="doc-ref__liste">
        {extraits.map((extrait) => (
          <li
            key={extrait.etiquette}
            className={`doc-ref__item${extrait.cite ? " doc-ref__item--cite" : ""}`}
          >
            <div className="doc-ref__entete">
              <span className="doc-ref__etiquette" title="Repère de citation">
                {extrait.etiquette}
              </span>
              <span className="doc-ref__document">{extrait.document}</span>
              {extrait.cite ? (
                <span className="doc-ref__cite">
                  <Link2 size={11} aria-hidden="true" />
                  cité dans la réponse
                </span>
              ) : (
                <span className="doc-ref__non-cite">non cité</span>
              )}
            </div>
            <blockquote className="doc-ref__extrait">
              <Quote size={11} aria-hidden="true" />
              <span>{extrait.extrait}</span>
            </blockquote>
          </li>
        ))}
      </ol>
    </details>
  );
}