import { NextResponse } from "next/server";

import { recordLinkClick } from "@/lib/billing/client";
import { SITE, SOURCE_COOKIE, botLink } from "@/lib/site";

export const dynamic = "force-dynamic";

/** Campaign slug rules mirror the backend's normalize_source_slug exactly, so
 *  the same campaign never splits into two rows in the funnel. */
const SLUG_RE = /[^a-z0-9_-]+/g;
const SLUG_MAX = 32;

const SOURCE_COOKIE_MAX_AGE = 60 * 60 * 24 * 30; // 30 days

function normalizeSlug(raw: string): string | null {
  const slug = decodeURIComponent(raw).trim().toLowerCase().replace(SLUG_RE, "").slice(0, SLUG_MAX).replace(/^[-_]+|[-_]+$/g, "");
  return slug || null;
}

/**
 * Tracking entry point: `/go/<campaign>` counts the tap, remembers the campaign
 * for the rest of the site visit, and forwards to the bot (default) or the
 * landing page (`?to=site`). One link per channel covers both funnels.
 */
export async function GET(request: Request, { params }: { params: { campaign: string } }) {
  const campaign = normalizeSlug(params.campaign ?? "");
  const url = new URL(request.url);
  const toSite = url.searchParams.get("to") === "site";

  // An unusable campaign name (e.g. Cyrillic-only) still forwards the visitor —
  // we lose the attribution, never the click-through.
  if (campaign) {
    await recordLinkClick(campaign, toSite ? "site" : "bot");
  }

  const destination = toSite
    ? new URL("/", SITE.url).toString()
    : botLink(campaign ? `src_${campaign}` : undefined);

  const response = NextResponse.redirect(destination, 302);
  if (campaign) {
    response.cookies.set(SOURCE_COOKIE, campaign, {
      maxAge: SOURCE_COOKIE_MAX_AGE,
      path: "/",
      sameSite: "lax",
      httpOnly: false, // read by the signup form to attribute a site purchase
    });
  }
  return response;
}
