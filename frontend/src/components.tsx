import { Children, cloneElement, isValidElement, useId, useState } from "react";
import type { FormEvent, ReactElement, ReactNode } from "react";
import { AlertCircle, CircleHelp, Inbox, LoaderCircle, X } from "lucide-react";
import { ApiError } from "./api";
import { t } from "./i18n";

export function Empty({
  title = "empty",
  subtitle = "emptySub",
  children,
}: {
  title?: string;
  subtitle?: string;
  children?: ReactNode;
}) {
  return (
    <div className="empty">
      <span className="empty-icon">
        <Inbox size={28} />
      </span>
      <h3>{t(title)}</h3>
      <p>{t(subtitle)}</p>
      {children}
    </div>
  );
}
export function Loading() {
  return (
    <div className="loading" role="status">
      <LoaderCircle className="spin" size={20} />
      {t("loading")}
    </div>
  );
}
export function ErrorNotice({ error }: { error: unknown }) {
  if (!error) return null;
  return (
    <div role="alert" className="notice error">
      <AlertCircle size={18} />
      {t(error instanceof ApiError ? error.code : "error")}
    </div>
  );
}
export function Badge({ value }: { value: string }) {
  return (
    <span className={`badge badge-${value}`}>
      {t(value === "cooldown" ? "cooldownStatus" : value)}
    </span>
  );
}
export function HelpTip({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  return (
    <span
      className="help-tip"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      <button
        type="button"
        className="help-tip-button"
        aria-label="توضیح این گزینه"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <CircleHelp size={15} />
      </button>
      {open && <span className="help-tip-popover" role="tooltip">{text}</span>}
    </span>
  );
}
export function Field({
  label,
  children,
  hint,
  help,
}: {
  label: string;
  children: ReactNode;
  hint?: string;
  help?: string;
}) {
  const fieldId = useId();
  const labeledChildren = Children.map(children, (child) =>
    isValidElement(child) &&
    typeof child.type === "string" &&
    ["input", "select", "textarea"].includes(child.type)
      ? (() => {
          const element = child as ReactElement<{ id?: string }>;
          return cloneElement(element, { id: element.props.id ?? fieldId });
        })()
      : child,
  );
  return (
    <div className="field">
      <div className="field-label"><label htmlFor={fieldId}>{t(label)}</label>{help && <HelpTip text={help} />}</div>
      {labeledChildren}
      {hint && <small>{t(hint)}</small>}
    </div>
  );
}
export function PageTitle({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children?: ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        <p className="eyebrow">{t("workspace")}</p>
        <h1>{t(title)}</h1>
        {subtitle && <p>{t(subtitle)}</p>}
      </div>
      <div className="heading-actions">{children}</div>
    </div>
  );
}
export function Modal({
  title,
  close,
  children,
}: {
  title: string;
  close: () => void;
  children: ReactNode;
}) {
  return (
    <dialog
      className="modal"
      ref={(node) => {
        if (node && !node.open) node.showModal();
      }}
      onCancel={close}
      aria-label={t(title)}
    >
      <div className="modal-heading">
        <h2>{t(title)}</h2>
        <button className="icon-button" aria-label={t("close")} onClick={close}>
          <X size={20} />
        </button>
      </div>
      {children}
    </dialog>
  );
}
export function Confirm({
  action,
  close,
}: {
  action: () => Promise<unknown>;
  close: () => void;
}) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<unknown>();
  return (
    <Modal title="confirmTitle" close={close}>
      <p>{t("confirmSub")}</p>
      <ErrorNotice error={error} />
      <div className="form-actions">
        <button className="secondary" onClick={close}>
          {t("cancel")}
        </button>
        <button
          disabled={pending}
          onClick={async () => {
            setPending(true);
            try {
              await action();
              close();
            } catch (e) {
              setError(e);
            } finally {
              setPending(false);
            }
          }}
        >
          {t("confirm")}
        </button>
      </div>
    </Modal>
  );
}
export function Form({
  submit,
  children,
  label = "save",
}: {
  submit: (data: FormData) => Promise<unknown>;
  children: ReactNode;
  label?: string;
}) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<unknown>();
  const [success, setSuccess] = useState(false);
  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    setPending(true);
    setError(undefined);
    setSuccess(false);
    try {
      await submit(data);
      setSuccess(true);
    } catch (e) {
      setError(e);
    } finally {
      setPending(false);
    }
  }
  return (
    <form onSubmit={onSubmit}>
      <ErrorNotice error={error} />
      {children}
      {success && (
        <p className="notice success" role="status">
          {t("done")}
        </p>
      )}
      <div className="form-actions">
        <button disabled={pending} type="submit">
          {pending ? <LoaderCircle size={17} className="spin" /> : null}
          {t(label)}
        </button>
      </div>
    </form>
  );
}
