const routes = {
  overview: {
    title: "Overview",
    meta: "Loaded graph, source health, and open risk",
    render: renderOverview,
  },
  dashboard: {
    title: "Overview",
    meta: "Loaded graph, source health, and open risk",
    render: renderOverview,
    navRoute: "overview",
  },
  search: {
    title: "Search",
    meta: "Find graph entities and open their evidence",
    render: renderSearch,
  },
  impact: {
    title: "Impact",
    meta: "Trace blast radius from an entity",
    render: renderImpact,
  },
  unresolved: {
    title: "Unresolved",
    meta: "Find missing sources, parser gaps, and ambiguous targets",
    render: renderUnresolved,
  },
  jobs: {
    title: "Jobs",
    meta: "Sync, build, and refresh operations",
    render: renderJobs,
  },
  sources: {
    title: "Sources",
    meta: "Configured, loaded, and changed repositories",
    render: renderSources,
    navRoute: "overview",
  },
  scope: {
    title: "Scope",
    meta: "Loaded graph scope",
    render: renderScope,
    navRoute: "overview",
  },
  explore: {
    title: "Explore",
    meta: "Understand graph shape and drill into evidence",
    render: renderExplore,
    navRoute: "overview",
  },
  source: {
    title: "Source",
    meta: "Inspect one repository's surface and dependencies",
    render: renderSource,
    navRoute: "overview",
  },
  entity: {
    title: "Entity",
    meta: "Inspect one graph entity and its direct relationships",
    render: renderEntity,
    navRoute: "search",
  },
  relationships: {
    title: "Relationships",
    meta: "Find edge evidence between sources and entity types",
    render: renderRelationships,
    navRoute: "search",
  },
};

const view = document.querySelector("#app-view");
const title = document.querySelector("#page-title");
const pageMeta = document.querySelector("#page-meta");
const runtimeState = document.querySelector("#runtime-state");
const refreshButton = document.querySelector("#refresh-button");
const apiBase = document.querySelector("#api-base");

const state = {
  currentRoute: "overview",
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
  source: {
    name: "",
    limit: 50,
  },
  entity: {
    id: "",
    limit: 50,
  },
  relationships: {
    fromSource: "",
    toSource: "",
    type: "",
    fromType: "",
    toType: "",
    resolved: "",
    limit: 100,
  },
  snippet: {
    source: "",
    path: "",
    line: 1,
    context: 3,
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
  return routes[hash] ? hash : "overview";
}

function renderRoute() {
  const routeName = activeRoute();
  state.currentRoute = routeName;
  const route = routes[routeName];
  const navRoute = route.navRoute || routeName;
  document.querySelectorAll("[data-route]").forEach((link) => {
    link.classList.toggle("active", link.dataset.route === navRoute);
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

async function renderOverview() {
  const [health, manifest, scope, stats, overview, unresolved] = await Promise.all([
    fetchMaybe("/health"),
    fetchMaybe("/manifest"),
    fetchMaybe("/scope"),
    fetchMaybe("/stats"),
    fetchMaybe(`/explore?limit=${state.explore.limit}`),
    fetchMaybe("/reports/unresolved?limit=8&examples=1"),
  ]);
  const scopeData = scope.data || {};
  const summary = scopeData.summary || {};
  const statsData = stats.data || {};
  const overviewData = overview.data || {};
  view.innerHTML = `
    <div class="grid three">
      ${metric("Runtime", health.ok ? "ok" : "error", health.ok ? health.data.version : health.error, health.ok)}
      ${metric("Graph", scopeData.loaded ? "loaded" : "not loaded", scopeData.scope_name || "scope unavailable", scopeData.loaded)}
      ${metric("Sources", numberValue(scopeData.source_count), "loaded sources", true)}
      ${metric("Entities", numberValue(summary.entity_count || statsData.entity_count), "graph entities", stats.ok)}
      ${metric("Edges", numberValue(summary.edge_count || statsData.edge_count), "graph relationships", stats.ok)}
      ${metric("Unresolved", numberValue(summary.unresolved_edge_count || statsData.unresolved_edge_count), "unresolved edges", stats.ok)}
    </div>
    ${panel("Start Here", workflowStarters())}
    <div class="grid two">
      ${panel("Source Activity", overview.ok ? sourceActivityTable(overviewData.sources || []) : errorMarkup(overview.error))}
      ${panel("Needs Attention", unresolved.ok ? unresolvedHotspotsTable(unresolved.data.items || []) : errorMarkup(unresolved.error))}
    </div>
    ${panel("Change Preview", snapshotStatusPanel())}
    ${advancedPanel(
      "Advanced runtime details",
      `<div class="grid two">
        ${panel("Runtime", keyValueTable(runtimeRows(health, manifest)))}
        ${panel("Graph Store", keyValueTable(storeRows(manifest, stats)))}
      </div>`
    )}
  `;
}

async function renderDashboard() {
  await renderOverview();
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

async function renderSource() {
  if (!state.source.name) {
    const overview = await fetchMaybe(`/explore?limit=${state.source.limit}`);
    view.innerHTML = `
      ${panel("Select Source", overview.ok ? sourceActivityTable(overview.data.sources || []) : errorMarkup(overview.error))}
    `;
    return;
  }
  const result = await fetchMaybe(
    `/sources/${encodeURIComponent(state.source.name)}/overview?limit=${state.source.limit}`
  );
  if (!result.ok) {
    view.innerHTML = errorMarkup(result.error);
    return;
  }
  view.innerHTML = sourceOverviewMarkup(result.data);
}

async function renderSearch() {
  view.innerHTML = `
    ${panel(
      "Find Something",
      `<form class="stack" data-form="search">
        <div class="query-row">
          <label class="field query-field">
            <span>Search</span>
            <input name="q" value="${escapeAttr(state.search.q)}" placeholder="route, table, service, symbol" />
          </label>
          <button class="button" type="submit">Search</button>
        </div>
        <div class="quick-actions">
          <button class="button secondary" type="button" data-search-type="api_route">API Routes</button>
          <button class="button secondary" type="button" data-search-type="stored_procedure">Stored Procedures</button>
          <button class="button secondary" type="button" data-search-type="sql_table">SQL Tables</button>
          <button class="button secondary" type="button" data-route-link="unresolved">Unresolved</button>
        </div>
        ${advancedControls(
          `<div class="toolbar">
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
          </div>`
        )}
      </form>`
    )}
    <div id="search-results"></div>
  `;
  await runSearch();
}

async function renderEntity() {
  view.innerHTML = `
    ${panel(
      "Entity Lookup",
      `<form class="toolbar" data-form="entity">
        <label class="field wide">
          <span>Entity ID</span>
          <input name="entityId" value="${escapeAttr(state.entity.id)}" />
        </label>
        <label class="field small">
          <span>Limit</span>
          <input name="limit" type="number" min="1" max="200" value="${state.entity.limit}" />
        </label>
        <button class="button" type="submit">Open</button>
      </form>`
    )}
    <div id="entity-results">${state.entity.id ? loadingMarkup() : emptyMarkup("Open an entity from search or paste an entity ID.")}</div>
  `;
  if (state.entity.id) {
    await runEntityOverview();
  }
}

async function renderRelationships() {
  view.innerHTML = `
    ${panel("Relationship Evidence", relationshipsForm())}
    <div id="relationship-results">${loadingMarkup()}</div>
    <div id="snippet-results"></div>
  `;
  await runRelationshipSearch();
  await runSnippetLookup();
}

async function renderUnresolved() {
  view.innerHTML = `
    ${panel(
      "Needs Attention",
      `<form class="stack" data-form="unresolved">
        <div class="quick-actions">
          <button class="button secondary" type="button" data-unresolved-type="CALLS_SERVICE">Service Calls</button>
          <button class="button secondary" type="button" data-unresolved-type="CALLS_SQL">SQL Calls</button>
          <button class="button secondary" type="button" data-unresolved-type="IMPORTS">Imports</button>
          <button class="button secondary" type="submit">Refresh</button>
        </div>
        ${advancedControls(
          `<div class="toolbar">
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
          </div>`
        )}
      </form>`
    )}
    <div id="unresolved-results">${loadingMarkup()}</div>
  `;
  await runUnresolvedReport();
}

async function renderImpact() {
  view.innerHTML = `
    ${panel(
      "Blast Radius",
      `<form class="stack" data-form="impact">
        <div class="query-row">
          <label class="field query-field">
            <span>Entity ID</span>
            <input name="entityId" value="${escapeAttr(state.impact.entityId)}" />
          </label>
          <button class="button" type="submit">Run Impact</button>
        </div>
        <div class="quick-actions">
          <button class="button secondary" type="button" data-impact-direction="in">Show Callers</button>
          <button class="button secondary" type="button" data-impact-direction="out">Show Dependencies</button>
          <button class="button secondary" type="button" data-impact-direction="both">Show Both</button>
        </div>
        ${advancedControls(
          `<div class="toolbar">
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
          </div>`
        )}
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

async function runEntityOverview() {
  const target = document.querySelector("#entity-results");
  if (!state.entity.id) {
    target.innerHTML = emptyMarkup("Open an entity from search or paste an entity ID.");
    return;
  }
  const params = new URLSearchParams();
  params.set("limit", String(state.entity.limit));
  target.innerHTML = loadingMarkup();
  const result = await fetchMaybe(`/entities/${encodeURIComponent(state.entity.id)}/overview?${params}`);
  target.innerHTML = result.ok ? entityOverviewMarkup(result.data) : errorMarkup(result.error);
}

async function runRelationshipSearch() {
  const params = new URLSearchParams();
  if (state.relationships.fromSource) params.set("from_source", state.relationships.fromSource);
  if (state.relationships.toSource) params.set("to_source", state.relationships.toSource);
  if (state.relationships.type) params.set("type", state.relationships.type);
  if (state.relationships.fromType) params.set("from_type", state.relationships.fromType);
  if (state.relationships.toType) params.set("to_type", state.relationships.toType);
  if (state.relationships.resolved) params.set("resolved", state.relationships.resolved);
  params.set("limit", String(state.relationships.limit));
  const target = document.querySelector("#relationship-results");
  target.innerHTML = loadingMarkup();
  const result = await fetchMaybe(`/relationships/search?${params}`);
  target.innerHTML = result.ok ? relationshipSearchMarkup(result.data) : errorMarkup(result.error);
}

async function runSnippetLookup() {
  const target = document.querySelector("#snippet-results");
  if (!target) return;
  if (!state.snippet.source || !state.snippet.path) {
    target.innerHTML = "";
    return;
  }
  const params = new URLSearchParams();
  params.set("path", state.snippet.path);
  params.set("line", String(state.snippet.line || 1));
  params.set("context", String(state.snippet.context || 3));
  target.innerHTML = panel("Source Snippet", loadingMarkup());
  const result = await fetchMaybe(`/sources/${encodeURIComponent(state.snippet.source)}/files/snippet?${params}`);
  target.innerHTML = panel("Source Snippet", result.ok ? sourceSnippetMarkup(result.data) : errorMarkup(result.error));
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
  const searchQueryButton = event.target.closest("[data-search-query]");
  if (searchQueryButton) {
    state.search = { q: searchQueryButton.dataset.searchQuery || "", type: "", source: "", limit: 25 };
    navigateToRoute("search");
    return;
  }
  const sourceSearchTypeButton = event.target.closest("[data-source-search-type]");
  if (sourceSearchTypeButton) {
    state.search = {
      q: "",
      type: sourceSearchTypeButton.dataset.sourceSearchType,
      source: state.source.name,
      limit: 25,
    };
    navigateToRoute("search");
    return;
  }
  const unresolvedTypeButton = event.target.closest("[data-unresolved-type]");
  if (unresolvedTypeButton) {
    state.unresolved = { source: "", type: unresolvedTypeButton.dataset.unresolvedType, limit: 50, examples: 3 };
    navigateToRoute("unresolved");
    return;
  }
  const sourceUnresolvedTypeButton = event.target.closest("[data-source-unresolved-type]");
  if (sourceUnresolvedTypeButton) {
    state.unresolved = {
      source: state.source.name,
      type: sourceUnresolvedTypeButton.dataset.sourceUnresolvedType,
      limit: 50,
      examples: 3,
    };
    navigateToRoute("unresolved");
    return;
  }
  const unresolvedSourceButton = event.target.closest("[data-unresolved-source]");
  if (unresolvedSourceButton) {
    state.unresolved = { source: unresolvedSourceButton.dataset.unresolvedSource, type: "", limit: 50, examples: 3 };
    navigateToRoute("unresolved");
    return;
  }
  const sourceButton = event.target.closest("[data-source-name]");
  if (sourceButton) {
    state.source.name = sourceButton.dataset.sourceName;
    navigateToRoute("source");
    return;
  }
  const relationshipButton = event.target.closest("[data-relationship-filter]");
  if (relationshipButton) {
    state.relationships = relationshipStateFromDataset(relationshipButton.dataset);
    state.snippet = { source: "", path: "", line: 1, context: 3 };
    navigateToRoute("relationships");
    return;
  }
  const snippetButton = event.target.closest("[data-snippet-source]");
  if (snippetButton) {
    state.snippet = {
      source: snippetButton.dataset.snippetSource || "",
      path: snippetButton.dataset.snippetPath || "",
      line: Number(snippetButton.dataset.snippetLine || 1),
      context: Number(snippetButton.dataset.snippetContext || 3),
    };
    if (state.currentRoute === "relationships") {
      runSnippetLookup().catch((error) => {
        document.querySelector("#snippet-results").innerHTML = panel("Source Snippet", errorMarkup(error));
      });
    } else {
      navigateToRoute("relationships");
    }
    return;
  }
  const entitySourceTypeButton = event.target.closest("[data-entity-source-type]");
  if (entitySourceTypeButton) {
    state.search = {
      q: "",
      type: entitySourceTypeButton.dataset.entitySourceType,
      source: entitySourceTypeButton.dataset.entitySourceName || "",
      limit: 25,
    };
    navigateToRoute("search");
    return;
  }
  const entityButton = event.target.closest("[data-entity-id]");
  if (entityButton) {
    state.entity.id = entityButton.dataset.entityId;
    navigateToRoute("entity");
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
  const impactDirectionButton = event.target.closest("[data-impact-direction]");
  if (impactDirectionButton) {
    state.impact.direction = impactDirectionButton.dataset.impactDirection || "in";
    const directionSelect = document.querySelector('form[data-form="impact"] select[name="direction"]');
    if (directionSelect) {
      directionSelect.value = state.impact.direction;
    }
    if (state.currentRoute === "impact" && state.impact.entityId) {
      runImpact().catch((error) => {
        document.querySelector("#impact-results").innerHTML = errorMarkup(error);
      });
    }
    return;
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

function relationshipStateFromDataset(dataset) {
  return {
    fromSource: dataset.relationshipFromSource || "",
    toSource: dataset.relationshipToSource || "",
    type: dataset.relationshipType || "",
    fromType: dataset.relationshipFromType || "",
    toType: dataset.relationshipToType || "",
    resolved: dataset.relationshipResolved || "",
    limit: Number(dataset.relationshipLimit || 100),
  };
}

function handleDocumentSubmit(event) {
  const form = event.target.closest("form[data-form]");
  if (!form) return;
  event.preventDefault();
  const data = new FormData(form);
  if (form.dataset.form === "global-search") {
    state.search = {
      q: stringField(data, "globalQuery"),
      type: "",
      source: "",
      limit: 25,
    };
    navigateToRoute("search");
    return;
  }
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
  if (form.dataset.form === "entity") {
    state.entity = {
      id: stringField(data, "entityId"),
      limit: numberField(data, "limit", 50),
    };
    runEntityOverview().catch((error) => {
      document.querySelector("#entity-results").innerHTML = errorMarkup(error);
    });
  }
  if (form.dataset.form === "relationships") {
    state.relationships = {
      fromSource: stringField(data, "fromSource"),
      toSource: stringField(data, "toSource"),
      type: stringField(data, "type"),
      fromType: stringField(data, "fromType"),
      toType: stringField(data, "toType"),
      resolved: stringField(data, "resolved"),
      limit: numberField(data, "limit", 100),
    };
    runRelationshipSearch().catch((error) => {
      document.querySelector("#relationship-results").innerHTML = errorMarkup(error);
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
          <td class="row-actions">
            <button class="button secondary" type="button" data-source-name="${escapeAttr(item.name || "")}">Open</button>
          </td>
        </tr>`
    )
    .join("");
  return table(["Name", "Type", "Ref", "Commit", "Path", ""], rows);
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

function workflowStarters() {
  return `
    <div class="action-grid">
      ${actionButton("Find Something", "Search routes, data objects, packages, and symbols", "data-route-link", "search")}
      ${actionButton("Review Impact", "Trace callers and dependencies from a known entity", "data-route-link", "impact")}
      ${actionButton("Needs Attention", "Group unresolved references by likely cause", "data-route-link", "unresolved")}
      ${actionButton("Refresh Graph", "Sync sources and update loaded graph data", "data-route-link", "jobs")}
      ${actionButton("Source Map", "Open source-level ownership and dependency summaries", "data-route-link", "explore")}
      ${actionButton("API Routes", "Start with declared HTTP routes", "data-search-type", "api_route")}
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

function advancedPanel(label, body) {
  return `
    <details class="advanced-panel">
      <summary>${escapeHtml(label)}</summary>
      <div class="advanced-body">${body}</div>
    </details>
  `;
}

function advancedControls(body) {
  return `
    <details class="advanced-controls">
      <summary>Advanced</summary>
      <div class="advanced-body">${body}</div>
    </details>
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
            <button class="button secondary" type="button" data-source-name="${escapeAttr(item.source_name || "")}">Open</button>
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
            ${relationshipFilterButton("Evidence", {
              fromSource: item.from_source,
              toSource: item.to_source,
              type: item.edge_type,
              resolved: "true",
            })}
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

function sourceOverviewMarkup(payload) {
  const source = payload.source || {};
  const summary = payload.summary || {};
  return `
    <div class="grid three">
      ${metric("Entities", numberValue(summary.entity_count), "owned by source", true)}
      ${metric("Edges", numberValue(summary.edge_count), "discovered in source", true)}
      ${metric("Unresolved", numberValue(summary.unresolved_edge_count), "needs review", true)}
    </div>
    ${panel("Source", sourceWorkbench(source))}
    <div class="grid two">
      ${panel("Entity Types", sourceEntityTypesTable(payload.entity_types || []))}
      ${panel("Relationship Types", sourceEdgeTypesTable(payload.edge_types || []))}
    </div>
    ${panel("Owned Surface", ownedSurfaceTable(payload.owned_surface || []))}
    ${panel("Uses", sourceUsesTable(payload.uses || []))}
    <div class="grid two">
      ${panel("Calls Out", outgoingSourceLinksTable(payload.outgoing_cross_source_edges || []))}
      ${panel("Called By", incomingSourceLinksTable(payload.incoming_cross_source_edges || []))}
    </div>
    ${panel("Unresolved Hotspots", unresolvedHotspotsTable(payload.unresolved_report?.items || []))}
  `;
}

function sourceWorkbench(source) {
  const sourceName = source.name || state.source.name;
  return `
    <div class="stack">
      ${keyValueTable([
        ["Name", sourceName],
        ["Type", source.type || ""],
        ["Ref", source.ref || ""],
        ["Commit", source.commit || ""],
        ["Path", source.path || ""],
      ])}
      <div class="action-grid">
        ${actionButton("Search Source", "All entities in this source", "data-search-source", sourceName)}
        ${actionButton("API Routes", "Routes owned by this source", "data-source-search-type", "api_route")}
        ${actionButton("Stored Procedures", "Procedures owned by this source", "data-source-search-type", "stored_procedure")}
        ${actionButton("SQL Tables", "Tables owned by this source", "data-source-search-type", "sql_table")}
        ${actionButton("SQL Calls", "Unresolved SQL calls here", "data-source-unresolved-type", "CALLS_SQL")}
        ${actionButton("Service Calls", "Unresolved service calls here", "data-source-unresolved-type", "CALLS_SERVICE")}
      </div>
    </div>
  `;
}

function sourceEntityTypesTable(items) {
  if (!items.length) return emptyMarkup("No entity types.");
  const rows = items
    .map(
      (item) => `
        <tr>
          <td>${escapeHtml(item.entity_type || "")}</td>
          <td>${numberValue(item.entity_count)}</td>
          <td class="row-actions">
            <button class="button secondary" type="button" data-source-search-type="${escapeAttr(item.entity_type || "")}">Search</button>
          </td>
        </tr>`
    )
    .join("");
  return table(["Type", "Entities", ""], rows);
}

function sourceEdgeTypesTable(items) {
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
            <button class="button secondary" type="button" data-source-unresolved-type="${escapeAttr(item.edge_type || "")}">Unresolved</button>
            ${relationshipFilterButton("Evidence", {
              fromSource: state.source.name,
              type: item.edge_type,
            })}
          </td>
        </tr>`
    )
    .join("");
  return table(["Edge", "Total", "Resolved", "Unresolved", ""], rows);
}

function ownedSurfaceTable(items) {
  if (!items.length) return emptyMarkup("No owned surface in the returned sample.");
  const rows = items
    .map(
      (item) => `
        <tr>
          <td>${escapeHtml(item.entity_type || "")}</td>
          <td>${escapeHtml(item.name || "")}</td>
          <td class="mono">${escapeHtml(item.file_path || "")}</td>
          <td>${escapeHtml(item.line_number || "")}</td>
          <td class="row-actions">
            <button class="button secondary" type="button" data-entity-id="${escapeAttr(item.entity_id || "")}">Open</button>
            <button class="button secondary" type="button" data-impact-id="${escapeAttr(item.entity_id || "")}">Impact</button>
          </td>
        </tr>`
    )
    .join("");
  return table(["Type", "Name", "File", "Line", ""], rows);
}

function sourceUsesTable(items) {
  if (!items.length) return emptyMarkup("No dependency/use relationships in the returned sample.");
  const rows = items
    .map(
      (item) => `
        <tr>
          <td>${escapeHtml(item.edge_type || "")}</td>
          <td>${escapeHtml(item.target_type || "")}</td>
          <td>${escapeHtml(item.target_name || "")}</td>
          <td>${escapeHtml(item.target_source || "")}</td>
          <td>${numberValue(item.edge_count)}</td>
          <td>${numberValue(item.unresolved_edge_count)}</td>
          <td class="mono">${escapeHtml(item.file_path || "")}</td>
          <td class="row-actions">
            ${relationshipFilterButton("Evidence", {
              fromSource: state.source.name,
              toSource: item.target_source,
              type: item.edge_type,
              toType: item.target_type,
            })}
          </td>
        </tr>`
    )
    .join("");
  return table(["Edge", "Target Type", "Target", "Target Source", "Count", "Unresolved", "Example File", ""], rows);
}

function relationshipsForm() {
  return `
    <form class="toolbar" data-form="relationships">
      <label class="field">
        <span>From Source</span>
        <input name="fromSource" value="${escapeAttr(state.relationships.fromSource)}" />
      </label>
      <label class="field">
        <span>To Source</span>
        <input name="toSource" value="${escapeAttr(state.relationships.toSource)}" />
      </label>
      <label class="field">
        <span>Edge Type</span>
        <input name="type" value="${escapeAttr(state.relationships.type)}" placeholder="CALLS_SQL" />
      </label>
      <label class="field">
        <span>From Type</span>
        <input name="fromType" value="${escapeAttr(state.relationships.fromType)}" placeholder="api_route" />
      </label>
      <label class="field">
        <span>To Type</span>
        <input name="toType" value="${escapeAttr(state.relationships.toType)}" placeholder="stored_procedure" />
      </label>
      <label class="field small">
        <span>Resolved</span>
        <select name="resolved">
          ${option("", "Any", state.relationships.resolved)}
          ${option("true", "true", state.relationships.resolved)}
          ${option("false", "false", state.relationships.resolved)}
        </select>
      </label>
      <label class="field small">
        <span>Limit</span>
        <input name="limit" type="number" min="1" max="200" value="${state.relationships.limit}" />
      </label>
      <button class="button" type="submit">Search</button>
    </form>
  `;
}

function relationshipSearchMarkup(payload) {
  return `
    <div class="grid three">
      ${metric("Edges", numberValue(payload.count), "returned evidence", true)}
      ${metric("Groups", numberValue((payload.groups || []).length), "summaries", true)}
      ${metric("Limit", numberValue(payload.limit), "edge records", true)}
    </div>
    ${panel("Active Filters", keyValueTable(objectRows(payload.filters || {})))}
    ${panel("Grouped Evidence", relationshipSearchGroupsTable(payload.groups || []))}
    ${panel("Edge Evidence", relationshipEvidenceTable(payload.items || []))}
  `;
}

function relationshipSearchGroupsTable(items) {
  if (!items.length) return emptyMarkup("No relationship groups.");
  const rows = items
    .map(
      (item) => `
        <tr>
          <td>${escapeHtml(item.edge_type || "")}</td>
          <td>${escapeHtml(item.from_source || "")}</td>
          <td>${escapeHtml(item.to_source || "")}</td>
          <td>${escapeHtml(item.from_type || "")}</td>
          <td>${escapeHtml(item.to_type || "")}</td>
          <td>${status(String(Boolean(item.resolved)), item.resolved ? "ok" : "warn")}</td>
          <td>${numberValue(item.count)}</td>
          <td class="row-actions">
            ${relationshipFilterButton("Open", {
              fromSource: item.from_source,
              toSource: item.to_source,
              type: item.edge_type,
              fromType: item.from_type,
              toType: item.to_type,
              resolved: String(Boolean(item.resolved)),
            })}
          </td>
        </tr>`
    )
    .join("");
  return table(["Edge", "From Source", "To Source", "From Type", "To Type", "Resolved", "Count", ""], rows);
}

function relationshipEvidenceTable(items) {
  if (!items.length) return emptyMarkup("No relationship evidence.");
  const rows = items
    .map((item) => {
      const from = item.from_entity || {};
      const edge = item.edge || {};
      const target = item.target || {};
      const targetId = target.entity_id || "";
      const sourceName = item.from_source || from.source_name || edge.source_name || "";
      return `
        <tr>
          <td>${status(String(Boolean(edge.resolved)), edge.resolved ? "ok" : "warn")}</td>
          <td>${escapeHtml(edge.edge_type || "")}</td>
          <td>${escapeHtml(item.from_type || from.entity_type || "")}</td>
          <td>${escapeHtml(from.name || "")}</td>
          <td>${escapeHtml(sourceName)}</td>
          <td>${escapeHtml(item.to_type || target.entity_type || target.target_type || "")}</td>
          <td>${escapeHtml(target.name || edge.to_name || "")}</td>
          <td>${escapeHtml(item.to_source || target.source_name || "")}</td>
          <td class="mono">${escapeHtml(edge.file_path || "")}</td>
          <td>${escapeHtml(edge.line_number || "")}</td>
          <td>${escapeHtml(edge.parser || "")}</td>
          <td>${escapeHtml(edge.confidence || "")}</td>
          <td class="row-actions">
            <button class="button secondary" type="button" data-entity-id="${escapeAttr(from.entity_id || "")}">From</button>
            ${targetId ? `<button class="button secondary" type="button" data-entity-id="${escapeAttr(targetId)}">To</button>` : ""}
            ${snippetButton(sourceName, edge.file_path, edge.line_number)}
          </td>
        </tr>`;
    })
    .join("");
  return table(
    ["Resolved", "Edge", "From Type", "From", "From Source", "To Type", "To", "To Source", "File", "Line", "Parser", "Confidence", ""],
    rows
  );
}

function snippetButton(sourceName, filePath, lineNumber) {
  if (!sourceName || !filePath) return "";
  return `
    <button
      class="button secondary"
      type="button"
      data-snippet-source="${escapeAttr(sourceName)}"
      data-snippet-path="${escapeAttr(filePath)}"
      data-snippet-line="${escapeAttr(lineNumber || 1)}"
      data-snippet-context="3"
    >Snippet</button>
  `;
}

function sourceSnippetMarkup(payload) {
  const rows = (payload.lines || [])
    .map(
      (item) => `
        <tr class="${item.highlight ? "snippet-highlight" : ""}">
          <td class="mono">${escapeHtml(item.number || "")}</td>
          <td class="mono snippet-code">${escapeHtml(item.text || "")}</td>
        </tr>`
    )
    .join("");
  return `
    <div class="stack">
      ${keyValueTable([
        ["Source", payload.source_name || ""],
        ["File", payload.file_path || ""],
        ["Lines", `${payload.start_line || ""}-${payload.end_line || ""}`],
        ["Highlight", payload.highlight_line || ""],
      ])}
      ${table(["Line", "Code"], rows)}
    </div>
  `;
}

function relationshipFilterButton(label, filters) {
  return `
    <button
      class="button secondary"
      type="button"
      data-relationship-filter="true"
      data-relationship-from-source="${escapeAttr(filters.fromSource || "")}"
      data-relationship-to-source="${escapeAttr(filters.toSource || "")}"
      data-relationship-type="${escapeAttr(filters.type || "")}"
      data-relationship-from-type="${escapeAttr(filters.fromType || "")}"
      data-relationship-to-type="${escapeAttr(filters.toType || "")}"
      data-relationship-resolved="${escapeAttr(filters.resolved || "")}"
      data-relationship-limit="${escapeAttr(filters.limit || 100)}"
    >${escapeHtml(label)}</button>
  `;
}

function entityOverviewMarkup(payload) {
  const entity = payload.entity || {};
  const incoming = payload.incoming || {};
  const outgoing = payload.outgoing || {};
  return `
    <div class="grid three">
      ${metric("Incoming", numberValue(incoming.count), "direct relationships", true)}
      ${metric("Outgoing", numberValue(outgoing.count), "direct relationships", true)}
      ${metric("Limit", numberValue(payload.limit), "per direction", true)}
    </div>
    ${panel("Entity", entityWorkbench(entity))}
    <div class="grid two">
      ${panel("Incoming Groups", entityRelationshipGroupsTable(incoming.groups || [], entity, "in"))}
      ${panel("Outgoing Groups", entityRelationshipGroupsTable(outgoing.groups || [], entity, "out"))}
    </div>
    ${panel("Incoming Relationships", neighborsTable(incoming.items || []))}
    ${panel("Outgoing Relationships", neighborsTable(outgoing.items || []))}
  `;
}

function entityWorkbench(entity) {
  const entityId = entity.entity_id || state.entity.id;
  return `
    <div class="stack">
      ${keyValueTable(entityRows(entity))}
      <div class="action-grid">
        ${actionButton("Impact", "Trace dependency blast radius", "data-impact-id", entityId)}
        ${actionButton("Open Source", "Inspect repository context", "data-source-name", entity.source_name || "")}
        ${actionButton("Same Source", "Search entities in this source", "data-search-source", entity.source_name || "")}
        ${actionButton("Same Type", "Search entities of this type", "data-search-type", entity.entity_type || "")}
        ${entitySourceTypeButton(entity)}
      </div>
    </div>
  `;
}

function entitySourceTypeButton(entity) {
  return `
    <button
      class="action-button"
      type="button"
      data-entity-source-type="${escapeAttr(entity.entity_type || "")}"
      data-entity-source-name="${escapeAttr(entity.source_name || "")}"
    >
      <span>Same Type In Source</span>
      <small>${escapeHtml(entity.entity_type || "entity")} in ${escapeHtml(entity.source_name || "source")}</small>
    </button>
  `;
}

function entityRelationshipGroupsTable(items, entity, direction) {
  if (!items.length) return emptyMarkup("No relationship groups.");
  const rows = items
    .map((item) => {
      const filters =
        direction === "in"
          ? {
              fromSource: item.source_name,
              toSource: entity.source_name,
              type: item.edge_type,
              fromType: item.neighbor_type,
              toType: entity.entity_type,
            }
          : {
              fromSource: entity.source_name,
              toSource: item.source_name,
              type: item.edge_type,
              fromType: entity.entity_type,
              toType: item.neighbor_type,
            };
      return `
        <tr>
          <td>${escapeHtml(item.edge_type || "")}</td>
          <td>${escapeHtml(item.source_name || "")}</td>
          <td>${escapeHtml(item.neighbor_type || "")}</td>
          <td>${numberValue(item.count)}</td>
          <td>${numberValue(item.min_depth)}</td>
          <td class="row-actions">
            <button class="button secondary" type="button" data-search-source="${escapeAttr(item.source_name || "")}">Search</button>
            <button class="button secondary" type="button" data-source-name="${escapeAttr(item.source_name || "")}">Source</button>
            ${relationshipFilterButton("Evidence", filters)}
          </td>
        </tr>`;
    })
    .join("");
  return table(["Edge", "Source", "Neighbor Type", "Count", "Min Depth", ""], rows);
}

function outgoingSourceLinksTable(items) {
  if (!items.length) return emptyMarkup("No outgoing cross-source links in the returned sample.");
  const rows = items
    .map(
      (item) => `
        <tr>
          <td>${escapeHtml(item.target_source || "")}</td>
          <td>${escapeHtml(item.edge_type || "")}</td>
          <td>${escapeHtml(item.target_type || "")}</td>
          <td>${numberValue(item.edge_count)}</td>
          <td class="row-actions">
            <button class="button secondary" type="button" data-source-name="${escapeAttr(item.target_source || "")}">Open</button>
            ${relationshipFilterButton("Evidence", {
              fromSource: state.source.name,
              toSource: item.target_source,
              type: item.edge_type,
              toType: item.target_type,
              resolved: "true",
            })}
          </td>
        </tr>`
    )
    .join("");
  return table(["Target Source", "Edge", "Target Type", "Count", ""], rows);
}

function incomingSourceLinksTable(items) {
  if (!items.length) return emptyMarkup("No incoming cross-source links in the returned sample.");
  const rows = items
    .map(
      (item) => `
        <tr>
          <td>${escapeHtml(item.source_name || "")}</td>
          <td>${escapeHtml(item.edge_type || "")}</td>
          <td>${escapeHtml(item.source_type || "")}</td>
          <td>${numberValue(item.edge_count)}</td>
          <td class="row-actions">
            <button class="button secondary" type="button" data-source-name="${escapeAttr(item.source_name || "")}">Open</button>
            ${relationshipFilterButton("Evidence", {
              fromSource: item.source_name,
              toSource: state.source.name,
              type: item.edge_type,
              fromType: item.source_type,
              resolved: "true",
            })}
          </td>
        </tr>`
    )
    .join("");
  return table(["Source", "Edge", "Source Type", "Count", ""], rows);
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
      const entityId = neighbor.entity_id || "";
      const actions = entityId
        ? `<button class="button secondary" type="button" data-entity-id="${escapeAttr(entityId)}">Open</button>
           <button class="button secondary" type="button" data-impact-id="${escapeAttr(entityId)}">Impact</button>`
        : "";
      return `
        <tr>
          <td>${escapeHtml(item.direction || "")}</td>
          <td>${escapeHtml(item.depth || "")}</td>
          <td>${escapeHtml(edge.edge_type || "")}</td>
          <td>${escapeHtml(neighbor.entity_type || neighbor.target_type || "")}</td>
          <td>${escapeHtml(neighbor.name || "")}</td>
          <td>${escapeHtml(edge.source_name || "")}</td>
          <td class="row-actions">${actions}</td>
        </tr>`;
    })
    .join("");
  return table(["Direction", "Depth", "Edge", "Type", "Name", "Source", ""], rows);
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
    ${panel("Path Groups", impactPathGroupsTable(payload.path_groups || []))}
    ${panel("Path Evidence", impactPathEvidenceTable(payload.items || []))}
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

function impactPathGroupsTable(items) {
  if (!items.length) return emptyMarkup("No path groups.");
  const rows = items
    .map(
      (item) => `
        <tr>
          <td>${escapeHtml(item.source_name || "")}</td>
          <td>${escapeHtml(item.edge_type || "")}</td>
          <td>${numberValue(item.count)}</td>
          <td>${numberValue(item.min_depth)}</td>
          <td class="row-actions">
            ${relationshipFilterButton("Evidence", {
              fromSource: item.source_name,
              type: item.edge_type,
            })}
          </td>
        </tr>`
    )
    .join("");
  return table(["Source", "Edge", "Paths", "Min Depth", ""], rows);
}

function impactPathEvidenceTable(items) {
  if (!items.length) return emptyMarkup("No impact paths.");
  const rows = items
    .flatMap((item, pathIndex) =>
      impactPathSteps(item).map((step) => {
        const from = step.from || {};
        const edge = step.edge || {};
        const to = step.to || {};
        const fromId = from.entity_id || "";
        const toId = to.entity_id || "";
        const sourceName = edge.source_name || from.source_name || "";
        return `
          <tr>
            <td>${pathIndex + 1}</td>
            <td>${escapeHtml(item.direction || "")}</td>
            <td>${escapeHtml(item.depth || "")}</td>
            <td>${escapeHtml(step.index || "")}</td>
            <td>${escapeHtml(from.entity_type || from.target_type || edge.from_type || "")}</td>
            <td>${escapeHtml(from.name || edge.from_name || "")}</td>
            <td>${escapeHtml(from.source_name || edge.source_name || "")}</td>
            <td>${escapeHtml(edge.edge_type || "")}</td>
            <td>${escapeHtml(to.entity_type || to.target_type || edge.to_type || "")}</td>
            <td>${escapeHtml(to.name || edge.to_name || "")}</td>
            <td>${escapeHtml(to.source_name || "")}</td>
            <td class="mono">${escapeHtml(edge.file_path || "")}</td>
            <td>${escapeHtml(edge.line_number || "")}</td>
            <td>${escapeHtml(edge.parser || "")}</td>
            <td class="row-actions">
              ${fromId ? `<button class="button secondary" type="button" data-entity-id="${escapeAttr(fromId)}">From</button>` : ""}
              ${toId ? `<button class="button secondary" type="button" data-entity-id="${escapeAttr(toId)}">To</button>` : ""}
              ${snippetButton(sourceName, edge.file_path, edge.line_number)}
            </td>
          </tr>`;
      })
    )
    .join("");
  return table(
    ["Path", "Direction", "Depth", "Step", "From Type", "From", "From Source", "Edge", "To Type", "To", "To Source", "File", "Line", "Parser", ""],
    rows
  );
}

function impactPathSteps(item) {
  const steps = item.path?.steps || [];
  if (steps.length) return steps;
  const edge = item.edge || {};
  return [
    {
      index: 1,
      from: {
        entity_id: edge.from_entity_id || "",
        entity_type: edge.from_type || "",
        name: edge.from_name || "",
        source_name: edge.source_name || "",
      },
      edge,
      to: item.neighbor || {},
    },
  ];
}

function unresolvedReportMarkup(report) {
  const summary = report.summary || {};
  const groups = report.items || [];
  return `
    <div class="grid three">
      ${metric("Unresolved Edges", numberValue(summary.unresolved_edge_count), "matching edges", true)}
      ${metric("Groups", numberValue(summary.group_count), "target groups", true)}
      ${metric("Returned", numberValue(summary.returned_group_count), "visible groups", true)}
    </div>
    ${panel("Triage Summary", unresolvedTriageSummaryTable(report.classification_groups || []))}
    <div class="grid two">
      ${panel("Top Sources", unresolvedSourceHotspotsTable(report.source_hotspots || []))}
      ${panel("Top Targets", unresolvedTargetHotspotsTable(report.target_hotspots || []))}
    </div>
    ${groups.length ? unresolvedClassificationSections(groups, report.classification_groups || []) : emptyMarkup("No unresolved groups.")}
  `;
}

function unresolvedTriageSummaryTable(items) {
  if (!items.length) return emptyMarkup("No triage summaries.");
  const rows = items
    .map(
      (item) => `
        <tr>
          <td>${status(item.classification || "", classificationTone(item.classification))}</td>
          <td>${numberValue(item.count)}</td>
          <td>${numberValue(item.group_count)}</td>
          <td>${inlineList(item.edge_types || [])}</td>
          <td>${inlineList(item.source_names || [])}</td>
          <td>${escapeHtml(item.recommended_action || unresolvedRecommendedAction(item.classification))}</td>
        </tr>`
    )
    .join("");
  return table(["Class", "Edges", "Groups", "Edge Types", "Sources", "Recommended Action"], rows);
}

function unresolvedSourceHotspotsTable(items) {
  if (!items.length) return emptyMarkup("No source hotspots.");
  const rows = items
    .map(
      (item) => `
        <tr>
          <td>${escapeHtml(item.source_name || "")}</td>
          <td>${numberValue(item.count)}</td>
          <td>${numberValue(item.group_count)}</td>
          <td>${inlineList(item.classifications || [])}</td>
          <td>${inlineList(item.edge_types || [])}</td>
          <td class="row-actions">
            <button class="button secondary" type="button" data-search-source="${escapeAttr(item.source_name || "")}">Search</button>
            <button class="button secondary" type="button" data-unresolved-source="${escapeAttr(item.source_name || "")}">Unresolved</button>
          </td>
        </tr>`
    )
    .join("");
  return table(["Source", "Edges", "Groups", "Classes", "Edge Types", ""], rows);
}

function unresolvedTargetHotspotsTable(items) {
  if (!items.length) return emptyMarkup("No target hotspots.");
  const rows = items
    .map(
      (item) => `
        <tr>
          <td>${escapeHtml(item.to_name || "")}</td>
          <td>${escapeHtml(item.to_type || "")}</td>
          <td>${numberValue(item.count)}</td>
          <td>${numberValue(item.group_count)}</td>
          <td>${inlineList(item.source_names || [])}</td>
          <td>${inlineList(item.classifications || [])}</td>
          <td class="row-actions">
            <button class="button secondary" type="button" data-search-query="${escapeAttr(item.to_name || "")}">Search Target</button>
            <button class="button secondary" type="button" data-unresolved-type="${escapeAttr((item.edge_types || [])[0] || "")}">Same Edge</button>
          </td>
        </tr>`
    )
    .join("");
  return table(["Target", "Type", "Edges", "Groups", "Sources", "Classes", ""], rows);
}

function unresolvedClassificationSections(groups, summaries) {
  const groupsByClassification = groups.reduce((result, group) => {
    const classification = group.classification || "needs_review";
    if (!result.has(classification)) result.set(classification, []);
    result.get(classification).push(group);
    return result;
  }, new Map());
  const summaryByClassification = new Map(summaries.map((summary) => [summary.classification, summary]));
  return unresolvedClassificationOrder(groupsByClassification)
    .map((classification) =>
      unresolvedClassificationSection(
        classification,
        summaryByClassification.get(classification) || unresolvedClassificationSummary(classification, groupsByClassification.get(classification) || []),
        groupsByClassification.get(classification) || []
      )
    )
    .join("");
}

function unresolvedClassificationOrder(groupsByClassification) {
  const knownOrder = ["likely_missing_source", "likely_parser_gap", "ambiguous_target", "needs_review"];
  const unknown = [...groupsByClassification.keys()].filter((classification) => !knownOrder.includes(classification)).sort();
  return knownOrder.filter((classification) => groupsByClassification.has(classification)).concat(unknown);
}

function unresolvedClassificationSummary(classification, groups) {
  return {
    classification,
    recommended_action: unresolvedRecommendedAction(classification),
    count: groups.reduce((total, group) => total + Number(group.count || 0), 0),
    group_count: groups.length,
  };
}

function unresolvedClassificationSection(classification, summary, groups) {
  return `
    <section class="triage-section">
      <div class="triage-section-header">
        <div>
          <h2>${escapeHtml(unresolvedClassificationLabel(classification))}</h2>
          <div class="muted">${escapeHtml(summary.recommended_action || unresolvedRecommendedAction(classification))}</div>
        </div>
        <div class="inline-list">
          ${status(classification, classificationTone(classification))}
          <span class="chip">${numberValue(summary.count)} edges</span>
          <span class="chip">${numberValue(summary.group_count)} groups</span>
        </div>
      </div>
      <div class="triage-card-grid">
        ${groups.map((group) => unresolvedGroupCard(group)).join("")}
      </div>
    </section>
  `;
}

function unresolvedGroupCard(group) {
  return `
    <article class="triage-card">
      <div class="triage-card-header">
        <div>
          <h3>${escapeHtml(group.to_name || "unknown target")}</h3>
          <div class="muted">${escapeHtml(group.edge_type || "")} to ${escapeHtml(group.to_type || "")}</div>
        </div>
        <span class="chip">${numberValue(group.count)} edges</span>
      </div>
      <div class="muted">${escapeHtml(group.classification_reason || "")}</div>
      <div class="triage-action">${escapeHtml(group.recommended_action || unresolvedRecommendedAction(group.classification))}</div>
      <div class="inline-list">
        ${(group.source_names || [])
          .slice(0, 6)
          .map(
            (sourceName) =>
              `<button class="button secondary" type="button" data-search-source="${escapeAttr(sourceName)}">${escapeHtml(sourceName)}</button>`
          )
          .join("")}
        <button class="button secondary" type="button" data-search-query="${escapeAttr(group.to_name || "")}">Search Target</button>
        ${relationshipFilterButton("Evidence", {
          type: group.edge_type,
          toType: group.to_type,
          resolved: "false",
        })}
      </div>
      ${unresolvedExampleEvidenceTable(group)}
    </article>
  `;
}

function unresolvedExampleEvidenceTable(group) {
  const examples = group.examples || [];
  if (!examples.length) return emptyMarkup("No examples.");
  const rows = examples
    .map((example) => {
      const sourceName = example.source_name || "";
      const target = example.raw_target || example.normalized_target || group.to_name || "";
      return `
        <tr>
          <td>${escapeHtml(sourceName)}</td>
          <td class="mono">${escapeHtml(example.file_path || "")}</td>
          <td>${escapeHtml(example.line_number || "")}</td>
          <td>${escapeHtml(example.parser || "")}</td>
          <td class="mono">${escapeHtml(target)}</td>
          <td class="row-actions">
            ${snippetButton(sourceName, example.file_path, example.line_number)}
            <button class="button secondary" type="button" data-search-source="${escapeAttr(sourceName)}">Source</button>
            <button class="button secondary" type="button" data-search-query="${escapeAttr(group.to_name || target)}">Target</button>
            ${relationshipFilterButton("Evidence", {
              fromSource: sourceName,
              type: group.edge_type,
              toType: group.to_type,
              resolved: "false",
            })}
          </td>
        </tr>`;
    })
    .join("");
  return table(["Source", "File", "Line", "Parser", "Target", ""], rows);
}

function unresolvedClassificationLabel(classification) {
  return (
    {
      likely_missing_source: "Likely Missing Source",
      likely_parser_gap: "Likely Parser Gap",
      ambiguous_target: "Ambiguous Target",
      needs_review: "Needs Review",
    }[classification] || classification
  );
}

function unresolvedRecommendedAction(classification) {
  return (
    {
      likely_missing_source: "Add or sync the repository, package, service, or database project that owns this target.",
      likely_parser_gap: "Improve extractor coverage or add a parser slice for this declaration or reference shape.",
      ambiguous_target: "Review the candidates and add enough context for Repo Graph to resolve the target safely.",
      needs_review: "Inspect the evidence and decide whether this is missing scope, a parser gap, or expected dynamic behavior.",
    }[classification] || "Inspect the evidence and decide the next action."
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
