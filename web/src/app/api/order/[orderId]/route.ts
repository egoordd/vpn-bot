import { NextResponse } from "next/server";

import { getWebOrder } from "@/lib/billing/client";

export const dynamic = "force-dynamic";

const ORDER_ID_RE = /^[A-Za-z0-9._-]{1,128}$/;

/**
 * Poll a site order. The order id is the YooKassa payment id — unguessable
 * (uuid entropy) and known only to the buyer's browser, which is what makes
 * this safe to expose without a session (email buyers have no session).
 */
export async function GET(
  _request: Request,
  { params }: { params: { orderId: string } },
) {
  const orderId = params.orderId ?? "";
  if (!ORDER_ID_RE.test(orderId)) {
    return NextResponse.json({ error: "order_not_found" }, { status: 404 });
  }

  const order = await getWebOrder(orderId);
  if (!order) {
    return NextResponse.json({ error: "order_not_found" }, { status: 404 });
  }

  return NextResponse.json(order);
}
