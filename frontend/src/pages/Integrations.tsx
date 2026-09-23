import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Camera, Plus, Unplug } from "lucide-react";
import { api } from "../api";
import type { Account, Config } from "../api";
import {
  Badge,
  Confirm,
  Empty,
  ErrorNotice,
  Field,
  Form,
  Loading,
  Modal,
  PageTitle,
} from "../components";
import { t } from "../i18n";

export default function Integrations({ config }: { config: Config }) {
  const cache = useQueryClient();
  const query = useQuery({
    queryKey: ["accounts"],
    queryFn: () => api<Account[]>("/accounts"),
  });
  const [adding, setAdding] = useState(false);
  const [disconnect, setDisconnect] = useState<string>();
  const [error, setError] = useState<unknown>();
  return (
    <>
      <PageTitle title="integrations" subtitle="integrationsSub" />
      <div className="provider-card">
        <div className="provider-icon">
          <Camera size={32} />
        </div>
        <div>
          <h2>{t("instagram")}</h2>
          <p>{t("instagramDescription")}</p>
          <small>{t("prerequisites")}</small>
        </div>
        <button
          className="secondary"
          onClick={async () => {
            try {
              const data = await api<{ url: string }>(
                "/instagram/authorize",
                "POST",
              );
              window.location.assign(data.url);
            } catch (e) {
              setError(e);
            }
          }}
        >
          {t("connectInstagram")}
        </button>
      </div>
      <ErrorNotice error={error ?? query.error} />
      <div className="section-heading">
        <h2>{t("connectedAccounts")}</h2>
        {config.mock_mode && (
          <button onClick={() => setAdding(true)}>
            <Plus size={18} />
            {t("newAccount")}
          </button>
        )}
      </div>
      {query.isPending ? (
        <Loading />
      ) : !query.data?.length ? (
        <div className="card">
          <Empty />
        </div>
      ) : (
        <div className="account-grid">
          {query.data.map((account) => (
            <div className="card account-card" key={account.id}>
              <div className="account-top">
                <div className="avatar">
                  <Camera size={23} />
                </div>
                <Badge value={account.active ? "active" : "inactive"} />
              </div>
              <h3>{account.name}</h3>
              <small>
                {t(
                  account.provider === "instagram_mock"
                    ? "mockConnection"
                    : "officialConnection",
                )}
              </small>
              <div className="card-divider" />
              <button
                className="text-button danger"
                disabled={!account.active}
                onClick={() => setDisconnect(account.id)}
              >
                <Unplug size={16} />
                {t("disconnect")}
              </button>
            </div>
          ))}
        </div>
      )}
      {adding && (
        <Modal title="newAccount" close={() => setAdding(false)}>
          <Form
            label="create"
            submit={async (data) => {
              await api("/accounts/mock", "POST", { name: data.get("name") });
              await cache.invalidateQueries({ queryKey: ["accounts"] });
              setAdding(false);
            }}
          >
            <Field label="accountName">
              <input name="name" required maxLength={120} autoFocus />
            </Field>
            <p className="notice">{t("mockDescription")}</p>
          </Form>
        </Modal>
      )}
      {disconnect && (
        <Confirm
          close={() => setDisconnect(undefined)}
          action={async () => {
            await api("/accounts/" + disconnect, "DELETE");
            await cache.invalidateQueries({ queryKey: ["accounts"] });
          }}
        />
      )}
    </>
  );
}
