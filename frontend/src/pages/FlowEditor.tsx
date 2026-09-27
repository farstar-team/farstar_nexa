import { useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { X } from "lucide-react";
import { api } from "../api";
import type { Account, Rule } from "../api";
import type { Action, FAQItem, Media, Product } from "../commerce";
import { newAction, variableDescriptions, variableLabels, variables } from "../commerce";
import { ErrorNotice, Field, Form, HelpTip } from "../components";
import { t } from "../i18n";
import ExecutionDetail from "./ExecutionDetail";

const actionHelp: Record<string, string> = {
  SEND_DM: "یک متن برای مشتری در دایرکت می‌فرستد. برای لینک، توضیح کوتاه یا پاسخ معمولی از این گزینه استفاده کنید.",
  SEND_PRODUCT: "نام، توضیحات، لینک و اطلاعات محصول را برای مشتری می‌فرستد.",
  SEND_PRICE: "قیمت نهایی محصول را با توجه به تنظیمات قیمت‌گذاری برای مشتری می‌فرستد.",
  ADD_TAG: "یک برچسب داخلی به مخاطب اضافه می‌کند؛ مثلاً «پیگیری» یا «علاقه‌مند». مشتری این برچسب را نمی‌بیند.",
  CREATE_OR_UPDATE_LEAD: "مخاطب را در بخش مخاطبان فروش ثبت می‌کند یا اطلاعات قبلی او را به‌روز می‌کند.",
  DELAY: "قبل از اقدام بعدی چند ثانیه صبر می‌کند.",
  INTERNAL_NOTE: "یک یادداشت داخلی برای تیم فروش ثبت می‌کند؛ مشتری آن را نمی‌بیند.",
};

const presetHelp: Record<string, string> = {
  price: "وقتی مشتری درباره قیمت کامنت می‌گذارد، قیمت نهایی محصول برای او ارسال می‌شود.",
  product: "اطلاعات محصول و لینک آن برای مشتری ارسال می‌شود.",
  link: "یک پیام کوتاه شامل لینک محصول برای مشتری ارسال می‌شود.",
  text: "یک متن ثابت برای پاسخ سریع به مشتری ارسال می‌شود.",
  lead: "فقط مخاطب را ثبت می‌کند تا بعداً تیم فروش پیگیری کند.",
};

function newFaq(): FAQItem {
  return { id: `faq-${crypto.randomUUID().slice(0, 8)}`, question: "", answer: "" };
}

export default function FlowEditor({
  rule,
  accounts,
  done,
}: {
  rule: Rule | null;
  accounts: Account[];
  done: () => void;
}) {
  const [step, setStep] = useState(1);
  const [account, setAccount] = useState(
    rule?.account_id ?? accounts[0]?.id ?? "",
  );
  const [name, setName] = useState(rule?.name ?? "");
  const [trigger, setTrigger] = useState(
    rule?.trigger_type ?? "instagram.comment",
  );
  const [product, setProduct] = useState(rule?.product_id ?? "");
  const [scope, setScope] = useState(rule?.scope ?? "PRODUCT_MEDIA");
  const [mediaIds, setMediaIds] = useState<string[]>(rule?.media_ids ?? []);
  const [mode, setMode] = useState(rule?.match_mode ?? "contains");
  const [keywords, setKeywords] = useState(rule?.keywords.join("، ") ?? "قیمت");
  const [actions, setActions] = useState<Action[]>(
    rule?.flow?.actions ?? [
      newAction(),
    ],
  );
  const [faqEnabled, setFaqEnabled] = useState(rule?.flow?.faq_enabled ?? false);
  const [faqItems, setFaqItems] = useState<FAQItem[]>(rule?.flow?.faq_items ?? []);
  const [commentReplyEnabled, setCommentReplyEnabled] = useState(rule?.flow?.comment_reply?.enabled ?? false);
  const [commentReplyText, setCommentReplyText] = useState(rule?.flow?.comment_reply?.text ?? "قیمت برای شما در دایرکت ارسال شد.");
  const [cooldown, setCooldown] = useState(rule?.cooldown_seconds ?? 60);
  const [priority, setPriority] = useState(rule?.priority ?? 0);
  const [error, setError] = useState<unknown>();
  const [busy, setBusy] = useState(false);
  const templateRefs = useRef<Record<number, HTMLTextAreaElement | null>>({});
  const products = useQuery({
    queryKey: ["products"],
    queryFn: () => api<Product[]>("/products"),
  });
  const media = useQuery({
    queryKey: ["media", account, 0],
    queryFn: () =>
      api<Media[]>("/media?account_id=" + encodeURIComponent(account)),
    enabled: !!account,
  });
  function update(i: number, value: Partial<Action>) {
    setActions(actions.map((a, n) => (n === i ? { ...a, ...value } : a)));
  }
  function insertVariable(index: number, variable: string) {
    const textarea = templateRefs.current[index];
    const token = `{{${variable}}}`;
    const current = actions[index].template;
    const start = textarea?.selectionStart ?? current.length;
    const end = textarea?.selectionEnd ?? start;
    update(index, { template: current.slice(0, start) + token + current.slice(end) });
    requestAnimationFrame(() => {
      textarea?.focus();
      const caret = start + token.length;
      textarea?.setSelectionRange(caret, caret);
    });
  }
  function applyPreset(preset: "price" | "product" | "link" | "text" | "lead") {
    const isComment = preset === "price" || preset === "product";
    setTrigger(isComment ? "instagram.comment" : "message.keyword");
    setScope(isComment ? "PRODUCT_MEDIA" : "ANY_CONNECTED_MEDIA");
    setMode("contains");
    setKeywords(preset === "price" ? "قیمت، هزینه" : preset === "product" ? "مشخصات، اطلاعات" : preset === "link" ? "لینک، آدرس" : preset === "lead" ? "تماس، مشاوره" : "سلام، ممنون، راهنما");
    if (preset === "price") setActions([newAction("SEND_PRICE")]);
    if (preset === "product") setActions([newAction("SEND_PRODUCT")]);
    if (preset === "link") setActions([{ ...newAction("SEND_DM"), template: "سلام {{customer.name}}؛ لینک محصول: {{product.url}}" }]);
    if (preset === "text") setActions([{ ...newAction("SEND_DM"), template: "سلام {{customer.name}}؛ پیام شما دریافت شد. به‌زودی راهنمایی‌تان می‌کنیم." }]);
    if (preset === "lead") setActions([newAction("CREATE_OR_UPDATE_LEAD")]);
    setStep(1);
  }
  async function save() {
    setBusy(true);
    setError(undefined);
    try {
      await api(
        rule ? "/automations/" + rule.id : "/automations",
        rule ? "PUT" : "POST",
        {
          name,
          account_id: account,
          trigger_type: trigger,
          product_id: product || null,
          scope: trigger === "message.keyword" ? "ANY_CONNECTED_MEDIA" : scope,
          media_ids: mediaIds,
          match_mode: mode,
          keywords: keywords
            .split(/[,،]/)
            .map((s) => s.trim())
            .filter(Boolean),
          priority,
          cooldown_seconds: cooldown,
          status: "DRAFT",
          flow: {
            version: 2,
            actions,
            faq_enabled: faqEnabled,
            faq_items: faqItems.filter((item) => item.question.trim() && item.answer.trim()),
            comment_reply: { enabled: commentReplyEnabled, text: commentReplyText },
          },
        },
      );
      done();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="flow-editor">
      <div className="wizard-steps" aria-label="مراحل ساخت اتوماسیون">
        {["محرک و شرایط", "اقدام‌ها", "بازبینی"].map((label, i) => (
          <button
            type="button"
            className={step === i + 1 ? "" : "secondary"}
            key={label}
            onClick={() => setStep(i + 1)}
          >
            {i + 1}. {label}
          </button>
        ))}
      </div>
      <section className="automation-start card">
        <div><span className="eyebrow">شروع سریع <HelpTip text="یکی از دو الگوی آماده را بزنید تا شرط‌ها و اقدام‌های معمول خودکار پر شوند." /></span><h3>از یک الگوی آماده شروع کنید</h3><p>فقط محصول و حساب را انتخاب کنید؛ شرط‌ها و اقدام‌های رایج از قبل آماده می‌شوند.</p></div>
        <div className="automation-presets">
          {(Object.keys(presetHelp) as Array<"price" | "product" | "link" | "text" | "lead">).map((preset) => (
            <button type="button" className="secondary preset-button" key={preset} onClick={() => applyPreset(preset)} title={presetHelp[preset]}>
              {preset === "price" ? "پاسخ قیمت" : preset === "product" ? "اطلاعات محصول" : preset === "link" ? "ارسال لینک" : preset === "text" ? "پاسخ متن ثابت" : "ثبت مخاطب"}
            </button>
          ))}
        </div>
      </section>
      <ErrorNotice error={error ?? products.error ?? media.error} />
      {step === 1 && (
        <>
          <Field label="نام اتوماسیون" help="یک نام کوتاه انتخاب کنید تا بعداً این پاسخ را در فهرست اتوماسیون‌ها سریع پیدا کنید.">
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              maxLength={120}
            />
          </Field>
          <Field label="حساب اینستاگرام" help="حسابی را انتخاب کنید که کامنت یا پیام آن باید بررسی شود.">
            <select
              value={account}
              onChange={(e) => {
                setAccount(e.target.value);
                setMediaIds([]);
              }}
            >
              {accounts.map((a) => (
                <option value={a.id} key={a.id}>
                  {a.name}
                  {a.provider === "instagram_mock" ? " (فقط تست)" : ""}
                </option>
              ))}
            </select>
          </Field>
          <Field label="چه چیزی پاسخ را شروع کند؟" help="مشخص می‌کند پاسخ با کامنت روی پست/ریلز شروع شود یا با پیام دریافتی.">
            <select
              value={trigger}
              onChange={(e) => setTrigger(e.target.value)}
            >
              {["instagram.comment", "message.keyword"].map((s) => (
                <option key={s} value={s}>
                  {t(s)}
                </option>
              ))}
            </select>
          </Field>
          <Field label="محصول" help="محصولی را انتخاب کنید تا قیمت و اطلاعات آن در پاسخ قابل استفاده باشد.">
            <select
              value={product}
              onChange={(e) => setProduct(e.target.value)}
            >
              <option value="">بدون محصول / از مدیا</option>
              {products.data?.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </Field>
          {trigger === "instagram.comment" && (
            <>
              <Field label="این پاسخ برای کدام پست یا ریلز است؟" help="تعیین می‌کند پاسخ برای همه مدیاها، چند مدیای انتخابی یا مدیای متصل به محصول فعال شود.">
                <select
                  value={scope}
                  onChange={(e) => setScope(e.target.value)}
                >
                  {[
                    "ANY_CONNECTED_MEDIA",
                    "SPECIFIC_MEDIA",
                    "PRODUCT_MEDIA",
                  ].map((s) => (
                    <option key={s} value={s}>
                      {t(s)}
                    </option>
                  ))}
                </select>
              </Field>
              {scope === "SPECIFIC_MEDIA" && (
                <Field label="پست‌ها و ریلزهای انتخاب‌شده" help="فقط همین موارد با کامنت یا پیام مشتری، این اتوماسیون را اجرا می‌کنند.">
                  <select
                    multiple
                    value={mediaIds}
                    onChange={(e) =>
                      setMediaIds(
                        Array.from(e.target.selectedOptions, (o) => o.value),
                      )
                    }
                  >
                    {media.data?.map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.caption || m.external_id}
                      </option>
                    ))}
                  </select>
                </Field>
              )}
            </>
          )}
          <Field label="پیام چگونه بررسی شود؟" help="انتخاب کنید متن باید دقیقاً برابر باشد، شامل کلمه باشد یا با آن شروع شود.">
            <select value={mode} onChange={(e) => setMode(e.target.value)}>
              {["any", "exact", "contains", "starts_with", "keyword_set"].map(
                (m) => (
                  <option key={m} value={m}>
                    {t(m)}
                  </option>
                ),
              )}
            </select>
          </Field>
          {mode !== "any" && (
            <Field label="کلمه‌هایی که پاسخ را فعال می‌کنند" help="کلمه‌ها را با ویرگول جدا کنید؛ مثلاً قیمت، هزینه یا موجودی.">
              <input
                value={keywords}
                onChange={(e) => setKeywords(e.target.value)}
              />
            </Field>
          )}
          {trigger === "message.keyword" && (
            <details className="pretty-details" open={faqEnabled}>
              <summary>سؤال و جواب آماده برای مشتری</summary>
              <div>
                <label className="toggle-card">
                  <input type="checkbox" checked={faqEnabled} onChange={(event) => setFaqEnabled(event.target.checked)} />
                  <span><b>نمایش سؤال‌های آماده در دایرکت</b><small>مشتری سؤال را انتخاب می‌کند و پاسخ ثبت‌شده برای او ارسال می‌شود.</small></span>
                </label>
                {faqEnabled && <div className="faq-builder">
                  {!faqItems.length && <p className="field-help">برای شروع، یک سؤال و جواب اضافه کنید.</p>}
                  {faqItems.map((item, index) => <div className="faq-builder-row" key={item.id}>
                    <Field label={`سؤال ${index + 1}`}><input value={item.question} placeholder="مثلاً هزینه ارسال چقدر است؟" onChange={(event) => setFaqItems(faqItems.map((current) => current.id === item.id ? { ...current, question: event.target.value } : current))} /></Field>
                    <Field label="جواب"><textarea rows={2} value={item.answer} placeholder="پاسخ کوتاه و روشن بنویسید." onChange={(event) => setFaqItems(faqItems.map((current) => current.id === item.id ? { ...current, answer: event.target.value } : current))} /></Field>
                    <button type="button" className="icon-button action-remove" aria-label="حذف سؤال" onClick={() => setFaqItems(faqItems.filter((current) => current.id !== item.id))}><X size={17} /></button>
                  </div>)}
                  <button type="button" className="secondary" disabled={faqItems.length >= 8} onClick={() => setFaqItems([...faqItems, newFaq()])}>+ سؤال و جواب جدید</button>
                </div>}
              </div>
            </details>
          )}
          {trigger === "instagram.comment" && (
            <details className="pretty-details">
              <summary>کامنت عمومی بعد از ارسال دایرکت</summary>
              <div>
                <label className="toggle-card">
                  <input type="checkbox" checked={commentReplyEnabled} onChange={(event) => setCommentReplyEnabled(event.target.checked)} />
                  <span><b>بعد از دایرکت، زیر همان کامنت پیام بگذار</b><small>این پیام عمومی است و همهٔ کسانی که پست را می‌بینند آن را می‌بینند.</small></span>
                </label>
                {commentReplyEnabled && <Field label="متن کامنت"><textarea rows={2} value={commentReplyText} maxLength={1000} onChange={(event) => setCommentReplyText(event.target.value)} /></Field>}
              </div>
            </details>
          )}
          <div className="form-grid">
            <Field label="فاصله بین دو پاسخ به یک مشتری (ثانیه)" help="برای جلوگیری از پاسخ‌های تکراری، تا این مدت دوباره پاسخ مشابه ارسال نمی‌شود.">
              <input
                type="number"
                min={2}
                max={86400}
                value={cooldown}
                onChange={(e) => setCooldown(Number(e.target.value))}
              />
            </Field>
            <Field label="اولویت اجرای پاسخ" help="اگر چند اتوماسیون هم‌زمان منطبق شدند، عدد بزرگ‌تر زودتر بررسی می‌شود.">
              <input
                type="number"
                min={0}
                max={1000}
                value={priority}
                onChange={(e) => setPriority(Number(e.target.value))}
              />
            </Field>
          </div>
        </>
      )}
      {step === 2 && (
        <>
          <p className="notice">
            برای هر رویداد یک پیام مجاز است. پاسخ خصوصی کامنت تا ۷ روز؛ پیام
            بعدی فقط پس از پاسخ مخاطب و در بازهٔ ۲۴ساعته.
          </p>
          {!actions.length && <p className="empty action-empty">هنوز اقدامی اضافه نشده است. از دکمه «اقدام جدید» استفاده کنید.</p>}
          {actions.map((a, i) => (
            <section className="action-editor action-card" key={i}>
              <div className="action-card-header">
                <div><span className="eyebrow">مرحله {i + 1}</span><h3>{t(a.type)}</h3></div>
                <div className="action-card-tools"><HelpTip text={actionHelp[a.type] ?? "این اقدام بعد از برقرار شدن شرط اجرا می‌شود."} /><button type="button" className="icon-button action-remove" aria-label={`حذف ${t(a.type)}`} onClick={() => setActions(actions.filter((_, n) => n !== i))}><X size={18} /></button></div>
              </div>
              <Field label={`نوع اقدام مرحله ${i + 1}`} help={actionHelp[a.type] ?? "نوع کاری را انتخاب کنید که بعد از برقرار شدن شرط انجام شود."}>
                <select
                  value={a.type}
                  onChange={(e) => update(i, { type: e.target.value })}
                >
                  {[
                    "SEND_DM",
                    "SEND_PRODUCT",
                    "SEND_PRICE",
                    "ADD_TAG",
                    "CREATE_OR_UPDATE_LEAD",
                    "DELAY",
                    "INTERNAL_NOTE",
                  ].map((s) => (
                    <option key={s} value={s}>
                      {t(s)}
                    </option>
                  ))}
                </select>
              </Field>
              {a.type.startsWith("SEND_") && (
                <>
                  <Field label="قالب پیام" help="متنی که برای مشتری ارسال می‌شود. از دکمه‌های متغیر برای نام، قیمت، محصول و لینک استفاده کنید.">
                    <textarea
                      ref={(element) => {
                        templateRefs.current[i] = element;
                      }}
                      rows={4}
                      maxLength={1000}
                      value={a.template}
                      onChange={(e) => update(i, { template: e.target.value })}
                      onDragOver={(e) => e.preventDefault()}
                      onDrop={(e) => {
                        e.preventDefault();
                        const token = e.dataTransfer.getData("text/plain");
                        const variable = token.match(/^{{([a-z_]+\.[a-z_]+)}}$/)?.[1];
                        if (variable && variables.includes(variable)) insertVariable(i, variable);
                      }}
                    />
                  </Field>
                  <details className="pretty-details">
                    <summary>افزودن متغیر به متن پاسخ</summary>
                    <p className="field-help">متغیر در محل نشانگر متن درج می‌شود؛ می‌توانید آن را بکشید و داخل کادر متن رها کنید.</p>
                    <div className="variable-list">
                      {variables.map((v) => (
                        <button
                          className="secondary variable-chip"
                          type="button"
                          key={v}
                          draggable
                          title={variableDescriptions[v] ?? v}
                          onDragStart={(e) => e.dataTransfer.setData("text/plain", `{{${v}}}`)}
                          onClick={() => insertVariable(i, v)}
                        >
                          <span>{variableLabels[v] ?? v}</span><code>{`{{${v}}}`}</code>
                        </button>
                      ))}
                    </div>
                    <div className="variable-guide"><strong>راهنمای متغیرها</strong>{variables.map((v) => <div key={v}><code>{`{{${v}}}`}</code><span>{variableDescriptions[v] ?? "مقدار این متغیر در پیام نمایش داده می‌شود."}</span></div>)}</div>
                  </details>
                </>
              )}
              {["ADD_TAG", "INTERNAL_NOTE"].includes(a.type) && (
                <Field label="اطلاعات این اقدام" help="مقدار لازم برای این اقدام را بنویسید؛ مثلاً نام برچسب یا یادداشت داخلی.">
                  <input
                    value={a.value}
                    maxLength={a.type === "ADD_TAG" ? 60 : 500}
                    onChange={(e) => update(i, { value: e.target.value })}
                  />
                </Field>
              )}
              {a.type === "DELAY" && (
                <Field label="چند ثانیه صبر کند؟" help="قبل از اجرای اقدام بعدی این مقدار مکث می‌کند.">
                  <input
                    type="number"
                    min={0}
                    max={86400}
                    value={a.seconds}
                    onChange={(e) =>
                      update(i, { seconds: Number(e.target.value) })
                    }
                  />
                </Field>
              )}
              <div className="heading-actions action-order-tools">
                <button
                  type="button"
                  className="secondary"
                  disabled={i === 0}
                  onClick={() => {
                    const next = [...actions];
                    [next[i - 1], next[i]] = [next[i], next[i - 1]];
                    setActions(next);
                  }}
                >
                  بالاتر
                </button>
                <button
                  type="button"
                  className="secondary"
                  disabled={i === actions.length - 1}
                  onClick={() => {
                    const next = [...actions];
                    [next[i], next[i + 1]] = [next[i + 1], next[i]];
                    setActions(next);
                  }}
                >
                  پایین‌تر
                </button>
              </div>
            </section>
          ))}
          <div className="action-with-help">
            <button
              type="button"
              className="secondary"
              disabled={actions.length >= 12}
              onClick={() => setActions([...actions, newAction()])}
            >
              + اقدام جدید
            </button>
            <HelpTip text="یک کارت تازه برای کار بعدی اضافه می‌کند. ترتیب کارت‌ها همان ترتیب اجراست." />
          </div>
        </>
      )}
      {step === 3 && (
        <section className="price-preview">
          <h3>{name || "بدون نام"}</h3>
          <p>
            {t(trigger)} · {t(mode)} · {keywords}
          </p>
          <p>
            محصول:{" "}
            {products.data?.find((p) => p.id === product)?.name ||
              "از مدیا / بدون محصول"}
          </p>
          <ol>
            {actions.map((a, i) => (
              <li key={i}>
                {t(a.type)}
                {a.type.startsWith("SEND_") && (
                  <blockquote>{a.template}</blockquote>
                )}
              </li>
            ))}
          </ol>
          <p className="notice">
            به‌صورت پیش‌نویس ذخیره می‌شود. سپس Dry Run را اجرا کنید و برای ارسال
            واقعی آن را فعال کنید.
          </p>
          <button disabled={busy || !name.trim() || !account || !actions.length} onClick={save}>
            ذخیره پیش‌نویس
          </button>
        </section>
      )}
      <div className="pagination">
        <button
          className="secondary"
          disabled={step === 1}
          onClick={() => setStep(step - 1)}
        >
          مرحله قبل
        </button>
        <button disabled={step === 3} onClick={() => setStep(step + 1)}>
          مرحله بعد
        </button>
      </div>
    </div>
  );
}

export function DryRun({ rule }: { rule: Rule }) {
  const [execution, setExecution] = useState("");
  const [duplicate, setDuplicate] = useState(false);
  const media = useQuery({
    queryKey: ["media", rule.account_id, 0],
    queryFn: () =>
      api<Media[]>("/media?account_id=" + encodeURIComponent(rule.account_id)),
  });
  return (
    <>
      <p className="notice">
        هیچ پیام واقعی و هیچ مخاطب فروش واقعی ساخته نمی‌شود. برای بررسی
        idempotency شناسهٔ رویداد را ثابت نگه دارید.
      </p>
      <ErrorNotice error={media.error} />
      <Form
        label="اجرای Dry Run"
        submit={async (data) => {
          const result = await api<{
            execution_id: string;
            duplicate: boolean;
          }>(`/automations/${rule.id}/dry-run`, "POST", {
            account_id: rule.account_id,
            media_id: data.get("media"),
            sender: data.get("sender"),
            display_name: data.get("display_name"),
            text: data.get("text"),
            event_id: data.get("event"),
            sample_rate: data.get("sample_rate") || null,
          });
          setExecution(result.execution_id);
          setDuplicate(result.duplicate);
        }}
      >
        <Field label="مدیا برای تست">
          <select name="media" required>
            {media.data?.map((m) => (
              <option key={m.id} value={m.id}>
                {m.caption || m.external_id}
              </option>
            ))}
          </select>
        </Field>
        <Field label="نام مشتری نمونه">
          <input
            name="display_name"
            defaultValue="مشتری نمونه"
            maxLength={120}
          />
        </Field>
        <Field label="شناسه مشتری نمونه">
          <input
            name="sender"
            defaultValue="sample-customer"
            required
            maxLength={128}
          />
        </Field>
        <Field label="متن کامنت یا پیام">
          <textarea
            name="text"
            defaultValue="قیمت لطفاً"
            required
            maxLength={2000}
          />
        </Field>
        <Field label="شناسه رویداد نمونه">
          <input
            name="event"
            defaultValue={crypto.randomUUID()}
            required
            maxLength={100}
          />
        </Field>
        <Field label="نرخ ارز نمونه (اختیاری)">
          <input
            name="sample_rate"
            type="number"
            step="any"
            min="0.0000000001"
          />
        </Field>
      </Form>
      {duplicate && (
        <p className="notice">
          رویداد تکراری بود؛ نتیجه قبلی نمایش داده شد و دوباره اجرا نشد.
        </p>
      )}
      {execution && <ExecutionDetail id={execution} />}
    </>
  );
}
