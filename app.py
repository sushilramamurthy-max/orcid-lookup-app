"""
app.py
------
Local web app: a form (First Name, Last Name, Email, Affiliation) that
searches the ORCID public registry and cross-checks candidates against
CrossRef publication records, returning a confidence score and the
underlying evidence for each candidate so a corresponding author can
validate the match themselves.

Setup
=====
    pip install -r requirements.txt
    export ORCID_CLIENT_ID="APP-XXXXXXXXXXXXXXXX"
    export ORCID_CLIENT_SECRET="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
    python app.py

Then open http://127.0.0.1:5050 in your browser.

Credentials are free -- register an app at https://orcid.org/developer-tools.
CrossRef needs no credentials. The app runs without ORCID credentials too;
the UI will show a setup notice and searches will return a clear error.
"""

from flask import Flask, jsonify, render_template, request

from orcid_core import credentials_present
from validator import build_candidates, check_manual_orcid
from records import (
    record_confirmation, record_flag, list_records, InvalidOrcidError,
    add_comment, list_comments, reset_all, mark_submitted, get_submission,
    validate_orcid_format,
)
from sample_articles import ARTICLES

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html", credentials_present=credentials_present())


@app.route("/api/articles", methods=["GET"])
def api_articles():
    """
    Sample articles for the sidebar, with each author's live status
    (pending / confirmed / flagged) merged in from records.py -- so
    reloading the page still shows prior progress on that article.
    """
    articles_out = []
    for art in ARTICLES:
        records_for_article = list_records(art["doi"])
        latest_by_name = {}
        for r in records_for_article:  # already ordered newest-first
            latest_by_name.setdefault(r["author_name"], r)

        authors_out = []
        for au in art["authors"]:
            full_name = f"{au['given_name']} {au['family_name']}".strip()
            rec = latest_by_name.get(full_name)
            authors_out.append({
                **au,
                "full_name": full_name,
                "status": rec["status"] if rec else "pending",
                "orcid": rec["orcid"] if rec else None,
                "source": rec["source"] if rec else None,
            })
        submission = get_submission(art["doi"])
        articles_out.append({
            **art,
            "authors": authors_out,
            "submitted": submission is not None,
            "submitted_at": submission["submitted_at"] if submission else None,
        })

    return jsonify({"articles": articles_out})


@app.route("/api/search", methods=["POST"])
def api_search():
    data = request.get_json(silent=True) or {}
    given_name = (data.get("given_name") or "").strip()
    family_name = (data.get("family_name") or "").strip()
    email = (data.get("email") or "").strip()
    affiliation = (data.get("affiliation") or "").strip()

    if not given_name and not family_name:
        return jsonify({"error": "Enter at least a first or last name."}), 400

    try:
        result = build_candidates(given_name, family_name, email, affiliation)
    except Exception as e:
        return jsonify({"error": f"Search failed: {e}"}), 502

    return jsonify({
        "candidates": result["candidates"],
        "count": len(result["candidates"]),
        "crossref_error": result["crossref_error"],
        "orcid_unavailable": result["orcid_unavailable"],
    })


@app.route("/api/confirm", methods=["POST"])
def api_confirm():
    """'This is me' -- records the ORCID as confirmed for this article/author."""
    data = request.get_json(silent=True) or {}
    author_name = (data.get("author_name") or "").strip()
    orcid = (data.get("orcid") or "").strip()
    article_id = (data.get("article_id") or "").strip()
    source = (data.get("source") or "").strip()
    consent_attested = bool(data.get("consent_attested"))

    if not author_name or not orcid:
        return jsonify({"error": "author_name and orcid are required."}), 400
    if not consent_attested:
        return jsonify({"error": "Please confirm you've checked this with the author before continuing."}), 400

    try:
        row = record_confirmation(article_id, author_name, orcid, source, consent_attested=consent_attested)
    except InvalidOrcidError as e:
        return jsonify({"error": str(e)}), 400

    return jsonify({"record": row})


@app.route("/api/flag", methods=["POST"])
def api_flag():
    """'Not me' + manual ORCID entry -- flags this for production review."""
    data = request.get_json(silent=True) or {}
    author_name = (data.get("author_name") or "").strip()
    orcid = (data.get("orcid") or "").strip()
    article_id = (data.get("article_id") or "").strip()
    note = (data.get("note") or "").strip()

    if not author_name or not orcid:
        return jsonify({"error": "author_name and orcid are required."}), 400

    try:
        row = record_flag(article_id, author_name, orcid, note)
    except InvalidOrcidError as e:
        return jsonify({"error": str(e)}), 400

    return jsonify({"record": row})


@app.route("/api/records", methods=["GET"])
def api_records():
    """Lets a production user pull up everything confirmed/flagged for an article."""
    article_id = (request.args.get("article_id") or "").strip() or None
    return jsonify({"records": list_records(article_id)})


@app.route("/api/comment", methods=["POST"])
def api_add_comment():
    """Adds a message to an author's discussion thread -- lets a
    corresponding author ask a co-author to double-check a match, or a
    co-author reply, without either needing an account."""
    data = request.get_json(silent=True) or {}
    article_id = (data.get("article_id") or "").strip()
    author_name = (data.get("author_name") or "").strip()
    role = (data.get("role") or "").strip()
    body = (data.get("body") or "").strip()

    if not author_name:
        return jsonify({"error": "author_name is required."}), 400

    try:
        row = add_comment(article_id, author_name, role, body)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    return jsonify({"comment": row})


@app.route("/api/comments", methods=["GET"])
def api_get_comments():
    article_id = (request.args.get("article_id") or "").strip()
    author_name = (request.args.get("author_name") or "").strip()
    if not article_id or not author_name:
        return jsonify({"error": "article_id and author_name are required."}), 400
    return jsonify({"comments": list_comments(article_id, author_name)})


@app.route("/api/submit", methods=["POST"])
def api_submit():
    """Marks a proof as submitted, once every author on it has been
    confirmed or flagged. The server re-checks this rather than trusting
    the client, since the client's article data can be stale."""
    data = request.get_json(silent=True) or {}
    article_id = (data.get("article_id") or "").strip()
    if not article_id:
        return jsonify({"error": "article_id is required."}), 400

    article = next((a for a in ARTICLES if a["doi"] == article_id), None)
    if not article:
        return jsonify({"error": "Unknown article."}), 404

    resolved_names = {r["author_name"] for r in list_records(article_id)}
    all_names = {f"{au['given_name']} {au['family_name']}".strip() for au in article["authors"]}
    unresolved = all_names - resolved_names
    if unresolved:
        return jsonify({
            "error": f"Not all authors are resolved yet: {', '.join(sorted(unresolved))}"
        }), 400

    row = mark_submitted(article_id)
    return jsonify({"submission": row})


@app.route("/api/verify-orcid", methods=["POST"])
def api_verify_orcid():
    """Sanity-checks a manually-entered ORCID against ORCID's registry and
    CrossRef, before it gets flagged. A nudge, not a hard gate -- the
    frontend decides how much friction a 'mismatch' verdict should add."""
    data = request.get_json(silent=True) or {}
    given_name = (data.get("given_name") or "").strip()
    family_name = (data.get("family_name") or "").strip()
    orcid = (data.get("orcid") or "").strip()
    affiliation = (data.get("affiliation") or "").strip()

    if not orcid:
        return jsonify({"error": "orcid is required."}), 400
    try:
        orcid = validate_orcid_format(orcid)
    except InvalidOrcidError as e:
        return jsonify({"error": str(e)}), 400

    result = check_manual_orcid(given_name, family_name, orcid, affiliation)
    return jsonify(result)


@app.route("/api/reset", methods=["POST"])
def api_reset():
    """Clears every confirmation, flag, and comment -- for repeatable demos.
    No auth gate: this app has no user model, so anyone with the URL can
    reset it. Don't wire this button up in a real production deployment
    without adding access control in front of it."""
    reset_all()
    return jsonify({"reset": True})


if __name__ == "__main__":
    app.run(debug=True, port=5050)
