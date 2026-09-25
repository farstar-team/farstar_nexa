import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import type { Activity, Execution, User } from "../api";
import { Badge, Empty, ErrorNotice, Loading, PageTitle } from "../components";
import { date, t } from "../i18n";
import { useState } from "react";
import { Modal } from "../components";
import ExecutionDetail from "./ExecutionDetail";

export default function History({
  page,
  user,
}: {
  page: "activity" | "executions";
  user: User;
}) {
  const [detail, setDetail] = useState<string>();
  const [offset, setOffset] = useState(0);
  const query = useQuery({
    queryKey: [page, offset],
    queryFn: () =>
      api<(Activity & Execution)[]>("/" + page + "?offset=" + offset),
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
                  {page === "executions" && (
                    <>
                      <th>محصول / مدیا</th>
                      <th>محرک و اقدامات</th>
                    </>
                  )}
                  <th>{t("status")}</th>
                  <th>{t("date")}</th>
                </tr>
              </thead>
              <tbody>
                {query.data.map((row) => (
                  <tr key={row.id}>
                    <td>
                      <code>
                        {row.action ?? row.automation_name ?? row.automation_id}
                      </code>
                      {page === "executions" && (
                        <>
                          <small>
                            {t(row.trigger)} {row.dry_run ? "· Dry Run" : ""}
                          </small>
                          <button
                            className="secondary"
                            onClick={() => setDetail(row.id)}
                          >
                            جزئیات اجرا
                          </button>
                        </>
                      )}
                    </td>
                    {page === "executions" && (
                      <>
                        <td>
                          {row.product_name ?? "—"}
                          <small>{row.media_caption ?? ""}</small>
                        </td>
                        <td>
                          {t(row.trigger)}
                          <small>
                            {row.actions?.map((action) => t(action)).join("، ")}
                          </small>
                        </td>
                      </>
                    )}
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
      {page === "executions" && (
        <div className="pagination">
          <button
            disabled={!offset}
            onClick={() => setOffset(Math.max(0, offset - 100))}
          >
            قبلی
          </button>
          <button
            disabled={(query.data?.length ?? 0) < 100}
            onClick={() => setOffset(offset + 100)}
          >
            بعدی
          </button>
        </div>
      )}
      {detail && (
        <Modal title="جزئیات اجرا" close={() => setDetail(undefined)}>
          <ExecutionDetail id={detail} />
        </Modal>
      )}
    </>
  );
}
