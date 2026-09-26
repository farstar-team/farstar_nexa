import { useState } from "react";
import { AtSign, MailCheck } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { api, ApiError } from "../api";
import { Badge, ErrorNotice, Field, Form } from "../components";

const names = ["smtp_host", "smtp_port", "smtp_username", "smtp_password", "smtp_security"];
type EmailConfig = { [key: string]: boolean | string; email_domain: string; email_local_part: string };

export default function EmailSettings() {
  const query = useQuery({ queryKey: ["email-settings"], queryFn: () => api<EmailConfig>("/admin/integrations") });
  const [localPartDraft, setLocalPartDraft] = useState("");
  const localPart = localPartDraft || query.data?.email_local_part || "noreply";
  const domain = query.data?.email_domain || "example.com";
  return <section className="card email-settings">
    <div className="section-heading"><div><h2>مدیریت ایمیل</h2><p>فرستنده را با نام دلخواه بسازید و ارسال ایمیل را با SMTP کنترل کنید.</p></div><MailCheck size={28} /></div>
    <ErrorNotice error={query.error} />
    <div className="email-sender-preview"><AtSign size={21} /><div><small>فرستنده پیشنهادی</small><strong dir="ltr">{localPart || "noreply"}@{domain}</strong></div></div>
    <Form submit={async (data) => {
      const local = String(data.get("email_local_part") || "").trim().toLowerCase();
      if (!/^[a-z0-9][a-z0-9._-]{1,62}$/.test(local)) throw new ApiError("email_local_part_invalid", 422);
      const values = Object.fromEntries(names.map((key) => [key, String(data.get(key) || "")]).filter(([, value]) => value));
      values.smtp_from = `${local}@${domain}`;
      values.smtp_security = String(data.get("smtp_security") || "starttls");
      await api("/admin/integrations", "PUT", { values, password: data.get("password") });
      await query.refetch();
    }}>
      <Field label="نام فرستنده قبل از @"><input name="email_local_part" value={localPart} onChange={(e) => setLocalPartDraft(e.target.value)} dir="ltr" placeholder="noreply" required /></Field>
      <p className="field-help">دامنه از دامنه فعلی سیستم یا فرستنده قبلی خوانده می‌شود: <b dir="ltr">@{domain}</b></p>
      <div className="form-grid">
        {names.map((key) => <Field label={key} key={key}><div className="setting-label"><Badge value={query.data?.[key] ? "active" : "inactive"} /></div><input name={key} type={key === "smtp_password" ? "password" : "text"} dir="ltr" maxLength={1024} autoComplete="off" /></Field>)}
      </div>
      <Field label="reenterPassword"><input name="password" type="password" required dir="ltr" autoComplete="current-password" /></Field>
    </Form>
    <div className="card-divider" />
    <p className="notice">ساخت آدرس فرستنده در پنل انجام می‌شود؛ ایجاد واقعی mailbox به سرویس ایمیل میزبان دامنه و دسترسی SMTP آن وابسته است.</p>
    <Form label="sendTestEmail" submit={async (data) => { await api("/admin/email/test", "POST", { to: data.get("to"), password: data.get("password") }); }}>
      <div className="form-grid"><Field label="testRecipient"><input name="to" type="email" required dir="ltr" /></Field><Field label="reenterPassword"><input name="password" type="password" required dir="ltr" autoComplete="current-password" /></Field></div>
    </Form>
  </section>;
}
