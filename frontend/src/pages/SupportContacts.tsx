import { ArrowLeft, AtSign, Camera, Mail, Send, Ticket } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import { brand } from "../brand";
import { ErrorNotice, Loading, PageTitle } from "../components";
import { t } from "../i18n";

const external = (value: string | undefined) => Boolean(value && /^https?:\/\//i.test(value));

export default function SupportContacts() {
  const content = useQuery({ queryKey: ["public-content"], queryFn: () => api<Record<string, string>>("/content") });
  const values = content.data ?? {};
  const links = [
    { key: "support.telegram", title: "تلگرام پشتیبانی", icon: Send, value: values["support.telegram"] },
    { key: "support.instagram", title: "اینستاگرام پشتیبانی", icon: Camera, value: values["support.instagram"] },
    { key: "support.channel", title: "کانال اطلاع‌رسانی", icon: AtSign, value: values["support.channel"] },
    { key: "support.email", title: "ایمیل پشتیبانی", icon: Mail, value: values["support.email"] },
  ];
  return <>
    <PageTitle title="support" subtitle="supportSub" />
    <ErrorNotice error={content.error} />
    {content.isPending ? <Loading /> : <>
    <section className="support-hero card"><div className="support-hero-mark"><img src={brand.mark} alt="" /></div><div><span className="eyebrow">پشتیبانی Farstar Nexa</span><h2>{values["support.title"] || "کنار شما هستیم"}</h2><p>{values["support.subtitle"] || "اگر سؤال یا مشکلی دارید، از راه ارتباطی دلخواه با ما در تماس باشید."}</p><small>{values["support.hours"] || "ساعت پاسخ‌گویی توسط تیم پشتیبانی اعلام می‌شود."}</small></div></section>
      <section className="support-contact-grid">{links.map(({ key, title, icon: Icon, value }) => <article className={`card support-contact-card ${value ? "configured" : "unconfigured"}`} key={key}><span className="support-contact-icon"><Icon size={21} /></span><div><h3>{title}</h3>{value && external(value) ? <a href={value} target="_blank" rel="noreferrer" dir="ltr">{value.replace(/^https?:\/\//i, "")}</a> : <p>{value || "به‌زودی اعلام می‌شود"}</p>}</div></article>)}</section>
      <section className="support-ticket-cta card"><div><span className="support-contact-icon"><Ticket size={20} /></span><div><h2>{t("supportTicketsPage")}</h2><p>{t("supportTicketsHint")}</p></div></div><a className="button" href="#support-tickets">ورود به تیکت‌ها <ArrowLeft size={17} /></a></section>
    </>}
  </>;
}
