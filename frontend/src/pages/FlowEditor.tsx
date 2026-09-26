import { useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import type { Account, Rule } from "../api";
import type { Action, Media, Product } from "../commerce";
import { newAction, variableLabels, variables } from "../commerce";
import { ErrorNotice, Field, Form } from "../components";
import { t } from "../i18n";
import ExecutionDetail from "./ExecutionDetail";

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
      { ...newAction("CREATE_OR_UPDATE_LEAD") },
      newAction(),
    ],
  );
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
          flow: { version: 2, actions },
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
      <ErrorNotice error={error ?? products.error ?? media.error} />
      {step === 1 && (
        <>
          <Field label="نام اتوماسیون">
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              maxLength={120}
            />
          </Field>
          <Field label="حساب Instagram">
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
          <Field label="محرک">
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
          <Field label="محصول">
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
              <Field label="محدوده مدیا">
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
                <Field label="مدیاهای انتخاب‌شده">
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
          <Field label="نوع تطبیق متن">
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
            <Field label="کلمات (جداشده با ویرگول)">
              <input
                value={keywords}
                onChange={(e) => setKeywords(e.target.value)}
              />
            </Field>
          )}
          <div className="form-grid">
            <Field label="فاصله مجاز هر مشتری/محصول (ثانیه)">
              <input
                type="number"
                min={2}
                max={86400}
                value={cooldown}
                onChange={(e) => setCooldown(Number(e.target.value))}
              />
            </Field>
            <Field label="اولویت">
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
          {actions.map((a, i) => (
            <section className="action-editor" key={i}>
              <Field label={`اقدام ${i + 1}`}>
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
                  <Field label="قالب پیام">
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
                    <summary>درج متغیر در پیام (کلیک یا بکش و رها کن)</summary>
                    <p className="field-help">متغیر در محل نشانگر متن درج می‌شود؛ می‌توانید آن را بکشید و داخل کادر متن رها کنید.</p>
                    <div className="variable-list">
                      {variables.map((v) => (
                        <button
                          className="secondary"
                          type="button"
                          key={v}
                          draggable
                          title={`{{${v}}}`}
                          onDragStart={(e) => e.dataTransfer.setData("text/plain", `{{${v}}}`)}
                          onClick={() => insertVariable(i, v)}
                        >
                          {variableLabels[v] ?? v}
                        </button>
                      ))}
                    </div>
                  </details>
                </>
              )}
              {["ADD_TAG", "INTERNAL_NOTE"].includes(a.type) && (
                <Field label="متن اقدام">
                  <input
                    value={a.value}
                    maxLength={a.type === "ADD_TAG" ? 60 : 500}
                    onChange={(e) => update(i, { value: e.target.value })}
                  />
                </Field>
              )}
              {a.type === "DELAY" && (
                <Field label="تأخیر (ثانیه)">
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
              <div className="heading-actions">
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
                  disabled={actions.length === 1}
                  onClick={() => setActions(actions.filter((_, n) => n !== i))}
                >
                  حذف اقدام
                </button>
              </div>
            </section>
          ))}
          <button
            type="button"
            className="secondary"
            disabled={actions.length >= 12}
            onClick={() => setActions([...actions, newAction("ADD_TAG")])}
          >
            افزودن اقدام
          </button>
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
          <button disabled={busy || !name.trim() || !account} onClick={save}>
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
