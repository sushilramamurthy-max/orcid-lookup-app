const form = document.getElementById("search-form");
const statusEl = document.getElementById("status");
const resultsEl = document.getElementById("results");
const btn = document.getElementById("search-btn");

const RING_RADIUS = 24;
const RING_CIRCUMFERENCE = 2 * Math.PI * RING_RADIUS;

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str || "";
  return div.innerHTML;
}

function renderWork(w) {
  const bits = [];
  if (w.journal) bits.push(escapeHtml(w.journal));
  if (w.year) bits.push(w.year);
  const meta = bits.length ? ` — ${bits.join(", ")}` : "";
  const link = w.doi
    ? `<a href="https://doi.org/${encodeURIComponent(w.doi)}" target="_blank" rel="noopener">${escapeHtml(w.title)}</a>`
    : escapeHtml(w.title);
  return `<li>${link}${meta}</li>`;
}

function renderCandidate(c, index) {
  const institutions = (c.institutions || []).filter(Boolean);
  const otherNames = (c.other_names || []).filter(Boolean);
  const evidenceItems = (c.evidence || []).map(e => `<li>${escapeHtml(e)}</li>`).join("");
  const supportingWorks = (c.supporting_works || []).map(renderWork).join("");
  const recentWorks = (c.recent_works || []).map(renderWork).join("");

  // The single strongest evidence line shows by default; everything else
  // (full evidence list, CrossRef corroboration, recent works) is one
  // click away via <details> instead of always taking up space.
  const topEvidence = (c.evidence && c.evidence[0]) || "";
  const hasMoreDetail = (c.evidence && c.evidence.length > 1) || supportingWorks || recentWorks;

  const offset = RING_CIRCUMFERENCE - (c.score_pct / 100) * RING_CIRCUMFERENCE;

  return `
    <article class="result-card" data-orcid="${c.orcid_id}" data-offset="${offset}"
             style="animation-delay:${index * 70}ms">
      <div class="ring-wrap">
        <svg viewBox="0 0 56 56">
          <circle class="ring-track" cx="28" cy="28" r="${RING_RADIUS}"></circle>
          <circle class="ring-fill ${c.confidence_key}" cx="28" cy="28" r="${RING_RADIUS}"
                  stroke-dasharray="${RING_CIRCUMFERENCE}" stroke-dashoffset="${RING_CIRCUMFERENCE}"></circle>
        </svg>
        <span class="ring-label">${c.score_pct}</span>
      </div>
      <div class="result-body">
        <div class="result-top-row">
          <h2 class="result-name"><a href="${c.orcid_url}" target="_blank" rel="noopener">${escapeHtml(c.credit_name || "(name not public)")}</a></h2>
          <span class="result-tag ${c.confidence_key}">${c.confidence_label}</span>
        </div>
        <div class="result-orcid">${c.orcid_id}</div>
        ${institutions.length ? `<div class="result-line"><span class="label">Affiliation</span> ${escapeHtml(institutions.join("; "))}</div>` : ""}
        ${otherNames.length ? `<div class="result-line"><span class="label">Also known as</span> ${escapeHtml(otherNames.join("; "))}</div>` : ""}
        ${topEvidence ? `<p class="top-evidence">${escapeHtml(topEvidence)}</p>` : ""}

        ${hasMoreDetail ? `
        <details class="evidence-toggle">
          <summary>Show evidence</summary>
          <div class="evidence-block">
            <span class="block-label">Why this score</span>
            <ul class="evidence-list">${evidenceItems}</ul>
          </div>
          ${supportingWorks ? `<div class="evidence-block"><span class="block-label">CrossRef corroboration</span><ul class="works-list">${supportingWorks}</ul></div>` : ""}
          ${recentWorks ? `<div class="evidence-block"><span class="block-label">Recent works</span><ul class="works-list">${recentWorks}</ul></div>` : ""}
        </details>` : ""}

        <div class="validate-row">
          <span class="validate-label">Is this you?</span>
          <button type="button" class="validate-btn confirm" data-action="confirm">This is me</button>
          <button type="button" class="validate-btn reject" data-action="reject">Not me</button>
        </div>
      </div>
    </article>
  `;
}

function attachRingAnimations() {
  // Two rAF ticks so the browser paints the ring at offset=full first,
  // then transitions to the real value -- otherwise CSS collapses the
  // "from" and "to" states into one frame and nothing animates.
  // Wrapped defensively: this is purely cosmetic, so any failure here
  // must never be allowed to look like a search failure to the caller.
  try {
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        document.querySelectorAll(".result-card").forEach(card => {
          const fill = card.querySelector(".ring-fill");
          if (fill) fill.style.strokeDashoffset = card.dataset.offset;
        });
      });
    });
  } catch (err) {
    // Rings just won't animate; scores are still shown as plain numbers.
  }
}

function attachValidateHandlers() {
  document.querySelectorAll(".result-card").forEach(card => {
    card.querySelectorAll(".validate-btn").forEach(button => {
      button.addEventListener("click", () => {
        card.classList.remove("state-confirmed", "state-rejected");
        card.classList.add(button.dataset.action === "confirm" ? "state-confirmed" : "state-rejected");
        card.querySelectorAll(".validate-btn").forEach(b => b.classList.remove("active"));
        button.classList.add("active");
      });
    });
  });
}

function renderResults(candidates, crossrefError) {
  let html = "";
  if (crossrefError) {
    html += `<div class="notice">${escapeHtml(crossrefError)} — showing ORCID-only results.</div>`;
  }
  if (!candidates.length) {
    html += `<div class="empty-state">No matching records found. Try fewer fields, or check spelling.</div>`;
  } else {
    html += candidates.map(renderCandidate).join("");
  }
  resultsEl.innerHTML = html;
  attachRingAnimations();
  attachValidateHandlers();
}

function setStatus(text, isError) {
  statusEl.className = isError ? "status error" : "status";
  statusEl.innerHTML = text;
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const given_name = document.getElementById("given_name").value.trim();
  const family_name = document.getElementById("family_name").value.trim();
  const email = document.getElementById("email").value.trim();
  const affiliation = document.getElementById("affiliation").value.trim();

  if (!given_name && !family_name) {
    setStatus("Enter at least a first or last name.", true);
    return;
  }

  btn.disabled = true;
  setStatus(`<span class="spinner"><span></span><span></span><span></span></span>Searching`);
  resultsEl.innerHTML = "";

  try {
    const resp = await fetch("/api/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ given_name, family_name, email, affiliation }),
    });
    const data = await resp.json();

    if (!resp.ok) {
      setStatus(data.error || "Search failed.", true);
      return;
    }

    setStatus(`${data.count} candidate${data.count === 1 ? "" : "s"} found`);
    renderResults(data.candidates, data.crossref_error);
  } catch (err) {
    setStatus("Network error reaching the server.", true);
  } finally {
    btn.disabled = false;
  }
});
