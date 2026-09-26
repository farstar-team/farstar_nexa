export type PricingRule = {
  direct_price?: boolean;
  adjustment_enabled?: boolean | null;
  rate_source?: string | null;
  percentage: string;
  fixed: string;
  rounding: string;
  minimum: string | null;
  maximum: string | null;
  discount_type: string;
  discount_value: string;
  discount_start: string | null;
  discount_end: string | null;
  fallback: string;
};
export type Product = {
  id: string;
  name: string;
  slug: string;
  description: string;
  sku: string;
  status: string;
  availability: string;
  base_price: string;
  base_currency: string;
  output_currency: string;
  pricing_mode: string;
  manual_rate: string | null;
  pricing: PricingRule;
  url: string;
  custom_fields: Record<string, string>;
  media_count: number;
  automation_count: number;
  created_at: string;
  updated_at: string;
};
export type Media = {
  id: string;
  account_id: string;
  external_id: string;
  product_id: string | null;
  caption: string;
  media_type: string;
  permalink: string;
  thumbnail_url: string;
  published_at: string | null;
};
export type Price = {
  base_price: string;
  converted_price: string;
  original_price: string;
  adjustment: string;
  discount: string;
  final_price: string;
  formatted_price: string;
  currency: string;
  rate: string;
  source: string;
  updated_at: string;
  expires_at: string | null;
  warning: string;
  stale: boolean;
};
export type Action = {
  type: string;
  template: string;
  value: string;
  seconds: number;
};
export type ExecutionDetail = {
  id: string;
  automation_id: string;
  product_id: string | null;
  media_id: string | null;
  trigger: string;
  event_id: string;
  dry_run: boolean;
  status: string;
  automation_name: string;
  product_name: string | null;
  media_caption: string | null;
  detail: string;
  created_at: string;
  actions: {
    id: string;
    position: number;
    kind: string;
    status: string;
    attempts: number;
    result: {
      rendered_text?: string;
      pricing?: Price;
      error?: string;
      value?: string;
      seconds?: number;
      retry_at?: string;
    };
  }[];
};
export const currencies = ["USD", "EUR", "AED", "IRR", "TOMAN"];
export const variables = [
  "customer.id",
  "customer.name",
  "comment.id",
  "comment.text",
  "product.name",
  "product.description",
  "product.sku",
  "product.availability",
  "product.base_price",
  "product.base_currency",
  "product.price",
  "product.currency",
  "product.converted_price",
  "product.original_price",
  "product.discount",
  "product.url",
  "exchange.rate",
  "exchange.source",
  "exchange.updated_at",
  "instagram.username",
  "media.caption",
  "media.url",
];
export const variableLabels: Record<string, string> = {
  "customer.id": "شناسه مشتری",
  "customer.name": "نام مشتری",
  "comment.id": "شناسه رویداد",
  "comment.text": "متن پیام",
  "product.name": "نام محصول",
  "product.description": "توضیحات محصول",
  "product.sku": "کد کالا",
  "product.availability": "وضعیت موجودی",
  "product.base_price": "قیمت پایه",
  "product.base_currency": "ارز پایه",
  "product.price": "قیمت نهایی",
  "product.currency": "ارز قیمت",
  "product.converted_price": "قیمت تبدیل‌شده",
  "product.original_price": "قیمت قبل از تخفیف",
  "product.discount": "مقدار تخفیف",
  "product.url": "لینک محصول",
  "exchange.rate": "نرخ ارز",
  "exchange.source": "منبع نرخ",
  "exchange.updated_at": "زمان به‌روزرسانی نرخ",
  "instagram.username": "نام کاربری اینستاگرام",
  "media.caption": "عنوان پست",
  "media.url": "لینک پست",
};
export const newAction = (type = "SEND_PRICE"): Action => ({
  type,
  template:
    "سلام {{customer.name}}؛ قیمت {{product.name}}: {{product.price}} {{product.currency}}",
  value: "",
  seconds: 60,
});
