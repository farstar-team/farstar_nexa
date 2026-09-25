import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactElement } from "react";
import Products, { ProductEditor } from "../pages/Products";
import Media from "../pages/Media";
import FlowEditor, { DryRun } from "../pages/FlowEditor";
import Automations from "../pages/Automations";
import ExecutionDetail from "../pages/ExecutionDetail";
import type { Rule } from "../api";
import { newAction } from "../commerce";

const account = {
  id: "account-1",
  name: "حساب تست",
  provider: "instagram_mock",
  active: true,
};
const product = {
  id: "product-1",
  name: "تور دبی",
  slug: "dubai",
  description: "سه شب",
  sku: "DXB",
  status: "ACTIVE",
  availability: "IN_STOCK",
  base_price: "250",
  base_currency: "AED",
  output_currency: "TOMAN",
  pricing_mode: "MANUAL",
  manual_rate: "27000",
  pricing: {
    percentage: "8",
    fixed: "150000",
    rounding: "10000",
    minimum: null,
    maximum: null,
    discount_type: "NONE",
    discount_value: "0",
    discount_start: null,
    discount_end: null,
    fallback: "STOP",
  },
  url: "",
  custom_fields: {},
};
const media = {
  id: "media-1",
  account_id: account.id,
  external_id: "sample-post",
  product_id: null,
  caption: "پست تور دبی",
  media_type: "IMAGE",
  permalink: "",
  thumbnail_url: "",
  published_at: null,
};
const rule: Rule = {
  id: "rule-1",
  account_id: account.id,
  name: "قیمت تور",
  enabled: false,
  status: "DRAFT",
  trigger_type: "instagram.comment",
  product_id: product.id,
  scope: "PRODUCT_MEDIA",
  media_ids: [],
  keywords: ["قیمت"],
  match_mode: "contains",
  response: "",
  priority: 0,
  cooldown_seconds: 60,
  flow: { version: 2, actions: [newAction()] },
};
const price = {
  base_price: "250",
  converted_price: "6750000",
  original_price: "7440000",
  adjustment: "690000",
  discount: "0",
  final_price: "7440000.00",
  formatted_price: "7,440,000",
  currency: "TOMAN",
  rate: "27000",
  source: "manual",
  updated_at: "2026-09-25T10:00:00Z",
  expires_at: null,
  warning: "",
  stale: false,
};
const execution = {
  id: "execution-1",
  status: "simulated",
  dry_run: true,
  trigger: "instagram.comment",
  event_id: "sample-event",
  detail: "",
  actions: [
    {
      id: "action-1",
      position: 0,
      kind: "SEND_PRICE",
      status: "simulated",
      attempts: 0,
      result: { rendered_text: "قیمت تور دبی 7,440,000 تومان", pricing: price },
    },
  ],
};
function setup(element: ReactElement, handlers: Record<string, unknown> = {}) {
  const calls: {
    path: string;
    method: string;
    body: Record<string, unknown>;
  }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string, init: RequestInit) => {
      const path = String(input);
      const method = init?.method ?? "GET";
      calls.push({
        path,
        method,
        body: JSON.parse(String(init?.body ?? "{}")),
      });
      const defaults: Record<string, unknown> = {
        "/api/accounts": [account],
        "/api/products": [product],
        "/api/automations": [rule],
        ["/api/media?account_id=" + account.id]: [media],
        ["/api/media?account_id=" + account.id + "&offset=0"]: [media],
        "/api/products?offset=0": [product],
        "/api/products/preview": price,
        "/api/executions/execution-1": execution,
      };
      return new Response(
        JSON.stringify(handlers[path] ?? defaults[path] ?? {}),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    }),
  );
  const query = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  render(<QueryClientProvider client={query}>{element}</QueryClientProvider>);
  return { user: userEvent.setup(), calls };
}

describe("commerce user workflows", () => {
  it("previews a price without saving a product", async () => {
    const { user, calls } = setup(
      <ProductEditor product={product} done={() => {}} />,
    );
    await user.click(
      screen.getByRole("button", { name: "محاسبه و پیش‌نمایش قیمت" }),
    );
    expect(await screen.findByText("7,440,000 تومان")).toBeTruthy();
    expect(calls.filter((c) => c.method === "POST").map((c) => c.path)).toEqual(
      ["/api/products/preview"],
    );
    const body = calls.find((c) => c.path.endsWith("preview"))!.body;
    expect(body.base_price).toBe("250");
    expect(body.manual_rate).toBe("27000");
  });
  it("creates a product using decimal strings", async () => {
    const done = vi.fn();
    const { user, calls } = setup(<ProductEditor product={null} done={done} />);
    await user.type(screen.getByLabelText("نام محصول"), "تور دبی");
    await user.type(screen.getByLabelText("شناسه محصول (slug)"), "dubai");
    await user.type(screen.getByLabelText("قیمت پایه"), "250.25");
    await user.type(
      screen.getByLabelText("نرخ دستی (یک واحد ارز پایه)"),
      "27000",
    );
    await user.click(screen.getByRole("button", { name: "ذخیره" }));
    await waitFor(() => expect(done).toHaveBeenCalledOnce());
    expect(calls.find((c) => c.method === "POST")!.body.base_price).toBe(
      "250.25",
    );
  });
  it("opens an existing product editor", async () => {
    const { user } = setup(<Products />);
    await screen.findByText("تور دبی");
    await user.click(screen.getByRole("button", { name: "ویرایش محصول" }));
    expect((screen.getByLabelText("قیمت پایه") as HTMLInputElement).value).toBe(
      "250",
    );
  });
  it("links selected media to a product", async () => {
    const { user, calls } = setup(<Media />);
    await screen.findByText("پست تور دبی");
    await user.click(screen.getByRole("checkbox", { name: "پست تور دبی" }));
    await user.selectOptions(
      screen.getByLabelText("محصول برای اتصال"),
      product.id,
    );
    await user.click(
      screen.getByRole("button", { name: "اتصال مدیاهای انتخاب‌شده" }),
    );
    await waitFor(() =>
      expect(
        calls.some(
          (c) => c.path === "/api/media/product" && c.method === "PUT",
        ),
      ).toBe(true),
    );
    expect(calls.find((c) => c.path === "/api/media/product")!.body).toEqual({
      media_ids: [media.id],
      product_id: product.id,
    });
  });
  it("builds a draft flow with trigger, conditions and actions", async () => {
    const done = vi.fn();
    const { user, calls } = setup(
      <FlowEditor rule={null} accounts={[account]} done={done} />,
    );
    await user.type(screen.getByLabelText("نام اتوماسیون"), "قیمت تور");
    await user.selectOptions(screen.getByLabelText("محصول"), product.id);
    await user.click(screen.getByRole("button", { name: "مرحله بعد" }));
    expect(screen.getByLabelText("قالب پیام")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "مرحله بعد" }));
    await user.click(screen.getByRole("button", { name: "ذخیره پیش‌نویس" }));
    await waitFor(() => expect(done).toHaveBeenCalledOnce());
    expect(calls.find((c) => c.method === "POST")!.body).toMatchObject({
      status: "DRAFT",
      product_id: product.id,
      trigger_type: "instagram.comment",
      scope: "PRODUCT_MEDIA",
    });
  });
  it("runs a simulation and shows calculated message and actions", async () => {
    const { user, calls } = setup(<DryRun rule={rule} />, {
      ["/api/automations/" + rule.id + "/dry-run"]: {
        execution_id: "execution-1",
        duplicate: false,
      },
    });
    await screen.findByText("پست تور دبی");
    await user.click(screen.getByRole("button", { name: "اجرای Dry Run" }));
    expect(
      await screen.findByText("قیمت تور دبی 7,440,000 تومان"),
    ).toBeTruthy();
    expect(calls.find((c) => c.method === "POST")!.body.account_id).toBe(
      account.id,
    );
    expect(screen.getByText(/هیچ پیامی ارسال نشده/)).toBeTruthy();
  });
  it("shows failures without exposing raw provider responses", async () => {
    setup(<ExecutionDetail id="execution-1" />, {
      "/api/executions/execution-1": {
        ...execution,
        status: "failed",
        detail: "exchange_rate_unavailable",
        actions: [],
      },
    });
    expect(
      await screen.findByText(/نرخ آنلاین معتبر در دسترس نیست/),
    ).toBeTruthy();
  });
  it("pauses an active automation through the existing control", async () => {
    const { user, calls } = setup(
      <Automations
        config={{
          mock_mode: true,
          registration_enabled: false,
          version: "0.2.0",
        }}
      />,
      { "/api/automations": [{ ...rule, status: "ACTIVE", enabled: true }] },
    );
    await screen.findByText("قیمت تور");
    await user.click(screen.getByRole("button", { name: "غیرفعال کردن" }));
    await user.click(screen.getByRole("button", { name: "تأیید" }));
    await waitFor(() =>
      expect(
        calls.some((c) => c.method === "PATCH" && c.body.enabled === false),
      ).toBe(true),
    );
  });
});
