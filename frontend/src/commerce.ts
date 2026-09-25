export type PricingRule = {
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
  "customer.name",
  "comment.text",
  "product.name",
  "product.description",
  "product.base_price",
  "product.base_currency",
  "product.price",
  "product.currency",
  "product.converted_price",
  "product.url",
  "exchange.rate",
  "exchange.updated_at",
  "instagram.username",
];
export const newAction = (type = "SEND_PRICE"): Action => ({
  type,
  template:
    "سلام {{customer.name}}؛ قیمت {{product.name}}: {{product.price}} {{product.currency}}",
  value: "",
  seconds: 60,
});
