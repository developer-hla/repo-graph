const routes = {
  dashboard: {
    title: "Dashboard",
    meta: "Runtime overview",
    render: renderDashboard,
  },
  sources: {
    title: "Sources",
    meta: "Configured, loaded, and changed repositories",
    render: renderSources,
  },
  jobs: {
    title: "Jobs",
    meta: "Sync, build, and load operations",
    render: renderJobs,
  },
  scope: {
    title: "Scope",
    meta: "Loaded graph scope",
    render: renderScope,
  },
  explore: {
    title: "Explore",
    meta: "Understand graph shape and drill into evidence",
    render: renderExplore,
  },
  search: {
    title: "Entity Search",
    meta: "Find graph entities",
    render: renderSearch,
  },
  impact: {
    title: "Impact",
    meta: "Trace blast radius from an entity",
    render: renderImpact,
  },
  unresolved: {
    title: "Unresolved",
    meta: "Grouped unresolved references",
    render: renderUnresolved,
  },
};

const view = document.querySelector("#app-view");
const title = document.querySelector("#page-title");
const pageMeta = document.querySelector("#page-meta");
const runtimeState = document.querySelector("#runtime-state");
const refreshButton = document.querySelector("#refresh-button");
const apiBase = document.querySelector("#api-base");

const state = {
  currentRoute: "dashboard",
  search: {
    q: "",
    type: "",
    source: "",
    limit: 25,
  },
  unresolved: {
    source: "",
    type: "",
    limit: 50,
    examples: 3,
  },
  impact: {
    entityId: "",
    direction: "in",
    profile: "impact",
    type: "",
    depth: 2,
    limit: 100,
  },
  explore: {
    limit: 50,
  },
  snapshotStatus: null,
};

apiBase.textContent = window.location.origin || "local";

window.addEventListener("hashchange", renderRoute);
refreshButton.addEventListener("click", () => renderRoute({ force: true }));
document.addEventListener("click", handleDocumentClick);
document.addEventListener("submit", handleDocumentSubmit);

checkRuntime();
renderRoute();

function activeRoute() {
  const hash = window.location.hash.replace(/^#/, "");
  return routes[hash] ? hash : "dashboard";
}

function renderRoute() {
  const routeName = activeRoute();
  state.currentRoute = routeName;
  const route = routes[routeName];
  document.querySelectorAll("[data-route]").forEach((link) => {
    link.classList.toggle("active", link.dataset.route === routeName);
  });
  title.textContent = route.title;
  pageMeta.textContent = route.meta;
  view.innerHTML = loadingMarkup();
  route.render().catch((error) => {
    view.innerHTML = errorMarkup(error);
  });
}

async function checkRuntime() {
  try {
    const health = await fetchJson("/health");
    runtimeState.textContent = `${health.status} ${health.version || ""}`.trim();
    runtimeState.className = "runtime-state ok";
  } catch (error) {
    runtimeState.textContent = "offline";
    runtimeState.className = "runtime-state error";
  }
}

async function renderDashboard() {
  const [health, manifest, scope, stats] = await Promise.all([
    fetchMaybe("/health"),
    fetchMaybe("/manifest"),
    fetchMaybe("/scope"),
    fetchMaybe("/stats"),
  ]);
  const scopeData = scope.data || {};
  const summary = scopeData.summary || {};
  const statsData = stats.data || {};
  view.innerHTML = `
    <div class="grid three">
      ${metric("Runtime", health.ok ? "ok" : "error", health.ok ? health.data.version : health.error, health.ok)}
      ${metric("Graph", scopeData.loaded ? "loaded" : "not loaded", scopeData.scope_name || "scope unavailable", scopeData.loaded)}
      ${metric("Sources", numberValue(scopeData.source_count), "loaded sources", true)}
      ${metric("Entities", numberValue(summary.entity_count || statsData.entity_count), "graph entities", stats.ok)}
      ${metric("Edges", numberValue(summary.edge_count || statsData.edge_count), "graph relationships", stats.ok)}
      ${metric("Unresolved", numberValue(summary.unresolved_edge_count || statsData.unresolved_edge_count), "unresolved edges", stats.ok)}
    </div>
    <div class="grid two">
      ${panel("Runtime", keyValueTable(runtimeRows(health, manifest)))}
      ${panel("Graph Store", keyValueTable(storeRows(manifest, stats)))}
    </div>
  `;
}

async function renderSources() {
  const [configured, loaded] = await Promise.all([fetchMaybe("/sources/configured"), fetchMaybe("/sources")]);
  view.innerHTML = `
    ${sourceMetrics(configured.data, loaded.data)}
    ${panel("Change Preview", snapshotStatusPanel())}
    ${panel("Configured Sources", configured.ok ? configuredSourcesTable(configured.data.items || []) : errorMarkup(configured.error))}
    ${panel("Loaded Sources", loaded.ok ? loadedSourcesTable(loaded.data.items || []) : errorMarkup(loaded.error))}
  `;
}

async function renderJobs() {
  const jobs = await fetchMaybe("/jobs?limit=50");
  view.innerHTML = `
    ${panel(
      "Operations",
      `<div class="toolbar">
        <label class="field small">
          <span>Strict</span>
          <select id="job-strict">
            <option value="true">true</option>
            <option value="false">false</option>
          </select>
        </label>
        <label class="checkbox-field">
          <input id="job-sync" type="checkbox" />
          <span>Sync</span>
        </label>
        <label class="checkbox-field">
          <input id="job-load" type="checkbox" checked />
          <span>Load</span>
        </label>
        <button class="button" type="button" data-job-action="sync">Sync</button>
        <button class="button" type="button" data-job-action="build">Build</button>
        <button class="button" type="button" data-job-action="build-load">Build Load</button>
        <button class="button" type="button" data-job-action="refresh">Refresh</button>
        <button class="button" type="button" data-job-action="refresh-changed">Refresh Changed</button>
      </div>
      <div id="job-action-result" class="stack"></div>`
    )}
    ${panel("Recent Jobs", jobs.ok ? jobsTable(jobs.data.items || []) : errorMarkup(jobs.error))}
  `;
}

async function renderScope() {
  const scope = await fetchMaybe("/scope");
  if (!scope.ok) {
    view.innerHTML = errorMarkup(scope.error);
    return;
  }
  const payload = scope.data;
  view.innerHTML = `
    <div class="grid three">
      ${metric("Status", payload.loaded ? "loaded" : "not loaded", payload.scope_name || "no scope", payload.loaded)}
      ${metric("Sources", numberValue(payload.source_count), "loaded sources", true)}
      ${metric("Generated", payload.generated_at ? formatDate(payload.generated_at) : "unknown", "graph export", true)}
    </div>
    ${panel("Summary", keyValueTable(objectRows(payload.summary || {})))}
    ${panel("Sources", loadedSourcesTable(payload.sources || []))}
  `;
}

async function renderExplore() {
  const [overview, unresolved] = await Promise.all([
    fetchMaybe(`/explore?limit=${state.explore.limit}`),
    fetchMaybe("/reports/unresolved?limit=8&examples=1"),
  ]);
  if (!overview.ok) {
    view.innerHTML = errorMarkup(overview.error);
    return;
  }
  const payload = overview.data;
  view.innerHTML = `
    ${exploreMetrics(payload)}
    ${panel("Start Here", exploreStarters())}
    <div class="grid two">
      ${panel("Entity Types", entityTypesTable(payload.entity_types || []))}
      ${panel("Relationship Types", edgeTypesTable(payload.edge_types || []))}
    </div>
    ${panel("Sources", sourceActivityTable(payload.sources || []))}
    ${panel("Cross Source Relationships", crossSourceEdgesTable(payload.cross_source_edges || []))}
    ${panel("Unresolved Hotspots", unresolved.ok ? unresolvedHotspotsTable(unresolved.data.items || []) : errorMarkup(unresolved.error))}
  `;
}

async function renderSearch() {
  view.innerHTML = `
    ${panel(
      "Search",
      `<form class="toolbar" data-form="search">
        <label class="field">
          <span>Query</span>
          <input name="q" value="${escapeAttr(state.search.q)}" />
        </label>
        <label class="field">
          <span>Type</span>
          <input name="type" value="${escapeAttr(state.search.type)}" placeholder="api_route" />
        </label>
        <label class="field">
          <span>Source</span>
          <input name="source" value="${escapeAttr(state.search.source)}" />
        </label>
        <label class="field small">
          <span>Limit</span>
          <input name="limit" type="number" min="1" max="100" value="${state.search.limit}" />
        </label>
        <button class="button" type="submit">Search</button>
      </form>`
    )}
    <div id="search-results"></div>
    <div id="entity-detail"></div>
  `;
  await runSearch();
}

async function renderUnresolved() {
  view.innerHTML = `
    ${panel(
      "Filters",
      `<form class="toolbar" data-form="unresolved">
        <label class="field">
          <span>Source</span>
          <input name="source" value="${escapeAttr(state.unresolved.source)}" />
        </label>
        <label class="field">
          <span>Edge Type</span>
          <input name="type" value="${escapeAttr(state.unresolved.type)}" placeholder="CALLS_SQL" />
        </label>
        <label class="field small">
          <span>Limit</span>
          <input name="limit" type="number" min="1" max="200" value="${state.unresolved.limit}" />
        </label>
        <label class="field small">
          <span>Examples</span>
          <input name="examples" type="number" min="1" max="10" value="${state.unresolved.examples}" />
        </label>
        <button class="button" type="submit">Apply</button>
      </form>`
    )}
    <div id="unresolved-results">${loadingMarkup()}</div>
  `;
  await runUnresolvedReport();
}

async function renderImpact() {
  view.innerHTML = `
    ${panel(
      "Impact Query",
      `<form class="toolbar" data-form="impact">
        <label class="field wide">
          <span>Entity ID</span>
          <input name="entityId" value="${escapeAttr(state.impact.entityId)}" />
        </label>
        <label class="field small">
          <span>Direction</span>
          <select name="direction">
            ${option("in", "Incoming", state.impact.direction)}
            ${option("out", "Outgoing", state.impact.direction)}
            ${option("both", "Both", state.impact.direction)}
          </select>
        </label>
        <label class="field">
          <span>Profile</span>
          <select name="profile">
            ${option("impact", "Dependency impact", state.impact.profile)}
            ${option("all", "All graph paths", state.impact.profile)}
            ${option("structural", "Structural paths", state.impact.profile)}
          </select>
        </label>
        <label class="field">
          <span>Edge Type</span>
          <input name="type" value="${escapeAttr(state.impact.type)}" placeholder="CALLS_SQL" />
        </label>
        <label class="field small">
          <span>Depth</span>
          <input name="depth" type="number" min="1" max="3" value="${state.impact.depth}" />
        </label>
        <label class="field small">
          <span>Limit</span>
          <input name="limit" type="number" min="1" max="200" value="${state.impact.limit}" />
        </label>
        <button class="button" type="submit">Run</button>
      </form>`
    )}
    <div id="impact-results">${state.impact.entityId ? loadingMarkup() : emptyMarkup("Open an entity from search or paste an entity ID.")}</div>
  `;
  if (state.impact.entityId) {
    await runImpact();
  }
}

async function runSearch() {
  const params = new URLSearchParams();
  if (state.search.q) params.set("q", state.search.q);
  if (state.search.type) params.set("type", state.search.type);
  if (state.search.source) params.set("source", state.search.source);
  params.set("limit", String(state.search.limit));
  const target = document.querySelector("#search-results");
  target.innerHTML = loadingMarkup();
  const result = await fetchMaybe(`/entities/search?${params}`);
  target.innerHTML = result.ok ? panel("Results", searchResultsTable(result.data.items || [])) : errorMarkup(result.error);
}

async function runUnresolvedReport() {
  const params = new URLSearchParams();
  if (state.unresolved.source) params.set("source", state.unresolved.source);
  if (state.unresolved.type) params.set("type", state.unresolved.type);
  params.set("limit", String(state.unresolved.limit));
  params.set("examples", String(state.unresolved.examples));
  const target = document.querySelector("#unresolved-results");
  const result = await fetchMaybe(`/reports/unresolved?${params}`);
  target.innerHTML = result.ok ? unresolvedReportMarkup(result.data) : errorMarkup(result.error);
}

async function runImpact() {
  const target = document.querySelector("#impact-results");
  if (!state.impact.entityId) {
    target.innerHTML = emptyMarkup("Open an entity from search or paste an entity ID.");
    return;
  }
  const params = new URLSearchParams();
  params.set("direction", state.impact.direction);
  params.set("profile", state.impact.profile);
  if (state.impact.type) params.set("type", state.impact.type);
  params.set("depth", String(state.impact.depth));
  params.set("limit", String(state.impact.limit));
  target.innerHTML = loadingMarkup();
  const result = await fetchMaybe(`/entities/${encodeURIComponent(state.impact.entityId)}/impact?${params}`);
  target.innerHTML = result.ok ? impactMarkup(result.data) : errorMarkup(result.error);
}

async function loadEntity(entityId) {
  const detail = document.querySelector("#entity-detail");
  detail.innerHTML = loadingMarkup();
  const [entity, neighbors] = await Promise.all([
    fetchMaybe(`/entities/${encodeURIComponent(entityId)}`),
    fetchMaybe(`/entities/${encodeURIComponent(entityId)}/neighbors?limit=25`),
  ]);
  if (!entity.ok) {
    detail.innerHTML = errorMarkup(entity.error);
    return;
  }
  detail.innerHTML = panel(
    "Entity Detail",
    `<div class="entity-detail">
      ${keyValueTable(entityRows(entity.data))}
      ${neighbors.ok ? neighborsTable(neighbors.data.items || []) : errorMarkup(neighbors.error)}
    </div>`
  );
}

async function submitJob(kind) {
  const result = document.querySelector("#job-action-result");
  const strict = document.querySelector("#job-strict")?.value !== "false";
  const sync = Boolean(document.querySelector("#job-sync")?.checked);
  const load = Boolean(document.querySelector("#job-load")?.checked);
  const payload = jobPayload(kind, strict, sync, load);
  result.innerHTML = loadingMarkup();
  const response = await fetchMaybe(`/jobs/${kind}`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  if (response.ok) {
    result.innerHTML = jobStatusMarkup(response.data);
    pollJob(response.data.job_id);
  } else {
    result.innerHTML = errorMarkup(response.error);
  }
  await refreshJobsPanel();
}

async function checkSnapshotStatus() {
  const target = document.querySelector("#snapshot-status-results");
  if (!target) return;
  const sync = Boolean(document.querySelector("#snapshot-sync")?.checked);
  target.innerHTML = loadingMarkup();
  const response = await fetchMaybe("/snapshot/status", {
    method: "POST",
    body: JSON.stringify({ sync }),
  });
  if (response.ok) {
    state.snapshotStatus = response.data;
    target.innerHTML = snapshotStatusMarkup(response.data);
  } else {
    target.innerHTML = errorMarkup(response.error);
  }
}

function jobPayload(kind, strict, sync, load) {
  if (kind === "sync") return {};
  if (kind === "refresh") return { strict, sync, load };
  if (kind === "refresh-changed") return { strict, sync };
  return { strict, sync };
}

async function pollJob(jobId, attempts = 0) {
  if (!jobId || attempts > 60) return;
  const response = await fetchMaybe(`/jobs/${encodeURIComponent(jobId)}`);
  const result = document.querySelector("#job-action-result");
  if (response.ok && result) {
    result.innerHTML = jobStatusMarkup(response.data);
    await refreshJobsPanel();
    if (!["succeeded", "failed"].includes(response.data.status)) {
      window.setTimeout(() => pollJob(jobId, attempts + 1), 1000);
    }
  }
}

async function refreshJobsPanel() {
  const jobs = await fetchMaybe("/jobs?limit=50");
  const panels = document.querySelectorAll(".panel");
  const recent = panels[panels.length - 1];
  if (recent && jobs.ok) {
    recent.outerHTML = panel("Recent Jobs", jobsTable(jobs.data.items || []));
  }
}

function handleDocumentClick(event) {
  const routeLink = event.target.closest("[data-route-link]");
  if (routeLink) {
    navigateToRoute(routeLink.dataset.routeLink);
    return;
  }
  const searchTypeButton = event.target.closest("[data-search-type]");
  if (searchTypeButton) {
    state.search = { q: "", type: searchTypeButton.dataset.searchType, source: "", limit: 25 };
    navigateToRoute("search");
    return;
  }
  const searchSourceButton = event.target.closest("[data-search-source]");
  if (searchSourceButton) {
    state.search = { q: "", type: "", source: searchSourceButton.dataset.searchSource, limit: 25 };
    navigateToRoute("search");
    return;
  }
  const unresolvedTypeButton = event.target.closest("[data-unresolved-type]");
  if (unresolvedTypeButton) {
    state.unresolved = { source: "", type: unresolvedTypeButton.dataset.unresolvedType, limit: 50, examples: 3 };
    navigateToRoute("unresolved");
    return;
  }
  const unresolvedSourceButton = event.target.closest("[data-unresolved-source]");
  if (unresolvedSourceButton) {
    state.unresolved = { source: unresolvedSourceButton.dataset.unresolvedSource, type: "", limit: 50, examples: 3 };
    navigateToRoute("unresolved");
    return;
  }
  const entityButton = event.target.closest("[data-entity-id]");
  if (entityButton) {
    loadEntity(entityButton.dataset.entityId);
    return;
  }
  const jobButton = event.target.closest("[data-job-action]");
  if (jobButton) {
    submitJob(jobButton.dataset.jobAction);
    return;
  }
  const snapshotButton = event.target.closest("[data-snapshot-action]");
  if (snapshotButton) {
    checkSnapshotStatus();
  }
  const impactButton = event.target.closest("[data-impact-id]");
  if (impactButton) {
    state.impact.entityId = impactButton.dataset.impactId;
    navigateToRoute("impact");
  }
}

function navigateToRoute(routeName) {
  if (!routes[routeName]) return;
  const nextHash = `#${routeName}`;
  if (window.location.hash === nextHash) {
    renderRoute();
  } else {
    window.location.hash = nextHash;
  }
}

function handleDocumentSubmit(event) {
  const form = event.target.closest("form[data-form]");
  if (!form) return;
  event.preventDefault();
  const data = new FormData(form);
  if (form.dataset.form === "search") {
    state.search = {
      q: stringField(data, "q"),
      type: stringField(data, "type"),
      source: stringField(data, "source"),
      limit: numberField(data, "limit", 25),
    };
    runSearch().catch((error) => {
      document.querySelector("#search-results").innerHTML = errorMarkup(error);
    });
  }
  if (form.dataset.form === "unresolved") {
    state.unresolved = {
      source: stringField(data, "source"),
      type: stringField(data, "type"),
      limit: numberField(data, "limit", 50),
      examples: numberField(data, "examples", 3),
    };
    runUnresolvedReport().catch((error) => {
      document.querySelector("#unresolved-results").innerHTML = errorMarkup(error);
    });
  }
  if (form.dataset.form === "impact") {
    state.impact = {
      entityId: stringField(data, "entityId"),
      direction: stringField(data, "direction") || "in",
      profile: stringField(data, "profile") || "impact",
      type: stringField(data, "type"),
      depth: numberField(data, "depth", 2),
      limit: numberField(data, "limit", 100),
    };
    runImpact().catch((error) => {
      document.querySelector("#impact-results").innerHTML = errorMarkup(error);
    });
  }
}

async function fetchMaybe(path, options = {}) {
  try {
    return { ok: true, data: await fetchJson(path, options) };
  } catch (error) {
    return { ok: false, error };
  }
}

async function fetchJson(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      "content-type": "application/json",
      ...(options.headers || {}),
    },
  });
  const text = await response.text();
  const data = text ? JSON.parse(text) : {};
  if (!response.ok) {
    throw new Error(errorMessage(data, response));
  }
  return data;
}

function errorMessage(data, response) {
  if (data && typeof data.detail === "string") return data.detail;
  return `${response.status} ${response.statusText}`.trim();
}

function metric(label, value, note, healthy) {
  return `
    <div class="metric">
      <div class="metric-label">${escapeHtml(label)}</div>
      <div class="metric-value">${escapeHtml(value ?? "unknown")}</div>
      <div class="metric-note">${escapeHtml(note ?? "")}</div>
      <span class="status ${healthy ? "ok" : "warn"}">${healthy ? "available" : "check"}</span>
    </div>
  `;
}

function panel(heading, body, actions = "") {
  return `
    <section class="panel">
      <div class="panel-header">
        <h2>${escapeHtml(heading)}</h2>
        <div>${actions}</div>
      </div>
      <div class="panel-body">${body}</div>
    </section>
  `;
}

function sourceMetrics(configured, loaded) {
  return `
    <div class="grid three">
      ${metric("Configured", numberValue(configured?.count), "expanded sources", Boolean(configured))}
      ${metric("Ready", numberValue(configured?.ready_count), "local sources ready", Boolean(configured))}
      ${metric("Loaded", numberValue(loaded?.count), "graph sources", Boolean(loaded?.loaded))}
    </div>
  `;
}

function configuredSourcesTable(items) {
  if (!items.length) return emptyMarkup("No configured sources.");
  const rows = items
    .map(
      (item) => `
        <tr>
          <td>${status(item.ready ? "ready" : "not ready", item.ready ? "ok" : "warn")}</td>
          <td>${escapeHtml(item.name)}</td>
          <td>${escapeHtml(item.type)}</td>
          <td class="mono">${escapeHtml(item.resolved_path || "")}</td>
          <td>${inlineList(item.problems || [])}</td>
        </tr>`
    )
    .join("");
  return table(["Status", "Name", "Type", "Path", "Problems"], rows);
}

function loadedSourcesTable(items) {
  if (!items.length) return emptyMarkup("No loaded sources.");
  const rows = items
    .map(
      (item) => `
        <tr>
          <td>${escapeHtml(item.name)}</td>
          <td>${escapeHtml(item.type || "")}</td>
          <td class="mono">${escapeHtml(item.ref || "")}</td>
          <td class="mono">${escapeHtml(item.commit || "")}</td>
          <td class="mono">${escapeHtml(item.path || "")}</td>
        </tr>`
    )
    .join("");
  return table(["Name", "Type", "Ref", "Commit", "Path"], rows);
}

function exploreMetrics(payload) {
  const summary = payload.summary || {};
  return `
    <div class="grid three">
      ${metric("Sources", numberValue(payload.source_count), "loaded sources", Boolean(payload.loaded))}
      ${metric("Entities", numberValue(summary.entity_count), "graph entities", Boolean(payload.loaded))}
      ${metric("Edges", numberValue(summary.edge_count), "relationships", Boolean(payload.loaded))}
      ${metric("Resolved", numberValue(summary.resolved_edge_count), "linked edges", Boolean(payload.loaded))}
      ${metric("Unresolved", numberValue(summary.unresolved_edge_count), "unlinked references", Boolean(payload.loaded))}
      ${metric("Generated", payload.generated_at ? formatDate(payload.generated_at) : "unknown", payload.scope_name || "", Boolean(payload.loaded))}
    </div>
  `;
}

function exploreStarters() {
  return `
    <div class="action-grid">
      ${actionButton("API Routes", "Find declared HTTP routes", "data-search-type", "api_route")}
      ${actionButton("Stored Procedures", "Find SQL procedures", "data-search-type", "stored_procedure")}
      ${actionButton("SQL Tables", "Find table declarations", "data-search-type", "sql_table")}
      ${actionButton("Service Calls", "Review unresolved service calls", "data-unresolved-type", "CALLS_SERVICE")}
      ${actionButton("SQL Calls", "Review unresolved SQL calls", "data-unresolved-type", "CALLS_SQL")}
      ${actionButton("Missing Coverage", "Open unresolved groups", "data-route-link", "unresolved")}
    </div>
  `;
}

function actionButton(label, note, dataAttr, value) {
  return `
    <button class="action-button" type="button" ${dataAttr}="${escapeAttr(value)}">
      <span>${escapeHtml(label)}</span>
      <small>${escapeHtml(note)}</small>
    </button>
  `;
}

function entityTypesTable(items) {
  if (!items.length) return emptyMarkup("No entity types.");
  const rows = items
    .map(
      (item) => `
        <tr>
          <td>${escapeHtml(item.entity_type || "")}</td>
          <td>${numberValue(item.entity_count)}</td>
          <td class="row-actions">
            <button class="button secondary" type="button" data-search-type="${escapeAttr(item.entity_type || "")}">Search</button>
          </td>
        </tr>`
    )
    .join("");
  return table(["Type", "Entities", ""], rows);
}

function edgeTypesTable(items) {
  if (!items.length) return emptyMarkup("No relationship types.");
  const rows = items
    .map(
      (item) => `
        <tr>
          <td>${escapeHtml(item.edge_type || "")}</td>
          <td>${numberValue(item.edge_count)}</td>
          <td>${numberValue(item.resolved_edge_count)}</td>
          <td>${numberValue(item.unresolved_edge_count)}</td>
          <td class="row-actions">
            <button class="button secondary" type="button" data-unresolved-type="${escapeAttr(item.edge_type || "")}">Unresolved</button>
          </td>
        </tr>`
    )
    .join("");
  return table(["Edge", "Total", "Resolved", "Unresolved", ""], rows);
}

function sourceActivityTable(items) {
  if (!items.length) return emptyMarkup("No source activity.");
  const rows = items
    .map(
      (item) => `
        <tr>
          <td>${escapeHtml(item.source_name || "")}</td>
          <td>${escapeHtml(item.source_type || "")}</td>
          <td>${numberValue(item.entity_count)}</td>
          <td>${numberValue(item.edge_count)}</td>
          <td>${numberValue(item.unresolved_edge_count)}</td>
          <td class="row-actions">
            <button class="button secondary" type="button" data-search-source="${escapeAttr(item.source_name || "")}">Search</button>
            <button class="button secondary" type="button" data-unresolved-source="${escapeAttr(item.source_name || "")}">Unresolved</button>
          </td>
        </tr>`
    )
    .join("");
  return table(["Source", "Type", "Entities", "Edges", "Unresolved", ""], rows);
}

function crossSourceEdgesTable(items) {
  if (!items.length) return emptyMarkup("No cross-source relationships in the returned sample.");
  const rows = items
    .map(
      (item) => `
        <tr>
          <td>${escapeHtml(item.from_source || "")}</td>
          <td>${escapeHtml(item.to_source || "")}</td>
          <td>${escapeHtml(item.edge_type || "")}</td>
          <td>${numberValue(item.edge_count)}</td>
          <td class="row-actions">
            <button class="button secondary" type="button" data-search-source="${escapeAttr(item.from_source || "")}">From</button>
            <button class="button secondary" type="button" data-search-source="${escapeAttr(item.to_source || "")}">To</button>
          </td>
        </tr>`
    )
    .join("");
  return table(["From Source", "To Source", "Edge", "Count", ""], rows);
}

function unresolvedHotspotsTable(items) {
  if (!items.length) return emptyMarkup("No unresolved hotspots.");
  const rows = items
    .map(
      (item) => `
        <tr>
          <td>${status(item.classification || "unknown", classificationTone(item.classification))}</td>
          <td>${escapeHtml(item.edge_type || "")}</td>
          <td>${escapeHtml(item.to_name || "")}</td>
          <td>${numberValue(item.count)}</td>
          <td>${inlineList(item.source_names || [])}</td>
          <td class="row-actions">
            <button class="button secondary" type="button" data-unresolved-type="${escapeAttr(item.edge_type || "")}">Open</button>
          </td>
        </tr>`
    )
    .join("");
  return table(["Class", "Edge", "Target", "Count", "Sources", ""], rows);
}

function snapshotStatusPanel() {
  return `
    <div class="stack">
      <div class="toolbar">
        <label class="checkbox-field">
          <input id="snapshot-sync" type="checkbox" />
          <span>Sync</span>
        </label>
        <button class="button" type="button" data-snapshot-action="status">Check Changes</button>
      </div>
      <div id="snapshot-status-results">
        ${state.snapshotStatus ? snapshotStatusMarkup(state.snapshotStatus) : emptyMarkup("No change preview has been run.")}
      </div>
    </div>
  `;
}

function snapshotStatusMarkup(payload) {
  const items = payload.items || [];
  return `
    <div class="stack">
      <div class="grid three">
        ${metric("Changed", numberValue(payload.changed_count), "sources", true)}
        ${metric("Unchanged", numberValue(payload.unchanged_count), "sources", true)}
        ${metric("Total", numberValue(payload.count), "configured sources", true)}
      </div>
      ${snapshotStatusTable(items)}
    </div>
  `;
}

function snapshotStatusTable(items) {
  if (!items.length) return emptyMarkup("No sources returned.");
  const rows = items
    .map(
      (item) => `
        <tr>
          <td>${status(item.status || "unknown", snapshotStatusTone(item.status))}</td>
          <td>${escapeHtml(item.source_name || "")}</td>
          <td>${inlineList(item.reasons || [])}</td>
          <td>${numberValue((item.added_files || []).length)}</td>
          <td>${numberValue((item.modified_files || []).length)}</td>
          <td>${numberValue((item.removed_files || []).length)}</td>
        </tr>`
    )
    .join("");
  return table(["Status", "Source", "Reasons", "Added", "Modified", "Removed"], rows);
}

function jobsTable(items) {
  if (!items.length) return emptyMarkup("No jobs.");
  const rows = items
    .map(
      (item) => `
        <tr>
          <td>${status(item.status || "unknown", statusTone(item.status))}</td>
          <td>${escapeHtml(item.kind || "")}</td>
          <td class="mono">${escapeHtml(item.job_id || "")}</td>
          <td>${escapeHtml(formatDate(item.created_at))}</td>
          <td>${escapeHtml(item.finished_at ? formatDate(item.finished_at) : "")}</td>
        </tr>`
    )
    .join("");
  return table(["Status", "Kind", "Job", "Created", "Finished"], rows);
}

function searchResultsTable(items) {
  if (!items.length) return emptyMarkup("No entities.");
  const rows = items
    .map(
      (item) => `
        <tr>
          <td><button class="button secondary" type="button" data-entity-id="${escapeAttr(item.entity_id)}">Open</button></td>
          <td><button class="button secondary" type="button" data-impact-id="${escapeAttr(item.entity_id)}">Impact</button></td>
          <td>${escapeHtml(item.entity_type || "")}</td>
          <td>${escapeHtml(item.name || "")}</td>
          <td>${escapeHtml(item.source_name || "")}</td>
          <td class="mono">${escapeHtml(item.file_path || "")}</td>
        </tr>`
    )
    .join("");
  return table(["", "", "Type", "Name", "Source", "File"], rows);
}

function neighborsTable(items) {
  if (!items.length) return emptyMarkup("No neighbors.");
  const rows = items
    .map((item) => {
      const edge = item.edge || {};
      const neighbor = item.neighbor || {};
      return `
        <tr>
          <td>${escapeHtml(item.direction || "")}</td>
          <td>${escapeHtml(item.depth || "")}</td>
          <td>${escapeHtml(edge.edge_type || "")}</td>
          <td>${escapeHtml(neighbor.entity_type || neighbor.target_type || "")}</td>
          <td>${escapeHtml(neighbor.name || "")}</td>
          <td>${escapeHtml(edge.source_name || "")}</td>
        </tr>`;
    })
    .join("");
  return table(["Direction", "Depth", "Edge", "Type", "Name", "Source"], rows);
}

function impactMarkup(payload) {
  const entity = payload.entity || {};
  return `
    <div class="grid three">
      ${metric("Affected Sources", numberValue(payload.affected_source_count), "grouped by source", true)}
      ${metric("Paths", numberValue(payload.count), "returned paths", true)}
      ${metric("Depth", numberValue(payload.depth), `${payload.direction || ""} / ${payload.profile || ""}`, true)}
    </div>
    ${panel("Start Entity", keyValueTable(entityRows(entity)))}
    ${panel("Affected Sources", affectedSourcesTable(payload.affected_sources || []))}
    ${panel("Paths", neighborsTable(payload.items || []))}
  `;
}

function affectedSourcesTable(items) {
  if (!items.length) return emptyMarkup("No affected sources.");
  const rows = items
    .map(
      (item) => `
        <tr>
          <td>${escapeHtml(item.source_name || "")}</td>
          <td>${numberValue(item.count)}</td>
          <td>${numberValue(item.min_depth)}</td>
          <td>${inlineList(item.edge_types || [])}</td>
          <td>${inlineList(item.entity_types || [])}</td>
        </tr>`
    )
    .join("");
  return table(["Source", "Paths", "Min Depth", "Edges", "Entity Types"], rows);
}

function unresolvedReportMarkup(report) {
  const summary = report.summary || {};
  const groups = report.items || [];
  const groupMarkup = groups.length
    ? groups.map((group) => unresolvedGroupMarkup(group)).join("")
    : emptyMarkup("No unresolved groups.");
  return `
    <div class="grid three">
      ${metric("Unresolved Edges", numberValue(summary.unresolved_edge_count), "matching edges", true)}
      ${metric("Groups", numberValue(summary.group_count), "target groups", true)}
      ${metric("Returned", numberValue(summary.returned_group_count), "visible groups", true)}
    </div>
    ${panel("Classification Edge Counts", keyValueTable(objectRows(summary.classification_edge_counts || {})))}
    <div class="stack">${groupMarkup}</div>
  `;
}

function unresolvedGroupMarkup(group) {
  const examples = group.examples || [];
  const exampleRows = examples
    .map(
      (example) => `
        <tr>
          <td>${escapeHtml(example.source_name || "")}</td>
          <td class="mono">${escapeHtml(example.file_path || "")}</td>
          <td>${escapeHtml(example.line_number || "")}</td>
          <td>${escapeHtml(example.parser || "")}</td>
          <td class="mono">${escapeHtml(example.raw_target || example.normalized_target || "")}</td>
        </tr>`
    )
    .join("");
  return panel(
    `${group.edge_type} to ${group.to_name}`,
    `<div class="stack">
      <div class="inline-list">
        ${status(group.classification, classificationTone(group.classification))}
        <span class="chip">${escapeHtml(group.to_type)}</span>
        <span class="chip">${numberValue(group.count)} edges</span>
        ${inlineList(group.source_names || [])}
      </div>
      <div class="muted">${escapeHtml(group.classification_reason || "")}</div>
      ${table(["Source", "File", "Line", "Parser", "Target"], exampleRows)}
    </div>`
  );
}

function keyValueTable(rows) {
  if (!rows.length) return emptyMarkup("No values.");
  const body = rows
    .map(
      ([key, value]) => `
        <tr>
          <th>${escapeHtml(key)}</th>
          <td>${escapeHtml(formatValue(value))}</td>
        </tr>`
    )
    .join("");
  return `<div class="table-wrap"><table><tbody>${body}</tbody></table></div>`;
}

function table(headers, rows) {
  return `
    <div class="table-wrap">
      <table>
        <thead><tr>${headers.map((header) => `<th>${escapeHtml(header)}</th>`).join("")}</tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
  `;
}

function option(value, label, selected) {
  return `<option value="${escapeAttr(value)}" ${value === selected ? "selected" : ""}>${escapeHtml(label)}</option>`;
}

function runtimeRows(health, manifest) {
  const endpoints = manifest.ok ? manifest.data.endpoints || [] : [];
  return [
    ["Health", health.ok ? health.data.status : health.error.message],
    ["Version", health.ok ? health.data.version : ""],
    ["Config", manifest.ok ? manifest.data.config?.path : ""],
    ["Schema", manifest.ok ? manifest.data.schema_version : ""],
    ["Change Preview", endpointAvailable(endpoints, "POST", "/snapshot/status") ? "available" : "unavailable"],
    ["Refresh", endpointAvailable(endpoints, "POST", "/refresh") ? "available" : "unavailable"],
    ["Refresh Changed", endpointAvailable(endpoints, "POST", "/jobs/refresh-changed") ? "available" : "unavailable"],
  ];
}

function storeRows(manifest, stats) {
  return [
    ["Store", manifest.ok ? manifest.data.graph_store?.type : ""],
    ["URI", manifest.ok ? manifest.data.graph_store?.uri : ""],
    ["Database", manifest.ok ? manifest.data.graph_store?.database || "default" : ""],
    ["Stats", stats.ok ? "available" : stats.error?.message || "unavailable"],
  ];
}

function objectRows(value) {
  return Object.entries(value || {});
}

function entityRows(entity) {
  return [
    ["ID", entity.entity_id],
    ["Type", entity.entity_type],
    ["Name", entity.name],
    ["Source", entity.source_name],
    ["File", entity.file_path],
    ["Line", entity.line_number],
    ["Aliases", (entity.aliases || []).join(", ")],
    ["Properties", JSON.stringify(entity.properties || {}, null, 2)],
  ];
}

function status(label, tone) {
  return `<span class="status ${escapeAttr(tone || "")}">${escapeHtml(label || "")}</span>`;
}

function statusTone(value) {
  if (value === "succeeded" || value === "synced" || value === "built" || value === "refreshed") return "ok";
  if (value === "failed") return "bad";
  return "warn";
}

function snapshotStatusTone(value) {
  if (value === "unchanged") return "ok";
  if (value === "changed" || value === "new") return "warn";
  return "";
}

function endpointAvailable(endpoints, method, path) {
  return endpoints.some((endpoint) => endpoint.method === method && endpoint.path === path && endpoint.available);
}

function jobStatusMarkup(job) {
  const result = job.result || {};
  const error = job.error || {};
  return `
    <div class="message">
      <div class="inline-list">
        ${status(job.status || "unknown", statusTone(job.status))}
        <span class="chip">${escapeHtml(job.kind || "")}</span>
        <span class="chip mono">${escapeHtml(job.job_id || "")}</span>
      </div>
      ${job.finished_at ? `<div class="muted">${escapeHtml(formatDate(job.finished_at))}</div>` : ""}
      ${job.status === "failed" ? `<div class="message error">${escapeHtml(error.message || "Job failed")}</div>` : ""}
      ${["refresh", "refresh-changed"].includes(job.kind) && result.status ? refreshSummaryMarkup(result) : ""}
    </div>
  `;
}

function refreshSummaryMarkup(result) {
  const changes = result.changes || {};
  const cache = result.cache || {};
  const load = result.load || {};
  return `
    <div class="refresh-summary">
      ${metric("Changed", numberValue(changes.changed_count), "sources", true)}
      ${metric("Rebuilt", numberValue(cache.rebuilt_count), "source graphs", true)}
      ${metric("Reused", numberValue(cache.reused_count), "source graphs", true)}
      ${keyValueTable([
        ["Load", load.action || ""],
        ["Reason", load.reason || ""],
        ["Changed Sources", (changes.changed_sources || []).join(", ")],
      ])}
    </div>
  `;
}

function classificationTone(value) {
  if (value === "ambiguous_target") return "warn";
  if (value === "likely_missing_source") return "bad";
  if (value === "likely_parser_gap") return "warn";
  return "";
}

function inlineList(items) {
  if (!items.length) return "";
  return `<span class="inline-list">${items.map((item) => `<span class="chip">${escapeHtml(item)}</span>`).join("")}</span>`;
}

function loadingMarkup() {
  return `<div class="message">Loading</div>`;
}

function emptyMarkup(message) {
  return `<div class="message muted">${escapeHtml(message)}</div>`;
}

function errorMarkup(error) {
  const message = error instanceof Error ? error.message : String(error);
  return `<div class="message error">${escapeHtml(message)}</div>`;
}

function stringField(data, name) {
  const value = data.get(name);
  return typeof value === "string" ? value.trim() : "";
}

function numberField(data, name, fallback) {
  const value = Number(data.get(name));
  return Number.isFinite(value) && value > 0 ? value : fallback;
}

function numberValue(value) {
  return value === undefined || value === null || value === "" ? "0" : String(value);
}

function formatValue(value) {
  if (value === undefined || value === null || value === "") return "";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function formatDate(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString();
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function escapeAttr(value) {
  return escapeHtml(value);
}
