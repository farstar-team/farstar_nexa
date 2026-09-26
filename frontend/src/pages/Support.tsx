import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { LifeBuoy, Send } from "lucide-react";
import { api } from "../api";
import type { User } from "../api";
import { Empty, ErrorNotice, Field, Form, Loading, PageTitle } from "../components";
import { date, t } from "../i18n";

type Ticket = {
  id: string;
  subject: string;
  status: string;
  channel: string;
  user_id: string;
  created_at: string;
  updated_at: string;
  messages?: { id: string; body: string; author_role: string; created_at: string }[];
};

export default function Support({ user }: { user: User }) {
  const cache = useQueryClient();
  const [selected, setSelected] = useState<string>();
  const tickets = useQuery({
    queryKey: ["support-tickets"],
    queryFn: () => api<Ticket[]>("/support/tickets"),
    refetchInterval: 8000,
  });
  const detail = useQuery({
    queryKey: ["support-ticket", selected],
    queryFn: () => api<Ticket>(`/support/tickets/${selected}`),
    enabled: Boolean(selected),
    refetchInterval: 5000,
  });
  return (
    <>
      <PageTitle title="support" subtitle="supportSub" />
      <ErrorNotice error={tickets.error ?? detail.error} />
      <div className="support-layout">
        <section className="card support-list">
          <div className="section-heading"><h2>{t("supportTickets")}</h2><LifeBuoy size={19} /></div>
          {tickets.isPending ? <Loading /> : !tickets.data?.length ? <Empty title="supportEmpty" /> : tickets.data.map((ticket) => (
            <button key={ticket.id} className={`support-ticket ${selected === ticket.id ? "selected" : ""}`} onClick={() => setSelected(ticket.id)}>
              <span><b>{ticket.subject}</b><small>{date(ticket.updated_at, user.timezone)}</small></span>
              <span className={`ticket-status ${ticket.status}`}>{t(ticket.status)}</span>
            </button>
          ))}
          <div className="card-divider" />
          <h3>{t("newSupportTicket")}</h3>
          <Form submit={async (data) => {
            const result = await api<Ticket>("/support/tickets", "POST", {
              subject: data.get("subject"), message: data.get("message"), channel: data.get("channel"),
            });
            await cache.invalidateQueries({ queryKey: ["support-tickets"] });
            setSelected(result.id);
          }}>
            <Field label="subject"><input name="subject" maxLength={160} required /></Field>
            <Field label="message"><textarea name="message" rows={4} required /></Field>
            <Field label="supportChannel"><select name="channel"><option value="ticket">{t("ticket")}</option><option value="live_chat">{t("liveChat")}</option></select></Field>
          </Form>
        </section>
        <section className="card support-thread">
          {!selected ? <Empty title="selectTicket" /> : detail.isPending ? <Loading /> : detail.data ? (
            <>
              <div className="section-heading"><div><h2>{detail.data.subject}</h2><small>{detail.data.channel === "live_chat" ? t("liveChat") : t("ticket")}</small></div>{["ADMIN", "SUPER_ADMIN"].includes(user.role) && <select value={detail.data.status} onChange={async (event) => { await api(`/support/tickets/${selected}`, "PATCH", { status: event.target.value }); await cache.invalidateQueries({ queryKey: ["support-ticket", selected] }); await cache.invalidateQueries({ queryKey: ["support-tickets"] }); }}><option value="open">{t("open")}</option><option value="pending">{t("pending")}</option><option value="resolved">{t("resolved")}</option><option value="closed">{t("closed")}</option></select>}</div>
              <div className="support-messages">{detail.data.messages?.map((message) => <article className={`support-message ${message.author_role === "admin" ? "admin" : ""}`} key={message.id}><p>{message.body}</p><small>{message.author_role === "admin" ? t("supportTeam") : t("you")} · {date(message.created_at, user.timezone)}</small></article>)}</div>
              {detail.data.status !== "closed" && <Form label="send" submit={async (data) => { await api(`/support/tickets/${selected}/messages`, "POST", { body: data.get("body") }); await cache.invalidateQueries({ queryKey: ["support-ticket", selected] }); await cache.invalidateQueries({ queryKey: ["support-tickets"] }); }}><Field label="reply"><textarea name="body" rows={3} required placeholder={t("replyPlaceholder")} /></Field><div className="form-actions"><span /><button type="submit"><Send size={16} />{t("send")}</button></div></Form>}
            </>
          ) : null}
        </section>
      </div>
    </>
  );
}
