const queryEl = document.getElementById("query");
const sageResultsEl = document.getElementById("sage-results");
const statementsEl = document.getElementById("statements");
const selectedSageTitleEl = document.getElementById("selected-sage-title");
const tooltipEl = document.getElementById("sage-tooltip");

let searchToken = 0;
const sageInfoCache = new Map();

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function highlightAliases(text, aliases, sageId) {
  let html = escapeHtml(text);
  for (const alias of aliases || []) {
    if (!alias) continue;
    const esc = alias.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    html = html.replace(
      new RegExp(`(${esc})`, "g"),
      `<span class="sage-mention" data-sage-id="${sageId}">$1</span>`
    );
  }
  return html;
}

function showTooltip(html, x, y) {
  tooltipEl.innerHTML = html;
  tooltipEl.style.display = "block";
  tooltipEl.style.left = `${x + 12}px`;
  tooltipEl.style.top = `${y + 12}px`;
}

function hideTooltip() {
  tooltipEl.style.display = "none";
}

async function fetchSageInfo(sageId) {
  if (sageInfoCache.has(sageId)) return sageInfoCache.get(sageId);
  const res = await fetch(`/api/sage/${encodeURIComponent(sageId)}`);
  if (!res.ok) return null;
  const data = await res.json();
  sageInfoCache.set(sageId, data);
  return data;
}

async function searchSages() {
  const token = ++searchToken;
  const q = queryEl.value.trim();
  const res = await fetch(`/api/sages?q=${encodeURIComponent(q)}`);
  const data = await res.json();
  if (token !== searchToken) return;

  const items = data.items || [];
  sageResultsEl.innerHTML = items
    .map(
      (s) => `
      <button class="sage-item" data-sage-id="${s.id}" data-sage-name="${escapeHtml(s.name)}">
        <div><strong>${escapeHtml(s.name)}</strong></div>
        <div class="sage-meta">${escapeHtml(s.generation || "")} | ${escapeHtml(s.yeshiva || "")}</div>
      </button>
    `
    )
    .join("");
}

async function loadStatements(sageId, sageName) {
  const res = await fetch(`/api/statements?sage_id=${encodeURIComponent(sageId)}`);
  const data = await res.json();

  selectedSageTitleEl.textContent = `אמרות: ${sageName}`;
  const items = data.items || [];
  statementsEl.innerHTML = items
    .map(
      (st) => `
      <article class="statement">
        <div class="ref">${escapeHtml(st.tractate)} ${escapeHtml(st.daf)}:${st.segment}</div>
        <div>${highlightAliases(st.text_he, st.matched_aliases, sageId)}</div>
      </article>
    `
    )
    .join("");

  if (!items.length) {
    statementsEl.innerHTML = "<p>לא נמצאו אמרות לחכם זה.</p>";
  }
}

queryEl.addEventListener("input", () => {
  searchSages().catch((err) => {
    console.error(err);
  });
});

sageResultsEl.addEventListener("click", (e) => {
  const button = e.target.closest(".sage-item");
  if (!button) return;
  const sageId = button.getAttribute("data-sage-id");
  const sageName = button.getAttribute("data-sage-name");
  loadStatements(sageId, sageName).catch((err) => {
    console.error(err);
  });
});

statementsEl.addEventListener("mousemove", async (e) => {
  const mentionEl = e.target.closest(".sage-mention");
  if (!mentionEl) {
    hideTooltip();
    return;
  }
  const sageId = mentionEl.getAttribute("data-sage-id");
  if (!sageId) return;
  const info = await fetchSageInfo(sageId);
  if (!info) return;

  const aliases = (info.aliases || []).slice(0, 8).join(" | ");
  const html = `
    <div class="tip-title">${escapeHtml(info.name || "")}</div>
    <div class="tip-row">${escapeHtml(info.generation || "")}</div>
    <div class="tip-row">${escapeHtml(info.yeshiva || "")}</div>
    <div class="tip-row tip-aliases">${escapeHtml(aliases)}</div>
  `;
  showTooltip(html, e.clientX, e.clientY);
});

statementsEl.addEventListener("mouseleave", () => {
  hideTooltip();
});

searchSages().catch((err) => {
  console.error(err);
});
