import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import {
  Badge,
  Confirm,
  Empty,
  ErrorNotice,
  Field,
  Form,
  Loading,
  Modal,
  PageTitle,
} from "../components";
import { currencies } from "../commerce";
import type { Price, Product } from "../commerce";
import { date, t } from "../i18n";

export function PricePreview({ price }: { price: Price }) {
  return (
    <section className="price-preview" aria-label="پیش‌نمایش قیمت">
      <strong>
        {price.formatted_price} {t(price.currency)}
      </strong>
      <dl>
        {[
          ["قیمت تبدیل‌شده", price.converted_price],
          ["تعدیل", price.adjustment],
          ["تخفیف", price.discount],
          ["نرخ تبدیل", price.rate],
          ["منبع نرخ", t(price.source)],
          ["زمان نرخ", date(price.updated_at)],
        ].map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
      {price.warning && <p className="notice">{t(price.warning)}</p>}
      <small>
        هر تومان برابر ۱۰ ریال است. محاسبهٔ نهایی هنگام ارسال دوباره انجام
        می‌شود.
      </small>
    </section>
  );
}

export function productPayload(data: FormData) {
  const value = (key: string) => String(data.get(key) ?? "");
  const timestamp = (key: string) =>
    value(key) ? new Date(value(key)).toISOString() : null;
  return {
    name: value("name"),
    slug: value("slug"),
    description: value("description"),
    sku: value("sku"),
    status: value("status"),
    availability: value("availability"),
    base_price: value("base_price"),
    base_currency: value("base_currency"),
    output_currency: value("output_currency"),
    pricing_mode: value("pricing_mode"),
    manual_rate: value("manual_rate") || null,
    url: value("url"),
    custom_fields: Object.fromEntries(
      value("custom_fields")
        .split("\n")
        .filter((line) => line.includes(":"))
        .map((line) => {
          const i = line.indexOf(":");
          return [line.slice(0, i).trim(), line.slice(i + 1).trim()];
        }),
    ),
    pricing: {
      percentage: value("percentage") || "0",
      fixed: value("fixed") || "0",
      rounding: value("rounding") || "0",
      minimum: value("minimum") || null,
      maximum: value("maximum") || null,
      discount_type: value("discount_type"),
      discount_value: value("discount_value") || "0",
      discount_start: timestamp("discount_start"),
      discount_end: timestamp("discount_end"),
      fallback: value("fallback"),
    },
  };
}

function productUpdatePayload(product: Product, status = product.status) {
  return {
    name: product.name,
    slug: product.slug,
    description: product.description,
    sku: product.sku,
    status,
    availability: product.availability,
    base_price: product.base_price,
    base_currency: product.base_currency,
    output_currency: product.output_currency,
    pricing_mode: product.pricing_mode,
    manual_rate: product.manual_rate,
    pricing: product.pricing,
    url: product.url,
    custom_fields: product.custom_fields,
  };
}

function localInput(value?: string | null) {
  if (!value) return "";
  const d = new Date(value);
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 16);
}

export function ProductEditor({
  product,
  done,
}: {
  product: Product | null;
  done: () => void;
}) {
  const [price, setPrice] = useState<Price>();
  const [error, setError] = useState<unknown>();
  const [busy, setBusy] = useState(false);
  const choices = (
    name: string,
    label: string,
    values: string[],
    selected?: string,
  ) => (
    <Field label={label}>
      <select name={name} defaultValue={selected ?? values[0]}>
        {values.map((v) => (
          <option key={v} value={v}>
            {t(v)}
          </option>
        ))}
      </select>
    </Field>
  );
  return (
    <Form
      label="save"
      submit={async (data) => {
        await api(
          product ? "/products/" + product.id : "/products",
          product ? "PUT" : "POST",
          productPayload(data),
        );
        done();
      }}
    >
      <div className="form-grid">
        <Field label="نام محصول">
          <input
            name="name"
            defaultValue={product?.name}
            required
            maxLength={120}
          />
        </Field>
        <Field label="شناسه محصول (slug)">
          <input
            name="slug"
            defaultValue={product?.slug}
            required
            pattern="[a-zA-Z0-9_-]+"
            maxLength={80}
            dir="ltr"
          />
        </Field>
      </div>
      <Field label="توضیحات">
        <textarea
          name="description"
          defaultValue={product?.description}
          maxLength={4000}
        />
      </Field>
      <div className="form-grid">
        <Field label="کد کالا (SKU)">
          <input name="sku" defaultValue={product?.sku} maxLength={80} />
        </Field>
        {choices("status", "وضعیت", ["ACTIVE", "INACTIVE"], product?.status)}
        {choices(
          "availability",
          "موجودی",
          ["IN_STOCK", "OUT_OF_STOCK", "LIMITED", "ON_REQUEST"],
          product?.availability,
        )}
        <Field label="قیمت پایه">
          <input
            name="base_price"
            type="number"
            step="0.000001"
            min="0"
            required
            defaultValue={product?.base_price}
          />
        </Field>
        {choices(
          "base_currency",
          "ارز پایه",
          currencies,
          product?.base_currency,
        )}
        {choices(
          "output_currency",
          "ارز نمایش",
          currencies,
          product?.output_currency ?? "TOMAN",
        )}
        {choices(
          "pricing_mode",
          "روش قیمت‌گذاری",
          ["MANUAL", "LIVE", "LIVE_WITH_ADJUSTMENT"],
          product?.pricing_mode,
        )}
        <Field label="نرخ دستی (یک واحد ارز پایه)">
          <input
            name="manual_rate"
            type="number"
            min="0.0000000001"
            step="any"
            defaultValue={product?.manual_rate ?? ""}
          />
        </Field>
      </div>
      <p className="notice">
        نرخ آنلاین، نرخ مرجع روزانه است؛ برای قیمت بازار آزاد ایران نرخ دستی
        خودتان را وارد کنید. نرخ خالی از تنظیمات ارز Workspace خوانده می‌شود.
      </p>
      <details open>
        <summary>تعدیل، گردکردن و حدود قیمت</summary>
        <div className="form-grid">
          {(
            [
              ["percentage", "درصد تعدیل (+ / −)"],
              ["fixed", "مبلغ تعدیل (+ / −)"],
              ["rounding", "گردکردن به مضرب"],
              ["minimum", "حداقل قیمت"],
              ["maximum", "حداکثر قیمت"],
            ] as const
          ).map(([key, label]) => (
            <Field key={key} label={label}>
              <input
                name={key}
                type="number"
                step="any"
                defaultValue={product?.pricing[key] ?? ""}
              />
            </Field>
          ))}
          {choices(
            "fallback",
            "هنگام نبود نرخ آنلاین",
            ["STOP", "MANUAL"],
            product?.pricing.fallback,
          )}
        </div>
        <small>
          STOP یعنی توقف امن ارسال قیمت. تعدیل در حالت LIVE اعمال نمی‌شود.
        </small>
      </details>
      <details>
        <summary>تخفیف زمان‌دار</summary>
        <div className="form-grid">
          {choices(
            "discount_type",
            "نوع تخفیف",
            ["NONE", "PERCENTAGE", "FIXED"],
            product?.pricing.discount_type,
          )}
          <Field label="مقدار تخفیف">
            <input
              name="discount_value"
              type="number"
              min="0"
              step="any"
              defaultValue={product?.pricing.discount_value ?? "0"}
            />
          </Field>
          <Field label="شروع (زمان محلی مرورگر)">
            <input
              name="discount_start"
              type="datetime-local"
              defaultValue={localInput(product?.pricing.discount_start)}
            />
          </Field>
          <Field label="پایان (زمان محلی مرورگر)">
            <input
              name="discount_end"
              type="datetime-local"
              defaultValue={localInput(product?.pricing.discount_end)}
            />
          </Field>
        </div>
      </details>
      <Field label="لینک محصول">
        <input
          name="url"
          type="url"
          defaultValue={product?.url}
          maxLength={2048}
          dir="ltr"
        />
      </Field>
      <Field label="ویژگی‌های سفارشی؛ هر خط نام: مقدار">
        <textarea
          name="custom_fields"
          defaultValue={Object.entries(product?.custom_fields ?? {})
            .map(([k, v]) => `${k}: ${v}`)
            .join("\n")}
        />
      </Field>
      <button
        type="button"
        className="secondary"
        disabled={busy}
        onClick={async (e) => {
          const form = e.currentTarget.form!;
          if (!form.reportValidity()) return;
          setBusy(true);
          setError(undefined);
          setPrice(undefined);
          try {
            setPrice(
              await api<Price>(
                "/products/preview",
                "POST",
                productPayload(new FormData(form)),
              ),
            );
          } catch (e) {
            setError(e);
          } finally {
            setBusy(false);
          }
        }}
      >
        محاسبه و پیش‌نمایش قیمت
      </button>
      <ErrorNotice error={error} />
      {price && <PricePreview price={price} />}
    </Form>
  );
}

export default function Products() {
  const cache = useQueryClient();
  const [edit, setEdit] = useState<Product | null | undefined>();
  const [offset, setOffset] = useState(0);
  const [ratesOpen, setRatesOpen] = useState(false);
  const [confirm, setConfirm] = useState<{
    product: Product;
    action: "toggle" | "delete";
  }>();
  const query = useQuery({
    queryKey: ["products", offset],
    queryFn: () => api<Product[]>("/products?offset=" + offset),
  });
  return (
    <>
      <PageTitle
        title="products"
        subtitle="قیمت، ارز و موجودی محصولات فروش خود را مدیریت کنید."
      >
        <button className="secondary" onClick={() => setRatesOpen(true)}>
          نرخ‌های Workspace
        </button>
        <button onClick={() => setEdit(null)}>محصول جدید</button>
      </PageTitle>
      <ErrorNotice error={query.error} />
      {query.isPending ? (
        <Loading />
      ) : !query.data?.length ? (
        <Empty
          title="محصولی ثبت نشده"
          subtitle="اولین محصول را برای اتصال به پست‌ها اضافه کنید."
        />
      ) : (
        <div className="commerce-grid">
          {query.data.map((p) => (
            <article className="card commerce-card" key={p.id}>
              <div className="section-heading">
                <h2>{p.name}</h2>
                <Badge value={p.status} />
              </div>
              <p>{p.description}</p>
              <strong>
                {p.base_price} {t(p.base_currency)}
              </strong>
              <p>
                {t(p.pricing_mode)} · {t(p.availability)}
              </p>
              <small>
                {p.sku || p.slug} · {p.media_count} محتوای متصل · {p.automation_count}{" "}
                اتوماسیون
              </small>
              <small>آخرین تغییر: {date(p.updated_at)}</small>
              <div className="form-actions">
                <button className="secondary" onClick={() => setEdit(p)}>
                  مشاهده و ویرایش محصول
                </button>
                <button
                  className="secondary"
                  onClick={() => setConfirm({ product: p, action: "toggle" })}
                >
                  {p.status === "ACTIVE" ? "غیرفعال کردن" : "فعال کردن"}
                </button>
                <button
                  className="danger"
                  onClick={() => setConfirm({ product: p, action: "delete" })}
                >
                  حذف امن
                </button>
              </div>
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
          disabled={(query.data?.length ?? 0) < 100}
          onClick={() => setOffset(offset + 100)}
        >
          بعدی
        </button>
      </div>
      {edit !== undefined && (
        <Modal
          title={edit ? "ویرایش محصول" : "محصول جدید"}
          close={() => setEdit(undefined)}
        >
          <ProductEditor
            product={edit}
            done={() => {
              void cache.invalidateQueries({ queryKey: ["products"] });
              setEdit(undefined);
            }}
          />
        </Modal>
      )}
      {ratesOpen && (
        <Modal title="نرخ‌های Workspace" close={() => setRatesOpen(false)}>
          <RateSettings />
        </Modal>
      )}
      {confirm && (
        <Confirm
          close={() => setConfirm(undefined)}
          action={async () => {
            if (confirm.action === "delete") {
              await api("/products/" + confirm.product.id, "DELETE");
            } else {
              await api("/products/" + confirm.product.id, "PUT", {
                ...productUpdatePayload(confirm.product),
                status: confirm.product.status === "ACTIVE" ? "INACTIVE" : "ACTIVE",
              });
            }
            await cache.invalidateQueries({ queryKey: ["products"] });
          }}
        />
      )}
    </>
  );
}

function RateSettings() {
  const query = useQuery({
    queryKey: ["exchange-rates"],
    queryFn: () =>
      api<{
        manual: {
          id: string;
          base_currency: string;
          quote_currency: string;
          rate: string;
        }[];
        provider: { status: string };
      }>("/exchange-rates"),
  });
  return (
    <>
      <ErrorNotice error={query.error} />
      <p>هر تومان = ۱۰ ریال. نرخ‌های ذخیره‌شده فقط برای Workspace شما هستند.</p>
      <ul>
        {query.data?.manual.map((r) => (
          <li key={r.id}>
            {t(r.base_currency)} ← {t(r.quote_currency)}: {r.rate}
          </li>
        ))}
      </ul>
      <Form
        label="save"
        submit={async (data) => {
          await api("/exchange-rates", "PUT", {
            base_currency: data.get("base"),
            quote_currency: data.get("quote"),
            rate: data.get("rate"),
          });
          await query.refetch();
        }}
      >
        {["base", "quote"].map((name, i) => (
          <Field key={name} label={i ? "ارز مقصد" : "ارز مبدأ"}>
            <select name={name} defaultValue={i ? "TOMAN" : "USD"}>
              {currencies.map((c) => (
                <option key={c} value={c}>
                  {t(c)}
                </option>
              ))}
            </select>
          </Field>
        ))}
        <Field label="نرخ تبدیل">
          <input
            name="rate"
            type="number"
            step="any"
            min="0.0000000001"
            required
          />
        </Field>
      </Form>
      <p>
        وضعیت منبع آنلاین: {t(query.data?.provider.status ?? "not_checked")}
      </p>
      <a
        href="https://www.exchangerate-api.com"
        target="_blank"
        rel="noreferrer"
      >
        Rates By Exchange Rate API
      </a>
    </>
  );
}
