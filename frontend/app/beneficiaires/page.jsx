"use client";

import {
  ArrowDownRight,
  ArrowUpRight,
  CalendarRange,
  Database,
  Minus,
  RefreshCcw,
  Search,
  Users,
  UsersRound,
} from "lucide-react";

import StatCard from "@/components/dashboard/StatCard";
import PageContainer from "@/components/layout/PageContainer";
import Badge from "@/components/ui/Badge";
import EmptyState from "@/components/ui/EmptyState";
import Loading from "@/components/ui/Loading";
import Select from "@/components/ui/Select";
import useBeneficiaires from "@/hooks/useBeneficiaires";
import { getApiErrorText } from "@/lib/errors";
import { formatDate, formatNumber } from "@/lib/formatters";

const SITUATION_LABELS = {
  actif: "Actif",
  pensionne: "Pensionné",
  indeterminee: "Indéterminée",
};

const SITUATION_VARIANTS = {
  actif: "success",
  pensionne: "info",
  indeterminee: "warning",
};

function libelleSituation(situation) {
  return SITUATION_LABELS[situation] || situation || "—";
}

function Ecart({ valeur }) {
  const numerique = Number(valeur);
  if (numerique === 0) {
    return (
      <span className="ecart ecart--nul">
        <Minus size={13} />
        stable
      </span>
    );
  }
  if (numerique > 0) {
    return (
      <span className="ecart ecart--hausse">
        <ArrowUpRight size={13} />
        +{formatNumber(numerique)}
      </span>
    );
  }
  return (
    <span className="ecart ecart--baisse">
      <ArrowDownRight size={13} />
      {formatNumber(numerique)}
    </span>
  );
}

function BarreRepartition({ titre, items, cleLibelle = "situation", libelles }) {
  if (!items || items.length === 0) return null;
  const total = items.reduce((somme, item) => somme + item.total, 0);

  function libelle(item) {
    if (item.libelle) return item.libelle;
    const cle = item[cleLibelle];
    return libelles?.[cle] || cle || "—";
  }

  return (
    <div className="card card__padding chart-card">
      <h3 className="chart-card__title">{titre}</h3>
      <ul className="repartition-list">
        {items.map((item) => {
          const nom = libelle(item);
          const part = total > 0 ? (item.total / total) * 100 : 0;
          return (
            <li key={nom} className="repartition-item">
              <div className="repartition-item__row">
                <span className="repartition-item__label">{nom}</span>
                <span className="repartition-item__value">
                  {formatNumber(item.total)}
                  <small>{part.toFixed(0)} %</small>
                </span>
              </div>
              <div className="repartition-item__track">
                <span
                  className="repartition-item__fill"
                  style={{ width: `${part}%` }}
                />
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

const METRIQUES_COMPARAISON = [
  { cle: "total", label: "Population totale" },
  { cle: "actifs", label: "Actifs" },
  { cle: "pensionnes", label: "Pensionnés" },
  { cle: "beneficiaires_rfm", label: "Bénéficiaires RFM" },
];

export default function BeneficiairesPage() {
  const {
    exercices,
    exercice,
    setExercice,
    statistiques,
    liste,
    filtres,
    modifieFiltres,
    reinitialiserFiltres,
    saut,
    setSaut,
    limite,
    loading,
    error,
    recharger,
  } = useBeneficiaires();

  const sourceImportation = statistiques?.source === "importation";
  const comparaison = statistiques?.comparaison;

  const debut = liste?.total ? saut + 1 : 0;
  const fin = liste ? Math.min(saut + limite, liste.total) : 0;

  const filtresActifs =
    filtres.recherche.trim() !== "" ||
    filtres.situation !== "" ||
    filtres.rfm !== "" ||
    filtres.tri !== "nom" ||
    filtres.ordre !== "asc";

  return (
    <PageContainer
      title="Bénéficiaires"
      subtitle="Population bénéficiaire : actifs, pensionnés et bénéficiaires RFM"
      actions={
        exercices.length > 1 && (
          <Select
            label="Exercice"
            value={exercice ?? ""}
            onChange={(evenement) => setExercice(Number(evenement.target.value))}
            options={exercices.map((annee) => ({
              value: annee,
              label: `Exercice ${annee}`,
            }))}
            disabled={loading}
          />
        )
      }
    >
      {!statistiques && loading && <Loading label="Calcul de la population…" />}

      {error && !statistiques && (
        <div className="card card__padding">
          <EmptyState
            icon={Users}
            title="Impossible de charger la population"
            description={getApiErrorText(error)}
            action={
              <button
                type="button"
                className="btn btn--primary btn--md"
                onClick={recharger}
              >
                <RefreshCcw size={15} />
                Réessayer
              </button>
            }
          />
        </div>
      )}

      {statistiques && sourceImportation && (
        <div className="notice notice--info">
          <Database size={16} />
          Données issues des importations normalisées (source&nbsp;:
          importations) car les collections métier sont vides. Les indicateurs
          RFM ne sont pas calculables dans ce mode.
        </div>
      )}

      {statistiques && (
        <>
          <section className="conv-section">
            <div className="conv-section__header">
              <span className="conv-section__icon">
                <UsersRound size={18} />
              </span>
              <div>
                <h2 className="conv-section__title">Vue d'ensemble</h2>
                <p className="conv-section__subtitle">
                  Population recensée à fin d'exercice
                </p>
              </div>
            </div>
            <div className="dash-grid">
              <StatCard
                icon={Users}
                label="Bénéficiaires"
                value={formatNumber(statistiques.total)}
                sub={`taux d'actifs : ${formatNumber(
                  Math.round((statistiques.taux_dactifs || 0) * 100)
                )} %`}
              />
              <StatCard
                icon={UsersRound}
                label="Actifs"
                value={formatNumber(statistiques.actifs)}
                variant="success"
                sub="fonctionnaires et contractuels"
              />
              <StatCard
                icon={UsersRound}
                label="Pensionnés"
                value={formatNumber(statistiques.pensionnes)}
                variant="info"
                sub="retraités"
              />
              <StatCard
                icon={UsersRound}
                label="Bénéficiaires RFM"
                value={formatNumber(statistiques.beneficiaires_rfm)}
                variant={sourceImportation ? "default" : "warning"}
                sub={
                  sourceImportation
                    ? "non calculable (source importation)"
                    : "avec au moins une demande"
                }
              />
              <StatCard
                icon={CalendarRange}
                label="Âge moyen"
                value={
                  statistiques.moyenne_age != null
                    ? formatNumber(statistiques.moyenne_age)
                    : "—"
                }
                sub={
                  statistiques.age_minimal != null
                    ? `${statistiques.age_minimal} à ${statistiques.age_maximal} ans`
                    : "date de naissance absente"
                }
              />
            </div>
          </section>

          {comparaison && (
            <section className="conv-section">
              <div className="conv-section__header">
                <span className="conv-section__icon">
                  <ArrowUpRight size={18} />
                </span>
                <div>
                  <h2 className="conv-section__title">
                    Comparaison avec l'exercice {comparaison.exercice_precedent}
                  </h2>
                  <p className="conv-section__subtitle">
                    Évolution de la population entre les deux exercices
                  </p>
                </div>
              </div>
              <div className="comparaison-grid">
                {METRIQUES_COMPARAISON.map(({ cle, label }) => (
                  <div key={cle} className="comparaison-card">
                    <span className="comparaison-card__label">{label}</span>
                    <span className="comparaison-card__valeur">
                      {formatNumber(comparaison[cle])}
                    </span>
                    <Ecart valeur={comparaison[`ecart_${cle}`]} />
                  </div>
                ))}
              </div>
            </section>
          )}

          <section className="conv-section">
            <div className="conv-section__header">
              <span className="conv-section__icon">
                <Search size={18} />
              </span>
              <div>
                <h2 className="conv-section__title">Répartitions</h2>
                <p className="conv-section__subtitle">
                  Situation, tranches d'âge et catégories
                </p>
              </div>
            </div>
            <div className="dashboard-charts">
              <BarreRepartition
                titre="Par situation"
                items={statistiques.repartition_par_situation}
                cleLibelle="situation"
                libelles={SITUATION_LABELS}
              />
              <BarreRepartition
                titre="Par tranche d'âge"
                items={statistiques.tranches_age}
                cleLibelle="tranche"
              />
              <BarreRepartition
                titre="Par catégorie"
                items={statistiques.repartition_par_categorie}
                cleLibelle="categorie"
              />
            </div>
          </section>

          <section className="conv-section conv-section--filtres">
            <div className="conv-section__header">
              <span className="conv-section__icon">
                <Search size={18} />
              </span>
              <div>
                <h2 className="conv-section__title">Population détaillée</h2>
                <p className="conv-section__subtitle">
                  Filtres, tri et pagination du tableau
                </p>
              </div>
            </div>

            <div className="filtres-bar">
              <div className="filtres-bar__champ filtres-bar__champ--recherche">
                <label className="field__label" htmlFor="recherche-beneficiaire">
                  Recherche
                </label>
                <input
                  id="recherche-beneficiaire"
                  type="search"
                  className="input"
                  placeholder="Matricule, nom ou prénom…"
                  value={filtres.recherche}
                  onChange={(evenement) =>
                    modifieFiltres({ recherche: evenement.target.value })
                  }
                />
              </div>
              <div className="filtres-bar__champ">
                <Select
                  label="Situation"
                  value={filtres.situation}
                  onChange={(evenement) =>
                    modifieFiltres({ situation: evenement.target.value })
                  }
                  options={[
                    { value: "", label: "Toutes" },
                    { value: "actif", label: "Actifs" },
                    { value: "pensionne", label: "Pensionnés" },
                    { value: "indeterminee", label: "Indéterminée" },
                  ]}
                />
              </div>
              {!sourceImportation && (
                <div className="filtres-bar__champ">
                  <Select
                    label="Bénéficiaire RFM"
                    value={filtres.rfm}
                    onChange={(evenement) =>
                      modifieFiltres({ rfm: evenement.target.value })
                    }
                    options={[
                      { value: "", label: "Tous" },
                      { value: "oui", label: "Avec demande" },
                      { value: "non", label: "Sans demande" },
                    ]}
                  />
                </div>
              )}
              <div className="filtres-bar__champ">
                <Select
                  label="Trier par"
                  value={filtres.tri}
                  onChange={(evenement) =>
                    modifieFiltres({ tri: evenement.target.value })
                  }
                  options={[
                    { value: "nom", label: "Nom" },
                    { value: "matricule", label: "Matricule" },
                    { value: "prenom", label: "Prénom" },
                    { value: "age", label: "Âge" },
                    { value: "situation", label: "Situation" },
                  ]}
                />
              </div>
              <div className="filtres-bar__champ">
                <Select
                  label="Ordre"
                  value={filtres.ordre}
                  onChange={(evenement) =>
                    modifieFiltres({ ordre: evenement.target.value })
                  }
                  options={[
                    { value: "asc", label: "Croissant" },
                    { value: "desc", label: "Décroissant" },
                  ]}
                />
              </div>
              {filtresActifs && (
                <button
                  type="button"
                  className="btn btn--ghost btn--md filtres-bar__reinitialiser"
                  onClick={reinitialiserFiltres}
                >
                  <RefreshCcw size={14} />
                  Réinitialiser
                </button>
              )}
            </div>

            <div className="card card__padding">
              {loading && !liste && <Loading label="Chargement du tableau…" />}

              {liste && liste.total === 0 && (
                <EmptyState
                  icon={Users}
                  title="Aucun bénéficiaire"
                  description="Aucune ligne ne correspond aux filtres sélectionnés pour cet exercice."
                />
              )}

              {liste && liste.total > 0 && (
                <div className="tableau">
                  <table className="tableau__table">
                    <thead>
                      <tr>
                        <th>Matricule</th>
                        <th>Bénéficiaire</th>
                        <th>Situation</th>
                        <th>Catégorie</th>
                        <th>Date de naissance</th>
                        <th>Âge</th>
                        <th>Direction</th>
                        {!sourceImportation && <th>RFM</th>}
                        {sourceImportation && <th>Exercice</th>}
                      </tr>
                    </thead>
                    <tbody>
                      {liste.items.map((beneficiaire) => (
                        <tr key={beneficiaire.id || beneficiaire.matricule}>
                          <td className="tableau__code">
                            {beneficiaire.matricule || "—"}
                          </td>
                          <td>
                            <span className="tableau__nom">
                              {beneficiaire.nom || "—"}
                            </span>
                            <span className="tableau__sous-texte">
                              {beneficiaire.prenom || ""}
                            </span>
                          </td>
                          <td>
                            <Badge
                              variant={SITUATION_VARIANTS[beneficiaire.situation] || "neutral"}
                            >
                              {libelleSituation(beneficiaire.situation)}
                            </Badge>
                          </td>
                          <td>{beneficiaire.categorie || "—"}</td>
                          <td>{formatDate(beneficiaire.date_naissance)}</td>
                          <td>
                            {beneficiaire.age != null
                              ? `${beneficiaire.age} ans`
                              : "—"}
                          </td>
                          <td className="tableau__direction">
                            {beneficiaire.direction || "—"}
                          </td>
                          {!sourceImportation && (
                            <td>
                              {beneficiaire.rfm === "oui" ? (
                                <Badge variant="success" dot>
                                  RFM
                                </Badge>
                              ) : (
                                <Badge variant="neutral">—</Badge>
                              )}
                            </td>
                          )}
                          {sourceImportation && (
                            <td>{beneficiaire.exercice ?? "—"}</td>
                          )}
                        </tr>
                      ))}
                    </tbody>
                  </table>

                  <div className="tableau__pied">
                    <span className="tableau__resume">
                      {formatNumber(debut)}–{formatNumber(fin)} sur{" "}
                      {formatNumber(liste.total)}
                    </span>
                    <div className="tableau__nav">
                      <button
                        type="button"
                        className="btn btn--ghost btn--sm"
                        disabled={saut === 0 || loading}
                        onClick={() =>
                          setSaut(Math.max(0, saut - limite))
                        }
                      >
                        Précédent
                      </button>
                      <button
                        type="button"
                        className="btn btn--ghost btn--sm"
                        disabled={fin >= liste.total || loading}
                        onClick={() => setSaut(saut + limite)}
                      >
                        Suivant
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </section>
        </>
      )}
    </PageContainer>
  );
}