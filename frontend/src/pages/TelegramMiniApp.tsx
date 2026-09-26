import { useEffect, useState } from "react";
import { ArrowUpLeft, BarChart3, Bot, ExternalLink, Workflow } from "lucide-react";
import { api } from "../api";
import { brand } from "../brand";

type Stats = { counts: Record<string, number> };
type WebApp = { initData: string; ready: () => void; expand: () => void };
type TelegramWindow = Window & { Telegram?: { WebApp?: WebApp } };

export default function TelegramMiniApp() {
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [stats, setStats] = useState<Stats>();
  useEffect(() => {
    (async () => {
      try {
        const existing = (window as TelegramWindow).Telegram?.WebApp;
        const webApp = existing ?? await new Promise<WebApp | undefined>((resolve) => {
          const script = document.createElement("script");
          script.src = "https://telegram.org/js/telegram-web-app.js";
          script.onload = () => resolve((window as TelegramWindow).Telegram?.WebApp);
          script.onerror = () => resolve(undefined);
          document.head.appendChild(script);
        });
        webApp?.ready();
        webApp?.expand();
        if (webApp?.initData) await api("/telegram/webapp-auth", "POST", { init_data: webApp.initData });
        setStats(await api<Stats>("/dashboard"));
        setState("ready");
      } catch {
        setState("error");
      }
    })();
  }, []);
  return <main className="mini-app"><header><img src={brand.mark} alt="" /><div><strong>فاراستار نکسا</strong><small>Telegram Mini App</small></div></header>{state === "loading" && <p>در حال آماده‌سازی…</p>}{state === "error" && <p className="notice error">برای استفاده، ابتدا تلگرام را از پنل به حساب خود وصل کنید.</p>}{state === "ready" && <><section className="mini-hero"><Bot size={25} /><div><b>سلام، آماده‌ایم.</b><small>مدیریت فروش اجتماعی از داخل تلگرام</small></div></section><div className="mini-stats"><div><BarChart3 size={19} /><b>{stats?.counts.messages ?? 0}</b><small>پیام‌ها</small></div><div><Workflow size={19} /><b>{stats?.counts.automations ?? 0}</b><small>اتوماسیون‌ها</small></div></div><a className="button" href="/"><ExternalLink size={16} /> باز کردن پنل کامل <ArrowUpLeft size={15} /></a></>}</main>;
}
