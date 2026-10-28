"""Curated volunteering resources. Reference data, not a live feed: there is no
free, universal API listing vetted volunteer placements, so this is a hand-picked
set of well-known platforms plus a few safety points worth reading before
committing to any placement, especially ones involving children.
"""
from __future__ import annotations

VOLUNTEER_PLATFORMS = [
    {"name": "Workaway", "url": "https://www.workaway.info/",
     "blurb": "Exchange a few hours of help a day (hostels, farms, teaching, NGOs) for food & "
              "accommodation. Huge, worldwide, informal — vet hosts via reviews."},
    {"name": "Worldpackers", "url": "https://www.worldpackers.com/",
     "blurb": "Similar work-exchange model to Workaway; strong presence in Latin America and Asia."},
    {"name": "WWOOF", "url": "https://wwoof.net/",
     "blurb": "World-Wide Opportunities on Organic Farms. Organized as separate national chapters — "
              "look for the specific WWOOF site for the country you're visiting."},
    {"name": "Idealist", "url": "https://www.idealist.org/",
     "blurb": "Listings for short- and long-term volunteering and nonprofit jobs worldwide."},
    {"name": "GoAbroad — Volunteer Abroad", "url": "https://www.goabroad.com/volunteer-abroad",
     "blurb": "A directory of structured volunteer-abroad programs — many are paid programs; check "
              "exactly what the fee covers before committing."},
    {"name": "UN Volunteers", "url": "https://www.unv.org/",
     "blurb": "Official United Nations volunteering opportunities, generally aimed at more "
              "experienced or specialist applicants."},
]

SAFETY_TIPS = [
    "Verify any placement independently before paying or traveling — a legitimate program doesn't "
    "pressure you to wire money quickly or skip a video call first.",
    "Be especially cautious with orphanage or children's-home volunteering: child-protection charities "
    "widely warn that short-term 'orphanage tourism' can cause real harm to kids. Consider donating to, "
    "or supporting the trained local staff of, a reputable child welfare organization instead.",
    "If a placement works with children or vulnerable adults and doesn't ask for a background check, "
    "treat that as a red flag.",
    "Ask in advance about accommodation, expected hours, and who to contact on-site if something feels wrong.",
    "Standard travel insurance often doesn't cover unpaid 'work' by default — check your policy covers "
    "the specific activities you'll be doing.",
]


def get_volunteering(country_code: str | None = None) -> dict:
    cc = (country_code or "").upper()
    note = (f"Looking at {cc}? Search each platform for listings in that specific country or region — "
            "coverage varies a lot by platform." if cc else
            "Search any of these platforms for listings in the country you're visiting.")
    return {
        "source": "reference", "country_code": cc or None,
        "label": "REFERENCE \u00b7 curated volunteering platforms, not a live feed",
        "platforms": VOLUNTEER_PLATFORMS, "safety_tips": SAFETY_TIPS, "note": note,
    }
