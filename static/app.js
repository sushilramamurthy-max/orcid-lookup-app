// ---------- Shared helpers ----------

const RING_RADIUS = 24;
const RING_CIRCUMFERENCE = 2 * Math.PI * RING_RADIUS;
const ORCID_FORMAT = /^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$/i;

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

async function runSearch(given_name, family_name, email, affiliation) {
  const resp = await fetch("/api/search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ given_name, family_name, email, affiliation }),
  });
  const data = await resp.json();
  if (!resp.ok) throw new Error(data.error || "Search failed.");
  return data; // { candidates, count, crossref_error, orcid_unavailable }
}

// ---------- Candidate card rendering (shared by both custom search and
// per-author article search) ----------

function renderCandidate(c, index) {
  const institutions = (c.institutions || []).filter(Boolean);
  const otherNames = (c.other_names || []).filter(Boolean);
  const evidenceItems = (c.evidence || []).map(e => `<li>${escapeHtml(e)}</li>`).join("");
  const supportingWorks = (c.supporting_works || []).map(renderWork).join("");
  const recentWorks = (c.recent_works || []).map(renderWork).join("");

  const topEvidence = (c.evidence && c.evidence[0]) || "";
  const hasMoreDetail = (c.evidence && c.evidence.length > 1) || supportingWorks || recentWorks;
  const offset = RING_CIRCUMFERENCE - (c.score_pct / 100) * RING_CIRCUMFERENCE;
  const source = (c.supporting_works || []).length ? "CrossRef" : "ORCID registry";

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

        <div class="validate-row" data-orcid="${c.orcid_id}"
             data-name="${escapeHtml(c.credit_name || "")}"
             data-source="${source}">
          <span class="validate-label">Is this you?</span>
          <button type="button" class="validate-btn confirm" data-action="confirm">This is me</button>
          <button type="button" class="validate-btn reject" data-action="reject">Not me</button>
        </div>
      </div>
    </article>
  `;
}

function attachRingAnimations(root) {
  try {
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        (root || document).querySelectorAll(".result-card").forEach(card => {
          const fill = card.querySelector(".ring-fill");
          if (fill) fill.style.strokeDashoffset = card.dataset.offset;
        });
      });
    });
  } catch (err) {
    // Purely cosmetic -- rings just won't animate.
  }
}

function renderConfirmedBadge(orcid, source) {
  return `
    <div class="verify-badge confirmed">
      <span class="badge-icon">✓</span>
      <span>ORCID confirmed <span class="badge-source">— verified via ${escapeHtml(source)}</span></span>
    </div>
  `;
}

function renderFlaggedBadge(orcid) {
  return `
    <div class="verify-badge flagged">
      <span class="badge-icon">⚑</span>
      <span>Flagged for production <span class="badge-source">— manual ORCID ${escapeHtml(orcid)} on file</span></span>
    </div>
  `;
}

function renderManualEntryForm() {
  return `
    <form class="manual-entry" autocomplete="off">
      <label class="manual-entry-label">Enter the correct ORCID iD</label>
      <div class="manual-entry-row">
        <input type="text" class="manual-orcid-input" placeholder="0000-0000-0000-0000" inputmode="numeric">
        <button type="submit" class="manual-entry-submit">Flag for production</button>
      </div>
      <div class="manual-entry-error" hidden></div>
    </form>
  `;
}

/**
 * Wires up a single .validate-row's confirm/reject buttons.
 * `getArticleId` is called at click time (not render time) so it always
 * reflects the current value, whether that's a text field or a fixed
 * article DOI from the sidebar.
 * `onResolved(status, orcid, source)` is an optional callback fired after
 * a successful confirm/flag, for callers that need to update something
 * outside the row itself (e.g. an author byline, a sidebar progress count).
 */
function bindRow(row, { getArticleId, onResolved } = {}) {
  const orcid = row.dataset.orcid;
  const authorName = row.dataset.name;
  const source = row.dataset.source;
  const articleIdFn = getArticleId || (() => "");

  row.querySelector('[data-action="confirm"]').addEventListener("click", async () => {
    const articleId = articleIdFn();
    row.querySelectorAll(".validate-btn").forEach(b => b.disabled = true);
    const originalHtml = row.innerHTML;
    row.innerHTML = `<span class="validate-label">Saving…</span>`;

    try {
      const resp = await fetch("/api/confirm", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ author_name: authorName, orcid, article_id: articleId, source }),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.error || "Could not save confirmation.");
      const badgeWrap = document.createElement("div");
      badgeWrap.className = "verify-result";
      badgeWrap.innerHTML = renderConfirmedBadge(orcid, source);
      row.replaceWith(badgeWrap);
      if (onResolved) onResolved("confirmed", orcid, source);
    } catch (err) {
      row.innerHTML = originalHtml;
      row.insertAdjacentHTML("beforeend", `<div class="manual-entry-error">${escapeHtml(err.message)}</div>`);
      bindRow(row, { getArticleId, onResolved }); // rebind ONLY this row
    }
  });

  row.querySelector('[data-action="reject"]').addEventListener("click", () => {
    row.innerHTML = renderManualEntryForm();
    const manualForm = row.querySelector(".manual-entry");
    const input = row.querySelector(".manual-orcid-input");
    const errorEl = row.querySelector(".manual-entry-error");

    manualForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const typed = input.value.trim();

      if (!ORCID_FORMAT.test(typed)) {
        errorEl.textContent = "Enter a valid ORCID iD, e.g. 0000-0001-5250-9122.";
        errorEl.hidden = false;
        return;
      }
      errorEl.hidden = true;

      const articleId = articleIdFn();
      const submitBtn = row.querySelector(".manual-entry-submit");
      submitBtn.disabled = true;
      submitBtn.textContent = "Flagging…";

      try {
        const resp = await fetch("/api/flag", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ author_name: authorName, orcid: typed, article_id: articleId }),
        });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.error || "Could not save flag.");
        const badgeWrap = document.createElement("div");
        badgeWrap.className = "verify-result";
        badgeWrap.innerHTML = renderFlaggedBadge(typed);
        row.replaceWith(badgeWrap);
        if (onResolved) onResolved("flagged", typed, "manual");
      } catch (err) {
        errorEl.textContent = err.message;
        errorEl.hidden = false;
        submitBtn.disabled = false;
        submitBtn.textContent = "Flag for production";
      }
    });
  });
}

function renderCandidatesInto(container, candidates, crossrefError, bindOptions) {
  let html = "";
  if (crossrefError) {
    html += `<div class="notice">${escapeHtml(crossrefError)} — showing ORCID-only results.</div>`;
  }
  if (!candidates.length) {
    html += `<div class="empty-state">No matching records found. Try fewer fields, or check spelling.</div>`;
  } else {
    html += candidates.map(renderCandidate).join("");
  }
  container.innerHTML = html;
  attachRingAnimations(container);
  container.querySelectorAll(".validate-row").forEach(row => bindRow(row, bindOptions));
}

// ---------- Custom search view ----------

const form = document.getElementById("search-form");
const statusEl = document.getElementById("status");
const resultsEl = document.getElementById("results");
const btn = document.getElementById("search-btn");

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
    const data = await runSearch(given_name, family_name, email, affiliation);
    setStatus(`${data.count} candidate${data.count === 1 ? "" : "s"} found`);
    renderCandidatesInto(resultsEl, data.candidates, data.crossref_error, {
      getArticleId: () => document.getElementById("article_id").value.trim(),
    });
  } catch (err) {
    setStatus(err.message || "Network error reaching the server.", true);
  } finally {
    btn.disabled = false;
  }
});

// ---------- Sidebar: sample articles in track mode ----------

const customSearchItem = document.getElementById("custom-search-item");
const customView = document.getElementById("custom-view");
const articleView = document.getElementById("article-view");
const articleListEl = document.getElementById("article-list");

let articlesCache = [];

function progressFor(article) {
  const total = article.authors.length;
  const resolved = article.authors.filter(a => a.status !== "pending").length;
  if (resolved === 0) return { key: "none", label: `${resolved}/${total}` };
  if (resolved === total) return { key: "done", label: `${resolved}/${total}` };
  return { key: "partial", label: `${resolved}/${total}` };
}

function renderSidebar() {
  articleListEl.innerHTML = articlesCache.map(article => {
    const p = progressFor(article);
    return `
      <button type="button" class="sidebar-item" data-article-id="${article.id}">
        <span class="sidebar-item-title">${escapeHtml(article.title)}</span>
        <span class="sidebar-item-sub">${escapeHtml(article.journal)}</span>
        <span class="sidebar-progress ${p.key}">${p.label} resolved</span>
      </button>
    `;
  }).join("");

  articleListEl.querySelectorAll(".sidebar-item").forEach(el => {
    el.addEventListener("click", () => showArticle(el.dataset.articleId));
  });
}

function setActiveSidebarItem(articleId) {
  customSearchItem.classList.toggle("active", !articleId);
  articleListEl.querySelectorAll(".sidebar-item").forEach(el => {
    el.classList.toggle("active", el.dataset.articleId === articleId);
  });
}

function renderAuthorRow(article, author) {
  const affilHtml = `<span class="byline-affil">${escapeHtml(author.affiliation || "")}</span>`;

  if (author.status === "confirmed" || author.status === "flagged") {
    const metaText = author.status === "confirmed"
      ? `Confirmed — verified via ${escapeHtml(author.source || "evidence")}`
      : `Flagged for production — entered manually, needs review`;
    return `
      <div class="author-row" data-author-name="${escapeHtml(author.full_name)}">
        <p class="byline">
          <span class="byline-name">${escapeHtml(author.full_name)}</span><span class="track-insert ${author.status}">${escapeHtml(author.orcid)}</span>
          ${affilHtml}
        </p>
        <span class="track-meta">${metaText}</span>
      </div>
    `;
  }

  return `
    <div class="author-row" data-author-name="${escapeHtml(author.full_name)}">
      <p class="byline">
        <span class="byline-name">${escapeHtml(author.full_name)}</span>
        ${affilHtml}
      </p>
      <div class="author-actions">
        <button type="button" class="find-orcid-btn" data-author="${escapeHtml(author.full_name)}">Find ORCID</button>
      </div>
      <div class="author-results"></div>
    </div>
  `;
}

function showArticle(articleId) {
  const article = articlesCache.find(a => a.id === articleId);
  if (!article) return;

  customView.hidden = true;
  articleView.hidden = false;
  setActiveSidebarItem(articleId);

  document.getElementById("article-journal").textContent = article.journal;
  document.getElementById("article-title").textContent = article.title;
  document.getElementById("article-doi").textContent = article.doi;

  const container = document.getElementById("author-rows");
  container.innerHTML = article.authors.map(au => renderAuthorRow(article, au)).join("");

  container.querySelectorAll(".find-orcid-btn").forEach(button => {
    button.addEventListener("click", async () => {
      const authorRow = button.closest(".author-row");
      const author = article.authors.find(a => a.full_name === button.dataset.author);
      const resultsContainer = authorRow.querySelector(".author-results");

      button.disabled = true;
      button.textContent = "Searching…";

      try {
        const data = await runSearch(author.given_name, author.family_name, author.email, author.affiliation);
        renderCandidatesInto(resultsContainer, data.candidates, data.crossref_error, {
          getArticleId: () => article.doi,
          onResolved: (status, orcid, source) => {
            author.status = status;
            author.orcid = orcid;
            author.source = source;
            authorRow.outerHTML = renderAuthorRow(article, author);
            refreshSidebarProgress();
          },
        });
        button.closest(".author-actions").remove();
      } catch (err) {
        button.disabled = false;
        button.textContent = "Find ORCID";
        resultsContainer.innerHTML = `<div class="manual-entry-error">${escapeHtml(err.message)}</div>`;
      }
    });
  });
}

function refreshSidebarProgress() {
  const activeId = articleListEl.querySelector(".sidebar-item.active")?.dataset.articleId;
  renderSidebar();
  if (activeId) setActiveSidebarItem(activeId);
}

customSearchItem.addEventListener("click", () => {
  articleView.hidden = true;
  customView.hidden = false;
  setActiveSidebarItem(null);
});

async function loadArticles() {
  try {
    const resp = await fetch("/api/articles");
    const data = await resp.json();
    articlesCache = data.articles || [];
    renderSidebar();
  } catch (err) {
    articleListEl.innerHTML = `<div class="manual-entry-error">Couldn't load sample articles.</div>`;
  }
}

loadArticles();
