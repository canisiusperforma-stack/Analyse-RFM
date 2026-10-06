"use client";

import {
  ArrowDownRight,
  ArrowUpRight,
  BadgeCheck,
  Clock,
  Minus,
  Receipt,
  RefreshCcw,
  Search,
  Wallet,
  XCircle,
} from "lucide-react";
import {
  Bar,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
  Line,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import StatCard from "@/components/dashboard/StatCard";
import PageContainer from "@/components/layout/PageContainer";
import Badge from "@/components/ui/Badge";
import EmptyState from "@/components/ui/EmptyState";
import Loading from "@/components/ui/Loading";
import Select from "@/components/ui/Select";
import useRemboursements from "@/hooks/useRemboursements";
import { getApiErrorText } from "@/lib/errors";
import {
  compactCurrency,
  formatCurrency,
  formatDate,
  formatNumber,
  formatPercent,
  formatSignedCurrency,
} from "@/lib/formatters";

const STATUT_LABELS = {
  soumis: "Soumis",
  en_attente: "En attente",
  a_completer: "À compléter",
  valide: "Validé",
  paye: "Payé",
  refuse: "Refusé",
  annule: "Annulé",
};

const STATUT_VARIANTS = {
  soumis: "neutral",
  en_attente: "warning",
  a_completer: "warning",
  valide: "info",
  paye: "success",
  refuse: "danger",
  annule: "neutral",
};

const CIRCUIT_LABELS = {
  circuit_normal: "Circuit normal",
  circuit_accelere: "Circuit accéléré",
};

const COULEURS = ["#2563eb", "#0891b2", "#d97706", "#059669", "#7c3aed", "#dc2626", "#6b7280"];

function Ecart({ valeur, decimale = false }) {
  const numerique = Number(valeur);
  if (numerique === 0) {
    return (
      <span className="ecart ecart--nul">
        <Minus size={13} />
        stable
      </span>
    );
  }
  const texte = decimale
    ? formatNumber(numerique)
    : formatSignedCurrency(numerique);
  if (numerique > 0) {
    return (
      <span className="ecart ecart--hausse">
        <ArrowUpRight size={13} />
        {texte}
      </span>
    );
  }
  return (
    <span className="ecart ecart--baisse">
      <ArrowDownRight size={13} />
      {texte}
    </span>
  );
}

function EtiqueterRepartition(items, libelles) {
  return items.map((item) => ({
    ...item,
    name: libelles?.[item.statut] || item.statut || "—",
  }));
}

function SerieChart({ donnees }) {
  if (!donnees || donnees.length === 0) return null;
  return (
    <div className="card card__padding chart-card">
      <h3 className="chart-card__title">Demandes et paiements mensuels</h3>
      <p className="chart-card__subtitle">
        Volumes de demandes et montants effectivement payés
      </p>
      <div className="chart-card__body">
        <ResponsiveContainer width="100%" height={240}>
          <ComposedChart
            data={donnees}
            margin={{ top: 8, right: 8, left: 0, bottom: 0 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
            <XAxis
              dataKey="mois"
              tick={{ fontSize: 11 }}
              interval="preserveStartEnd"
            />
            <YAxis
              yAxisId="volume"
              tick={{ fontSize: 11 }}
              width={36}
              allowDecimals={false}
            />
            <YAxis
              yAxisId="montant"
              orientation="right"
              tickFormatter={compactCurrency}
              tick={{ fontSize: 11 }}
              width={58}
            />
            <Tooltip
              formatter={(valeur, nom) =>
                nom === "Montant payé"
                  ? [formatCurrency(valeur), nom]
                  : [formatNumber(valeur), nom]
              }
            />
            <Legend />
            <Bar
              yAxisId="volume"
              dataKey="demandes"
              name="Demandes"
              fill="#2563eb"
              radius={[4, 4, 0, 0]}
            />
            <Line
              yAxisId="montant"
              dataKey="montant_paye"
              name="Montant payé"
              stroke="#d97706"
              strokeWidth={2}
              dot={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function RepartitionStatut({ items }) {
  if (!items || items.length === 0) return null;
  const donnees = EtiqueterRepartition(items, STATUT_LABELS);
  return (
    <div className="card card__padding chart-card">
      <h3 className="chart-card__title">Demandes par statut</h3>
      <div className="chart-card__pie">
        <ResponsiveContainer width="100%" height={220}>
          <PieChart>
            <Pie
              data={donnees}
              dataKey="total"
              nameKey="name"
              innerRadius={48}
              outerRadius={78}
              paddingAngle={2}
            >
              {donnees.map((item, index) => (
                <Cell key={item.name} fill={COULEURS[index % COULEURS.length]} />
              ))}
            </Pie>
            <Tooltip formatter={(valeur) => [formatNumber(valeur), "Dossiers"]} />
            <Legend verticalAlign="bottom" height={36} />
          </PieChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function RepartitionTypes({ items }) {
  if (!items || items.length === 0) return null;
  return (
    <div className="card card__padding chart-card">
      <h3 className="chart-card__title">Montants par type de dépense</h3>
      <div className="chart-card__body">
        <ResponsiveContainer width="100%" height={240}>
          <ComposedChart
            data={items}
            margin={{ top: 8, right: 8, left: 0, bottom: 0 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
            <XAxis dataKey="type_prestation" tick={{ fontSize: 11 }} />
            <YAxis
              tickFormatter={compactCurrency}
              tick={{ fontSize: 11 }}
              width={58}
            />
            <Tooltip
              formatter={(valeur, nom) => [formatCurrency(valeur), nom]}
            />
            <Legend />
            <Bar
              dataKey="montant_demande"
              name="Demandé"
              fill="#2563eb"
              radius={[4, 4, 0, 0]}
            />
            <Bar
              dataKey="montant_paye"
              name="Payé"
              fill="#059669"
              radius={[4, 4, 0, 0]}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function RepartitionCircuit({ items }) {
  if (!items || items.length === 0) return null;
  const total = items.reduce((somme, item) => somme + item.total, 0);
  return (
    <div className="card card__padding chart-card">
      <h3 className="chart-card__title">Circuit de traitement</h3>
      <ul className="repartition-list">
        {items.map((item) => {
          const nom = CIRCUIT_LABELS[item.circuit] || item.circuit;
          const part = total > 0 ? (item.total / total) * 100 : 0;
          return (
            <li key={item.circuit} className="repartition-item">
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
  { cle: "demandes", label: "Demandes", decimale: true },
  { cle: "payes", label: "Payés", decimale: true },
  { cle: "montant_demande", label: "Montant demandé" },
  { cle: "montant_paye", label: "Montant payé" },
];

export default function RemboursementsPage() {
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
  } = useRemboursements();

  const montants = statistiques?.montants;
  const comparaison = statistiques?.comparaison;
  const types = statistiques?.repartition_par_type || [];
  const circuits = statistiques?.repartition_par_circuit || [];

  const debut = liste?.total ? saut + 1 : 0;
  const fin = liste ? Math.min(saut + limite, liste.total) : 0;

  const typesOptions = types.map((item) => ({
    value: item.type_prestation,
    label: item.type_prestation,
  }));
  const circuitsOptions = circuits.map((item) => ({
    value: item.circuit,
    label: CIRCUIT_LABELS[item.circuit] || item.circuit,
  }));

  const filtresActifs =
    filtres.recherche.trim() !== "" ||
    filtres.statut !== "" ||
    filtres.type_prestation !== "" ||
    filtres.circuit !== "" ||
    filtres.montant_min !== "" ||
    filtres.montant_max !== "" ||
    filtres.tri !== "date_demande" ||
    filtres.ordre !== "desc";

  return (
    <PageContainer
      title="Remboursements"
      subtitle="Suivi et analyse des demandes de remboursement des frais médicaux"
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
      {!statistiques && loading && <Loading label="Calcul des remboursements…" />}

      {error && !statistiques && (
        <div className="card card__padding">
          <EmptyState
            icon={Receipt}
            title="Impossible de charger les remboursements"
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

      {statistiques && (
        <>
          <section>
            <div className="dash-grid">
              <StatCard
                icon={Receipt}
                label="Demandes"
                value={formatNumber(statistiques.demandes)}
                sub="dossiers déposés"
              />
              <StatCard
                icon={BadgeCheck}
                label="Acceptées"
                value={formatNumber(statistiques.acceptees)}
                sub={`taux d'acceptation : ${formatPercent(statistiques.taux_acceptation)}`}
                variant="success"
              />
              <StatCard
                icon={XCircle}
                label="Refusées"
                value={formatNumber(statistiques.rejetees)}
                sub="dossiers rejetés"
                variant="danger"
              />
              <StatCard
                icon={Clock}
                label="En attente"
                value={formatNumber(statistiques.en_attente)}
                sub="en cours de traitement"
                variant="warning"
              />
              <StatCard
                icon={BadgeCheck}
                label="Payées"
                value={formatNumber(statistiques.payes)}
                sub="dossiers réglés"
                variant="info"
              />
              <StatCard
                icon={Wallet}
                label="Montant demandé"
                value={formatCurrency(montants.demande.total)}
                sub={`moyenne : ${formatCurrency(montants.demande.moyenne)}`}
              />
              <StatCard
                icon={Wallet}
                label="Montant payé"
                value={formatCurrency(montants.paye.total)}
                sub={`moyenne : ${formatCurrency(montants.paye.moyenne)}`}
                variant="success"
              />
              <StatCard
                icon={Wallet}
                label="Médiane demandé"
                value={
                  montants.demande.mediane != null
                    ? formatCurrency(montants.demande.mediane)
                    : "—"
                }
                sub={`médiane payé : ${montants.paye.mediane != null ? formatCurrency(montants.paye.mediane) : "—"}`}
              />
              <StatCard
                icon={Wallet}
                label="Minimum demandé"
                value={
                  montants.demande.montants
                    ? formatCurrency(montants.demande.minimum)
                    : "—"
                }
                sub={`min payé : ${montants.paye.montants ? formatCurrency(montants.paye.minimum) : "—"}`}
              />
              <StatCard
                icon={Wallet}
                label="Maximum demandé"
                value={
                  montants.demande.montants
                    ? formatCurrency(montants.demande.maximum)
                    : "—"
                }
                sub={`max payé : ${montants.paye.montants ? formatCurrency(montants.paye.maximum) : "—"}`}
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
                    Évolution des demandes et des montants
                  </p>
                </div>
              </div>
              <div className="comparaison-grid">
                {METRIQUES_COMPARAISON.map(({ cle, label, decimale }) => {
                  const courant =
                    cle === "montant_demande" || cle === "montant_paye"
                      ? montants[cle === "montant_paye" ? "paye" : "demande"].total
                      : statistiques[cle];
                  const precedent = comparaison[`${cle}_precedent`];
                  return (
                    <div key={cle} className="comparaison-card">
                      <span className="comparaison-card__label">{label}</span>
                      <span className="comparaison-card__valeur">
                        {decimale
                          ? formatNumber(courant)
                          : formatCurrency(courant)}
                      </span>
                      <span className="comparaison-card__avant">
                        {decimale
                          ? formatNumber(precedent)
                          : formatCurrency(precedent)}{" "}
                        en {comparaison.exercice_precedent}
                      </span>
                      <Ecart valeur={comparaison[`ecart_${cle}`]} decimale={decimale} />
                      {comparaison[`variation_pct_${cle}`] != null && (
                        <span className="comparaison-card__avant">
                          {formatPercent(comparaison[`variation_pct_${cle}`])} en
                          variation
                        </span>
                      )}
                    </div>
                  );
                })}
              </div>
            </section>
          )}

          <section className="conv-section">
            <div className="conv-section__header">
              <span className="conv-section__icon">
                <Search size={18} />
              </span>
              <div>
                <h2 className="conv-section__title">Analyse des demandes</h2>
                <p className="conv-section__subtitle">
                  Série mensuelle et répartitions
                </p>
              </div>
            </div>
            <div className="dashboard-charts">
              <SerieChart donnees={statistiques.serie_mensuelle} />
              <RepartitionStatut items={statistiques.repartition_par_statut} />
              <RepartitionTypes items={statistiques.repartition_par_type} />
              <RepartitionCircuit items={statistiques.repartition_par_circuit} />
            </div>
          </section>

          <section className="conv-section conv-section--filtres">
            <div className="conv-section__header">
              <span className="conv-section__icon">
                <Search size={18} />
              </span>
              <div>
                <h2 className="conv-section__title">Détail des demandes</h2>
                <p className="conv-section__subtitle">
                  Recherche, filtres, tri et pagination
                </p>
              </div>
            </div>

            <div className="filtres-bar">
              <div className="filtres-bar__champ filtres-bar__champ--recherche">
                <label className="field__label" htmlFor="recherche-remboursement">
                  Recherche
                </label>
                <input
                  id="recherche-remboursement"
                  type="search"
                  className="input"
                  placeholder="N° de dossier, matricule, nom ou prénom…"
                  value={filtres.recherche}
                  onChange={(evenement) =>
                    modifieFiltres({ recherche: evenement.target.value })
                  }
                />
              </div>
              <div className="filtres-bar__champ">
                <Select
                  label="Statut"
                  value={filtres.statut}
                  onChange={(evenement) =>
                    modifieFiltres({ statut: evenement.target.value })
                  }
                  options={[
                    { value: "", label: "Tous" },
                    ...Object.entries(STATUT_LABELS).map(([value, label]) => ({
                      value,
                      label,
                    })),
                  ]}
                />
              </div>
              <div className="filtres-bar__champ">
                <Select
                  label="Type de dépense"
                  value={filtres.type_prestation}
                  onChange={(evenement) =>
                    modifieFiltres({ type_prestation: evenement.target.value })
                  }
                  options={[
                    { value: "", label: "Tous" },
                    ...typesOptions,
                  ]}
                />
              </div>
              <div className="filtres-bar__champ">
                <Select
                  label="Circuit"
                  value={filtres.circuit}
                  onChange={(evenement) =>
                    modifieFiltres({ circuit: evenement.target.value })
                  }
                  options={[
                    { value: "", label: "Tous" },
                    ...circuitsOptions,
                  ]}
                />
              </div>
              <div className="filtres-bar__champ">
                <label className="field__label" htmlFor="montant-min">
                  Montant min (Ar)
                </label>
                <input
                  id="montant-min"
                  type="number"
                  min="0"
                  className="input"
                  placeholder="0"
                  value={filtres.montant_min}
                  onChange={(evenement) =>
                    modifieFiltres({ montant_min: evenement.target.value })
                  }
                />
              </div>
              <div className="filtres-bar__champ">
                <label className="field__label" htmlFor="montant-max">
                  Montant max (Ar)
                </label>
                <input
                  id="montant-max"
                  type="number"
                  min="0"
                  className="input"
                  placeholder="—"
                  value={filtres.montant_max}
                  onChange={(evenement) =>
                    modifieFiltres({ montant_max: evenement.target.value })
                  }
                />
              </div>
              <div className="filtres-bar__champ">
                <Select
                  label="Trier par"
                  value={filtres.tri}
                  onChange={(evenement) =>
                    modifieFiltres({ tri: evenement.target.value })
                  }
                  options={[
                    { value: "date_demande", label: "Date de demande" },
                    { value: "numero_dossier", label: "N° de dossier" },
                    { value: "montant_demande", label: "Montant demandé" },
                    { value: "statut", label: "Statut" },
                    { value: "type_prestation", label: "Type de dépense" },
                    { value: "beneficiaire", label: "Bénéficiaire" },
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
                    { value: "desc", label: "Décroissant" },
                    { value: "asc", label: "Croissant" },
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
                  icon={Receipt}
                  title="Aucune demande"
                  description="Aucun dossier ne correspond aux filtres sélectionnés pour cet exercice."
                />
              )}

              {liste && liste.total > 0 && (
                <div className="tableau">
                  <table className="tableau__table">
                    <thead>
                      <tr>
                        <th>N° de dossier</th>
                        <th>Bénéficiaire</th>
                        <th>Prestation</th>
                        <th>Circuit</th>
                        <th>Date demande</th>
                        <th>Date décision</th>
                        <th>Demandé</th>
                        <th>Accordé</th>
                        <th>Payé</th>
                        <th>Statut</th>
                      </tr>
                    </thead>
                    <tbody>
                      {liste.items.map((item) => (
                        <tr key={item.numero_dossier}>
                          <td className="tableau__code">{item.numero_dossier}</td>
                          <td>
                            <span className="tableau__nom">
                              {item.beneficiaire?.nom || "—"}
                            </span>
                            <span className="tableau__sous-texte">
                              {item.beneficiaire?.matricule ||
                                item.beneficiaire?.prenom ||
                                ""}
                            </span>
                          </td>
                          <td>{item.type_prestation || "—"}</td>
                          <td>
                            <Badge variant="info">
                              {CIRCUIT_LABELS[item.circuit] || item.circuit || "—"}
                            </Badge>
                          </td>
                          <td>{formatDate(item.date_demande)}</td>
                          <td>{formatDate(item.date_decision)}</td>
                          <td className="tableau__montant">
                            {formatCurrency(item.montant_demande)}
                          </td>
                          <td className="tableau__montant">
                            {item.montant_accordee != null
                              ? formatCurrency(item.montant_accordee)
                              : "—"}
                          </td>
                          <td className="tableau__montant tableau__montant--execute">
                            {item.montant_paye != null
                              ? formatCurrency(item.montant_paye)
                              : "—"}
                          </td>
                          <td>
                            <Badge
                              variant={STATUT_VARIANTS[item.statut] || "neutral"}
                              dot
                              title={item.motif_refus || undefined}
                            >
                              {STATUT_LABELS[item.statut] || item.statut || "—"}
                            </Badge>
                          </td>
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
                        onClick={() => setSaut(Math.max(0, saut - limite))}
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