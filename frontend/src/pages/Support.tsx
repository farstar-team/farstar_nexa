import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, LifeBuoy, LockKeyhole, Search, Send } from "lucide-react";
import { api } from "../api";
import type { User } from "../api";
import { Empty, ErrorNotice, Field, Form, Loading, PageTitle } from "../components";
import { date, t } from "../i18n";

type Ticket = {
  id: string;
  ticket_code: string;
  subject: string;
  status: string;
  channel: string;
  user_id: string;
  created_at: string;
  updated_at: string;
  messages?: { id: string; body: string; author_role: string; created_at: string }[];
};

const PAGE_SIZE = 20;

export default function Support({ user }: { user: User }) {
  const cache = useQueryClient();
  const [selected, setSelected] = useState<string>();
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(0);
  const offset = page * PAGE_SIZE;
  const tickets = useQuery({
    queryKey: ["support-tickets", search, offset],
    queryFn: () => api<Ticket[]>(`/support/tickets?q=${encodeURIComponent(search)}&offset=${offset}`),
    refetchInterval: 8000,
  });
  const detail = useQuery({
    queryKey: ["support-ticket", selected],
    queryFn: () => api<Ticket>(`/support/tickets/${selected}`),
    enabled: Boolean(selected),
    refetchInterval: 5000,
  });
  const closeTicket = async () => {
    if (!selected) return;
    await api(`/support/tickets/${selected}`, "PATCH", { status: "closed" });
    await cache.invalidateQueries({ queryKey: ["support-ticket", selected] });
    await cache.invalidateQueries({ queryKey: ["support-tickets"] });
  };
  return <>
    <PageTitle title="supportTicketsPage" subtitle="supportTicketsHint" />
    <ErrorNotice error={tickets.error ?? detail.error} />
    <div className="support-layout support-ticket-page">
      <section className="card support-list">
        <div className="support-list-heading"><div><span className="eyebrow">پیگیری درخواست‌ها</span><h2>{t("supportTickets")}</h2></div><LifeBuoy size={22} /></div>
        <div className="ticket-search"><Search size={16} /><input value={search} onChange={(event) => { setSearch(event.target.value); setPage(0); setSelected(undefined); }} placeholder={t("ticketSearchPlaceholder")} aria-label={t("ticketSearchPlaceholder")} dir="ltr" /></div>
        {tickets.isPending ? <Loading /> : !tickets.data?.length ? <Empty title={search ? "ticketSearchEmpty" : "supportEmpty"} /> : <div className="ticket-list">{tickets.data.map((ticket) => <button key={ticket.id} className={`support-ticket ${selected === ticket.id ? "selected" : ""}`} onClick={() => setSelected(ticket.id)}><span><b>{ticket.subject}</b><code>{ticket.ticket_code}</code><small>{date(ticket.updated_at, user.timezone)}</small></span><span className={`ticket-status ${ticket.status}`}>{t(ticket.status)}</span></button>)}</div>}
        <div className="pagination support-pagination"><button disabled={!page} onClick={() => setPage(Math.max(0, page - 1))}>قبلی</button><span>{t("page")} {page + 1}</span><button disabled={(tickets.data?.length ?? 0) < PAGE_SIZE} onClick={() => setPage(page + 1)}>بعدی</button></div>
        <div className="card-divider" />
        <div className="new-ticket-intro"><div><h3>{t("newSupportTicket")}</h3><p>{t("ticketCreateHint")}</p></div><CheckCircle2 size={20} /></div>
        <Form submit={async (data) => { const result = await api<Ticket>("/support/tickets", "POST", { subject: data.get("subject"), message: data.get("message") }); await cache.invalidateQueries({ queryKey: ["support-tickets"] }); setSearch(""); setPage(0); setSelected(result.id); }}>
          <Field label="subject" required><input name="subject" maxLength={160} required /></Field>
          <Field label="message" required><textarea name="message" rows={4} required /></Field>
        </Form>
      </section>
      <section className="card support-thread">
        {!selected ? <div className="support-thread-empty"><LifeBuoy size={34} /><h2>{t("selectTicket")}</h2><p>از فهرست یک تیکت را انتخاب کنید یا درخواست تازه‌ای ثبت کنید.</p></div> : detail.isPending ? <Loading /> : detail.data ? <>
          <div className="ticket-thread-heading"><div><span className="eyebrow">کد پیگیری</span><code className="ticket-code-large">{detail.data.ticket_code}</code><h2>{detail.data.subject}</h2><small>{date(detail.data.created_at, user.timezone)}</small></div><div className="ticket-thread-actions"><span className={`ticket-status status-pill ${detail.data.status}`}>{t(detail.data.status)}</span>{detail.data.status !== "closed" && <button className="secondary close-ticket-button" onClick={closeTicket}><LockKeyhole size={15} />{t("closeTicket")}</button>}{["ADMIN", "SUPER_ADMIN"].includes(user.role) && detail.data.status !== "closed" && <select value={detail.data.status} onChange={async (event) => { await api(`/support/tickets/${selected}`, "PATCH", { status: event.target.value }); await cache.invalidateQueries({ queryKey: ["support-ticket", selected] }); await cache.invalidateQueries({ queryKey: ["support-tickets"] }); }}><option value="waiting_support">{t("waiting_support")}</option><option value="waiting_user">{t("waiting_user")}</option><option value="waiting_new_reply">{t("waiting_new_reply")}</option><option value="closed">{t("closed")}</option></select>}</div></div>
          <div className="support-messages">{detail.data.messages?.map((message) => <article className={`support-message ${message.author_role === "admin" ? "admin" : ""}`} key={message.id}><p>{message.body}</p><small>{message.author_role === "admin" ? t("supportTeam") : t("you")} · {date(message.created_at, user.timezone)}</small></article>)}</div>
          {detail.data.status !== "closed" ? <Form label="send" submit={async (data) => { await api(`/support/tickets/${selected}/messages`, "POST", { body: data.get("body") }); await cache.invalidateQueries({ queryKey: ["support-ticket", selected] }); await cache.invalidateQueries({ queryKey: ["support-tickets"] }); }}><Field label="reply"><textarea name="body" rows={3} required placeholder={t("replyPlaceholder")} /></Field><div className="form-actions"><span className="reply-note"><Send size={14} /> پاسخ در همین تیکت ثبت می‌شود</span><button type="submit"><Send size={16} />{t("send")}</button></div></Form> : <div className="closed-ticket-notice"><LockKeyhole size={17} />این تیکت بسته شده و امکان ارسال پیام جدید ندارد.</div>}
        </> : null}
      </section>
    </div>
  </>;
}
