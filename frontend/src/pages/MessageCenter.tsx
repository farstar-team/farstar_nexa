import { MessageCircle } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import type { User } from "../api";
import { Field, Form, Loading, ErrorNotice, PageTitle } from "../components";
import { t } from "../i18n";

export default function MessageCenter({ currentUser }: { currentUser: User }) {
  const users = useQuery({ queryKey: ["admin-message-users"], queryFn: () => api<User[]>("/admin/users") });
  if (users.isPending) return <Loading />;
  return <><PageTitle title="messageCenter" subtitle="messageCenterSub" /><section className="card message-center"><MessageCircle size={24} /><p>{t("messageCenterHint")}</p><ErrorNotice error={users.error} /><Form label="send" submit={async (data) => { const channels = ["panel", "email", "telegram"].filter((channel) => data.get(channel) === "on"); await api("/admin/messages", "POST", { user_id: data.get("user_id"), title: data.get("title"), body: data.get("body"), channels }); }}><Field label="recipient"><select name="user_id" required defaultValue=""><option value="" disabled>{t("selectRecipient")}</option><option value="*">ارسال عمومی برای همه کاربران فعال</option>{users.data?.filter((item) => item.id !== currentUser.id).map((item) => <option key={item.id} value={item.id}>{item.username} · {item.email}</option>)}</select></Field><Field label="title"><input name="title" maxLength={160} required /></Field><Field label="message"><textarea name="body" rows={6} maxLength={5000} required /></Field><fieldset className="channel-options"><legend>{t("deliveryChannels")}</legend>{[["panel", "panelNotification"], ["email", "email"], ["telegram", "telegram"]].map(([value, label]) => <label key={value}><input type="checkbox" name={value} defaultChecked={value === "panel"} /> {t(label)}</label>)}</fieldset></Form></section></>;
}
