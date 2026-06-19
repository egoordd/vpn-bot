import { NextResponse } from "next/server";

import { getBillingPlans } from "@/lib/billing/client";
import { type Tier } from "@/lib/tariffs";

export const dynamic = "force-dynamic";

const TIERS = new Set(["trial", "standard", "premium"]);

/** Public tariff catalogue. Uses the live billing API when configured. */
export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const rawTier = searchParams.get("tier");
  if (rawTier !== null && !TIERS.has(rawTier)) {
    return NextResponse.json({ error: "invalid tier" }, { status: 400 });
  }

  const plans = await getBillingPlans((rawTier ?? undefined) as Tier | undefined);
  return NextResponse.json({ plans });
}
