import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { KeyRound, Plus, ShieldCheck, UserRound, X } from "lucide-react";
import { api } from "../api";
import type { TeamMember } from "../api";
import { Field, Form, Loading } from "../components";
import { t } from "../i18n";

type Product = { id: string; name: string };

export default function TeamManagement() {
  const cache = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  const [editing, setEditing] = useState<TeamMember | null>(null);
  const products = useQuery({ queryKey: ["products"], queryFn: () => api<Product[]>("/products") });
  const members = useQuery({ queryKey: ["team"], queryFn: () => api<TeamMember[]>("/team") });
  const productNames = (ids: string[]) => ids.map((id) => products.data?.find((p) => p.id === id)?.name).filter(Boolean).join("، ") || "محصولی انتخاب نشده است";
  return <section className="team-management">
    <div className="team-heading"><div><h2>{t("teamMembers")}</h2><p className="muted">{t("teamMembersHint")}</p></div><button onClick={() => setShowCreate((value) => !value)}><Plus size={17} />{t("addTeamMember")}</button></div>
    {showCreate && <div className="card team-form-card"><div className="team-form-title"><UserRound size={18} />{t("newTeamMember")}</div><Form label="create" submit={async (data) => { await api("/team", "POST", { username: data.get("username"), email: data.get("email"), password: data.get("password"), product_ids: data.getAll("product_ids") }); await cache.invalidateQueries({ queryKey: ["team"] }); setShowCreate(false); }}><div className="settings-grid compact-grid"><Field label="username" required><input name="username" required minLength={3} maxLength={64} dir="ltr" /></Field><Field label="email" required><input name="email" type="email" required dir="ltr" /></Field><Field label="password" hint="passwordHint" required><input name="password" type="password" required minLength={12} dir="ltr" /></Field><Field label="assignedProducts" help="محصولاتی را انتخاب کنید که این مدیر فروش اجازه مدیریت آن‌ها را دارد."><select name="product_ids" multiple size={Math.min(5, Math.max(2, products.data?.length ?? 2))}>{(products.data ?? []).map((product) => <option value={product.id} key={product.id}>{product.name}</option>)}</select></Field></div></Form></div>}
    {members.isPending ? <Loading /> : <div className="team-list">{(members.data ?? []).map((member) => <article className="card team-member-card" key={member.id}><div className="team-member-top"><div className="team-avatar"><UserRound size={18} /></div><div><strong>{member.username}</strong><span dir="ltr">{member.email}</span></div><span className={member.active ? "online" : "offline"}>{member.active ? t("active") : t("inactive")}</span></div><p className="team-products"><ShieldCheck size={16} />{productNames(member.product_ids)}</p><div className="team-member-actions"><button className="secondary" onClick={() => setEditing(member)}><KeyRound size={15} />{t("manageTeamMember")}</button></div></article>)}{!members.data?.length && <div className="notice">{t("teamEmpty")}</div>}</div>}
    {editing && <div className="modal-backdrop" role="dialog" aria-modal="true"><div className="card team-edit-modal"><div className="modal-heading"><h2>{t("manageTeamMember")}: {editing.username}</h2><button className="icon-button" onClick={() => setEditing(null)}><X size={18} /></button></div><Form submit={async (data) => { await api(`/team/${editing.id}`, "PATCH", { active: data.get("active") === "on", password: data.get("password") || undefined, product_ids: data.getAll("product_ids") }); await cache.invalidateQueries({ queryKey: ["team"] }); setEditing(null); }}><Field label="active"><input name="active" type="checkbox" defaultChecked={editing.active} /></Field><Field label="assignedProducts"><select name="product_ids" multiple defaultValue={editing.product_ids} size={Math.min(6, Math.max(2, products.data?.length ?? 2))}>{(products.data ?? []).map((product) => <option value={product.id} key={product.id}>{product.name}</option>)}</select></Field><Field label="newPassword" hint="passwordHint"><input name="password" type="password" minLength={12} dir="ltr" /></Field></Form></div></div>}
  </section>;
}
