import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  ArrowUpLeft,
  Bell,
  ChevronLeft,
  FlaskConical,
  House,
  Inbox as InboxIcon,
  LogOut,
  Menu,
  Moon,
  Plug,
  Send,
  Settings as SettingsIcon,
  Shield,
  Sun,
  Workflow,
  X,
  Zap,
} from "lucide-react";
import { api, ApiError } from "./api";
import type { Config, User } from "./api";
import { brand } from "./brand";
import { ErrorNotice, Loading } from "./components";
import { t } from "./i18n";
import Auth from "./pages/Auth";
import Dashboard from "./pages/Dashboard";
import Integrations from "./pages/Integrations";
import Automations from "./pages/Automations";
import Inbox from "./pages/Inbox";
import Telegram from "./pages/Telegram";
import History from "./pages/History";
import Settings from "./pages/Settings";
import Admin from "./pages/Admin";
import Products from "./pages/Products";
import Media from "./pages/Media";
import Leads from "./pages/Leads";
import Landing from "./pages/Landing";
import { Package, Images, Users } from "lucide-react";

const navigation = [
  { key: "dashboard", icon: House },
  { key: "inbox", icon: InboxIcon },
  { key: "automations", icon: Zap },
  { key: "products", icon: Package },
  { key: "media", icon: Images },
  { key: "leads", icon: Users },
  { key: "integrations", icon: Plug },
  { key: "telegram", icon: Send },
  { key: "executions", icon: Workflow },
  { key: "activity", icon: Activity },
  { key: "settings", icon: SettingsIcon },
];
export default function App() {
  const cache = useQueryClient();
  const [page, setPage] = useState(location.hash.slice(1) || "dashboard");
  const [mobile, setMobile] = useState(false);
  const [dark, setDark] = useState(
    localStorage.getItem("nexa-theme") === "dark",
  );
  const [logoutError, setLogoutError] = useState<unknown>();
  const [showAuth, setShowAuth] = useState(false);
  const me = useQuery({
    queryKey: ["me"],
    queryFn: () => api<User>("/auth/me"),
  });
  const config = useQuery({
    queryKey: ["config"],
    queryFn: () => api<Config>("/config"),
  });
  useEffect(() => {
    document.documentElement.dataset.theme = dark ? "dark" : "light";
    localStorage.setItem("nexa-theme", dark ? "dark" : "light");
  }, [dark]);
  useEffect(() => {
    const change = () => setPage(location.hash.slice(1) || "dashboard");
    window.addEventListener("hashchange", change);
    return () => window.removeEventListener("hashchange", change);
  }, []);
  const navigate = (next: string) => {
    setPage(next);
    location.hash = next;
    setMobile(false);
  };
  if (me.isPending || config.isPending)
    return (
      <div className="initial-loading">
        <img src={brand.mark} alt={brand.name} />
        <Loading />
      </div>
    );
  if (!me.data) {
    if (me.error instanceof ApiError && me.error.status === 401)
      return showAuth ? <Auth config={config.data} /> : <Landing onStart={() => setShowAuth(true)} />;
    return (
      <div className="initial-loading">
        <ErrorNotice error={me.error} />
        <button onClick={() => me.refetch()}>{t("retry")}</button>
      </div>
    );
  }
  if (!config.data) return <ErrorNotice error={config.error} />;
  const user = me.data;
  const isAdmin = ["ADMIN", "SUPER_ADMIN"].includes(user.role);
  let content;
  switch (page) {
    case "products":
      content = <Products />;
      break;
    case "media":
      content = <Media />;
      break;
    case "leads":
      content = <Leads />;
      break;
    case "integrations":
      content = <Integrations config={config.data} />;
      break;
    case "automations":
      content = <Automations config={config.data} />;
      break;
    case "inbox":
      content = <Inbox user={user} />;
      break;
    case "telegram":
      content = <Telegram />;
      break;
    case "activity":
    case "executions":
      content = <History key={page} page={page} user={user} />;
      break;
    case "settings":
      content = <Settings user={user} />;
      break;
    case "admin":
      content = isAdmin ? (
        <Admin user={user} />
      ) : (
        <Dashboard navigate={navigate} />
      );
      break;
    default:
      content = <Dashboard navigate={navigate} />;
  }
  return (
    <div className="app-shell">
      {mobile && (
        <button
          className="sidebar-scrim"
          aria-label={t("close")}
          onClick={() => setMobile(false)}
        />
      )}
      <aside className={`sidebar ${mobile ? "mobile-open" : ""}`}>
        <a
          className="brand"
          href="#dashboard"
          onClick={() => navigate("dashboard")}
        >
          <img src={brand.mark} alt="" />
          <div>
            <strong>{brand.nameFa}</strong>
            <small>FARSTAR NEXA</small>
          </div>
        </a>
        <button
          className="mobile-close icon-button"
          onClick={() => setMobile(false)}
          aria-label={t("close")}
        >
          <X size={20} />
        </button>
        <div className="workspace-switch">
          <div className="workspace-avatar">
            {user.username.slice(0, 1).toUpperCase()}
          </div>
          <div>
            <strong>{user.username}</strong>
            <small>{t("workspace")}</small>
          </div>
          <ChevronLeft size={16} />
        </div>
        <p className="nav-label">{t("overview")}</p>
        <nav aria-label={t("navigation")}>
          {navigation.map(({ key, icon: Icon }) => (
            <button
              className={`nav-item ${page === key ? "selected" : ""}`}
              key={key}
              onClick={() => navigate(key)}
            >
              <Icon size={19} />
              <span>{t(key)}</span>
              {page === key && <span className="nav-dot" />}
            </button>
          ))}
        </nav>
        {isAdmin && (
          <div className="admin-nav">
            <button
              className={`nav-item ${page === "admin" ? "selected" : ""}`}
              onClick={() => navigate("admin")}
            >
              <Shield size={19} />
              <span>{t("admin")}</span>
            </button>
          </div>
        )}
        <div className="sidebar-bottom">
          <a href={brand.github} target="_blank" rel="noreferrer">
            {brand.tagline}
            <ArrowUpLeft size={16} />
          </a>
          <small>v{config.data.version}</small>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumb">
            <button
              className="mobile-menu icon-button"
              aria-label={t("openMenu")}
              onClick={() => setMobile(true)}
            >
              <Menu size={22} />
            </button>
            <span>{brand.short}</span>
            <ChevronLeft size={14} />
            <b>{t(page)}</b>
          </div>
          <div className="topbar-actions">
            {config.data.mock_mode && (
              <span className="mock-indicator">
                <FlaskConical size={15} />
                {t("mock")}
              </span>
            )}
            <button
              className="icon-button"
              aria-label={t(dark ? "light" : "dark")}
              onClick={() => setDark(!dark)}
            >
              {dark ? <Sun size={19} /> : <Moon size={19} />}
            </button>
            <button
              className="icon-button"
              aria-label={t("activity")}
              onClick={() => navigate("activity")}
            >
              <Bell size={19} />
            </button>
            <span className="topbar-divider" />
            <button
              className="profile-button"
              onClick={() => navigate("settings")}
            >
              <span className="avatar small-avatar">
                {user.username.slice(0, 1).toUpperCase()}
              </span>
              <b>{user.username}</b>
            </button>
            <button
              className="logout-button profile-action"
              aria-label={t("logout")}
              onClick={async () => {
                try {
                  await api("/auth/logout", "POST");
                  cache.clear();
                  window.location.assign("/");
                } catch (e) {
                  setLogoutError(e);
                }
              }}
            >
              <LogOut size={18} />
              <span>{t("logout")}</span>
            </button>
          </div>
        </header>
        <main>
          <ErrorNotice error={logoutError} />
          {new URLSearchParams(location.search).get("connection") ===
            "failed" && (
            <div className="notice error">{t("connectionFailed")}</div>
          )}
          {content}
        </main>
        <footer className="main-footer">
          <span>{brand.nameFa}</span>
          <span>{brand.tagline}</span>
        </footer>
      </div>
    </div>
  );
}
