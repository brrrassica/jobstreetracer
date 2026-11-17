"""List public JobStreet actors and their pricing via apify-client.

Research only — not part of the scraper runtime.

    .venv/bin/python research/apify_probe.py
"""

from __future__ import annotations

from apify_client import ApifyClient


def price_of(actor) -> str:
    info = getattr(actor, "current_pricing_info", None)
    if not info:
        return "unknown"
    model = getattr(info, "pricing_model", "unknown")
    events = getattr(info, "pricing_per_event", None) or {}
    charges = (events.get("actorChargeEvents") or {}) if isinstance(events, dict) else {}
    prices = []
    for name, event in charges.items():
        usd = event.get("eventPriceUsd")
        if usd is not None:
            prices.append(f"{name}=${usd}")
    return f"{model}: " + ", ".join(prices) if prices else model


def main() -> None:
    client = ApifyClient()  # store listing works without a token
    result = client.store().list(search="jobstreet", limit=50)
    print(f"{result.total} JobStreet actors found; showing {len(result.items)}\n")
    for actor in result.items:
        print(f"{actor.username}/{actor.name}")
        print(f"  {actor.title}")
        print(f"  runs={actor.stats.total_runs:,}  {price_of(actor)}")
        print(f"  {actor.url}")
        print()


if __name__ == "__main__":
    main()
