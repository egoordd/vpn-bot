import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { ADMIN_SESSION_TTL_SECONDS, createAdminSession, isAdminPassword } from "@/lib/admin";

export const dynamic = "force-dynamic";

const MAX_ATTEMPTS_PER_WINDOW = 5;
const WINDOW_MS = 15 * 60 * 1000;
const FAILED_ATTEMPT_DELAY_MS = 400;

interface AttemptWindow {
  count: number;
  resetAt: number;
}

// Best-effort limiter: state lives per serverless instance, which still caps
// sustained brute force from one client hitting a warm instance.
const attempts = new Map<string, AttemptWindow>();

function clientIp(request: Request): string {
  const forwarded = request.headers.get("x-forwarded-for") ?? "";
  return forwarded.split(",")[0]?.trim() || "unknown";
}

function isRateLimited(ip: string): boolean {
  const now = Date.now();
  const current = attempts.get(ip);
  if (!current || now > current.resetAt) return false;
  return current.count >= MAX_ATTEMPTS_PER_WINDOW;
}

function recordFailure(ip: string): void {
  const now = Date.now();
  const current = attempts.get(ip);
  if (!current || now > current.resetAt) {
    attempts.set(ip, { count: 1, resetAt: now + WINDOW_MS });
    return;
  }
  attempts.set(ip, { ...current, count: current.count + 1 });
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export async function POST(request: Request) {
  const ip = clientIp(request);
  if (isRateLimited(ip)) {
    return NextResponse.json({ error: "too_many_attempts" }, { status: 429 });
  }

  let password = "";
  try {
    const body = (await request.json()) as { password?: unknown };
    password = typeof body.password === "string" ? body.password : "";
  } catch {
    password = "";
  }

  if (!isAdminPassword(password)) {
    recordFailure(ip);
    await sleep(FAILED_ATTEMPT_DELAY_MS);
    return NextResponse.json({ error: "invalid" }, { status: 401 });
  }

  const session = createAdminSession();
  if (!session) {
    return NextResponse.json({ error: "not_configured" }, { status: 503 });
  }

  attempts.delete(ip);
  cookies().set("admin_auth", session, {
    httpOnly: true,
    secure: true,
    sameSite: "lax",
    path: "/",
    maxAge: ADMIN_SESSION_TTL_SECONDS,
  });
  return NextResponse.json({ ok: true });
}
