import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import {
  Empty,
  ErrorNotice,
  Field,
  Form,
  Loading,
  Modal,
  PageTitle,
} from "../components";
import { date } from "../i18n";
type Lead = {
  id: string;
  display_name: string;
  external_id: string;
  source: string;
  tags: string[];
  notes: { text: string; at: string }[];
  first_interaction: string;
  last_interaction: string;
};
export default function Leads() {
  const [offset, setOffset] = useState(0);
  const [edit, setEdit] = useState<Lead>();
  const q = useQuery({
    queryKey: ["leads", offset],
    queryFn: () => api<Lead[]>("/leads?offset=" + offset),
  });
  return (
    <>
      <PageTitle
        title="leads"
        subtitle="مخاطبان ثبت‌شده از اجرای واقعی اتوماسیون‌های شما"
      />
      <ErrorNotice error={q.error} />
      {q.isPending ? (
        <Loading />
      ) : !q.data?.length ? (
        <Empty />
      ) : (
        <div className="commerce-grid">
          {q.data.map((l) => (
            <article className="card commerce-card" key={l.id}>
              <h2>{l.display_name || l.external_id}</h2>
              <code>{l.external_id}</code>
              <p>{l.tags.join("، ") || "بدون برچسب"}</p>
              <small>آخرین تعامل: {date(l.last_interaction)}</small>
              <button className="secondary" onClick={() => setEdit(l)}>
                برچسب‌ها و یادداشت‌ها
              </button>
            </article>
          ))}
        </div>
      )}
      <div className="pagination">
        <button
          disabled={!offset}
          onClick={() => setOffset(Math.max(0, offset - 100))}
        >
          قبلی
        </button>
        <button
          disabled={(q.data?.length ?? 0) < 100}
          onClick={() => setOffset(offset + 100)}
        >
          بعدی
        </button>
      </div>
      {edit && (
        <Modal title="اطلاعات مخاطب" close={() => setEdit(undefined)}>
          <p>اولین تعامل: {date(edit.first_interaction)}</p>
          <Form
            label="save"
            submit={async (d) => {
              await api("/leads/" + edit.id, "PATCH", {
                tags: String(d.get("tags"))
                  .split(/[,،]/)
                  .map((t) => t.trim())
                  .filter(Boolean),
                note: d.get("note"),
              });
              setEdit(undefined);
              await q.refetch();
            }}
          >
            <Field label="برچسب‌ها (جداشده با ویرگول)">
              <input name="tags" defaultValue={edit.tags.join("، ")} />
            </Field>
            <Field label="یادداشت جدید">
              <textarea name="note" maxLength={500} />
            </Field>
          </Form>
          {edit.notes.map((n, i) => (
            <blockquote key={i}>
              {n.text}
              <small>{date(n.at)}</small>
            </blockquote>
          ))}
        </Modal>
      )}
    </>
  );
}
