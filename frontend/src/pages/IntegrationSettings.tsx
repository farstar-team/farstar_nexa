import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import { Badge, ErrorNotice, Field, Form } from "../components";
import { t } from "../i18n";

const names = [
  "meta_app_id",
  "meta_app_secret",
  "meta_verify_token",
  "telegram_bot_token",
  "telegram_bot_username",
  "telegram_webhook_secret",
  "telegram_channel_username",
];
export default function IntegrationSettings() {
  const query = useQuery({
    queryKey: ["integration-settings"],
    queryFn: () =>
      api<
        Record<string, boolean> & {
          public_urls: Record<string, string>;
        }
      >("/admin/integrations"),
  });
  return (
    <section className="card operation-history">
      <h2>{t("config")}</h2>
      <p>{t("integrationConfigHint")}</p>
      <ErrorNotice error={query.error} />
      <h3>{t("integrationUrls")}</h3>
      <p>{t("integrationUrlsHint")}</p>
      <div className="form-grid">
        {Object.entries(query.data?.public_urls ?? {}).map(([key, value]) => (
          <Field label={key} key={key}>
            <input
              value={value}
              readOnly
              dir="ltr"
              onFocus={(event) => event.currentTarget.select()}
            />
          </Field>
        ))}
      </div>
      <div className="card-divider" />
      <Form
        submit={async (data) => {
          const values = Object.fromEntries(
            names
              .map((key) => [key, String(data.get(key))])
              .filter(([, value]) => value),
          );
          await api("/admin/integrations", "PUT", {
            values,
            password: data.get("password"),
          });
          await query.refetch();
        }}
      >
        <div className="form-grid">
          {names.map((key) => (
            <Field label={key} key={key}>
              <div className="setting-label">
                <Badge value={query.data?.[key] ? "active" : "inactive"} />
              </div>
              <input
                name={key}
                type={
                  key.endsWith("username") || key.endsWith("_id") || key === "smtp_port" || key === "smtp_from" || key === "smtp_security"
                    ? "text"
                    : "password"
                }
                dir="ltr"
                maxLength={1024}
                autoComplete="off"
              />
            </Field>
          ))}
        </div>
        <Field label="reenterPassword">
          <input
            name="password"
            type="password"
            required
            dir="ltr"
            autoComplete="current-password"
          />
        </Field>
      </Form>
      <div className="card-divider" />
      <Form
        label="configureTelegramWebhook"
        submit={async (data) => {
          await api("/admin/telegram-webhook", "POST", {
            values: {},
            password: data.get("password"),
          });
        }}
      >
        <Field label="reenterPassword">
          <input
            name="password"
            type="password"
            required
            dir="ltr"
            autoComplete="current-password"
          />
        </Field>
      </Form>
    </section>
  );
}
