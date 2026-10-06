const VARIANTES = {
  default: "",
  success: "stat-card--success",
  warning: "stat-card--warning",
  danger: "stat-card--danger",
  info: "stat-card--info",
};

export default function StatCard({
  icon: Icon,
  label,
  value,
  sub,
  variant = "default",
}) {
  return (
    <div className={`stat-card ${VARIANTES[variant] || ""}`}>
      <div className="stat-card__top">
        {Icon && (
          <span className="stat-card__icon">
            <Icon size={16} strokeWidth={2} />
          </span>
        )}
        <span className="stat-card__label">{label}</span>
      </div>
      <div className="stat-card__value">{value}</div>
      {sub && <div className="stat-card__sub">{sub}</div>}
    </div>
  );
}