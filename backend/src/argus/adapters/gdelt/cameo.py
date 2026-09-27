"""
CAMEO event codes for the violent root categories (18, 19, 20).

Source: CAMEO Conflict and Mediation Event Observations codebook, v1.1b3.
Getting these right matters: OSINT-War-Room labelled 194 (artillery and
tanks) as "air/drone strike" and 1453 (a protest code) as "IED".
"""

from __future__ import annotations

VIOLENT_ROOT_CODES = frozenset({"18", "19", "20"})

ROOT_LABELS = {
    "18": "Assault",
    "19": "Fight",
    "20": "Unconventional mass violence",
}

BASE_LABELS = {
    "180": "Unconventional violence",
    "181": "Abduction, hijacking or hostage-taking",
    "182": "Physical assault",
    "183": "Bombing (suicide, vehicle or roadside)",
    "184": "Use as human shield",
    "185": "Attempted assassination",
    "186": "Assassination",
    "190": "Conventional military force",
    "191": "Blockade or movement restriction",
    "192": "Occupation of territory",
    "193": "Fighting with small arms and light weapons",
    "194": "Fighting with artillery and tanks",
    "195": "Aerial weapons",
    "196": "Ceasefire violation",
    "200": "Unconventional mass violence",
    "201": "Mass expulsion",
    "202": "Mass killings",
    "203": "Ethnic cleansing",
    "204": "Weapons of mass destruction",
}


def label(base_code: str, root_code: str) -> str:
    return BASE_LABELS.get(base_code) or ROOT_LABELS.get(root_code, "Violent event")
