import { NextResponse } from "next/server";

import { previewDiscount } from "@/lib/billing/client";

export const dynamic = "force-dynamic";

const DEMO_USER_ID = 1;
const MAX_AMOUNT_KOPECKS = 100_000_000;

/** Preview a promo discount against a checkout amount (kopecks). */
export async function POST(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "invalid json" }, { status: 400 });
  }

  const { code, amountKopecks } = (body ?? {}) as {
    code?: unknown;
    amountKopecks?: unknown;
  };

  if (typeof code !== "string" || code.trim().length === 0 || code.length > 64) {
    return NextResponse.json({ error: "invalid code" }, { status: 400 });
  }
  if (typeof amountKopecks !== "number" || !Number.isFinite(amountKopecks) || amountKopecks <= 0 || amountKopecks > MAX_AMOUNT_KOPECKS) {
    return NextResponse.json({ error: "invalid amount" }, { status: 400 });
  }

  const result = await previewDiscount(DEMO_USER_ID, code.trim(), Math.round(amountKopecks));
  return NextResponse.json({ result });
}
