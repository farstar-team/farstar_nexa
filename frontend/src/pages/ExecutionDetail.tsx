import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import type { ExecutionDetail as Detail } from "../commerce";
import { Badge, ErrorNotice, Loading } from "../components";
import { PricePreview } from "./Products";
import { t } from "../i18n";
export default function ExecutionDetail({ id }: { id: string }) {
  const query = useQuery({
    queryKey: ["execution", id],
    queryFn: () => api<Detail>("/executions/" + id),
    refetchInterval: 5000,
  });
  if (query.isPending) return <Loading />;
  return (
    <>
      <ErrorNotice error={query.error} />
      {query.data && (
        <section className="execution-detail">
          <Badge value={query.data.status} />
          <h2>{query.data.automation_name}</h2>
          <p>
            {query.data.product_name ?? "بدون محصول"} ·{" "}
            {query.data.media_caption ?? "بدون مدیا"}
          </p>
          <p>
            {t(query.data.trigger)} ·{" "}
            {query.data.dry_run
              ? "Dry Run — هیچ پیامی ارسال نشده"
              : "اجرای واقعی"}
          </p>
          {query.data.detail && (
            <p className="notice">{t(query.data.detail)}</p>
          )}
          <p>
            شناسه رویداد: <code>{query.data.event_id}</code>
          </p>
          {query.data.actions.map((a) => (
            <article className="card commerce-card" key={a.id}>
              <h3>
                {a.position + 1}. {t(a.kind)}
              </h3>
              <Badge value={a.status} />
              <small>تلاش ارسال: {a.attempts}</small>
              {a.result.error && (
                <p className="notice error">{t(a.result.error)}</p>
              )}
              {a.result.retry_at && (
                <p>
                  تلاش بعدی:{" "}
                  {new Date(a.result.retry_at).toLocaleString("fa-IR")}
                </p>
              )}
              {a.result.rendered_text && (
                <blockquote className="message-preview">
                  {a.result.rendered_text}
                </blockquote>
              )}
              {a.result.pricing && <PricePreview price={a.result.pricing} />}{" "}
              {a.result.value && <p>{a.result.value}</p>}
              {a.result.seconds !== undefined && (
                <p>{a.result.seconds} ثانیه تأخیر</p>
              )}
            </article>
          ))}
        </section>
      )}
    </>
  );
}
