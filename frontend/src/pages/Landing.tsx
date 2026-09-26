import { ArrowLeft, CircleDollarSign, MessageCircle, ShieldCheck, Sparkles, Workflow } from "lucide-react";
import { brand } from "../brand";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api";

export default function Landing({ onStart }: { onStart: () => void }) {
  const content = useQuery({ queryKey: ["public-content"], queryFn: () => api<Record<string, string>>("/content") });
  const text = (key: string, fallback: string) => content.data?.[key] || fallback;
  return (
    <main className="landing-page" dir="rtl">
      <header className="landing-nav">
        <a className="brand" href="/">
          <img src={brand.mark} alt="" />
          <div><strong>{brand.nameFa}</strong><small>FARSTAR NEXA</small></div>
        </a>
        <div className="landing-nav-actions"><a className="text-button" href="/">راهنمای استفاده</a><button className="secondary" onClick={onStart}>ورود به پنل</button></div>
      </header>
      <section className="landing-hero">
        <div className="landing-copy">
          <span className="landing-kicker"><Sparkles size={16} /> {text("landing.kicker", "فروش اجتماعی هوشمند")}</span>
          <h1>{text("landing.title", "پاسخ سریع‌تر، فروش منظم‌تر، تجربه‌ای حرفه‌ای برای مشتری")}</h1>
          <p>{text("landing.description", "Farstar Nexa پیام‌ها و کامنت‌های شبکه‌های اجتماعی را به فرایند فروش قابل مدیریت تبدیل می‌کند؛ از نمایش قیمت تا ثبت سرنخ و پیگیری.")}</p>
          <button className="landing-cta" onClick={onStart}>{text("landing.cta", "شروع کار با Nexa")} <ArrowLeft size={18} /></button>
          <small className="landing-note">قیمت‌ها و اطلاعات شما در پنل اختصاصی‌تان مدیریت می‌شود.</small>
        </div>
        <div className="landing-orbit" aria-hidden="true">
          <div className="orbit-center"><img src={brand.mark} alt="" /><b>NEXA</b></div>
          <span className="orbit-chip orbit-one"><MessageCircle size={18} /> پیام هوشمند</span>
          <span className="orbit-chip orbit-two"><CircleDollarSign size={18} /> قیمت پویا</span>
          <span className="orbit-chip orbit-three"><Workflow size={18} /> اتوماسیون فروش</span>
        </div>
      </section>
      <section className="landing-section">
        <div className="section-heading"><div><span className="eyebrow">یک پنل، یک جریان روشن</span><h2>{text("landing.features_title", "همه چیز برای فروش اجتماعی در یکجا")}</h2></div></div>
        <div className="landing-features">
          <article><span className="feature-icon"><MessageCircle /></span><h3>پاسخ خودکار و شخصی‌سازی‌شده</h3><p>برای هر پیام، قالب بسازید و نام مشتری، محصول، قیمت و اطلاعات پست را با یک کلیک وارد کنید.</p></article>
          <article><span className="feature-icon"><CircleDollarSign /></span><h3>قیمت‌گذاری قابل کنترل</h3><p>نرخ ایرانی، سود یا کارمزد و تخفیف را جداگانه روشن یا خاموش کنید؛ یا قیمت نهایی را مستقیم ثبت کنید.</p></article>
          <article><span className="feature-icon"><Workflow /></span><h3>اتوماسیون بدون سردرگمی</h3><p>محرک، محصول و اقدام‌ها را مرحله‌به‌مرحله تنظیم کنید و پیش از فعال‌سازی Dry Run بگیرید.</p></article>
          <article><span className="feature-icon"><ShieldCheck /></span><h3>کنترل و امنیت</h3><p>حساب‌ها، مخاطبان، سابقه اجرا و تنظیمات اتصال در پنل امن شما قابل مشاهده و مدیریت است.</p></article>
        </div>
      </section>
      <section className="landing-how"><div><span className="eyebrow">شروع ساده</span><h2>در سه گام آماده فروش شوید</h2></div><ol><li><b>۱</b><span><strong>حساب را متصل کنید</strong><small>اتصال Instagram را از پنل مدیریت کنید.</small></span></li><li><b>۲</b><span><strong>محصول و قیمت را بسازید</strong><small>منبع نرخ و روش محاسبه را خودتان انتخاب کنید.</small></span></li><li><b>۳</b><span><strong>اتوماسیون را فعال کنید</strong><small>پاسخ‌ها را تست کنید و بعد به فروش واقعی بسپارید.</small></span></li></ol></section>
      <section className="landing-bottom"><h2>وقت آن است پاسخ‌گویی فروش شما منظم شود.</h2><button onClick={onStart}>ورود و شروع <ArrowLeft size={18} /></button></section>
      <footer className="landing-footer"><span>{brand.nameFa}</span><span>{brand.tagline}</span></footer>
    </main>
  );
}
