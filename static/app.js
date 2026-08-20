const form = document.getElementById("search-form");
const statusEl = document.getElementById("status");
const resultsEl = document.getElementById("results");
const btn = document.getElementById("search-btn");

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str || "";
  return div.innerHTML;
}

function renderWork(w) {
  const bits = [];
  if (w.journal) bits.push(escapeHtml(w.journal));
  if (w.year) bits.push(w.year);
  const meta = bits.length ? ` &mdash; ${bits.join(", ")}` : "";
  const link = w.doi ? `<a href="https://doi.org/${encodeURIComponent(w.doi)}" target="_blank" rel="noopener">${escapeHtml(w.title)}</a>` : escapeHtml(w.title);
  return `<li>${link}${meta}</li>`;
}

function renderCandidate(c, idx) {
  const institutions = (c.institutions || []).filter(Boolean);
  const otherNames = (c.other_names || []).filter(Boolean);

  const evidenceItems = (c.evidence || []).map(e => `<li>${escapeHtml(e)}</li>`).join("");
  const supportingWorks = (c.supporting_works || []).map(renderWork).join("");
  const recentWorks = (c.recent_works || []).map(renderWork).join("");

  return `
    <article class="result-card" data-orcid="${c.orcid_id}">
      <span class="result-tab ${c.confidence_key}">${c.confidence_label}</span>

      <div class="score-row">
        <div class="score-bar"><div class="score-fill ${c.confidence_key}" style="width:${c.score_pct}%"></div></div>
        <span class="score-pct">${c.score_pct}%</span>
      </div>

      <h2 class="result-name"><a href="${c.orcid_url}" target="_blank" rel="noopener">${escapeHtml(c.credit_name || "(name not public)")}</a></h2>
      <div class="result-orcid">${c.orcid_id}</div>
      ${institutions.length ? `<div class="result-line"><span class="label">Affiliation</span>${escapeHtml(institutions.join("; "))}</div>` : ""}
      ${otherNames.length ? `<div class="result-line"><span class="label">Also known as</span>${escapeHtml(otherNames.join("; "))}</div>` : ""}

      <div class="evidence-block">
        <div class="block-label">Why this score</div>
        <ul class="evidence-list">${evidenceItems}</ul>
      </div>

      ${supportingWorks ? `
      <div class="evidence-block">
        <div class="block-label">CrossRef corroboration</div>
        <ul class="works-list">${supportingWorks}</ul>
      </div>` : ""}

      ${recentWorks ? `
      <div class="evidence-block">
        <div class="block-label">Recent works on this ORCID record</div>
        <ul class="works-list">${recentWorks}</ul>
      </div>` : ""}

      <div class="validate-row">
        <span class="validate-label">Is this you?</span>
        <button type="button" class="validate-btn confirm" data-action="confirm">&#10003; This is me</button>
        <button type="button" class="validate-btn reject" data-action="reject">&#10007; Not me</button>
      </div>
    </article>
  `;
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
    html += `<div class="crossref-warning">${escapeHtml(crossrefError)} &mdash; showing ORCID-only results.</div>`;
  }
  if (!candidates.length) {
    html += `<div class="empty-state">No matching ORCID records found. Try fewer fields, or check spelling.</div>`;
  } else {
    html += candidates.map(renderCandidate).join("");
  }
  resultsEl.innerHTML = html;
  attachValidateHandlers();
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();

  const given_name = document.getElementById("given_name").value.trim();
  const family_name = document.getElementById("family_name").value.trim();
  const email = document.getElementById("email").value.trim();
  const affiliation = document.getElementById("affiliation").value.trim();

  if (!given_name && !family_name) {
    statusEl.textContent = "Enter at least a first or last name.";
    statusEl.className = "status error";
    return;
  }

  btn.disabled = true;
  statusEl.className = "status";
  statusEl.textContent = "Searching ORCID and cross-checking against CrossRef…";
  resultsEl.innerHTML = "";

  try {
    const resp = await fetch("/api/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ given_name, family_name, email, affiliation }),
    });
    const data = await resp.json();

    if (!resp.ok) {
      statusEl.className = "status error";
      statusEl.textContent = data.error || "Search failed.";
      return;
    }

    statusEl.textContent = `${data.count} candidate${data.count === 1 ? "" : "s"} found`;
    renderResults(data.candidates, data.crossref_error);
  } catch (err) {
    statusEl.className = "status error";
    statusEl.textContent = "Network error reaching the local server.";
  } finally {
    btn.disabled = false;
  }
});
