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
from validator import build_candidates

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html", credentials_present=credentials_present())


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


if __name__ == "__main__":
    app.run(debug=True, port=5050)
