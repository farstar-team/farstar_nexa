import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import type { Account } from "../api";
import {
  Badge,
  Confirm,
  Empty,
  ErrorNotice,
  Field,
  Form,
  HelpTip,
  Loading,
  Modal,
  PageTitle,
} from "../components";
import { currencies, formatAmount } from "../commerce";
import type { Media, Price, Product } from "../commerce";
import { date, t } from "../i18n";

export function PricePreview({ price }: { price: Price }) {
  return (
    <section className="price-preview" aria-label="پیش‌نمایش قیمت">
      <strong>
        {price.formatted_price} {t(price.currency)}
      </strong>
      <dl>
        {[
          ["قیمت تبدیل‌شده", formatAmount(price.converted_price)],
          ["سود یا کارمزد", formatAmount(price.adjustment)],
          ["تخفیف", formatAmount(price.discount)],
          ["نرخ تبدیل", formatAmount(price.rate)],
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
  const directPrice = data.has("direct_price");
  const useLiveRate = data.has("use_live_rate");
  const directCurrency = value("direct_currency") || value("base_currency") || "TOMAN";
  const adjustmentEnabled = data.has("adjustment_enabled");
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
    base_currency: directPrice ? directCurrency : value("base_currency"),
    output_currency: directPrice ? directCurrency : value("output_currency"),
    pricing_mode: directPrice
      ? "MANUAL"
      : useLiveRate
        ? adjustmentEnabled
          ? "LIVE_WITH_ADJUSTMENT"
          : "LIVE"
        : "MANUAL",
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
      direct_price: directPrice,
      adjustment_enabled: adjustmentEnabled,
      rate_source: value("rate_source") || "tgju_sana",
      percentage: value("percentage") || "0",
      fixed: value("fixed") || "0",
      rounding: value("rounding") || "0",
      minimum: value("minimum") || null,
      maximum: value("maximum") || null,
      discount_type: value("discount_type"),
      discount_value: value("discount_value") || "0",
      discount_start: timestamp("discount_start"),
      discount_end: timestamp("discount_end"),
      fallback: value("fallback") || "STOP",
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
  const [pricingMode, setPricingMode] = useState<"converted" | "direct">(
    product?.pricing.direct_price ? "direct" : "converted",
  );
  const [mediaAccount, setMediaAccount] = useState("");
  const [mediaIds, setMediaIds] = useState<string[]>([]);
  const [mediaDraftIds, setMediaDraftIds] = useState<string[]>([]);
  const [mediaPickerOpen, setMediaPickerOpen] = useState(false);
  const accounts = useQuery({
    queryKey: ["accounts"],
    queryFn: () => api<Account[]>("/accounts"),
  });
  const accountId = mediaAccount || accounts.data?.find((a) => a.active)?.id || "";
  const media = useQuery({
    queryKey: ["product-editor-media", accountId],
    queryFn: () => api<Media[]>("/media?account_id=" + encodeURIComponent(accountId)),
    enabled: !!accountId,
  });
  const choices = (
    name: string,
    label: string,
    values: string[],
    selected?: string,
    required = false,
  ) => (
    <Field label={label} required={required}>
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
      className="product-editor"
      label="save"
      submit={async (data) => {
        const saved = await api<Product>(
          product ? "/products/" + product.id : "/products",
          product ? "PUT" : "POST",
          productPayload(data),
        );
        if (mediaIds.length) {
          await api("/media/product", "PUT", { media_ids: mediaIds, product_id: saved.id });
        }
        done();
      }}
    >
      <input type="hidden" name="sku" value={product?.sku ?? ""} readOnly />
      <div className="form-grid">
        <Field label="نام محصول" required>
          <input
            name="name"
            defaultValue={product?.name}
            required
            maxLength={120}
          />
        </Field>
        <Field
          label="شناسه محصول"
          required
          hint="برای کنترل محصول در سیستم؛ فقط حروف انگلیسی، عدد، خط تیره یا زیرخط."
        >
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
        {choices("status", "وضعیت", ["ACTIVE", "INACTIVE"], product?.status)}
        {choices(
          "availability",
          "موجودی",
          ["IN_STOCK", "OUT_OF_STOCK", "LIMITED", "ON_REQUEST"],
          product?.availability,
        )}
        <Field label="قیمت پایه" required hint="مبلغ را بدون جداکننده هزارگان وارد کنید.">
          <input
            name="base_price"
            type="number"
            step="0.000001"
            min="0"
            required
            defaultValue={product?.base_price}
          />
        </Field>
      </div>
      <section className="pricing-mode-section" aria-labelledby="pricing-mode-title">
        <div className="section-heading pricing-mode-heading">
          <div>
            <h3 id="pricing-mode-title">قیمت‌گذاری محصول</h3>
            <p>فقط یکی از دو روش زیر را انتخاب کنید.</p>
          </div>
        </div>
        <div className="pricing-mode-grid">
          <label className={`pricing-mode-card ${pricingMode === "converted" ? "selected" : ""}`}>
            <input
              type="checkbox"
              name="use_live_rate"
              checked={pricingMode === "converted"}
              onChange={() => setPricingMode("converted")}
            />
            <span>
              <b>قیمت با تبدیل ارز</b>
              <small>قیمت بر اساس نرخ آزاد TGJU، سود یا کارمزد محاسبه می‌شود.</small>
            </span>
          </label>
          <label className={`pricing-mode-card ${pricingMode === "direct" ? "selected" : ""}`}>
            <input
              type="checkbox"
              name="direct_price"
              checked={pricingMode === "direct"}
              onChange={() => setPricingMode("direct")}
            />
            <span>
              <b>قیمت مستقیم</b>
              <small>همان مبلغی که وارد می‌کنید به مشتری نمایش داده می‌شود.</small>
            </span>
          </label>
        </div>
      </section>
      {pricingMode === "direct" ? (
        <section className="pricing-settings-card">
          <div className="section-heading">
            <div>
              <h3>تنظیم قیمت مستقیم</h3>
              <p>تبدیل ارز و سود روی این محصول اعمال نمی‌شود.</p>
            </div>
          </div>
          <Field label="واحد قیمت مستقیم" required hint="مثلاً تومان یا دلار؛ قیمت پایه با همین واحد نمایش داده می‌شود.">
            <select name="direct_currency" defaultValue={product?.output_currency ?? product?.base_currency ?? "TOMAN"}>
              {currencies.map((currency) => <option key={currency} value={currency}>{t(currency)}</option>)}
            </select>
          </Field>
        </section>
      ) : (
        <section className="pricing-settings-card">
          <div className="section-heading">
            <div>
              <h3>تنظیم تبدیل ارز</h3>
              <p>ارز قیمت پایه را به ارز نمایش تبدیل می‌کنیم.</p>
            </div>
          </div>
          <div className="form-grid">
            {choices("base_currency", "ارز پایه", currencies, product?.base_currency, true)}
            {choices("output_currency", "ارز نمایش", currencies, product?.output_currency ?? "TOMAN", true)}
            <Field label="منبع نرخ">
              <select name="rate_source" defaultValue={product?.pricing.rate_source ?? "tgju_sana"}>
                <option value="tgju_sana">دلار آزاد TGJU</option>
              </select>
            </Field>
            <Field label="نرخ دستی جایگزین" hint="فقط زمانی استفاده می‌شود که نرخ آنلاین در دسترس نباشد.">
              <input name="manual_rate" type="number" min="0.0000000001" step="any" defaultValue={product?.manual_rate ?? ""} />
            </Field>
          </div>
          <p className="notice">
            نرخ TGJU به ریال دریافت و هنگام نمایش تومان به‌صورت خودکار تبدیل می‌شود.
          </p>
        </section>
      )}
      {pricingMode === "converted" && <details className="pretty-details" open>
        <summary>سود، کارمزد و گرد کردن قیمت</summary>
        <div className="form-grid">
          <label className="toggle-card">
            <input
              type="checkbox"
              name="adjustment_enabled"
              defaultChecked={
                product?.pricing.adjustment_enabled ??
                product?.pricing_mode !== "LIVE"
              }
            />
            <span>
              <b className="label-with-help">اعمال سود یا کارمزد <HelpTip text="اگر روشن باشد، درصد یا مبلغی که پایین می‌نویسید روی قیمت تبدیل‌شده اعمال می‌شود." /></b>
              <small>درصد و مبلغ تعدیل زیر روی نرخ تبدیل‌شده اعمال می‌شود.</small>
            </span>
          </label>
          {(
            [
              ["percentage", "درصد سود یا کارمزد", "مثلاً ۱۰ یعنی قیمت ۱۰٪ بیشتر شود؛ عدد منفی قیمت را کم می‌کند."],
              ["fixed", "مبلغ سود یا کارمزد", "یک مبلغ ثابت به قیمت اضافه یا از آن کم می‌شود؛ مثلاً ۱۰۰٬۰۰۰ تومان."],
              ["minimum", "حداقل قیمت", "اگر قیمت از این مقدار کمتر باشد، همین حداقل قیمت استفاده می‌شود."],
              ["maximum", "حداکثر قیمت", "اگر قیمت از این مقدار بیشتر باشد، همین حداکثر قیمت استفاده می‌شود."],
            ] as const
          ).map(([key, label, help]) => (
            <Field key={key} label={label} help={help}>
              <input
                name={key}
                type="number"
                step="any"
                defaultValue={product?.pricing[key] ?? ""}
              />
            </Field>
          ))}
          <Field label="گرد کردن قیمت" help="قیمت نهایی به نزدیک‌ترین مضرب انتخابی گرد می‌شود؛ مثلاً ۱۰٬۰۰۰ یا ۱۰۰٬۰۰۰ تومان.">
            <select name="rounding" defaultValue={String(Math.round(Number(product?.pricing.rounding ?? 0)))}>
              <option value="0">بدون گرد کردن</option>
              <option value="10000">نزدیک‌ترین ۱۰٬۰۰۰ تومان</option>
              <option value="100000">نزدیک‌ترین ۱۰۰٬۰۰۰ تومان</option>
              <option value="1000000">نزدیک‌ترین ۱٬۰۰۰٬۰۰۰ تومان</option>
            </select>
          </Field>
          {choices(
            "fallback",
            "هنگام نبود نرخ آنلاین",
            ["STOP", "MANUAL"],
            product?.pricing.fallback,
          )}
        </div>
        <small>
          STOP یعنی توقف امن ارسال قیمت. این گزینه‌ها را می‌توانید هر زمان
          خاموش و روشن کنید.
        </small>
      </details>}
      <details className="pretty-details">
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
      <section className="product-media-picker">
        <div className="section-heading">
          <div>
            <h3>اتصال پست و ریلز</h3>
            <p>پست‌ها و ریلزهای مربوط به این محصول را از نمای شبیه اینستاگرام انتخاب کنید.</p>
          </div>
          {mediaIds.length > 0 && <span className="media-selected-count">{mediaIds.length} انتخاب شده</span>}
        </div>
        <Field label="حساب Instagram">
          <select value={accountId} onChange={(e) => { setMediaAccount(e.target.value); setMediaIds([]); setMediaDraftIds([]); }}>
            <option value="">انتخاب حساب</option>
            {accounts.data?.filter((a) => a.active).map((a) => <option value={a.id} key={a.id}>{a.name}</option>)}
          </select>
        </Field>
        {accountId && media.isPending && <Loading />}
        {accountId && media.data?.length === 0 && <p className="notice">برای این حساب هنوز پست یا ریلزی همگام نشده است.</p>}
        <button
          type="button"
          className="media-picker-open"
          disabled={!accountId || media.isPending || !media.data?.length}
          onClick={() => { setMediaDraftIds(mediaIds); setMediaPickerOpen(true); }}
        >
          {mediaIds.length ? `ویرایش انتخاب‌ها (${mediaIds.length})` : "باز کردن فهرست پست‌ها و ریلزها"}
        </button>
      </section>
      {mediaPickerOpen && (
        <Modal title="انتخاب پست‌ها و ریلزها" close={() => setMediaPickerOpen(false)}>
          <div className="media-picker-modal">
            <div className="media-picker-intro">
              <div>
                <strong>{accounts.data?.find((account) => account.id === accountId)?.name ?? "حساب Instagram"}</strong>
                <span>موارد مرتبط را تیک بزنید و در پایان «تأیید انتخاب‌ها» را بزنید.</span>
              </div>
              <span className="media-selected-count">{mediaDraftIds.length} انتخاب</span>
            </div>
            <div className="media-picker-grid">
              {media.data?.map((item) => {
                const selected = mediaDraftIds.includes(item.id);
                return (
                  <label className={`media-tile ${selected ? "selected" : ""}`} key={item.id}>
                    <input
                      type="checkbox"
                      aria-label={item.caption || item.external_id}
                      checked={selected}
                      onChange={(event) => setMediaDraftIds((current) => event.target.checked ? [...current, item.id] : current.filter((id) => id !== item.id))}
                    />
                    {item.thumbnail_url ? <img src={item.thumbnail_url} alt="" loading="lazy" /> : <span className="media-tile-placeholder">بدون تصویر</span>}
                    <span className="media-tile-body">
                      <b>{item.media_type === "REELS" ? "ریلز" : "پست"}</b>
                      <small>{item.caption || item.external_id}</small>
                    </span>
                  </label>
                );
              })}
            </div>
            <div className="media-picker-footer">
              <span>{mediaDraftIds.length} مورد برای اتصال انتخاب شده است.</span>
              <div>
                <button type="button" className="secondary" onClick={() => setMediaPickerOpen(false)}>لغو</button>
                <button type="button" onClick={() => { setMediaIds(mediaDraftIds); setMediaPickerOpen(false); }}>تأیید انتخاب‌ها</button>
              </div>
            </div>
          </div>
        </Modal>
      )}
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
      <ErrorNotice error={error ?? accounts.error ?? media.error} />
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
                {formatAmount(p.base_price)} {t(p.base_currency)}
              </strong>
              <p>
                {t(p.pricing_mode)} · {t(p.availability)}
              </p>
              <small>
                شناسه: {p.slug} · {p.media_count} محتوای متصل · {p.automation_count}{" "}
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
        active_provider?: string;
        attribution_url: string;
        attribution: string;
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
        منبع فعال: {t(query.data?.active_provider ?? "tgju_sana")}
      </p>
      <p>
        وضعیت منبع آنلاین: {t(query.data?.provider.status ?? "not_checked")}
      </p>
      <a
        href={query.data?.attribution_url}
        target="_blank"
        rel="noreferrer"
      >
        {query.data?.attribution ?? "منبع نرخ آنلاین"}
      </a>
    </>
  );
}
