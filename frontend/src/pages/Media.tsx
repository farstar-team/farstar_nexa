import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import type { Account } from "../api";
import type { Media as MediaItem, Product } from "../commerce";
import {
  Empty,
  ErrorNotice,
  Field,
  Form,
  Loading,
  PageTitle,
} from "../components";
import { t } from "../i18n";

export default function Media() {
  const cache = useQueryClient();
  const [chosen, setChosen] = useState("");
  const [cursor, setCursor] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<string[]>([]);
  const [error, setError] = useState<unknown>();
  const [busy, setBusy] = useState(false);
  const accounts = useQuery({
    queryKey: ["accounts"],
    queryFn: () => api<Account[]>("/accounts"),
  });
  const accountId = chosen || accounts.data?.find((a) => a.active)?.id || "";
  const current = accounts.data?.find((a) => a.id === accountId);
  const products = useQuery({
    queryKey: ["products"],
    queryFn: () => api<Product[]>("/products"),
  });
  const media = useQuery({
    queryKey: ["media", accountId, offset],
    queryFn: () =>
      api<MediaItem[]>(
        `/media?account_id=${encodeURIComponent(accountId)}&offset=${offset}`,
      ),
    enabled: !!accountId,
  });
  async function sync(next = false) {
    setBusy(true);
    setError(undefined);
    try {
      const r = await api<{ cursor: string | null }>("/media/sync", "POST", {
        account_id: accountId,
        cursor: next ? cursor : null,
      });
      setCursor(r.cursor);
      await cache.invalidateQueries({ queryKey: ["media", accountId] });
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <PageTitle
        title="media"
        subtitle="پست و ریل را به محصول متصل کنید؛ چند مدیا می‌توانند یک محصول داشته باشند."
      >
        <button
          className="secondary"
          onClick={async () => {
            try {
              await api("/accounts/mock", "POST", {
                name: "حساب نمونه — فقط تست",
                dry_run_only: true,
              });
              await cache.invalidateQueries({ queryKey: ["accounts"] });
            } catch (e) {
              setError(e);
            }
          }}
        >
          ساخت حساب نمونه برای تست
        </button>
      </PageTitle>
      <ErrorNotice
        error={error ?? media.error ?? accounts.error ?? products.error}
      />
      <div className="card commerce-card">
        <Field label="حساب Instagram">
          <select
            value={accountId}
            onChange={(e) => {
              setChosen(e.target.value);
              setCursor(null);
              setOffset(0);
              setSelected([]);
            }}
          >
            <option value="">انتخاب حساب</option>
            {accounts.data
              ?.filter((a) => a.active)
              .map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                  {a.provider === "instagram_mock" ? " (نمونه؛ غیرواقعی)" : ""}
                </option>
              ))}
          </select>
        </Field>
        <div className="heading-actions">
          <button disabled={!accountId || busy} onClick={() => sync()}>
            دریافت مدیا
          </button>
          {cursor && (
            <button disabled={busy} onClick={() => sync(true)}>
              دریافت صفحهٔ بعد از Instagram
            </button>
          )}
        </div>
        {current?.provider === "instagram_mock" && (
          <p className="notice">
            این حساب و مدیاها نمونه هستند؛ اتصال واقعی Instagram یا ارسال واقعی
            پیام ندارند.
          </p>
        )}
      </div>
      {accountId && media.isPending ? (
        <Loading />
      ) : !media.data?.length ? (
        <Empty
          title="مدیایی دریافت نشده"
          subtitle="حساب را انتخاب کنید و دریافت مدیا را بزنید."
        />
      ) : (
        <>
          <Form
            label="اتصال مدیاهای انتخاب‌شده"
            submit={async (data) => {
              await api("/media/product", "PUT", {
                media_ids: selected,
                product_id: data.get("product_id") || null,
              });
              setSelected([]);
              await media.refetch();
            }}
          >
            <Field label="محصول برای اتصال">
              <select name="product_id">
                <option value="">قطع ارتباط محصول</option>
                {products.data?.map((p) => (
                  <option value={p.id} key={p.id}>
                    {p.name} — {t(p.status)}
                  </option>
                ))}
              </select>
            </Field>
            <p>{selected.length} مدیا انتخاب شده</p>
            <div className="commerce-grid">
              {media.data?.map((m) => (
                <article key={m.id} className="card media-card">
                  {m.thumbnail_url ? (
                    <img
                      src={m.thumbnail_url}
                      alt="پیش‌نمایش مدیا"
                      loading="lazy"
                      referrerPolicy="no-referrer"
                    />
                  ) : (
                    <div className="media-placeholder">{m.media_type}</div>
                  )}
                  <label className="media-choice">
                    <input
                      type="checkbox"
                      aria-label={m.caption || m.external_id}
                      checked={selected.includes(m.id)}
                      onChange={(e) =>
                        setSelected(
                          e.target.checked
                            ? [...selected, m.id]
                            : selected.filter((id) => id !== m.id),
                        )
                      }
                    />
                    <span>{m.caption || "بدون توضیحات"}</span>
                  </label>
                  <small>
                    {m.media_type} ·{" "}
                    {products.data?.find((p) => p.id === m.product_id)?.name ||
                      "بدون محصول"}
                  </small>
                  {m.permalink && (
                    <a href={m.permalink} target="_blank" rel="noreferrer">
                      نمایش در Instagram
                    </a>
                  )}
                </article>
              ))}
            </div>
          </Form>
          <div className="pagination">
            <button
              disabled={!offset}
              onClick={() => setOffset(Math.max(0, offset - 100))}
            >
              قبلی
            </button>
            <button
              disabled={(media.data?.length ?? 0) < 100}
              onClick={() => setOffset(offset + 100)}
            >
              بعدی
            </button>
          </div>
        </>
      )}
    </>
  );
}
