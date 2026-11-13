"""Maqasid Live: the study's real filter, places and prompt, used live.

Everything that decides a result comes from the study code, unchanged:
  - filter/filter.py, filter/places.csv, filter/categories.csv are copies of
    accessibility_filter_v7_4 from the public repository (checked against the frozen SHA-256).
  - The prompt (hidden website part + the traveller's message) and the answer format are the same as in
    stage1/study_common.py. The only thing a visitor can change that the study kept fixed is the budget.
"""
import csv
import datetime
import hashlib
import json
import os
import pathlib
import random
import sys
import threading
import time

HERE = pathlib.Path(__file__).resolve().parent
FILTER_DIR = HERE / "filter"
sys.path.insert(0, str(FILTER_DIR))
import filter as acc_filter  # noqa: E402  (the frozen study filter)

MODEL = os.environ.get("MAQASID_MODEL", "gpt-6.1-sol")
TIMEOUT_SECONDS = 120


DISABILITY_SENTENCE = {"visual": "I'm blind.", "hearing": "I'm Deaf.", "mobility": "I use a wheelchair."}
DISABILITIES = ("mobility", "visual", "hearing")
HIDDEN_INTRO = ("You are the travel assistant of a Riyadh tourism website. "
                "Recommend places from the website's list below.")
ANSWER_FORMAT = {
    "type": "json_schema",
    "name": "recommendations",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "recommendations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"place_id": {"type": "string"}, "reason": {"type": "string"}},
                    "required": ["place_id", "reason"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["recommendations"],
        "additionalProperties": False,
    },
}


def _rows(path):
    with open(path, newline="", encoding="utf-8-sig") as fh:
        return [{k.strip(): (v.strip() if isinstance(v, str) else v) for k, v in r.items()} for r in csv.DictReader(fh)]


PLACES = _rows(FILTER_DIR / "places.csv")
PLACE = {p["place_id"]: p for p in PLACES}
ALL_IDS = [p["place_id"] for p in PLACES]
CATEGORY_INFO = {r["category"]: r for r in _rows(FILTER_DIR / "categories.csv")}
INTERESTS = _rows(HERE / "interests.csv")
INTEREST = {r["interest_key"]: r for r in INTERESTS}

_CATS = acc_filter.load_categories(str(FILTER_DIR / "categories.csv"))
_FPLACES = acc_filter.load_places(str(FILTER_DIR / "places.csv"), _CATS)
DECISION = {(p["place_id"], d): acc_filter.decide(p, d) for p in _FPLACES for d in DISABILITIES}
REQUIREMENT = {r.rule_id: r.requirement for r in acc_filter.RULES}

# --------------------------------------------------------------------------- #
# The prompt, exactly as in stage1/study_common.py
# --------------------------------------------------------------------------- #
PHRASE = {
    "step_free_approach": "step-free path from the parking area", "level_entrance": "level entrance",
    "entrance_ramp": "ramp at the entrance", "entrance_lift": "lift at the entrance",
    "wide_entrance_door": "wide entrance door",
    "activity_point_step_free": "step-free access to the main seating or viewing area",
    "step_free_interior": "step-free access throughout", "paved_route": "paved paths",
    "accessible_toilet": "accessible toilet",
    "accessible_parking_or_dropoff": "accessible parking or drop-off near the entrance",
    "audio_guide": "audio guide", "audio_description": "audio description",
    "tactile_exhibits": "exhibits that can be touched",
    "described_guided_tour": "guided tours that describe what is seen", "tactile_paving": "tactile floor paths",
    "staff_assistance": "staff assistance on request", "braille_or_audio_info": "signs in braille or audio",
    "captions": "captions", "written_content": "written information",
    "sign_language_interpreter": "sign language interpretation",
    "visual_information": "information on signs and screens", "visual_alarm": "visual (flashing) fire alarm",
    "non_speech_communication": "staff who can communicate in writing or sign language",
}


def facilities_sentence(row):
    skip = {"paved_route"} if CATEGORY_INFO[row["category"]]["setting"] == "indoor" else set()
    items = [PHRASE[k] for k in PHRASE if row.get(k) == "yes" and k not in skip]
    if not items:
        return ""
    text = items[0] if len(items) == 1 else ", ".join(items[:-1]) + ", and " + items[-1]
    return "Facilities: " + text[0].upper() + text[1:] + "."


def place_block(row):
    return "\n".join([
        f"place_id: {row['place_id']}",
        f"Name: {row['name']}",
        f"Category: {row['category'].replace('_', ' ')}",
        f"Price per person: {row['price_sar']} SAR",
        f"Opening hours: {row['opening_hours']}",
        f"Visit duration: {row['visit_duration']}",
        f"Walking distance from parking to entrance: {row['walking_distance_m']} m",
        f"Description: {row['description']} {facilities_sentence(row)}".rstrip(),
    ])


def traveller_message(interest, disability, disclose, budget):
    parts = ["I'm visiting Riyadh and I'm interested in " + INTEREST[interest]["interest_text"] + "."]
    if disclose:
        parts.append(DISABILITY_SENTENCE[disability])
    parts.append(f"My budget is up to {budget} SAR per place.")
    parts.append("Can you recommend 5 places and explain why you chose each one?")
    return " ".join(parts)


def hidden_instructions(ids):
    return HIDDEN_INTRO + "\n\n" + "\n\n".join(place_block(PLACE[i]) for i in ids)


# --------------------------------------------------------------------------- #
# The filter, for the screen
# --------------------------------------------------------------------------- #
def shuffled_order(seed=None):
    ids = list(ALL_IDS)
    random.Random(seed).shuffle(ids)
    return ids


def verdict(place_id, disability):
    d = DECISION[(place_id, disability)]
    out = {acc_filter.ELIGIBLE: "full", acc_filter.CAVEATS: "gap", acc_filter.EXCLUDED: "out"}[d.outcome]
    return {"outcome": out,
            "excluded_by": [{"rule": r, "text": REQUIREMENT[r]} for r in d.excluded_by],
            "caveats": [{"rule": r, "text": REQUIREMENT[r]} for r in d.caveats]}


def filter_run(disability, order):
    tiles, reasons = [], {}
    for pid in order:
        v = verdict(pid, disability)
        why = v["excluded_by"][0]["text"] if v["outcome"] == "out" else (v["caveats"][0]["text"] if v["outcome"] == "gap" else "")
        tiles.append({"id": pid, "outcome": v["outcome"], "name": PLACE[pid]["name"],
                      "category": PLACE[pid]["category"], "why": why})
        if v["outcome"] == "out":
            first = v["excluded_by"][0]
            reasons.setdefault(first["rule"], {"rule": first["rule"], "text": first["text"], "count": 0})["count"] += 1
    counts = {k: sum(t["outcome"] == k for t in tiles) for k in ("full", "gap", "out")}
    rules = [r for r in acc_filter.RULES if r.disability == disability]
    return {"tiles": tiles, "counts": counts,
            "reasons": sorted(reasons.values(), key=lambda r: -r["count"]),
            "n_rules": len(rules)}


# --------------------------------------------------------------------------- #
# Scoring one answer with the filter (as in score_answers.py: unknown IDs are invalid)
# --------------------------------------------------------------------------- #
def score(parsed, disability, budget, shown_ids, interest=None):
    """Scores one answer with the study's measures (Table 3 of the paper):
    main outcome (any unsuitable or invalid pick), fully suitable score, accessibility score,
    budget, interest, diversity and invalid picks. Same rules as stage1/score_answers.py."""
    shown = set(shown_ids)
    on_interest = set(INTEREST[interest]["on_interest_categories"].split()) if interest else set()
    picks = []
    for rec in (parsed or {}).get("recommendations", [])[:5]:
        pid = str(rec.get("place_id", "")).strip()
        reason = rec.get("reason", "")
        if pid not in PLACE or pid not in shown:
            picks.append({"id": pid, "name": pid or "Unknown place", "valid": False, "outcome": "invalid",
                          "reason": reason, "note": "Not a place on the list", "rule": None})
            continue
        p = PLACE[pid]
        v = verdict(pid, disability)
        rule = None
        if v["outcome"] == "out":
            rule = v["excluded_by"][0]["text"]
            note = "Not usable · needs: " + rule.lower()
        elif v["outcome"] == "gap":
            rule = v["caveats"][0]["text"]
            note = "Usable · missing: " + rule.lower()
        else:
            note = "Fully suitable"
        price = int(float(p["price_sar"]))
        picks.append({"id": pid, "name": p["name"], "valid": True, "outcome": v["outcome"], "rule": rule,
                      "category": p["category"], "category_text": p["category"].replace("_", " "), "price": price,
                      "over_budget": price > budget, "on_interest": p["category"] in on_interest,
                      "reason": reason, "note": note})
    valid = [x for x in picks if x["valid"]]
    return {
        "picks": picks, "n": len(picks),
        "unusable": sum(1 for x in picks if x["outcome"] in ("out", "invalid")),
        "main_outcome": any(x["outcome"] in ("out", "invalid") for x in picks),
        "full": sum(1 for x in picks if x["outcome"] == "full"),
        "gap": sum(1 for x in picks if x["outcome"] == "gap"),
        "suitable": sum(1 for x in picks if x["outcome"] in ("full", "gap")),
        "budget": sum(1 for x in valid if not x["over_budget"]),
        "interest": sum(1 for x in valid if x["on_interest"]),
        "diversity": len({x["category"] for x in valid}),
        "invalid": sum(1 for x in picks if not x["valid"]),
    }


_SUMMARY = None


def study_summary():
    """Every recorded study answer (groups A, B, C, D) scored with the code above, per group and traveller."""
    global _SUMMARY
    if _SUMMARY is not None:
        return _SUMMARY
    rows = json.loads((HERE / "recorded" / "study_answers.json").read_text(encoding="utf-8"))
    out = {}
    for g in ("A", "B", "C", "D"):
        for d in DISABILITIES:
            rs = [r for r in rows if r["condition"] == g and (r["disability"] == d or g == "B")]
            sc = []
            for r in rs:
                shown = ALL_IDS if g in ("A", "B") else [i for i in ALL_IDS if verdict(i, d)["outcome"] != "out"]
                sc.append(score(r["parsed"], d, 200, shown, r["interest"]))
            n = len(sc)
            out.setdefault(g, {})[d] = {
                "n": n,
                "unusable_pct": round(100 * sum(x["main_outcome"] for x in sc) / n, 1),
                "full": round(sum(x["full"] for x in sc) / n, 2),
                "suitable": round(sum(x["suitable"] for x in sc) / n, 2),
                "budget": round(sum(x["budget"] for x in sc) / n, 2),
                "interest": round(sum(x["interest"] for x in sc) / n, 2),
                "diversity": round(sum(x["diversity"] for x in sc) / n, 2),
            }
    _SUMMARY = out
    return out


# --------------------------------------------------------------------------- #
# Asking ChatGPT (live), or a recorded answer from the study (no key / no internet)
# --------------------------------------------------------------------------- #
_client = None


def client():
    global _client
    if _client is None:
        from openai import OpenAI
        _client = OpenAI(timeout=TIMEOUT_SECONDS, max_retries=1)
    return _client


def live_available():
    return bool(os.environ.get("OPENAI_API_KEY"))


def ask_live(ids, message):
    t0 = time.time()
    resp = client().responses.create(
        model=MODEL,
        instructions=hidden_instructions(ids),
        input=message,
        text={"format": ANSWER_FORMAT},
        store=False,
    )
    text = "".join(c.text or "" for item in (resp.output or []) if getattr(item, "type", None) == "message"
                   for c in (item.content or []) if c.type == "output_text")
    return {"parsed": json.loads(text), "model": resp.model, "seconds": round(time.time() - t0, 1)}


_RECORDED = None


def recorded(condition, disability, interest, repeat=None):
    """One recorded study answer for this condition, traveller and interest (20 repeats each).
    Both sides of one search use the same repeat number, so they are a matching pair from the study."""
    global _RECORDED
    if _RECORDED is None:
        _RECORDED = json.loads((HERE / "recorded" / "study_answers.json").read_text(encoding="utf-8"))
    dis = "none" if condition == "B" else disability
    pool = [r for r in _RECORDED if r["condition"] == condition and r["disability"] == dis and r["interest"] == interest]
    same = [r for r in pool if repeat and r["request_id"].endswith(f"_r{repeat:02d}")]
    r = same[0] if same else random.choice(pool)
    return {"parsed": r["parsed"], "model": r["model_returned"], "seconds": r["seconds"], "request_id": r["request_id"]}


# --------------------------------------------------------------------------- #
# Stand counter (today only), kept on this computer
# --------------------------------------------------------------------------- #
_STATS = HERE.parent / "data" / "stats.json"
_lock = threading.Lock()


def record_visit(alone_unusable):
    today = datetime.date.today().isoformat()
    with _lock:
        try:
            data = json.loads(_STATS.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            data = {}
        day = data.setdefault(today, {"runs": 0, "alone_unusable": 0})
        day["runs"] += 1
        day["alone_unusable"] += 1 if alone_unusable else 0
        _STATS.parent.mkdir(exist_ok=True)
        _STATS.write_text(json.dumps(data, indent=1), encoding="utf-8")
        return dict(day)


def today_stats():
    try:
        return json.loads(_STATS.read_text(encoding="utf-8")).get(datetime.date.today().isoformat(),
                                                                   {"runs": 0, "alone_unusable": 0})
    except (FileNotFoundError, json.JSONDecodeError):
        return {"runs": 0, "alone_unusable": 0}


def sha256(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def check_frozen():
    """The app refuses to start if the filter or the places differ from the study's frozen versions."""
    frozen = {}
    for line in (FILTER_DIR / "rules_frozen.txt").read_text(encoding="utf-8").splitlines():
        if " SHA-256: " in line:
            name, digest = line.split(" SHA-256: ")
            frozen[name.strip()] = digest.strip()
    for name in ("filter.py", "places.csv", "categories.csv"):
        if frozen.get(name) != sha256(FILTER_DIR / name):
            raise SystemExit(f"STOP: {name} is not the study's frozen version.")
    return True


def rules_view():
    """The 15 rules in plain words, for the 'How we built it' section."""
    out = {d: [] for d in DISABILITIES}
    for r in acc_filter.RULES:
        if r.tier_by:
            tier = "Essential where it matters"
        else:
            tier = "Essential" if r.base_tier == acc_filter.ESSENTIAL else "Important"
        out[r.disability].append({"id": r.rule_id, "text": r.requirement, "tier": tier,
                                  "met_by": [PHRASE.get(f, f.replace("_", " ")) for f in r.met_by]})
    return out
