import { useState } from "react";
import { ArrowLeft, MessageSquare, ShieldCheck, Zap } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import type { Config, User } from "../api";
import { brand } from "../brand";
import { Field, Form } from "../components";
import { t } from "../i18n";

export default function Auth({ config }: { config?: Config }) {
  const [mode, setMode] = useState<"login" | "register" | "recovery">("login");
  const cache = useQueryClient();
  return (
    <div className="auth-layout">
      <div className="auth-form-side">
        <a className="brand" href="/">
          <img src={brand.mark} alt="" />
          <div>
            <strong>{brand.nameFa}</strong>
            <small>{brand.tagline}</small>
          </div>
        </a>
        <div className="auth-card">
          <p className="eyebrow">{brand.name}</p>
          <h1>{t(mode)}</h1>
          <p>{t(mode === "recovery" ? "recoveryHint" : mode + "Sub")}</p>
          <Form
            key={mode}
            label={mode}
            submit={async (data) => {
              if (mode === "recovery") {
                await api("/auth/reset-password", "POST", {
                  token: data.get("token"),
                  password: data.get("password"),
                });
                setMode("login");
                return;
              }
              if (mode === "register")
                await api("/auth/register", "POST", {
                  username: data.get("username"),
                  email: data.get("email"),
                  password: data.get("password"),
                });
              const user = await api<User>("/auth/login", "POST", {
                username: data.get("username"),
                password: data.get("password"),
              });
              cache.setQueryData(["me"], user);
            }}
          >
            {mode === "recovery" ? (
              <Field label="token">
                <input name="token" required dir="ltr" autoComplete="off" />
              </Field>
            ) : (
              <Field label="username">
                <input
                  name="username"
                  required
                  dir="ltr"
                  autoComplete="username"
                  pattern="[a-zA-Z0-9_]{3,64}"
                />
              </Field>
            )}
            {mode === "register" && (
              <Field label="email">
                <input
                  name="email"
                  type="email"
                  dir="ltr"
                  required
                  autoComplete="email"
                />
              </Field>
            )}
            <Field
              label="password"
              hint={mode !== "login" ? "passwordHint" : undefined}
            >
              <input
                name="password"
                type="password"
                required
                dir="ltr"
                minLength={mode === "login" ? 1 : 12}
                maxLength={256}
                autoComplete={
                  mode === "login" ? "current-password" : "new-password"
                }
              />
            </Field>
          </Form>
          <div className="auth-links">
            {config?.registration_enabled && (
              <button
                className="text-button"
                onClick={() => setMode(mode === "login" ? "register" : "login")}
              >
                {t(mode === "login" ? "noAccount" : "hasAccount")}{" "}
                <b>{t(mode === "login" ? "register" : "login")}</b>
                <ArrowLeft size={16} />
              </button>
            )}
            <button
              className="text-button"
              onClick={() =>
                setMode(mode === "recovery" ? "login" : "recovery")
              }
            >
              {t(mode === "recovery" ? "returnLogin" : "recovery")}
            </button>
          </div>
        </div>
        <small className="auth-footer">
          {brand.name} · {brand.tagline}
        </small>
      </div>
      <aside className="auth-art">
        <div className="auth-art-top">
          FARSTAR <b>NEXA</b>
          <span>01 / COMMUNICATION</span>
        </div>
        <div className="orbit">
          <div className="orbit-center">
            <MessageSquare size={54} />
          </div>
          <span className="orbit-chip chip-one">
            <Zap size={23} />
          </span>
          <span className="orbit-chip chip-two">
            <ShieldCheck size={23} />
          </span>
        </div>
        <h2>{t("welcome")}</h2>
        <p>{t("footer")}</p>
        <div className="auth-art-bottom">
          <span>A FARSTAR PRODUCT</span>
          <span>● NEXA</span>
        </div>
      </aside>
    </div>
  );
}
