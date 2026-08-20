# ORCID Lookup

A small local web app: search the ORCID public registry by First Name, Last
Name, Email (optional), and Affiliation/Institution, and get back candidate
ORCID iDs.

## Why a local server, not just a webpage?

ORCID's API requires OAuth client credentials to query. Those credentials
can't be safely embedded in browser JavaScript (anyone could view-source and
extract them), so this app uses a small Flask backend to hold the
credentials and talk to ORCID, with a browser-based form as the frontend.

## Setup

### Option A: Run it locally (for your own testing)

1. Register a free app at https://orcid.org/developer-tools to get a
   Client ID and Client Secret (you'll need a free ORCID account).
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Set your credentials as environment variables:
   ```
   export ORCID_CLIENT_ID="APP-XXXXXXXXXXXXXXXX"
   export ORCID_CLIENT_SECRET="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
   ```
4. Run the app:
   ```
   python app.py
   ```
5. Open http://127.0.0.1:5050 in your browser.

Without credentials set, the app still starts and shows a setup notice;
searches will return a clear error until you add them.

### Option B: Deploy it to a public URL (to share with your team)

This app includes a `render.yaml` "Blueprint", so deploying to
[Render.com](https://render.com) (free tier) takes just a few clicks and
gives you a real, shareable `https://your-app-name.onrender.com` link:

1. **Put this folder on GitHub.** Create a free GitHub account if needed,
   make a new repository, and use its "Add file > Upload files" page to
   drag in everything from this folder (you can drag the whole folder in
   most browsers).
2. **Create a free Render account** at render.com and connect it to your
   GitHub account.
3. In Render, choose **New > Blueprint**, pick the repository you just
   created. Render will read `render.yaml` automatically and ask you to
   fill in two values: `ORCID_CLIENT_ID` and `ORCID_CLIENT_SECRET` (get
   these free at https://orcid.org/developer-tools if you haven't already).
4. Click **Apply**. Render builds and deploys the app -- takes a couple of
   minutes the first time.
5. You'll get a URL like `https://orcid-lookup-app.onrender.com`. That's
   what you share with your team and stakeholders -- anyone with the link
   can open it in a browser, no setup needed on their end.

**Note on the free tier:** Render's free web services "sleep" after 15
minutes of no traffic and take ~30-50 seconds to wake up on the next
visit. That's normal -- just a one-time wait, not a bug. If that matters
for a live demo, open the link yourself a minute before your meeting to
wake it up, or upgrade to Render's cheapest paid tier ($7/mo) for
always-on.


## How matching works

Name search against a public registry is inherently ambiguous -- many people
share a name. So each candidate is checked against **two independent
sources** and scored on how much concrete evidence backs it, out of 100%:

| Evidence | Points | Why it counts |
|---|---|---|
| CrossRef lists this exact ORCID on a matching-name work | 5 | Publisher-asserted, not a name guess |
| Extra corroborating CrossRef works (up to 2) | +1 each | More independent confirmations |
| Email you searched matches a public ORCID email | 3 | Direct identifier match |
| Affiliation you searched matches an institution on record | 2 | From ORCID's own record or the matching CrossRef work |
| Only one ORCID record matched the name | 1 | Less ambiguity |

Scores map to bands: **Confirmed** (80%+), **Strong match** (50-79%),
**Possible match** (25-49%), **Weak match** (below 25%).

Every candidate also shows:
- **Why this score** -- the exact evidence list above, in plain language
- **CrossRef corroboration** -- the specific paper(s) that back the match
- **Recent works on this ORCID record** -- so the actual author can
  visually recognize their own papers
- **This is me / Not me** -- for the corresponding author (or the
  production team on their behalf) to make the final call

Even a "Confirmed" result is evidence-based, not a guarantee -- always
leave the final call to the person being identified.

## Confirming and flagging results

Clicking a validate button does more than change the display -- it's saved:

- **"This is me"** records the ORCID as confirmed, tagged with which
  source backed the match (CrossRef or the ORCID registry). The card
  updates to a confirmed badge showing that source.
- **"Not me"** opens an inline field to enter the correct ORCID iD by
  hand. On submit, it's validated for format (`0000-0001-5250-9122`
  shape) and saved with status `flagged` -- signaling to your production
  team that this one needs a manual check rather than being auto-accepted.

Records are stored in a local SQLite file (`records.db`, created
automatically) with an optional **Article ID / DOI** field on the search
form to group confirmations by article. Pull them back out via:

```
GET /api/records?article_id=10.1038/s41586-023-01234-x
```

or omit `article_id` to list everything.

**Note on Render's free tier:** its disk is ephemeral and resets on every
redeploy, so `records.db` will be wiped each time you push new code. Fine
for a demo; for real production use, either point `RECORDS_DB_PATH` (an
environment variable this app reads) at a
[persistent disk](https://render.com/docs/disks) on a paid plan, or swap
`records.py` for a hosted database.

## Files

- `app.py` -- Flask routes: serves the form, exposes `POST /api/search`,
  `POST /api/confirm`, `POST /api/flag`, and `GET /api/records`.
- `orcid_core.py` -- ORCID OAuth token handling, registry search, and
  fetching a candidate's own recent works.
- `crossref_core.py` -- searches CrossRef for works by a given name/
  affiliation, used as an independent cross-check source.
- `validator.py` -- combines both sources into scored, evidence-backed
  candidates, with concurrent API calls and short-lived caching for speed.
- `records.py` -- SQLite storage for confirmed/flagged author records.
- `templates/index.html`, `static/style.css`, `static/app.js` -- the UI.
