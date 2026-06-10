import { NextResponse } from "next/server";

import { TARIFFS } from "@/lib/tariffs";

export const dynamic = "force-static";

/** Public tariff catalogue. Mirrors services/tariffs.py until the live API feeds it. */
export function GET() {
  const plans = Object.values(TARIFFS).sort((a, b) => a.sortOrder - b.sortOrder);
  return NextResponse.json({ plans });
}
