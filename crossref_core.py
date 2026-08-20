"""
crossref_core.py
-----------------
Looks up an author's publication record in CrossRef by name (and optionally
affiliation). This is used as an independent, reliable cross-check against
ORCID registry name-search results: if CrossRef's publisher-supplied
metadata for a work already lists an ORCID for an author matching this
name, that's strong corroborating evidence -- publishers assert it, not a
name-similarity guess.
"""

import re
from typing import Optional

import requests

CROSSREF_WORKS_URL = "https://api.crossref.org/works"
REQUEST_TIMEOUT = 15


def _extract_year(item: dict) -> Optional[int]:
    for key in ("published-print", "published-online", "published", "issued"):
        parts = (item.get(key) or {}).get("date-parts")
        if parts and parts[0] and parts[0][0]:
            return parts[0][0]
    return None


def _given_name_matches(query_given: str, record_given: str) -> bool:
    """Loose match: full name, or first-initial only (handles 'J.' vs 'James')."""
    if not query_given or not record_given:
        return True  # nothing to compare against -- don't penalize
    q = query_given.strip().lower()
    r = record_given.strip().lower()
    if q == r:
        return True
    return q[0] == r[0]


def search_author_works(given_name: str, family_name: str, affiliation: str = "",
                         mailto: Optional[str] = None, rows: int = 15) -> list:
    """
    Search CrossRef for works whose author list includes someone matching
    the given name (and, if provided, affiliation). Returns a list of dicts:
    doi, title, journal, year, matched_orcid (or None), matched_affiliation.
    """
    if not given_name and not family_name:
        return []

    query_author = f"{given_name} {family_name}".strip()
    params = {
        "query.author": query_author,
        "rows": rows,
        "select": "DOI,title,author,container-title,published-print,published-online,issued",
    }
    if affiliation:
        params["query.affiliation"] = affiliation
    headers = {"User-Agent": f"orcid-lookup-app/0.1 (mailto:{mailto})" if mailto
               else "orcid-lookup-app/0.1"}

    resp = requests.get(CROSSREF_WORKS_URL, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    items = resp.json().get("message", {}).get("items", [])

    matches = []
    for item in items:
        for a in item.get("author", []):
            fam = (a.get("family") or "").strip()
            giv = (a.get("given") or "").strip()
            if family_name and fam.lower() != family_name.strip().lower():
                continue
            if not _given_name_matches(given_name, giv):
                continue

            orcid_raw = a.get("ORCID")
            orcid_id = orcid_raw.rstrip("/").split("/")[-1] if orcid_raw else None
            author_affils = [x.get("name", "") for x in a.get("affiliation", []) if x.get("name")]

            matches.append({
                "doi": item.get("DOI"),
                "title": (item.get("title") or ["(untitled)"])[0],
                "journal": (item.get("container-title") or [""])[0],
                "year": _extract_year(item),
                "matched_orcid": orcid_id,
                "matched_affiliation": "; ".join(author_affils),
            })
    return matches
