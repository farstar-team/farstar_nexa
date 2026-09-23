import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import type { Activity, Execution, User } from "../api";
import { Badge, Empty, ErrorNotice, Loading, PageTitle } from "../components";
import { date, t } from "../i18n";

export default function History({
  page,
  user,
}: {
  page: "activity" | "executions";
  user: User;
}) {
  const query = useQuery({
    queryKey: [page],
    queryFn: () => api<(Activity & Execution)[]>("/" + page),
    refetchInterval: 5000,
  });
  return (
    <>
      <PageTitle title={page} subtitle={page + "Sub"} />
      <ErrorNotice error={query.error} />
      <div className="card">
        {query.isPending ? (
          <Loading />
        ) : !query.data?.length ? (
          <Empty />
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>{t("action")}</th>
                  <th>{t("status")}</th>
                  <th>{t("date")}</th>
                </tr>
              </thead>
              <tbody>
                {query.data.map((row) => (
                  <tr key={row.id}>
                    <td>
                      <code>{row.action ?? row.automation_id}</code>
                    </td>
                    <td>
                      {row.status ? (
                        <Badge value={row.status} />
                      ) : (
                        <span>—</span>
                      )}
                    </td>
                    <td>{date(row.created_at, user.timezone)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}
