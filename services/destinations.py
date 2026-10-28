"""Suggest Trip — a curated destination catalog plus a simple, transparent
preference-matching scorer.

There is no AI model or travel-recommendation API behind this: it is a
hand-curated list of places tagged by vibe, budget fit, and season, scored
against whatever the traveller asks for with plain arithmetic. That's a
deliberate choice — same philosophy as emergency.py / phrasebook.py elsewhere
in this app: label things as curated reference data, never pretend they're
live or personalised beyond simple tag matching, and keep the scoring logic
visible enough that a result can be explained ("matched: beach, budget").

Festivals, stay tiers and local-transport-by-traveller-type are all reference
notes to plan around, not bookings or live listings — heyBro doesn't process
payments, so every "book" action still deep-links out to a real site/search
(see services/destinations.py:booking_links and static/js/book.js).
"""
from __future__ import annotations

# Each destination mixes identity/geo (used to drive the existing live
# services — weather, disasters, culture photos, food, phrasebook) with
# curated planning content that has no live data source anywhere.
DESTINATIONS: list[dict] = [
    {
        "id": "darjeeling-in", "name": "Darjeeling", "country": "India", "country_code": "IN",
        "lat": 27.041, "lon": 88.2663, "region": "south-asia",
        "tags": ["mountain", "tea", "trekking", "culture", "budget", "cool-climate"],
        "budget_fit": ["budget", "mid"], "best_months": ["Mar", "Apr", "May", "Oct", "Nov"],
        "climate_note": "Cool hill-station climate year-round; monsoon (Jun–Sep) brings heavy rain and landslide risk on the approach roads.",
        "festivals": [
            {"name": "Losar (Tibetan New Year)", "when": "Feb/Mar (lunar)", "note": "Monastery dances and prayer-flag renewals around Ghoom and the Tibetan Refugee Self-Help Centre."},
            {"name": "Darjeeling Tea & Tourism Festival", "when": "Nov", "note": "Tea-garden tours, food stalls, cultural shows."},
        ],
        "stays": {
            "luxury": ["Heritage tea-estate bungalows and colonial-era hotels along Mall Road / Chowrasta."],
            "mid": ["Comfortable guesthouses around Nehru Road and Jawahar Road with Kanchenjunga views."],
            "budget": ["Backpacker hostels and homestays near Clubside / Dr Zakir Hussain Road."],
        },
        "transport": {
            "solo": ["Shared jeeps (Darjeeling–Siliguri/Jorebunglow) are the cheapest, most solo-friendly option.", "The Darjeeling Himalayan Railway 'toy train' joy ride is touristy but safe and sociable."],
            "family": ["Private taxi hire for the day is worth it with kids/luggage — negotiate at the taxi stand, agree the route first."],
            "group": ["Book a shared Sumo/Bolero jeep for the whole group rather than several autos — cheaper and keeps everyone together on hill roads."],
            "couple": ["Early-morning shared jeep to Tiger Hill for sunrise is a popular couple's outing — book the night before through your guesthouse."],
        },
    },
    {
        "id": "kathmandu-np", "name": "Kathmandu Valley", "country": "Nepal", "country_code": "NP",
        "lat": 27.7172, "lon": 85.3240, "region": "south-asia",
        "tags": ["mountain", "trekking", "culture", "spiritual", "budget", "adventure"],
        "budget_fit": ["budget", "mid", "luxury"], "best_months": ["Mar", "Apr", "May", "Sep", "Oct", "Nov"],
        "climate_note": "Pre- and post-monsoon are best for both the valley and onward trekking; monsoon (Jun–Aug) brings landslide/flood risk on mountain roads, winter nights are cold.",
        "festivals": [
            {"name": "Indra Jatra", "when": "Sep (lunar)", "note": "Kathmandu Durbar Square — masked dances, chariot processions, the Kumari (living goddess) appearance."},
            {"name": "Dashain", "when": "Sep/Oct (lunar)", "note": "Nepal's biggest festival — expect transport and shop closures, but also the warmest hospitality of the year."},
            {"name": "Tihar", "when": "Oct/Nov (lunar)", "note": "Festival of lights — Kathmandu's old streets are strung with oil lamps."},
        ],
        "stays": {
            "luxury": ["Heritage hotels in Thamel/Durbar Marg with valley or mountain views."],
            "mid": ["Boutique guesthouses in Patan or Boudha, away from Thamel's noise."],
            "budget": ["Thamel's dense backpacker-hostel strip — easy to compare rooms in person."],
        },
        "transport": {
            "solo": ["Ride-hailing apps (Pathao, InDrive) are cheap and track your route — safer than hailing an unmarked taxi solo."],
            "family": ["Hire a private car with driver for valley sightseeing (Patan, Bhaktapur, Swayambhunath) — flat day rate, no haggling per stop."],
            "group": ["A shared micro-van/tempo for a group heading the same direction is standard and very cheap."],
            "couple": ["Rent a scooter only if confident in chaotic traffic; otherwise ride-hailing apps for valley day-trips."],
        },
    },
    {
        "id": "pokhara-np", "name": "Pokhara", "country": "Nepal", "country_code": "NP",
        "lat": 28.2096, "lon": 83.9856, "region": "south-asia",
        "tags": ["mountain", "lake", "trekking", "adventure", "budget", "relax"],
        "budget_fit": ["budget", "mid"], "best_months": ["Mar", "Apr", "Oct", "Nov"],
        "climate_note": "Gateway to the Annapurna region; Oct–Nov has the clearest mountain views, monsoon brings heavy rain and poor visibility.",
        "festivals": [
            {"name": "Pokhara Street Festival", "when": "Dec", "note": "Lakeside closed to traffic for live music, food stalls and craft stands."},
        ],
        "stays": {
            "luxury": ["Lakeside resorts with private Annapurna-facing balconies."],
            "mid": ["Lakeside guesthouses a short walk from the water."],
            "budget": ["Backpacker lodges clustered around Lakeside's main strip."],
        },
        "transport": {
            "solo": ["Rent a bicycle or scooter along Lakeside — flat, well-signed roads make solo exploring easy by day."],
            "family": ["Boat hire on Phewa Lake is calm and family-friendly; agree a return time with the boatman."],
            "group": ["Shared paragliding transfer vans (most operators include pickup) are the standard group activity here."],
            "couple": ["Sunset boat ride on Phewa Lake toward the Tal Barahi temple is the classic couple's evening out."],
        },
    },
    {
        "id": "chiangmai-th", "name": "Chiang Mai", "country": "Thailand", "country_code": "TH",
        "lat": 18.7883, "lon": 98.9853, "region": "southeast-asia",
        "tags": ["culture", "food", "temple", "nightlife", "budget", "digital-nomad"],
        "budget_fit": ["budget", "mid", "luxury"], "best_months": ["Nov", "Dec", "Jan", "Feb"],
        "climate_note": "Cool season (Nov–Feb) is most comfortable; Mar–Apr brings seasonal haze/burning smoke that affects air quality.",
        "festivals": [
            {"name": "Yi Peng / Loy Krathong", "when": "Nov (lunar)", "note": "Thousands of paper lanterns released into the sky and floating krathongs on the river — book lantern-release events ahead."},
            {"name": "Songkran", "when": "13–15 Apr", "note": "City-wide water fight for Thai New Year — fun but soak-proof your valuables."},
        ],
        "stays": {
            "luxury": ["Riverside resorts and converted teak-house hotels near the Ping River."],
            "mid": ["Boutique guesthouses inside or just outside the Old City moat."],
            "budget": ["Hostels clustered around Old City gates (Tha Phae Gate area)."],
        },
        "transport": {
            "solo": ["Grab app for metered rides; red shared songthaew trucks are the cheap local default for short hops."],
            "family": ["Private car/van hire for day trips to Doi Suthep or Doi Inthanon — easier with kids than songthaews."],
            "group": ["Rent a songthaew or minivan for the whole group to temple-hop together."],
            "couple": ["Rent a scooter (valid licence + insurance) for scenic rides to Mae Rim/Mae Sa valley."],
        },
    },
    {
        "id": "hanoi-vn", "name": "Hanoi", "country": "Vietnam", "country_code": "VN",
        "lat": 21.0278, "lon": 105.8342, "region": "southeast-asia",
        "tags": ["culture", "food", "history", "budget", "urban"],
        "budget_fit": ["budget", "mid", "luxury"], "best_months": ["Oct", "Nov", "Mar", "Apr"],
        "climate_note": "Autumn and spring are mild; summer (Jun–Aug) is hot and humid with typhoon-season rain possible.",
        "festivals": [
            {"name": "Tet (Lunar New Year)", "when": "Jan/Feb (lunar)", "note": "Biggest holiday of the year — flower markets everywhere, but many businesses close for several days."},
            {"name": "Mid-Autumn Festival", "when": "Sep/Oct (lunar)", "note": "Lantern displays and mooncakes around the Old Quarter."},
        ],
        "stays": {
            "luxury": ["French-colonial-era hotels near Hoan Kiem Lake."],
            "mid": ["Boutique hotels in the Old Quarter's quieter lanes."],
            "budget": ["Hostels packed into the Old Quarter's backpacker streets (Ta Hien area)."],
        },
        "transport": {
            "solo": ["Grab app for cars/bikes — far safer than flagging an unmetered taxi solo, and the fare is fixed upfront."],
            "family": ["Private car hire for day trips (Ha Long Bay, Ninh Binh) — far more comfortable than public buses with kids."],
            "group": ["Shared Grab vans or a hired minibus for group day-trips outside the city."],
            "couple": ["Walk the Old Quarter and take a cyclo (pedicab) ride around Hoan Kiem Lake in the evening."],
        },
    },
    {
        "id": "bali-id", "name": "Bali (Ubud & the coast)", "country": "Indonesia", "country_code": "ID",
        "lat": -8.5069, "lon": 115.2625, "region": "southeast-asia",
        "tags": ["beach", "wellness", "culture", "nightlife", "nature", "mid"],
        "budget_fit": ["budget", "mid", "luxury"], "best_months": ["Apr", "May", "Jun", "Sep"],
        "climate_note": "Dry season (Apr–Sep) is most reliable; wet season (Oct–Mar) brings short, heavy afternoon downpours.",
        "festivals": [
            {"name": "Nyepi (Day of Silence)", "when": "Mar (lunar, Balinese Saka calendar)", "note": "The whole island shuts down for 24 hours — no flights, no leaving your hotel; plan arrival/departure around it."},
            {"name": "Galungan & Kuningan", "when": "every 210 days (Pawukon calendar)", "note": "Penjor bamboo poles line every street; a striking time to be in Ubud."},
        ],
        "stays": {
            "luxury": ["Clifftop resorts in Uluwatu/Nusa Dua or private pool villas in Ubud/Canggu."],
            "mid": ["Boutique guesthouses and villa-stays across Ubud, Canggu and Seminyak."],
            "budget": ["Hostels and homestays (losmen) in Ubud, Canggu or Kuta."],
        },
        "stays_caveat": "Illustrative only — verify any specific property independently before booking.",
        "transport": {
            "solo": ["Gojek/Grab app rides are the easiest solo option; many solo travellers also rent a scooter (international licence required)."],
            "family": ["Hire a private driver for the day — standard in Bali and much easier than scooters with children."],
            "group": ["Rent a van with driver for the group — common for temple/waterfall circuits."],
            "couple": ["Scooter rental for coastal/rice-terrace routes is the classic Bali couple's way to get around — wear helmets, roads can be chaotic."],
        },
    },
    {
        "id": "manila-ph", "name": "Manila & Palawan", "country": "Philippines", "country_code": "PH",
        "lat": 14.5995, "lon": 120.9842, "region": "southeast-asia",
        "tags": ["beach", "island", "diving", "nature", "urban", "adventure"],
        "budget_fit": ["budget", "mid", "luxury"], "best_months": ["Dec", "Jan", "Feb", "Mar"],
        "climate_note": "Dry season (Dec–May) is best for island-hopping; typhoon season (Jun–Nov) can cancel inter-island boats with little notice.",
        "festivals": [
            {"name": "Sinulog (Cebu, easy add-on)", "when": "3rd Sun of Jan", "note": "Massive street-dance festival honouring the Santo Niño."},
            {"name": "Ati-Atihan (Kalibo)", "when": "Jan", "note": "The Philippines' oldest street festival — face paint, drums, parades."},
        ],
        "stays": {
            "luxury": ["Private-beach resorts in El Nido/Coron with island-hopping packages."],
            "mid": ["Mid-range beachfront guesthouses in El Nido town or Coron town."],
            "budget": ["Backpacker hostels in El Nido/Coron; shared dorm boat tours."],
        },
        "transport": {
            "solo": ["Join shared island-hopping tours (Tour A/B/C/D in El Nido) rather than chartering alone — cheaper and sociable."],
            "family": ["Private island-hopping boat charter gives control over pace/stops with kids."],
            "group": ["Charter a whole boat for the group rather than mixing into a shared tour."],
            "couple": ["A private sunset sandbar tour is a popular (if pricier) couple's add-on from El Nido."],
        },
    },
    {
        "id": "kyoto-jp", "name": "Kyoto", "country": "Japan", "country_code": "JP",
        "lat": 35.0116, "lon": 135.7681, "region": "east-asia",
        "tags": ["culture", "temple", "food", "history", "mid", "luxury"],
        "budget_fit": ["mid", "luxury"], "best_months": ["Mar", "Apr", "Oct", "Nov"],
        "climate_note": "Cherry blossoms (late Mar–early Apr) and autumn foliage (Nov) are peak — also peak crowds and prices; book well ahead.",
        "festivals": [
            {"name": "Gion Matsuri", "when": "Jul", "note": "Month-long festival; the Yamaboko float procession (17th) is the highlight."},
            {"name": "Jidai Matsuri", "when": "22 Oct", "note": "Costumed procession through 1,000+ years of Kyoto history."},
        ],
        "stays": {
            "luxury": ["Traditional ryokan with kaiseki dinners and private onsen baths."],
            "mid": ["Machiya townhouse stays and business hotels near Kyoto Station/Gion."],
            "budget": ["Capsule hotels and hostels near Kyoto or Kawaramachi stations."],
        },
        "transport": {
            "solo": ["City bus day-pass covers nearly all temples; IC card (ICOCA/Suica) works everywhere else."],
            "family": ["Taxis are reliable and not prohibitively expensive for short family hops between sights."],
            "group": ["Book a group taxi/van for a full-day multi-temple circuit to avoid splitting up on buses."],
            "couple": ["Rent bicycles for a slower-paced ride along the Kamo River and through Arashiyama."],
        },
    },
    {
        "id": "marrakech-ma", "name": "Marrakech", "country": "Morocco", "country_code": "MA",
        "lat": 31.6295, "lon": -7.9811, "region": "north-africa",
        "tags": ["culture", "desert", "food", "shopping", "history", "mid"],
        "budget_fit": ["budget", "mid", "luxury"], "best_months": ["Mar", "Apr", "Oct", "Nov"],
        "climate_note": "Spring and autumn are mild; summer (Jun–Aug) is very hot, winter nights can be cold despite warm days.",
        "festivals": [
            {"name": "Marrakech Popular Arts Festival", "when": "Jul", "note": "Folklore dance and music troupes from across Morocco perform in El Badi Palace."},
        ],
        "stays": {
            "luxury": ["Riads with private courtyards and rooftop pools inside the Medina."],
            "mid": ["Mid-range riad guesthouses just outside the busiest souk lanes."],
            "budget": ["Hostels and budget riads near Jemaa el-Fnaa / the Mellah."],
        },
        "stays_caveat": "Riad names/ratings change often — verify current reviews before booking.",
        "transport": {
            "solo": ["Walk the Medina by day with an offline map; agree petit-taxi fares (or insist on the meter) before getting in."],
            "family": ["Private driver/guide for day trips (Atlas Mountains, Ourika Valley) is far easier than public transport with kids."],
            "group": ["Hire a grand taxi or minivan for the whole group for out-of-town trips."],
            "couple": ["A private sunset camel ride or desert day-trip from Marrakech is a popular couple's excursion — book through a reviewed operator."],
        },
    },
    {
        "id": "cuzco-pe", "name": "Cusco & the Sacred Valley", "country": "Peru", "country_code": "PE",
        "lat": -13.5319, "lon": -71.9675, "region": "south-america",
        "tags": ["mountain", "trekking", "history", "adventure", "culture", "high-altitude"],
        "budget_fit": ["budget", "mid", "luxury"], "best_months": ["May", "Jun", "Jul", "Aug", "Sep"],
        "climate_note": "Dry season (May–Sep) is best for trekking (incl. Machu Picchu/Inca Trail); altitude (3,400m) means acclimatisation matters regardless of season.",
        "festivals": [
            {"name": "Inti Raymi", "when": "24 Jun", "note": "Inca sun-festival re-enactment at Sacsayhuamán — Cusco's biggest event of the year, book accommodation months ahead."},
        ],
        "stays": {
            "luxury": ["Boutique hotels in converted colonial buildings in Cusco's historic centre."],
            "mid": ["Sacred Valley lodges (Ollantaytambo/Urubamba) for better altitude acclimatisation."],
            "budget": ["Hostels around Plaza de Armas and San Blas."],
        },
        "transport": {
            "solo": ["Shared colectivo vans between Cusco and the Sacred Valley towns are cheap and frequent."],
            "family": ["Private driver for the Sacred Valley circuit — more flexible with altitude-related rest stops."],
            "group": ["Book a group Sacred Valley tour van rather than splitting into separate taxis."],
            "couple": ["The Vistadome or Belmond train to Machu Picchu is a scenic, comfortable couple's splurge."],
        },
    },
    {
        "id": "reykjavik-is", "name": "Reykjavik & the Ring Road", "country": "Iceland", "country_code": "IS",
        "lat": 64.1466, "lon": -21.9426, "region": "europe",
        "tags": ["nature", "adventure", "road-trip", "wildlife", "cool-climate", "luxury"],
        "budget_fit": ["mid", "luxury"], "best_months": ["Jun", "Jul", "Aug", "Sep"],
        "climate_note": "Summer (Jun–Aug) has near-endless daylight and the most accessible roads; winter driving requires real cold-weather experience.",
        "festivals": [
            {"name": "Þjóðhátíð (National Festival, Vestmannaeyjar)", "when": "early Aug", "note": "Iceland's biggest annual gathering — bonfires, music, fireworks on Heimaey island."},
            {"name": "Reykjavik Culture Night", "when": "Aug", "note": "Free concerts, open museums, fireworks over the harbour."},
        ],
        "stays": {
            "luxury": ["Design hotels in Reykjavik and geothermal-spa resorts (e.g. near the Golden Circle)."],
            "mid": ["Guesthouses and farm-stays along the Ring Road."],
            "budget": ["Hostels and campsites — camping is genuinely common and well set up here."],
        },
        "transport": {
            "solo": ["A rental car is close to essential outside Reykjavik — book well ahead in summer; bus tours cover the Golden Circle for non-drivers."],
            "family": ["A 4x4 rental with good boot space is the standard family choice for the Ring Road."],
            "group": ["Rent a van/minibus and split fuel costs — far cheaper than multiple cars for a group."],
            "couple": ["A smaller rental car plus a few nights in a glass-roofed cabin for aurora-viewing is a popular couple's combo (winter) or a hot-spring-hopping road trip (summer)."],
        },
    },
    {
        "id": "rome-it", "name": "Rome", "country": "Italy", "country_code": "IT",
        "lat": 41.9028, "lon": 12.4964, "region": "europe",
        "tags": ["culture", "history", "food", "urban", "luxury", "mid"],
        "budget_fit": ["mid", "luxury"], "best_months": ["Apr", "May", "Sep", "Oct"],
        "climate_note": "Spring and autumn are mild and less crowded than peak summer, which is hot and heavily touristed.",
        "festivals": [
            {"name": "Natale di Roma (Rome's birthday)", "when": "21 Apr", "note": "Historical re-enactments and free entry to some sites."},
            {"name": "Estate Romana", "when": "Jun–Sep", "note": "Summer-long season of open-air concerts, cinema and events across the city."},
        ],
        "stays": {
            "luxury": ["Historic hotels near the Spanish Steps / Via Veneto."],
            "mid": ["Boutique B&Bs around Trastevere or Monti."],
            "budget": ["Hostels near Termini station or Trastevere."],
        },
        "transport": {
            "solo": ["Rome's historic centre is very walkable; buy a multi-day transit pass for the metro/bus when you need to cover more ground."],
            "family": ["Taxis or ride-hailing for tired kids/long days — metro can be very crowded at peak times."],
            "group": ["Book a private minivan transfer for day trips (e.g. Tivoli, Ostia Antica) to keep the group together."],
            "couple": ["An evening passeggiata through Trastevere, then a scooter/Vespa tour by day, is a classic Rome couple's combo."],
        },
    },
    {
        "id": "capetown-za", "name": "Cape Town", "country": "South Africa", "country_code": "ZA",
        "lat": -33.9249, "lon": 18.4241, "region": "africa",
        "tags": ["nature", "beach", "wildlife", "food", "adventure", "mid"],
        "budget_fit": ["budget", "mid", "luxury"], "best_months": ["Nov", "Dec", "Jan", "Feb", "Mar"],
        "climate_note": "Southern-hemisphere summer (Nov–Mar) is warm and dry; winter (Jun–Aug) is wetter but still mild by most standards.",
        "festivals": [
            {"name": "Cape Town Carnival", "when": "Mar", "note": "Night-time street parade along Green Point's promenade."},
            {"name": "Cape Town International Jazz Festival", "when": "Mar/Apr", "note": "One of Africa's largest jazz festivals."},
        ],
        "stays": {
            "luxury": ["Boutique hotels on the Atlantic Seaboard (Camps Bay/Clifton) with ocean views."],
            "mid": ["Guesthouses in City Bowl or Sea Point."],
            "budget": ["Backpacker hostels in Long Street / Observatory."],
        },
        "transport": {
            "solo": ["Use ride-hailing apps (Uber/Bolt) rather than minibus taxis solo, especially after dark — well-reviewed, trackable rides."],
            "family": ["Rent a car for self-drive day trips (Cape Peninsula, Winelands) — far more flexible with kids than tours."],
            "group": ["Book a private shuttle/minibus for Peninsula or Winelands day tours — common and cost-effective split across a group."],
            "couple": ["A self-drive (or chauffeured) day along Chapman's Peak to Cape Point, finishing with a Winelands sunset, is a popular couple's day trip."],
        },
    },
    {
        "id": "queenstown-nz", "name": "Queenstown", "country": "New Zealand", "country_code": "NZ",
        "lat": -45.0312, "lon": 168.6626, "region": "oceania",
        "tags": ["mountain", "adventure", "nature", "adrenaline", "luxury", "mid"],
        "budget_fit": ["mid", "luxury"], "best_months": ["Dec", "Jan", "Feb", "Jun", "Jul", "Aug"],
        "climate_note": "Southern-hemisphere summer (Dec–Feb) for hiking/watersports, winter (Jun–Aug) for skiing — shoulder seasons can be unpredictable.",
        "festivals": [
            {"name": "Queenstown Winter Festival", "when": "Jun", "note": "Fireworks, parades and events kicking off the ski season."},
        ],
        "stays": {
            "luxury": ["Lakefront lodges with Remarkables mountain views."],
            "mid": ["Central guesthouses and motels walkable to the lakefront."],
            "budget": ["Hostels clustered in the town centre near the gondola."],
        },
        "transport": {
            "solo": ["Public bus (Orbus) covers the town; rental car needed for Glenorchy/Milford Sound day trips."],
            "family": ["Rental car with good luggage space for scenic drives — car seats available from most rental agencies."],
            "group": ["Book a shared shuttle/minivan for adventure-activity pickups (bungy, jet boat) — most operators include it."],
            "couple": ["A scenic drive to Glenorchy followed by a sunset gondola ride up Bob's Peak is a popular couple's day."],
        },
    },
]

# A tiny, honest helper dict so "no clean tag match" still returns a reason.
_ALL_VIBES = sorted({tag for d in DESTINATIONS for tag in d["tags"]})


def available_vibes() -> list[str]:
    return list(_ALL_VIBES)


def _score(dest: dict, vibes: set[str], budget: str | None, region: str | None) -> tuple[int, list[str]]:
    score, matched = 0, []
    overlap = vibes & set(dest["tags"])
    if overlap:
        score += 3 * len(overlap)
        matched.extend(sorted(overlap))
    if budget and budget in dest.get("budget_fit", []):
        score += 2
        matched.append(f"{budget} budget")
    if region and region == dest.get("region"):
        score += 2
        matched.append("region")
    return score, matched


def suggest(preferences: dict, limit: int = 6) -> dict:
    """Rank the curated catalog against a traveller's stated preferences.

    preferences: {
        "vibes": ["beach", "culture", ...],   # any of available_vibes()
        "budget": "budget" | "mid" | "luxury" | None,
        "region": "south-asia" | ... | None,
        "traveler_type": "solo" | "family" | "group" | "couple" | None,  # not scored, carried through for the detail page
        "trip_length_days": int | None,                                    # not scored, carried through
    }
    """
    vibes = {v.strip().lower() for v in (preferences.get("vibes") or []) if v and v.strip()}
    budget = (preferences.get("budget") or "").strip().lower() or None
    region = (preferences.get("region") or "").strip().lower() or None

    ranked = []
    for dest in DESTINATIONS:
        score, matched = _score(dest, vibes, budget, region)
        if vibes or budget or region:
            if score == 0:
                continue  # no match at all — don't pad results with irrelevant places
        ranked.append((score, dest, matched))

    ranked.sort(key=lambda t: t[0], reverse=True)
    if not ranked:
        # Nothing matched (or no preferences given) — fall back to a varied, clearly-labelled default set.
        ranked = [(0, d, []) for d in DESTINATIONS[:limit]]

    results = []
    for score, dest, matched in ranked[:limit]:
        results.append({
            "id": dest["id"], "name": dest["name"], "country": dest["country"],
            "country_code": dest["country_code"], "lat": dest["lat"], "lon": dest["lon"],
            "region": dest["region"], "tags": dest["tags"], "budget_fit": dest["budget_fit"],
            "best_months": dest["best_months"], "climate_note": dest["climate_note"],
            "match_score": score, "matched_on": matched,
        })

    return {
        "source": "reference",
        "label": "REFERENCE \u00b7 curated destination matches, not a personalised AI recommendation",
        "caveat": "Matched by simple tag overlap on a small hand-picked list — treat this as a starting point to explore, not the full universe of options.",
        "results": results,
    }


def get_destination(dest_id: str) -> dict | None:
    for dest in DESTINATIONS:
        if dest["id"] == dest_id:
            return dest
    return None


def destination_detail(dest_id: str, traveler_type: str | None = None) -> dict | None:
    dest = get_destination(dest_id)
    if not dest:
        return None
    transport = dest.get("transport") or {}
    tt = (traveler_type or "").strip().lower() or None
    return {
        "source": "reference",
        "label": "REFERENCE \u00b7 curated trip-planning notes, verify specifics before booking",
        "id": dest["id"], "name": dest["name"], "country": dest["country"],
        "country_code": dest["country_code"], "lat": dest["lat"], "lon": dest["lon"],
        "region": dest["region"], "tags": dest["tags"],
        "best_months": dest["best_months"], "climate_note": dest["climate_note"],
        "festivals": dest.get("festivals") or [],
        "stays": dest.get("stays") or {},
        "stays_caveat": dest.get("stays_caveat", "Illustrative only — availability, names and quality change; verify before booking."),
        "transport": transport,
        "transport_selected": transport.get(tt) if tt else None,
        "traveler_type": tt,
    }
