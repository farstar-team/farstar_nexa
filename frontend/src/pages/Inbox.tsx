import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { MessageSquare } from "lucide-react";
import { api } from "../api";
import type { Conversation, Message, User } from "../api";
import { Badge, Empty, ErrorNotice, Loading, PageTitle } from "../components";
import { date, t } from "../i18n";

export default function Inbox({ user }: { user: User }) {
  const [selected, setSelected] = useState<string>();
  const conversations = useQuery({
    queryKey: ["conversations"],
    queryFn: () => api<Conversation[]>("/conversations"),
    refetchInterval: 4000,
  });
  const messages = useQuery({
    queryKey: ["messages", selected],
    queryFn: () => api<Message[]>(`/conversations/${selected}/messages`),
    enabled: !!selected,
    refetchInterval: 4000,
  });
  return (
    <>
      <PageTitle title="inbox" subtitle="inboxSub" />
      <ErrorNotice error={conversations.error ?? messages.error} />
      <div className="inbox-layout">
        <aside className="conversation-list">
          <h2>{t("conversations")}</h2>
          {conversations.isPending ? (
            <Loading />
          ) : !conversations.data?.length ? (
            <Empty />
          ) : (
            conversations.data.map((c) => (
              <button
                key={c.id}
                className={`conversation ${selected === c.id ? "selected" : ""}`}
                onClick={() => setSelected(c.id)}
              >
                <span className="avatar">
                  <MessageSquare size={20} />
                </span>
                <span>
                  <b dir="auto">{c.sender_id}</b>
                  <small>{date(c.created_at, user.timezone)}</small>
                </span>
              </button>
            ))
          )}
        </aside>
        <section className="message-panel">
          {!selected ? (
            <Empty title="selectConversation" subtitle="inboxSub" />
          ) : messages.isPending ? (
            <Loading />
          ) : (
            <>
              <div className="message-header">
                <b dir="auto">
                  {
                    conversations.data?.find((c) => c.id === selected)
                      ?.sender_id
                  }
                </b>
                <span>{t("inbox")}</span>
              </div>
              <div className="message-list">
                {messages.data?.map((m) => (
                  <div key={m.id} className={`message message-${m.direction}`}>
                    <p dir="auto">{m.text}</p>
                    <div>
                      <small>{date(m.created_at, user.timezone)}</small>
                      <Badge value={m.status} />
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
        </section>
      </div>
    </>
  );
}
