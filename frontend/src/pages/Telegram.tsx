import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowUpLeft, Send } from "lucide-react";
import { api } from "../api";
import { Badge, Confirm, ErrorNotice, Loading, PageTitle } from "../components";
import { t } from "../i18n";

export default function Telegram() {
  const cache = useQueryClient();
  const query = useQuery({
    queryKey: ["telegram"],
    queryFn: () =>
      api<{ linked: boolean; configured: boolean; username: string }>(
        "/telegram",
      ),
    refetchInterval: 5000,
  });
  const [url, setUrl] = useState<string>();
  const [error, setError] = useState<unknown>();
  const [unlink, setUnlink] = useState(false);
  return (
    <>
      <PageTitle title="telegram" subtitle="telegramSub" />
      <ErrorNotice error={query.error ?? error} />
      {query.isPending ? (
        <Loading />
      ) : (
        <div className="card telegram-card">
          <div className="telegram-symbol">
            <Send size={44} />
          </div>
          <Badge value={query.data?.linked ? "active" : "inactive"} />
          <h2>{t(query.data?.linked ? "linked" : "notLinked")}</h2>
          <p>{t("telegramFeatures")}</p>
          {!query.data?.configured ? (
            <p className="notice">{t("telegramNotConfigured")}</p>
          ) : query.data.linked ? (
            <button
              className="secondary danger"
              onClick={() => setUnlink(true)}
            >
              {t("unlinkTelegram")}
            </button>
          ) : (
            <button
              onClick={async () => {
                try {
                  const result = await api<{ url: string }>(
                    "/telegram/link",
                    "POST",
                  );
                  setUrl(result.url);
                } catch (e) {
                  setError(e);
                }
              }}
            >
              {t("linkTelegram")}
              <ArrowUpLeft size={18} />
            </button>
          )}
          {url && !query.data?.linked && (
            <div className="link-result">
              <p>{t("linkHint")}</p>
              <a className="button" href={url} target="_blank" rel="noreferrer">
                {t("openBot")}
              </a>
            </div>
          )}
        </div>
      )}
      {unlink && (
        <Confirm
          close={() => setUnlink(false)}
          action={async () => {
            await api("/telegram/link", "DELETE");
            setUrl(undefined);
            await cache.invalidateQueries({ queryKey: ["telegram"] });
          }}
        />
      )}
    </>
  );
}
