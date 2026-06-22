import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { adminSessionToken, isAdminPassword } from "@/lib/admin";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  let password = "";
  try {
    const body = (await request.json()) as { password?: unknown };
    password = typeof body.password === "string" ? body.password : "";
  } catch {
    password = "";
  }

  if (!isAdminPassword(password)) {
    return NextResponse.json({ error: "invalid" }, { status: 401 });
  }

  cookies().set("admin_auth", adminSessionToken(), {
    httpOnly: true,
    secure: true,
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60 * 12,
  });
  return NextResponse.json({ ok: true });
}
