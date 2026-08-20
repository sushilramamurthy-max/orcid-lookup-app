"""
orcid_core.py
-------------
Authenticates with and queries the ORCID Public API:
  - search_people(): name/email/affiliation search of the public registry
  - get_recent_works(): pulls a candidate's own listed publications, so a
    corresponding author can visually recognize "yes, that's my paper"
"""

import os
import time

import requests

ORCID_TOKEN_URL = "https://orcid.org/oauth/token"
ORCID_SEARCH_URL = "https://pub.orcid.org/v3.0/expanded-search"
ORCID_WORKS_URL = "https://pub.orcid.org/v3.0/{orcid}/works"
REQUEST_TIMEOUT = 15

_token_cache = {"access_token": None, "expires_at": 0}


class OrcidConfigError(Exception):
    """Raised when ORCID API credentials are missing, invalid, or a call fails."""


def credentials_present() -> bool:
    return bool(os.environ.get("ORCID_CLIENT_ID")) and bool(os.environ.get("ORCID_CLIENT_SECRET"))


def get_access_token() -> str:
    """Fetch (and cache) an ORCID client-credentials access token."""
    now = time.time()
    if _token_cache["access_token"] and now < _token_cache["expires_at"] - 30:
        return _token_cache["access_token"]

    client_id = os.environ.get("ORCID_CLIENT_ID")
    client_secret = os.environ.get("ORCID_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise OrcidConfigError(
            "ORCID_CLIENT_ID / ORCID_CLIENT_SECRET are not set. "
            "Register a free app at https://orcid.org/developer-tools and set both "
            "as environment variables before starting the server."
        )

    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "client_credentials",
        "scope": "/read-public",
    }
    resp = requests.post(ORCID_TOKEN_URL, data=data,
                          headers={"Accept": "application/json"}, timeout=REQUEST_TIMEOUT)
    if resp.status_code != 200:
        raise OrcidConfigError(f"ORCID rejected the credentials ({resp.status_code}): {resp.text[:200]}")

    payload = resp.json()
    _token_cache["access_token"] = payload["access_token"]
    _token_cache["expires_at"] = now + payload.get("expires_in", 3600)
    return _token_cache["access_token"]


def _build_query(given_name: str, family_name: str, email: str = "", affiliation: str = "") -> str:
    parts = []
    if given_name:
        parts.append(f'given-names:"{given_name}"')
    if family_name:
        parts.append(f'family-name:"{family_name}"')
    if email:
        parts.append(f'email:"{email}"')
    if affiliation:
        parts.append(f'affiliation-org-name:"{affiliation}"')
    return " AND ".join(parts)


def search_people(given_name: str, family_name: str, email: str = "",
                   affiliation: str = "", rows: int = 10) -> list:
    """
    Raw ORCID registry search. Returns dicts: orcid_id, credit_name,
    other_names, institutions, emails -- no confidence scoring here, that's
    computed in validator.py once CrossRef evidence is also available.
    """
    query = _build_query(given_name, family_name, email, affiliation)
    if not query:
        return []

    token = get_access_token()
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    params = {"q": query, "rows": rows}
    resp = requests.get(ORCID_SEARCH_URL, headers=headers, params=params, timeout=REQUEST_TIMEOUT)
    if resp.status_code != 200:
        raise OrcidConfigError(f"ORCID search failed ({resp.status_code}): {resp.text[:200]}")

    hits = resp.json().get("expanded-result", []) or []
    results = []
    for hit in hits:
        orcid_id = hit.get("orcid-id")
        if not orcid_id:
            continue
        credit_name = hit.get("credit-name") or \
            f"{hit.get('given-names', '')} {hit.get('family-names', '')}".strip()
        results.append({
            "orcid_id": orcid_id,
            "orcid_url": f"https://orcid.org/{orcid_id}",
            "credit_name": credit_name,
            "other_names": hit.get("other-name", []) or [],
            "institutions": hit.get("institution-name", []) or [],
            "emails": hit.get("email", []) or [],
        })
    return results


def get_recent_works(orcid_id: str, limit: int = 3) -> list:
    """Fetch a few of a candidate's own listed publications (title/year/DOI),
    so the corresponding author can visually recognize their own work."""
    token = get_access_token()
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    url = ORCID_WORKS_URL.format(orcid=orcid_id)
    try:
        resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            return []
        payload = resp.json()
    except (requests.RequestException, ValueError):
        return []

    works = []
    for group in payload.get("group", []):
        summaries = group.get("work-summary", [])
        if not summaries:
            continue
        summary = summaries[0]
        title = ((summary.get("title") or {}).get("title") or {}).get("value")
        year = ((summary.get("publication-date") or {}).get("year") or {}).get("value")
        doi = None
        for eid in summary.get("external-ids", {}).get("external-id", []):
            if eid.get("external-id-type") == "doi":
                doi = eid.get("external-id-value")
                break
        if title:
            works.append({"title": title, "year": year, "doi": doi})
        if len(works) >= limit:
            break
    return works
