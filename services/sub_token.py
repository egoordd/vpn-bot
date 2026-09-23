"""Is this subscription token one the panel actually issued?

Ownership used to be checked by comparing the link a customer sent against the
URL stored on their subscription. That was wrong, and wrong in a way that made
the check fail for almost everybody: the panel reissues the token, the stored
URL is refreshed from it, and a link handed out an hour earlier no longer
matches — while still working perfectly for fetching the subscription.

    in the customer's link:  base64(tg_856…,1788973596) + signature
    in our database:         base64(tg_856…,1788974165) + signature

Both are genuine. Only the issue instant differs.

So ask the authority instead. The gateway refuses a token whose signature does
not check out — a mangled signature and a signature lifted onto another
username both come back 404, while the real one returns the subscription. That
is exactly the question we need answered, and the panel is the only thing that
can answer it.

The request must not look like a browser: the gateway bounces browsers to the
Happ import page *before* validating anything, so a browser user-agent would
turn any well-formed string into a "yes".
"""

from __future__ import annotations

import logging
import os

import aiohttp

logger = logging.getLogger(__name__)

# The gateway runs beside us; going out to the public host would drag DNS and
# the public network into an authorisation decision for no benefit.
VERIFY_BASE = os.environ.get("SUB_VERIFY_BASE", "http://127.0.0.1:8090").rstrip("/")

# Any client string that is not a browser reaches the real lookup.
_APP_USER_AGENT = "unlock-verify/1.0"

_TIMEOUT_SECONDS = 6.0


async def token_is_genuine(token: str) -> bool:
    """True when the panel serves a subscription for this exact token.

    Returns False on any doubt, including a gateway that cannot be reached: a
    verification that cannot be performed must not pass.
    """

    if not token:
        return False
    url = f"{VERIFY_BASE}/sub/{token}"
    try:
        timeout = aiohttp.ClientTimeout(total=_TIMEOUT_SECONDS)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers={"User-Agent": _APP_USER_AGENT}) as response:
                # An expired subscription still answers 200 with an empty body.
                # Expiry is not our question here — ownership is — and letting
                # it through is what lets someone reclaim an account in order
                # to renew it.
                return response.status == 200
    except Exception:  # noqa: BLE001 - unreachable gateway is simply "no"
        logger.warning("Subscription token verification failed for %s…", token[:8])
        return False
