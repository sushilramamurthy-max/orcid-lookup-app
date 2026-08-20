"""
validator.py
------------
Combines two independent sources into scored, evidence-backed ORCID
candidates for a corresponding author to review:

  1. ORCID registry name/email/affiliation search (orcid_core.search_people)
  2. CrossRef publication records for the same name/affiliation
     (crossref_core.search_author_works)

A candidate's confidence score is built entirely from concrete, visible
evidence -- never asserted as fact -- so the actual author can check each
signal and confirm or reject the match themselves.

Performance notes:
  - ORCID and CrossRef are independent network calls, run concurrently.
  - Each candidate's "recent works" ORCID lookup is also independent of
    the others, so those run concurrently too instead of one-by-one.
  - Identical searches (same name/email/affiliation) are cached in memory
    for a few minutes, since repeat lookups are common during a demo or
    when someone re-checks a result -- avoids redundant API round-trips.
"""

import time
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import orcid_core
import crossref_core

# Score weights (out of a soft max of ~10, capped at 10 -> 100%)
WEIGHT_CROSSREF_ORCID_MATCH = 5   # this ORCID is directly attached to a matching-name
                                  # CrossRef work -- publisher-asserted, strongest signal
WEIGHT_EMAIL_MATCH = 3           # the email you searched matches a public ORCID email
WEIGHT_AFFILIATION_MATCH = 2     # affiliation you searched matches ORCID or CrossRef affiliation text
WEIGHT_SOLE_CANDIDATE = 1        # this was the only ORCID registry hit for the name
WEIGHT_EXTRA_CROSSREF_WORK = 1   # each additional corroborating CrossRef work (capped)
MAX_EXTRA_WORKS_COUNTED = 2

CONFIDENCE_BANDS = [
    (80, "confirmed", "Confirmed"),
    (50, "strong", "Strong match"),
    (25, "possible", "Possible match"),
    (0, "weak", "Weak match"),
]

CACHE_TTL_SECONDS = 300  # 5 minutes -- long enough to help repeat/demo lookups,
                          # short enough that results stay reasonably fresh
_cache_lock = threading.Lock()
_cache: dict = {}


def _confidence_label(score_pct: int):
    for threshold, key, label in CONFIDENCE_BANDS:
        if score_pct >= threshold:
            return key, label
    return "weak", "Weak match"


def _affiliation_matches(affiliation: str, institutions: list, crossref_affil_texts: list) -> bool:
    if not affiliation:
        return False
    needle = affiliation.strip().lower()
    for inst in institutions:
        if needle in inst.lower() or inst.lower() in needle:
            return True
    for text in crossref_affil_texts:
        if needle in text.lower():
            return True
    return False


def _cache_key(given_name, family_name, email, affiliation) -> tuple:
    norm = lambda s: (s or "").strip().lower()
    return (norm(given_name), norm(family_name), norm(email), norm(affiliation))


def build_candidates(given_name: str, family_name: str, email: str = "",
                      affiliation: str = "", mailto: Optional[str] = None) -> dict:
    """
    Returns {"candidates": [...], "crossref_error": str|None, "orcid_unavailable": bool}.
    Each candidate: orcid_id, orcid_url, credit_name, other_names,
    institutions, score_pct, confidence_key, confidence_label, evidence
    (list of human-readable strings), supporting_works (from CrossRef),
    recent_works (from the ORCID record itself, for self-recognition).

    Works in two modes:
      - Full mode (ORCID credentials configured): searches the ORCID
        registry by name/email/affiliation, then cross-checks each
        candidate against CrossRef.
      - CrossRef-only mode (no ORCID credentials): CrossRef needs no
        credentials at all, so if ORCID isn't configured, candidates are
        built directly from CrossRef works whose author list already has
        a publisher-supplied ORCID attached for a matching name. Real
        results, just without the broader ORCID name-search net.
    """
    key = _cache_key(given_name, family_name, email, affiliation)
    now = time.time()
    with _cache_lock:
        cached = _cache.get(key)
        if cached and now - cached["ts"] < CACHE_TTL_SECONDS:
            return cached["result"]

    # ORCID registry search and CrossRef search are independent network
    # calls -- run them concurrently rather than waiting on one then the
    # other, roughly halving wall-clock time for the common case.
    orcid_unavailable = False
    orcid_hits = []
    crossref_works = []
    crossref_error = None

    with ThreadPoolExecutor(max_workers=2) as pool:
        orcid_future = pool.submit(orcid_core.search_people, given_name, family_name, email, affiliation)
        crossref_future = pool.submit(crossref_core.search_author_works, given_name, family_name, affiliation, mailto=mailto)

        try:
            orcid_hits = orcid_future.result()
        except orcid_core.OrcidConfigError:
            orcid_unavailable = True
        try:
            crossref_works = crossref_future.result()
        except Exception as e:  # CrossRef being unavailable shouldn't break ORCID-only results
            crossref_error = f"CrossRef cross-check unavailable: {e}"

    crossref_by_orcid = {}
    for w in crossref_works:
        if w["matched_orcid"]:
            crossref_by_orcid.setdefault(w["matched_orcid"], []).append(w)

    total_orcid_hits = len(orcid_hits)

    # Recent-works lookups (one ORCID API call per candidate) are also
    # independent of each other -- fetch them all concurrently instead of
    # in a loop, so N candidates cost roughly the time of one call, not N.
    recent_works_by_orcid = {}
    if orcid_hits:
        with ThreadPoolExecutor(max_workers=min(8, max(1, len(orcid_hits)))) as pool:
            future_to_id = {
                pool.submit(orcid_core.get_recent_works, hit["orcid_id"], 3): hit["orcid_id"]
                for hit in orcid_hits
            }
            for future, orcid_id in future_to_id.items():
                try:
                    recent_works_by_orcid[orcid_id] = future.result()
                except orcid_core.OrcidConfigError:
                    recent_works_by_orcid[orcid_id] = []

    candidates = []

    for hit in orcid_hits:
        evidence = []
        score = 0

        supporting_works = crossref_by_orcid.get(hit["orcid_id"], [])
        if supporting_works:
            score += WEIGHT_CROSSREF_ORCID_MATCH
            first = supporting_works[0]
            evidence.append(
                f'CrossRef lists this ORCID as an author on "{first["title"]}"'
                + (f' ({first["journal"]}, {first["year"]})' if first["journal"] or first["year"] else "")
            )
            extra = min(len(supporting_works) - 1, MAX_EXTRA_WORKS_COUNTED)
            if extra > 0:
                score += extra * WEIGHT_EXTRA_CROSSREF_WORK
                evidence.append(f"{extra} additional CrossRef work(s) corroborate the same ORCID")

        email_matched = bool(email and any(e.lower() == email.lower() for e in hit["emails"]))
        if email_matched:
            score += WEIGHT_EMAIL_MATCH
            evidence.append("The email you searched matches a public email on this ORCID record")

        # Only use CrossRef affiliation text from works actually tied to THIS
        # candidate's ORCID -- not all CrossRef matches for the name overall,
        # which would leak evidence across different people sharing a name.
        own_crossref_affil_texts = [w["matched_affiliation"] for w in supporting_works if w["matched_affiliation"]]
        if _affiliation_matches(affiliation, hit["institutions"], own_crossref_affil_texts):
            score += WEIGHT_AFFILIATION_MATCH
            evidence.append("Affiliation you searched matches an institution on record")

        if total_orcid_hits == 1:
            score += WEIGHT_SOLE_CANDIDATE
            evidence.append("Only one ORCID record matched this name")

        if not evidence:
            evidence.append("Name match only -- no independent corroboration found")

        score_pct = min(100, round(score / 10 * 100))
        confidence_key, confidence_label = _confidence_label(score_pct)

        candidates.append({
            "orcid_id": hit["orcid_id"],
            "orcid_url": hit["orcid_url"],
            "credit_name": hit["credit_name"],
            "other_names": hit["other_names"],
            "institutions": hit["institutions"],
            "score_pct": score_pct,
            "confidence_key": confidence_key,
            "confidence_label": confidence_label,
            "evidence": evidence,
            "supporting_works": [
                {"title": w["title"], "doi": w["doi"], "journal": w["journal"], "year": w["year"]}
                for w in supporting_works[:3]
            ],
            "recent_works": recent_works_by_orcid.get(hit["orcid_id"], []),
        })

    # CrossRef-only fallback: build candidates straight from CrossRef works
    # that already have a publisher-supplied ORCID attached for a matching
    # author name. No ORCID registry search involved, so no credentials
    # needed -- these are real, just a narrower slice (only authors whose
    # publisher happened to submit their ORCID with the paper).
    if orcid_unavailable:
        seen_orcids = set()
        for w in crossref_works:
            if not w["matched_orcid"] or w["matched_orcid"] in seen_orcids:
                continue
            seen_orcids.add(w["matched_orcid"])
            same_orcid_works = [x for x in crossref_works if x["matched_orcid"] == w["matched_orcid"]]

            evidence = [
                f'CrossRef lists this ORCID as an author on "{w["title"]}"'
                + (f' ({w["journal"]}, {w["year"]})' if w["journal"] or w["year"] else "")
                + " -- publisher-supplied, not a name-similarity guess"
            ]
            score = 85
            if len(same_orcid_works) > 1:
                extra = min(len(same_orcid_works) - 1, MAX_EXTRA_WORKS_COUNTED)
                score += extra * 5
                evidence.append(f"{extra} additional CrossRef work(s) attach the same ORCID")
            if affiliation and w["matched_affiliation"] and affiliation.lower() in w["matched_affiliation"].lower():
                score += 10
                evidence.append("Affiliation you searched matches the affiliation listed on this work")
            score_pct = min(100, score)
            confidence_key, confidence_label = _confidence_label(score_pct)

            candidates.append({
                "orcid_id": w["matched_orcid"],
                "orcid_url": f"https://orcid.org/{w['matched_orcid']}",
                "credit_name": f"{given_name} {family_name}".strip(),
                "other_names": [],
                "institutions": [w["matched_affiliation"]] if w["matched_affiliation"] else [],
                "score_pct": score_pct,
                "confidence_key": confidence_key,
                "confidence_label": confidence_label,
                "evidence": evidence,
                "supporting_works": [
                    {"title": x["title"], "doi": x["doi"], "journal": x["journal"], "year": x["year"]}
                    for x in same_orcid_works[:3]
                ],
                "recent_works": [],  # would need ORCID credentials to fetch
            })

    candidates.sort(key=lambda c: c["score_pct"], reverse=True)
    result = {"candidates": candidates, "crossref_error": crossref_error, "orcid_unavailable": orcid_unavailable}

    with _cache_lock:
        _cache[key] = {"ts": now, "result": result}
        # Simple cap so this can't grow unbounded over a long-running process
        if len(_cache) > 500:
            oldest_key = min(_cache, key=lambda k: _cache[k]["ts"])
            del _cache[oldest_key]

    return result
