import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { FlaskConical, Pencil, Plus, Zap } from "lucide-react";
import { api } from "../api";
import type { Account, Config, Rule } from "../api";
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
import { number, t } from "../i18n";

export default function Automations({ config }: { config: Config }) {
  const cache = useQueryClient();
  const accounts = useQuery({
    queryKey: ["accounts"],
    queryFn: () => api<Account[]>("/accounts"),
  });
  const rules = useQuery({
    queryKey: ["automations"],
    queryFn: () => api<Rule[]>("/automations"),
  });
  const [edit, setEdit] = useState<Rule | null | undefined>();
  const [test, setTest] = useState(false);
  const [toggle, setToggle] = useState<Rule>();
  const active = accounts.data?.filter((a) => a.active) ?? [];
  return (
    <>
      <PageTitle title="automations" subtitle="automationsSub">
        <button
          className="secondary"
          disabled={!active.some((a) => a.provider === "instagram_mock")}
          onClick={() => setTest(true)}
          hidden={!config.mock_mode}
        >
          <FlaskConical size={17} />
          {t("testMessage")}
        </button>
        <button disabled={!active.length} onClick={() => setEdit(null)}>
          <Plus size={17} />
          {t("newAutomation")}
        </button>
      </PageTitle>
      <ErrorNotice error={rules.error ?? accounts.error} />
      {rules.isPending ? (
        <Loading />
      ) : !rules.data?.length ? (
        <div className="card">
          <Empty title="rulesEmpty" subtitle="ruleIntro">
            <button disabled={!active.length} onClick={() => setEdit(null)}>
              {t("newAutomation")}
            </button>
          </Empty>
        </div>
      ) : (
        <div className="rules-list">
          {rules.data.map((rule) => (
            <article className="card rule-card" key={rule.id}>
              <div className="rule-icon">
                <Zap size={22} />
              </div>
              <div className="rule-body">
                <div className="rule-title">
                  <h3>{rule.name}</h3>
                  <Badge value={rule.enabled ? "active" : "inactive"} />
                </div>
                <p>
                  {accounts.data?.find((a) => a.id === rule.account_id)?.name}{" "}
                  <span>·</span> {t(rule.match_mode)} <span>·</span>{" "}
                  {t("priority")} {number(rule.priority)}
                </p>
                <div className="keyword-list">
                  {rule.keywords.map((k) => (
                    <span key={k}>{k}</span>
                  ))}
                </div>
                <blockquote>{rule.response}</blockquote>
              </div>
              <div className="rule-actions">
                <button
                  className="icon-button"
                  aria-label={t("edit")}
                  onClick={() => setEdit(rule)}
                >
                  <Pencil size={17} />
                </button>
                <button className="secondary" onClick={() => setToggle(rule)}>
                  {t(rule.enabled ? "disable" : "enable")}
                </button>
              </div>
            </article>
          ))}
        </div>
      )}
      {edit !== undefined && (
        <Modal
          title={edit ? "edit" : "newAutomation"}
          close={() => setEdit(undefined)}
        >
          <Form
            label="save"
            submit={async (data) => {
              const payload = {
                name: data.get("name"),
                account_id: data.get("account_id"),
                keywords: String(data.get("keywords"))
                  .split(/[,،]/)
                  .map((k) => k.trim())
                  .filter(Boolean),
                match_mode: data.get("match_mode"),
                response: data.get("response"),
                priority: Number(data.get("priority")),
                cooldown_seconds: Number(data.get("cooldown")),
                enabled: edit?.enabled ?? true,
              };
              await api(
                edit ? "/automations/" + edit.id : "/automations",
                edit ? "PUT" : "POST",
                payload,
              );
              await cache.invalidateQueries({ queryKey: ["automations"] });
              setEdit(undefined);
            }}
          >
            <Field label="name">
              <input
                name="name"
                defaultValue={edit?.name}
                required
                maxLength={120}
                autoFocus
              />
            </Field>
            <Field label="account">
              <select
                name="account_id"
                defaultValue={edit?.account_id}
                required
              >
                {active.map((a) => (
                  <option value={a.id} key={a.id}>
                    {a.name}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="keywords" hint="keywordsHint">
              <input
                name="keywords"
                defaultValue={edit?.keywords.join("، ")}
                required
              />
            </Field>
            <Field label="matchMode">
              <select
                name="match_mode"
                defaultValue={edit?.match_mode ?? "contains"}
              >
                {["contains", "exact", "starts_with"].map((mode) => (
                  <option value={mode} key={mode}>
                    {t(mode)}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="response">
              <textarea
                name="response"
                required
                maxLength={1000}
                rows={4}
                defaultValue={edit?.response}
              />
            </Field>
            <div className="form-grid">
              <Field label="priority">
                <input
                  type="number"
                  name="priority"
                  min={0}
                  max={1000}
                  defaultValue={edit?.priority ?? 0}
                />
              </Field>
              <Field label="cooldown">
                <input
                  type="number"
                  name="cooldown"
                  min={2}
                  max={86400}
                  defaultValue={edit?.cooldown_seconds ?? 60}
                />
              </Field>
            </div>
          </Form>
        </Modal>
      )}
      {test && (
        <Modal title="testMessage" close={() => setTest(false)}>
          <Form
            label="sendTest"
            submit={async (data) => {
              await api("/messages/simulate", "POST", {
                account_id: data.get("account_id"),
                sender: data.get("sender"),
                text: data.get("text"),
                event_id: crypto.randomUUID(),
              });
              await cache.invalidateQueries({ queryKey: ["dashboard"] });
            }}
          >
            <p className="notice">{t("testHint")}</p>
            <Field label="account">
              <select name="account_id">
                {active
                  .filter((a) => a.provider === "instagram_mock")
                  .map((a) => (
                    <option value={a.id} key={a.id}>
                      {a.name}
                    </option>
                  ))}
              </select>
            </Field>
            <Field label="sender">
              <input
                name="sender"
                dir="ltr"
                defaultValue="test_user"
                required
                maxLength={128}
              />
            </Field>
            <Field label="message">
              <textarea name="text" rows={4} required maxLength={2000} />
            </Field>
          </Form>
        </Modal>
      )}
      {toggle && (
        <Confirm
          close={() => setToggle(undefined)}
          action={async () => {
            await api("/automations/" + toggle.id, "PATCH", {
              enabled: !toggle.enabled,
            });
            await cache.invalidateQueries({ queryKey: ["automations"] });
          }}
        />
      )}
    </>
  );
}
