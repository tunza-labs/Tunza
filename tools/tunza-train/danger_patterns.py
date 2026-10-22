"""The danger keyword rules of decide() in lib/assessment.ts, in one place for the report tools.

Used to count and inspect rows only. Labels still come only from decide(). test_danger_patterns.py checks
these against the app source, so a change in assessment.ts fails the test instead of drifting.
"""
from __future__ import annotations

import re

# (copy key in the app, family name, regex alternatives). Order matches DANGER_PATTERNS in the app.
DANGER = [
    ("dangerNotWaking", "not-waking", ["unconscious", "not waking", "won'?t wake", "hajitambui", "haamki"]),
    ("dangerSeizure", "seizure", ["seizure", "convulsion", "fitting", "kifafa", "degedege"]),
    ("dangerNotBreathing", "not-breathing", ["not breathing", "stopped breathing", "hapumui"]),
    ("dangerBlueLips", "blue-lips", ["blue lips", "blue face", "midomo ya bluu"]),
    ("dangerHeavyBleeding", "heavy-bleeding", ["bleeding (a lot|heavily|won'?t stop)", "heavy bleeding", "damu nyingi"]),
]
SOURCES = {key: "|".join(alts) for key, _, alts in DANGER}
PATTERNS = [(key, re.compile(SOURCES[key])) for key, _, _ in DANGER]
FAMILIES = {family: re.compile(SOURCES[key]) for key, family, _ in DANGER}
ALTERNATIVES = [(family, alt) for _, family, alts in DANGER for alt in alts]

_APP_RULE = re.compile(r"re:\s*/(.+?)/,\s*key:\s*\"(\w+)\"", re.S)


def app_sources(assessment_ts: str) -> dict[str, str]:
    """copy key -> regex source, read from the DANGER_PATTERNS block of assessment.ts."""
    block = assessment_ts.split("const DANGER_PATTERNS", 1)[1].split("];", 1)[0]
    return {key: src for src, key in _APP_RULE.findall(block)}
