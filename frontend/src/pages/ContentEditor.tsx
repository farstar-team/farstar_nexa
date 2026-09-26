import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import { ErrorNotice, Field, Form, Loading } from "../components";
import { t } from "../i18n";

export default function ContentEditor() {
  const cache = useQueryClient();
  const query = useQuery({ queryKey: ["admin-content"], queryFn: () => api<{ values: Record<string, string>; defaults: Record<string, string> }>("/admin/content") });
  if (query.isPending) return <Loading />;
  return <section className="card content-editor"><h2>{t("siteContent")}</h2><p>{t("siteContentHint")}</p><ErrorNotice error={query.error} /><Form submit={async (data) => { const values: Record<string, string> = {}; Object.keys(query.data?.defaults ?? {}).forEach((key) => { values[key] = String(data.get(key) ?? ""); }); await api("/admin/content", "PUT", { values }); await cache.invalidateQueries({ queryKey: ["admin-content"] }); }}><div className="form-grid">{Object.entries(query.data?.defaults ?? {}).map(([key, fallback]) => <Field key={key} label={key} hint={fallback}><textarea name={key} rows={key.includes("description") ? 4 : 2} defaultValue={query.data?.values[key] ?? fallback} maxLength={2000} /></Field>)}</div></Form></section>;
}
