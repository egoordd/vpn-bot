import { NextResponse } from "next/server";

import { recordLinkClick } from "@/lib/billing/client";
import { SOURCE_COOKIE, botLink } from "@/lib/site";

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
 * for the rest of the site visit, and forwards to the bot.
 *
 * Every campaign link lands in the bot — that is the channel we run. The route
 * used to also accept `?to=site` and send the visitor to the landing page
 * instead; it is gone, and the parameter is now ignored rather than honoured,
 * so an old link already printed somewhere still arrives in the right place.
 *
 * The cookie is still set even though the visitor leaves for Telegram: it lives
 * on our domain, so if they later open the site in the same browser a purchase
 * there is still credited to the campaign that brought them.
 */
export async function GET(request: Request, { params }: { params: { campaign: string } }) {
  const campaign = normalizeSlug(params.campaign ?? "");

  // An unusable campaign name (e.g. Cyrillic-only) still forwards the visitor —
  // we lose the attribution, never the click-through.
  if (campaign) {
    await recordLinkClick(campaign, "bot");
  }

  const destination = botLink(campaign ? `src_${campaign}` : undefined);
  const response = NextResponse.redirect(destination, 302);
  if (campaign) {
    response.cookies.set(SOURCE_COOKIE, campaign, {
      maxAge: SOURCE_COOKIE_MAX_AGE,
      path: "/",
      sameSite: "lax",
      httpOnly: false, // read server-side on register/checkout to credit the campaign
    });
  }
  return response;
}
