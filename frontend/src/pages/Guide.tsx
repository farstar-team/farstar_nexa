import { useEffect, useState } from "react";
import { ArrowLeft, BookOpen, CheckCircle2, ChevronDown, Download, Inbox, MessageCircle, MousePointer2, Play, Sparkles, Workflow, Zap } from "lucide-react";
import { brand } from "../brand";
import { t } from "../i18n";

const steps = [
  { title: "حساب ارتباطی را وصل کنید", text: "از اتصال‌ها، Instagram یا تلگرام را وصل کنید تا پیام‌های واقعی وارد نکسا شوند." },
  { title: "محصول و قیمت را بسازید", text: "محصول، موجودی، قیمت مستقیم یا قیمت بر اساس نرخ ایرانی را تعریف کنید." },
  { title: "پاسخ خودکار را طراحی کنید", text: "کلیدواژه، محصول، قیمت و اقدام‌های اتوماسیون را انتخاب کنید و ابتدا Dry Run بگیرید." },
  { title: "نتیجه را در صندوق پیام ببینید", text: "گفت‌وگوها، پاسخ ارسال‌شده و وضعیت هر اجرا را از یک صفحه دنبال کنید." },
];

const faqs = [
  ["صندوق پیام‌ها چه چیزی نشان می‌دهد؟", "هر گفت‌وگوی ورودی از حساب‌های متصل، شناسه مخاطب، متن پیام‌ها، جهت پیام، زمان و وضعیت ارسال پاسخ را نشان می‌دهد."],
  ["اتوماسیون دقیقاً چه کار می‌کند؟", "وقتی پیام یا کامنت با شرط شما منطبق شود، نکسا اتوماسیون مربوط را اجرا می‌کند؛ مثلاً محصول و قیمت را پیدا می‌کند، پاسخ می‌سازد و نتیجه را ثبت می‌کند."],
  ["آیا پاسخ‌ها بدون کنترل من ارسال می‌شوند؟", "فقط اتوماسیون فعال روی حساب واقعی پاسخ می‌فرستد. قبل از فعال‌سازی می‌توانید از Dry Run استفاده کنید و وضعیت اجرا را ببینید."],
  ["اگر قیمت تغییر کند چه می‌شود؟", "در حالت نرخ آنلاین، قیمت هنگام اجرای پاسخ از نرخ ذخیره‌شده و تنظیمات سود/کارمزد محاسبه می‌شود. در حالت مستقیم، همان قیمت فروشنده استفاده می‌شود."],
  ["چطور پشتیبانی را پیگیری کنم؟", "از بخش پشتیبانی تیکت یا گفت‌وگوی آنلاین بسازید. پاسخ تیم در همان رشته و در صورت فعال‌بودن اعلان، داخل پنل نمایش داده می‌شود."],
  ["آیا Mini App تلگرام امن است؟", "بله؛ Mini App فقط پس از اعتبارسنجی امضای Telegram WebApp و اتصال قبلی حساب تلگرام به کاربر پنل، نشست ایجاد می‌کند."],
];

function GuidePreview() {
  const [active, setActive] = useState(0);
  const host = window.location.host;
  useEffect(() => {
    const timer = window.setInterval(() => setActive((value) => (value + 1) % steps.length), 3600);
    return () => window.clearInterval(timer);
  }, []);
  return <div className="guide-demo" aria-label="راهنمای مرحله‌به‌مرحله">
    <div className="demo-toolbar"><span className="demo-dot red" /><span className="demo-dot yellow" /><span className="demo-dot green" /><span className="demo-address">{host} / {active === 0 ? "integrations" : active === 1 ? "products" : active === 2 ? "automations" : "inbox"}</span></div>
    <div className="demo-body"><aside><div className="demo-logo"><img src={brand.mark} alt="" /> NEXA</div>{["داشبورد", "صندوق پیام‌ها", "محصولات", "اتوماسیون‌ها"].map((item, index) => <div className={`demo-nav ${active === index ? "active" : ""}`} key={item}><span>{index === 0 ? <BookOpen size={13} /> : index === 1 ? <Inbox size={13} /> : index === 2 ? <Zap size={13} /> : <Workflow size={13} />}</span>{item}</div>)}</aside><div className="demo-content"><div className="demo-heading"><span className="demo-eyebrow">راهنمای مرحله‌به‌مرحله</span><b>{steps[active].title}</b></div><div className="demo-card"><div className="demo-card-icon"><MousePointer2 size={20} /></div><div><strong>{steps[active].title}</strong><p>{steps[active].text}</p><div className="demo-progress"><i style={{ width: `${((active + 1) / steps.length) * 100}%` }} /></div></div></div><div className="demo-lines"><span /><span /><span /></div><div className="demo-cursor"><MousePointer2 size={28} /></div></div></div>
    <div className="demo-caption"><Play size={14} /> {steps[active].text}</div>
  </div>;
}

export default function Guide({ publicPage = false, onStart }: { publicPage?: boolean; onStart?: () => void }) {
  const [openFaq, setOpenFaq] = useState(0);
  return <main className={`guide-page ${publicPage ? "guide-public" : ""}`} dir="rtl">
    {publicPage && <header className="guide-public-nav"><a className="brand" href="/"><img src={brand.mark} alt="" /><div><strong>{brand.nameFa}</strong><small>FARSTAR NEXA</small></div></a><button className="secondary" onClick={onStart}>ورود به پنل</button></header>}
    <section className="guide-hero"><div><span className="landing-kicker"><BookOpen size={16} /> راهنمای تصویری Farstar Nexa</span><h1>در چند دقیقه، مسیر پیام تا فروش را ببینید.</h1><p>این راهنما نشان می‌دهد هر بخش نکسا چه کاری انجام می‌دهد و چطور بدون سردرگمی اولین پاسخ خودکار را آماده کنید.</p><a className="landing-cta button" href="#guide-demo">شروع آموزش <ArrowLeft size={17} /></a></div><div className="guide-hero-brand"><div className="guide-logo-badge"><img src={brand.mark} alt="لوگوی Farstar Nexa" /></div><div className="guide-brand-name"><strong>NEXA</strong><span>Social Commerce</span></div><div className="guide-brand-pills"><span><MessageCircle size={15} /> Inbox</span><span><Workflow size={15} /> Automation</span><span><Sparkles size={15} /> Smart Sales</span></div><a className="secondary guide-logo-download" href="/brand/farstar-nexa-logo.svg" download="farstar-nexa-logo.svg"><Download size={15} /> دانلود لوگو</a></div></section>
    <section id="guide-demo" className="guide-section"><div className="section-heading"><div><span className="eyebrow">راهنمای استفاده</span><h2>از شروع تا پاسخ آماده، قدم‌به‌قدم پیش بروید</h2></div></div><GuidePreview /><div className="guide-step-grid">{steps.map((step, index) => <article className="guide-step" key={step.title}><span>{index + 1}</span><div><h3>{step.title}</h3><p>{step.text}</p></div></article>)}</div></section>
    <section className="guide-section guide-explain"><div className="guide-explain-card"><Inbox size={28} /><h2>داخل صندوق پیام‌ها چه می‌بینید؟</h2><p>صندوق پیام، مرکز مشاهده‌ی گفت‌وگوهای ورودی است. هر ردیف یک مخاطب و هر پنجره متن پیام‌ها را نشان می‌دهد؛ پیام ورودی و پاسخ خروجی با رنگ جدا، زمان، و وضعیت‌هایی مثل queued، sent یا failed مشخص می‌شوند. این بخش برای پیگیری مکالمه و پیدا کردن پاسخ‌های ناموفق است، نه برای تنظیم شرط‌های اتوماسیون.</p><a href="#faq">پاسخ پرسش‌های رایج <ArrowLeft size={15} /></a></div><div className="guide-explain-card accent"><Workflow size={28} /><h2>اتوماسیون دقیقاً چه کار می‌کند؟</h2><p>اتوماسیون یک قانون اجرایی است: محرک پیام یا کامنت را می‌گیرد، شرط‌هایی مثل کلیدواژه و محصول را بررسی می‌کند، سپس اتوماسیون را اجرا می‌کند. اتوماسیون می‌تواند پاسخ متنی، اطلاعات محصول، قیمت محاسبه‌شده، ثبت سرنخ و اقدامات بعدی را انجام دهد. اول Dry Run بگیرید، بعد فعالش کنید.</p><a href="#guide-steps">مراحل فعال‌سازی <ArrowLeft size={15} /></a></div></section>
    <section id="guide-steps" className="guide-section"><div className="section-heading"><div><span className="eyebrow">چک‌لیست شروع</span><h2>ترتیب پیشنهادی برای اولین فروش</h2></div></div><ol className="guide-checklist">{["اتصال Instagram یا تلگرام", "ساخت محصول و تعیین روش قیمت", "ساخت اتوماسیون با متغیرهای پیام", "Dry Run با یک پیام نمونه", "فعال‌سازی و بررسی گزارش اجرا"].map((item, index) => <li key={item}><CheckCircle2 size={19} /><span><b>{index + 1}. {item}</b><small>{index === 0 ? "حساب را از بخش اتصال‌ها به شکل رسمی متصل کنید." : index === 1 ? "قیمت مستقیم یا نرخ ایرانی، سود و کارمزد را انتخاب کنید." : index === 2 ? "متغیر قیمت، نام محصول و لینک را از دکمه‌های اتوماسیون وارد کنید." : index === 3 ? "قبل از ارسال واقعی، مسیر پاسخ را در حالت آزمایشی ببینید." : "وضعیت sent، failed و unknown را در گزارش‌ها دنبال کنید."}</small></span></li>)}</ol></section>
    <section id="faq" className="guide-section faq-section"><div className="section-heading"><div><span className="eyebrow">پاسخ‌های کوتاه</span><h2>سؤالات متداول</h2></div></div>{faqs.map(([question, answer], index) => <div className={`faq-item ${openFaq === index ? "open" : ""}`} key={question}><button onClick={() => setOpenFaq(openFaq === index ? -1 : index)} aria-expanded={openFaq === index}><span>{question}</span><ChevronDown size={18} /></button>{openFaq === index && <p>{answer}</p>}</div>)}</section>
    {publicPage && <footer className="landing-footer"><span>{brand.nameFa}</span><span>{t("footer")}</span></footer>}
  </main>;
}
