import { fa } from "./locales/fa";
import { en } from "./locales/en";
import { commerceFa } from "./locales/commerce";
export const t = (key: string, locale: "fa" | "en" = "fa") =>
  (locale === "en" ? en[key] : fa[key]) ?? commerceFa[key] ?? fa[key] ?? key;
export const date = (value: string, timezone = "Asia/Tehran") =>
  new Intl.DateTimeFormat("fa-IR", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: timezone,
  }).format(new Date(value));
export const number = (value: number) =>
  new Intl.NumberFormat("fa-IR").format(value);
