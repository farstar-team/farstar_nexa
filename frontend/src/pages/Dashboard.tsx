import { useQuery } from "@tanstack/react-query";
import {
  ArrowUpLeft,
  Check,
  Circle,
  MessageSquare,
  Plug,
  Workflow,
  Zap,
} from "lucide-react";
import { api } from "../api";
import { ErrorNotice, Loading, PageTitle } from "../components";
import { number, t } from "../i18n";

type Data = {
  counts: Record<string, number>;
  activity: { date: string; count: number }[];
};
export default function Dashboard({
  navigate,
}: {
  navigate: (page: string) => void;
}) {
  const query = useQuery({
    queryKey: ["dashboard"],
    queryFn: () => api<Data>("/dashboard"),
    refetchInterval: 10000,
  });
  const stats = [
    { key: "accounts", icon: Plug, label: "connectedAccounts" },
    { key: "messages", icon: MessageSquare, label: "messages" },
    { key: "automations", icon: Zap, label: "automations" },
    { key: "executions", icon: Workflow, label: "executions" },
  ];
  return (
    <>
      <PageTitle title="dashboard" subtitle="dashboardSub">
        <button onClick={() => navigate("automations")}>
          <Zap size={17} />
          {t("newAutomation")}
        </button>
      </PageTitle>
      <ErrorNotice error={query.error} />
      {query.isPending ? (
        <Loading />
      ) : (
        query.data && (
          <>
            <div className="stats-grid">
              {stats.map(({ key, icon: Icon, label }) => (
                <div className="stat-card" key={key}>
                  <div className="stat-top">
                    <span>{t(label)}</span>
                    <Icon size={20} />
                  </div>
                  <strong>{number(query.data.counts[key])}</strong>
                  <small>{t("workspace")}</small>
                </div>
              ))}
            </div>
            <div className="dashboard-grid">
              <section className="card chart-card">
                <div className="section-heading">
                  <div>
                    <h2>{t("weekActivity")}</h2>
                    <p>{t("realData")}</p>
                  </div>
                  <span className="chart-legend">
                    <i />
                    {t("messages")}
                  </span>
                </div>
                <div className="chart" aria-label={t("weekActivity")}>
                  {query.data.activity.map((day) => (
                    <div className="chart-column" key={day.date}>
                      <div className="chart-track">
                        <div
                          className="chart-fill"
                          style={{
                            height: `${Math.max(2, (day.count / Math.max(1, ...query.data.activity.map((d) => d.count))) * 100)}%`,
                          }}
                        >
                          <span>{number(day.count)}</span>
                        </div>
                      </div>
                      <small>
                        {new Intl.DateTimeFormat("fa-IR", {
                          weekday: "short",
                        }).format(new Date(day.date))}
                      </small>
                    </div>
                  ))}
                </div>
              </section>
              <section className="getting-started">
                <span className="eyebrow">NEXA / GET STARTED</span>
                <h2>{t("quickStart")}</h2>
                <p>{t("quickStartSub")}</p>
                {["integrations", "automations", "inbox"].map((page, i) => {
                  const done =
                    query.data.counts[
                      ["accounts", "automations", "messages"][i]
                    ] > 0;
                  return (
                    <button
                      className="step"
                      key={page}
                      onClick={() => navigate(page)}
                    >
                      <span className={`step-number ${done ? "done" : ""}`}>
                        {done ? <Check size={16} /> : number(i + 1)}
                      </span>
                      <span>
                        <b>{t(`step${i + 1}`)}</b>
                        <small>{t(`step${i + 1}Sub`)}</small>
                      </span>
                      <ArrowUpLeft size={17} />
                    </button>
                  );
                })}
              </section>
            </div>
            <div className="bottom-banner">
              <Circle size={12} />
              <span>{t("welcome")}</span>
              <span className="ltr">Farstar Nexa</span>
            </div>
          </>
        )
      )}
    </>
  );
}
