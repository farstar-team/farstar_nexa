import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Bell, Check } from "lucide-react";
import { api } from "../api";
import { Empty, ErrorNotice, Loading, PageTitle } from "../components";
import { date, t } from "../i18n";
import type { User } from "../api";

type Notification = { id: string; title: string; body: string; status: string; read: boolean; created_at: string };

export default function Notifications({ user }: { user: User }) {
  const cache = useQueryClient();
  const [page, setPage] = useState(0);
  const query = useQuery({ queryKey: ["notifications", page], queryFn: () => api<Notification[]>(`/notifications?offset=${page * 20}`) });
  return <><PageTitle title="notifications" subtitle="notificationsSub" /><ErrorNotice error={query.error} /><section className="card notification-list">{query.isPending ? <Loading /> : !query.data?.length ? <Empty title="notificationsEmpty" /> : query.data.map((item) => <article className={`notification-item ${item.read ? "read" : ""}`} key={item.id}><div className="notification-icon"><Bell size={17} /></div><div><h3>{item.title}</h3><p>{item.body}</p><small>{date(item.created_at, user.timezone)}</small></div>{!item.read && <button className="icon-button" aria-label="خوانده شد" onClick={async () => { await api(`/notifications/${item.id}/read`, "POST"); await cache.invalidateQueries({ queryKey: ["notifications"] }); }}><Check size={17} /></button>}</article>)}</section><div className="pagination"><button disabled={!page} onClick={() => setPage(Math.max(0, page - 1))}>قبلی</button><span>{t("page")} {page + 1}</span><button disabled={(query.data?.length ?? 0) < 20} onClick={() => setPage(page + 1)}>بعدی</button></div></>;
}
