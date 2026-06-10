import { NextResponse } from "next/server";

import { getAccountOverview } from "@/lib/billing/client";

export const dynamic = "force-dynamic";

/**
 * Account overview for the cabinet. `userId` is a placeholder until session
 * auth (Telegram Login / email) resolves the real identity server-side.
 */
export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const userId = Number(searchParams.get("userId") ?? "1");
  if (!Number.isInteger(userId) || userId <= 0) {
    return NextResponse.json({ error: "invalid userId" }, { status: 400 });
  }

  try {
    const account = await getAccountOverview(userId);
    return NextResponse.json({ account });
  } catch {
    return NextResponse.json({ error: "account unavailable" }, { status: 502 });
  }
}
