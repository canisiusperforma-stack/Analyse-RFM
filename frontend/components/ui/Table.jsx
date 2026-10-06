import { cn } from "@/lib/utils";
import EmptyState from "@/components/ui/EmptyState";
import Loading from "@/components/ui/Loading";

export default function Table({
  columns = [],
  data = [],
  rowKey = "id",
  loading = false,
  empty = {},
  className,
}) {
  return (
    <div className={cn("table-wrap", className)}>
      <table className="table">
        <thead>
          <tr>
            {columns.map((col) => (
              <th key={col.key} style={col.width ? { width: col.width } : undefined}>
                {col.header || col.key}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {loading ? (
            <tr>
              <td colSpan={columns.length || 1}>
                <Loading label={empty.loadingLabel || "Chargement des données…"} />
              </td>
            </tr>
          ) : data.length === 0 ? (
            <tr>
              <td colSpan={columns.length || 1}>
                <EmptyState
                  icon={empty.icon}
                  title={empty.title || "Aucune donnée"}
                  description={
                    empty.description || "Aucune donnée n'est disponible."
                  }
                  action={empty.action}
                />
              </td>
            </tr>
          ) : (
            data.map((row) => (
              <tr key={row[rowKey]}>
                {columns.map((col) => (
                  <td key={col.key}>
                    {col.render ? col.render(row) : row[col.key]}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}