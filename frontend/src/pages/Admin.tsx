import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity as ActivityIcon,
  Archive,
  ArrowDownToLine,
  CheckCircle2,
  Download,
  Globe2,
  MessageCircle,
  Mail,
  RefreshCw,
  Server,
  Shield,
  Users,
} from "lucide-react";
import { api } from "../api";
import type { Activity, Backup, Operation, User } from "../api";
import {
  Badge,
  Empty,
  ErrorNotice,
  Field,
  Form,
  Loading,
  Modal,
  PageTitle,
} from "../components";
import { date, number, t } from "../i18n";
import IntegrationSettings from "./IntegrationSettings";
import EmailSettings from "./EmailSettings";
import ContentEditor from "./ContentEditor";
import MessageCenter from "./MessageCenter";

type Status = {
  version: string;
  counts: Record<string, number>;
  database: boolean;
  redis: boolean;
  worker: boolean;
  cpu_percent: number;
  memory_percent: number;
  disk_percent: number;
  uptime_seconds: number;
  jobs: Record<string, number>;
  base_url: string;
  telegram_configured: boolean;
  meta_configured: boolean;
  host?: {
    domain: string;
    dns: string[];
    server_addresses: string[];
    ssl: { status: string; issuer?: string; expires?: string };
    services: { service: string; state: string; health: string }[];
  };
};
const tabs = [
  { key: "system", icon: Server },
  { key: "users", icon: Users },
  { key: "backups", icon: Archive },
  { key: "domain", icon: Globe2 },
  { key: "updates", icon: Download },
  { key: "audit", icon: Shield },
  { key: "content", icon: Globe2 },
  { key: "messages", icon: MessageCircle },
  { key: "email", icon: Mail },
];

export default function Admin({ user }: { user: User }) {
  const owner = user.role === "SUPER_ADMIN";
  const [tab, setTab] = useState(owner ? "system" : "users");
  const [operation, setOperation] = useState<{
    action: string;
    argument: string;
  }>();
  const [editing, setEditing] = useState<User>();
  const [search, setSearch] = useState("");
  const cache = useQueryClient();
  const status = useQuery({
    queryKey: ["admin-status"],
    queryFn: () => api<Status>("/admin/status"),
    enabled: owner,
    refetchInterval: 10000,
  });
  const users = useQuery({
    queryKey: ["admin-users", search],
    queryFn: () => api<User[]>("/admin/users?q=" + encodeURIComponent(search)),
    enabled: tab === "users",
  });
  const backups = useQuery({
    queryKey: ["backups"],
    queryFn: () => api<Backup[]>("/admin/backups"),
    enabled: owner && tab === "backups",
    refetchInterval: 10000,
  });
  const operations = useQuery({
    queryKey: ["operations"],
    queryFn: () => api<Operation[]>("/admin/operations"),
    enabled: owner,
    refetchInterval: 3000,
  });
  const audit = useQuery({
    queryKey: ["admin-audit"],
    queryFn: () => api<Activity[]>("/admin/audit"),
    enabled: owner && tab === "audit",
  });
  const request = (action: string, argument = "") =>
    setOperation({ action, argument });
  const latest = operations.data?.find(
    (op) => op.action === "check-update" && op.status === "complete",
  )?.result;
  return (
    <>
      <PageTitle title="admin">
        <span className="version-tag">NEXA {status.data?.version}</span>
      </PageTitle>
      <nav className="tabs">
        {tabs
          .filter((item) => owner || item.key === "users")
          .map(({ key, icon: Icon }) => (
            <button
              key={key}
              className={tab === key ? "selected" : ""}
              onClick={() => setTab(key)}
            >
              <Icon size={17} />
              {t(key)}
            </button>
          ))}
      </nav>
      <ErrorNotice error={status.error} />
      {tab === "system" &&
        (status.isPending ? (
          <Loading />
        ) : (
          status.data && (
            <>
              <div className="stats-grid">
                {Object.entries(status.data.counts).map(([key, value]) => (
                  <div className="stat-card" key={key}>
                    <div className="stat-top">
                      {t(key)}
                      <ActivityIcon size={18} />
                    </div>
                    <strong>{number(value)}</strong>
                  </div>
                ))}
              </div>
              <div className="settings-grid">
                <section className="card">
                  <h2>{t("system")}</h2>
                  {["database", "redis", "worker"].map((key) => (
                    <div className="status-row" key={key}>
                      <span>{t(key)}</span>
                      <span
                        className={
                          status.data[key as "database"] ? "online" : "offline"
                        }
                      >
                        <CheckCircle2 size={15} />
                        {t(
                          status.data[key as "database"]
                            ? "healthy"
                            : "unavailable",
                        )}
                      </span>
                    </div>
                  ))}
                  {["cpu", "memory", "disk"].map((key) => (
                    <div className="metric" key={key}>
                      <span>{t(key)}</span>
                      <strong>
                        {number(status.data[`${key}_percent` as "cpu_percent"])}
                        %
                      </strong>
                      <meter
                        min={0}
                        max={100}
                        value={status.data[`${key}_percent` as "cpu_percent"]}
                      />
                    </div>
                  ))}
                  <small>{t("metricScope")}</small>
                  <p>
                    {t("uptime")}:{" "}
                    {number(Math.floor(status.data.uptime_seconds / 3600))} h
                  </p>
                </section>
                <section className="card">
                  <h2>{t("config")}</h2>
                  <div className="status-row">
                    <span>{t("instagram")}</span>
                    <Badge
                      value={
                        status.data.meta_configured ? "active" : "inactive"
                      }
                    />
                  </div>
                  <div className="status-row">
                    <span>{t("telegram")}</span>
                    <Badge
                      value={
                        status.data.telegram_configured ? "active" : "inactive"
                      }
                    />
                  </div>
                  <p className="notice">{t("configHint")}</p>
                  {Object.entries(status.data.jobs).map(([key, value]) => (
                    <div className="status-row" key={key}>
                      <span>{t(key + "Jobs")}</span>
                      <strong>{number(value)}</strong>
                    </div>
                  ))}
                </section>
              </div>
            </>
          )
        ))}
      {tab === "users" && (
        <section className="card">
          <div className="section-heading">
            <h2>{t("users")}</h2>
            <input
              className="search-input"
              aria-label={t("searchUsers")}
              placeholder={t("searchUsers")}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <ErrorNotice error={users.error} />
          {users.isPending ? (
            <Loading />
          ) : (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    {["username", "email", "role", "status", "actions"].map(
                      (k) => (
                        <th key={k}>{t(k)}</th>
                      ),
                    )}
                  </tr>
                </thead>
                <tbody>
                  {users.data?.map((row) => (
                    <tr key={row.id}>
                      <td>
                        <b>{row.username}</b>
                      </td>
                      <td>
                        <span dir="ltr">{row.email}</span>
                      </td>
                      <td>{t(row.role)}</td>
                      <td>
                        <Badge value={row.active ? "active" : "inactive"} />
                      </td>
                      <td>
                        {owner &&
                          row.id !== user.id &&
                          row.role !== "SUPER_ADMIN" && (
                            <button
                              className="secondary small"
                              onClick={() => setEditing(row)}
                            >
                              {t("edit")}
                            </button>
                          )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}
      {tab === "backups" && (
        <section className="card">
          <div className="section-heading">
            <h2>{t("backups")}</h2>
            <button onClick={() => request("backup")}>
              <Archive size={17} />
              {t("backupNow")}
            </button>
          </div>
          <p className="notice">{t("backupHint")}</p>
          <ErrorNotice error={backups.error} />
          {backups.isPending ? (
            <Loading />
          ) : !backups.data?.length ? (
            <Empty title="noBackups" />
          ) : (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    {["name", "date", "size", "version", "actions"].map((k) => (
                      <th key={k}>{t(k)}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {backups.data.map((row) => (
                    <tr key={row.name}>
                      <td>
                        <code>{row.name}</code>
                      </td>
                      <td>{date(row.created_at, user.timezone)}</td>
                      <td>{number(Math.round(row.size / 1024))} KB</td>
                      <td>{row.version}</td>
                      <td>
                        <div className="table-actions">
                          <a
                            className="icon-button"
                            aria-label={t("download")}
                            href={
                              "/api/admin/backups/" + row.name + "/download"
                            }
                          >
                            <ArrowDownToLine size={17} />
                          </a>
                          <button
                            className="secondary small"
                            onClick={() => request("restore", row.name)}
                          >
                            {t("restore")}
                          </button>
                          <button
                            className="text-button danger"
                            onClick={() => request("delete-backup", row.name)}
                          >
                            {t("delete")}
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}
      {tab === "domain" && (
        <div className="settings-grid">
          <section className="card">
            <h2>{t("currentDomain")}</h2>
            <p className="domain-display ltr">{status.data?.base_url}</p>
            <p className="notice">{t("domainHint")}</p>
            <Form
              label="setDomain"
              submit={async (data) =>
                request("domain", String(data.get("domain")))
              }
            >
              <Field label="newDomain">
                <input
                  name="domain"
                  dir="ltr"
                  placeholder="panel.example.com"
                  required
                />
              </Field>
            </Form>
            <button
              className="text-button danger"
              onClick={() => request("domain", "remove")}
            >
              {t("removeDomain")}
            </button>
          </section>
          <section className="card">
            <h2>{t("ssl")}</h2>
            <div className="status-row">
              <span>{t("status")}</span>
              <span>{status.data?.host?.ssl.status ?? t("unavailable")}</span>
            </div>
            <Field label="dns">
              <code>{status.data?.host?.dns.join(", ") || "—"}</code>
            </Field>
            <Field label="issuer">
              <code>{status.data?.host?.ssl.issuer || "—"}</code>
            </Field>
            <Field label="expires">
              <code>{status.data?.host?.ssl.expires || "—"}</code>
            </Field>
            <div className="form-actions">
              <button
                className="secondary"
                onClick={() => request("diagnostics")}
              >
                {t("checkDns")}
              </button>
              <button onClick={() => request("ssl")}>{t("renewSsl")}</button>
            </div>
          </section>
        </div>
      )}
      {tab === "updates" && (
        <section className="card update-card">
          <div className="update-symbol">
            <RefreshCw size={36} />
          </div>
          <h2>{t("updates")}</h2>
          <div className="release-versions">
            <div>
              <small>{t("version")}</small>
              <strong>{status.data?.version}</strong>
            </div>
            <span>←</span>
            <div>
              <small>{t("latestVersion")}</small>
              <strong>{latest?.latest ?? "—"}</strong>
            </div>
          </div>
          {latest?.status === "no_published_release" && <p>{t("noRelease")}</p>}
          <p>{t("updateHint")}</p>
          <button className="secondary" onClick={() => request("check-update")}>
            {t("checkUpdate")}
          </button>
          <Form
            label="updateNow"
            submit={async (data) => request("update", String(data.get("tag")))}
          >
            <Field label="releaseTag">
              <input
                name="tag"
                dir="ltr"
                pattern="v[0-9]+\.[0-9]+\.[0-9]+"
                placeholder="v0.2.1"
                required
              />
            </Field>
          </Form>
        </section>
      )}
      {tab === "audit" && (
        <section className="card">
          <ErrorNotice error={audit.error} />
          {audit.isPending ? (
            <Loading />
          ) : !audit.data?.length ? (
            <Empty />
          ) : (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>{t("action")}</th>
                    <th>{t("detail")}</th>
                    <th>{t("date")}</th>
                  </tr>
                </thead>
                <tbody>
                  {audit.data.map((row) => (
                    <tr key={row.id}>
                      <td>
                        <code>{row.action}</code>
                      </td>
                      <td>
                        <code>{row.target}</code>
                      </td>
                      <td>{date(row.created_at, user.timezone)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}
      {owner && tab === "content" && <ContentEditor />}
      {owner && tab === "messages" && <MessageCenter currentUser={user} />}
      {owner && tab === "email" && <EmailSettings />}
      {owner && tab === "system" && <IntegrationSettings />}
      {owner && !!operations.data?.length && (
        <section className="card operation-history">
          <h2>{t("operationHistory")}</h2>
          {operations.data.slice(0, 8).map((op) => (
            <div className="operation-row" key={op.id}>
              <span>{t(op.action)}</span>
              <span>{t(op.stage)}</span>
              <Badge value={op.status} />
              {op.status === "failed" && <small>{t("error")}</small>}
            </div>
          ))}
        </section>
      )}
      {operation && (
        <Modal title={operation.action} close={() => setOperation(undefined)}>
          <p className="notice warning">{t("operationWarning")}</p>
          {operation.argument && (
            <code className="operation-argument">{operation.argument}</code>
          )}
          <Form
            label="confirm"
            submit={async (data) => {
              await api("/admin/operations", "POST", {
                ...operation,
                confirmed: true,
                password: data.get("password"),
              });
              setOperation(undefined);
              await cache.invalidateQueries({ queryKey: ["operations"] });
            }}
          >
            <Field label="reenterPassword">
              <input
                name="password"
                type="password"
                required
                autoComplete="current-password"
                dir="ltr"
                autoFocus
              />
            </Field>
          </Form>
        </Modal>
      )}
      {editing && (
        <Modal title="edit" close={() => setEditing(undefined)}>
          <Form
            submit={async (data) => {
              await api("/admin/users/" + editing.id, "PATCH", {
                role: data.get("role"),
                active: data.get("active") === "true",
              });
              setEditing(undefined);
              await cache.invalidateQueries({ queryKey: ["admin-users"] });
            }}
          >
            <p>{editing.username}</p>
            <Field label="role">
              <select name="role" defaultValue={editing.role}>
                {["USER", "ADMIN", "SUPER_ADMIN"].map((role) => (
                  <option value={role} key={role}>
                    {t(role)}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="status">
              <select name="active" defaultValue={String(editing.active)}>
                <option value="true">{t("active")}</option>
                <option value="false">{t("inactive")}</option>
              </select>
            </Field>
          </Form>
        </Modal>
      )}
    </>
  );
}
