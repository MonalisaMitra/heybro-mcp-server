"""Curated emergency-contact numbers, by ISO 3166-1 alpha-2 country code.

This is reference data, not a live feed — there is no free, universal API for
emergency numbers, so this table is hand-curated and necessarily incomplete.
Everything returned here is labelled "reference" (not "live"), and the
fallback for an unlisted country says so plainly rather than guessing a
number that might be wrong in a way that matters.
"""
from __future__ import annotations

# Numbers are kept as strings (some have leading zeros or are letters-only
# in a few countries) and grouped by service. "general" is a single number
# that reaches multiple services where the country uses one (e.g. 911, 112).
EMERGENCY_NUMBERS: dict[str, dict] = {
    "IN": {"general": "112", "police": "100", "fire": "101", "ambulance": "102",
           "note": "112 reaches all services nationwide; 1070/1077 are state disaster helplines in several states."},
    "NP": {"police": "100", "fire": "101", "ambulance": "102",
           "note": "No single unified number; call the service directly."},
    "US": {"general": "911"},
    "CA": {"general": "911"},
    "GB": {"general": "999", "alt": "112"},
    "IE": {"general": "112", "alt": "999"},
    "AU": {"general": "000"},
    "NZ": {"general": "111"},
    "CN": {"police": "110", "fire": "119", "ambulance": "120"},
    "JP": {"police": "110", "fire_ambulance": "119"},
    "KR": {"police": "112", "fire_ambulance": "119"},
    "TH": {"general": "191", "tourist_police": "1155", "ambulance": "1669"},
    "VN": {"police": "113", "fire": "114", "ambulance": "115"},
    "PH": {"general": "911"},
    "ID": {"general": "112", "police": "110", "ambulance": "118"},
    "MY": {"general": "999"},
    "SG": {"police": "999", "fire_ambulance": "995"},
    "PK": {"general": "15", "ambulance": "1122"},
    "BD": {"general": "999"},
    "LK": {"general": "119", "ambulance": "1990"},
    "MM": {"police": "199", "fire": "191", "ambulance": "192"},
    "BT": {"police": "113", "fire": "110", "ambulance": "112"},
    "ZA": {"general": "112", "police": "10111", "ambulance": "10177"},
    "KE": {"general": "999", "alt": "112"},
    "EG": {"police": "122", "ambulance": "123"},
    "AE": {"police": "999", "ambulance": "998", "fire": "997"},
    "SA": {"police": "999", "ambulance": "997", "fire": "998"},
    "TR": {"general": "112"},
    "RU": {"general": "112"},
    "BR": {"police": "190", "fire": "193", "ambulance": "192"},
    "MX": {"general": "911"},
    "AR": {"general": "911"},
    "CL": {"police": "133", "fire": "132", "ambulance": "131"},
    "NP_TOURIST": {},  # placeholder, not used — kept out of the main lookup
}

# Every EU/EEA member plus a handful of other European countries use 112
# as the single pan-European emergency number; list them once instead of
# repeating the same entry.
_EU112 = [
    "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR",
    "HU", "IS", "IT", "LV", "LI", "LT", "LU", "MT", "NL", "NO", "PL", "PT",
    "RO", "SK", "SI", "ES", "SE", "CH", "AL", "RS", "ME", "MK", "BA", "UA",
]
for _cc in _EU112:
    EMERGENCY_NUMBERS.setdefault(_cc, {"general": "112"})

EMERGENCY_NUMBERS.pop("NP_TOURIST", None)


def get_emergency(country_code: str | None) -> dict:
    """Reference emergency numbers for a country, or an honest "we don't know" fallback."""
    cc = (country_code or "").upper()
    entry = EMERGENCY_NUMBERS.get(cc)
    if entry:
        return {
            "source": "reference", "country_code": cc, "numbers": entry,
            "label": "REFERENCE · curated list, not a live feed",
            "caveat": "Verify locally — numbers can change and this list is not official.",
        }
    return {
        "source": "none", "country_code": cc or None, "numbers": {},
        "label": "No emergency number on file for this country",
        "caveat": (
            "112 and 911 both work in a large number of countries as a fallback, but neither is "
            "universal. Ask locally — hotel staff, a police post or your embassy — as soon as you can."
        ),
    }
