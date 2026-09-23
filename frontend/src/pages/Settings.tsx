import { useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import type { User } from "../api";
import { Field, Form, PageTitle } from "../components";
import { t } from "../i18n";

export default function Settings({ user }: { user: User }) {
  const cache = useQueryClient();
  return (
    <>
      <PageTitle title="settings" subtitle="settingsSub" />
      <div className="settings-grid">
        <section className="card">
          <h2>{t("profile")}</h2>
          <Form
            submit={async (data) => {
              await api("/auth/profile", "PATCH", {
                email: data.get("email"),
                timezone: data.get("timezone"),
              });
              await cache.invalidateQueries({ queryKey: ["me"] });
            }}
          >
            <Field label="username">
              <input value={user.username} disabled dir="ltr" />
            </Field>
            <Field label="email">
              <input
                name="email"
                type="email"
                defaultValue={user.email}
                required
                dir="ltr"
              />
            </Field>
            <Field label="timezone">
              <select name="timezone" defaultValue={user.timezone}>
                {[
                  "Asia/Tehran",
                  "UTC",
                  "Europe/London",
                  "Europe/Berlin",
                  "America/New_York",
                  "Asia/Dubai",
                ].map((zone) => (
                  <option key={zone} value={zone}>
                    {zone}
                  </option>
                ))}
              </select>
            </Field>
          </Form>
        </section>
        <section className="card">
          <h2>{t("changePassword")}</h2>
          <Form
            submit={async (data) => {
              await api("/auth/password", "POST", {
                current_password: data.get("current"),
                new_password: data.get("password"),
              });
              cache.clear();
              window.location.reload();
            }}
          >
            <Field label="currentPassword">
              <input
                name="current"
                type="password"
                required
                autoComplete="current-password"
                dir="ltr"
              />
            </Field>
            <Field label="newPassword" hint="passwordHint">
              <input
                name="password"
                type="password"
                required
                minLength={12}
                maxLength={256}
                autoComplete="new-password"
                dir="ltr"
              />
            </Field>
            <p className="notice">{t("passwordChanged")}</p>
          </Form>
        </section>
      </div>
    </>
  );
}
