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

async function renderDatabaseReconciliation() {
  view.innerHTML = `
    ${panel(
      "Database Drift",
      `<form class="stack" data-form="database">
        <div class="quick-actions">
          <button class="button secondary" type="button" data-search-type="sql_table">SQL Tables</button>
          <button class="button secondary" type="button" data-search-type="sql_view">SQL Views</button>
          <button class="button secondary" type="button" data-search-type="stored_procedure">Stored Procedures</button>
          <button class="button secondary" type="submit">Refresh</button>
        </div>
        ${advancedControls(
          `<div class="toolbar">
            <label class="field">
              <span>Code Source</span>
              <input name="source" value="${escapeAttr(state.database.source)}" />
            </label>
            <label class="field">
              <span>Database Source</span>
              <input name="databaseSource" value="${escapeAttr(state.database.databaseSource)}" />
            </label>
            <label class="field small">
              <span>Limit</span>
              <input name="limit" type="number" min="1" max="200" value="${state.database.limit}" />
            </label>
            <label class="field small">
              <span>Examples</span>
              <input name="examples" type="number" min="1" max="10" value="${state.database.examples}" />
            </label>
          </div>`
        )}
      </form>`
    )}
    <div id="database-results">${loadingMarkup()}</div>
  `;
  await runDatabaseReconciliation();
}

async function renderImpact() {
  view.innerHTML = `
    ${panel("Find Start Entity", impactStartSearchForm())}
    <div id="impact-start-results">
      ${impactStartSearchActive() ? loadingMarkup() : emptyMarkup("Search for a graph entity.")}
    </div>
    ${panel("Trace", impactTraceForm())}
    <div id="impact-results">
      ${state.impact.entityId ? loadingMarkup() : emptyMarkup("Open an entity from search or paste an entity ID.")}
    </div>
  `;
  await runImpactEntitySearch();
  if (state.impact.entityId) {
    await runImpact();
  }
}

function impactStartSearchForm() {
  return `
    <form class="stack" data-form="impact-search">
      <div class="query-row">
        <label class="field query-field">
          <span>Search</span>
          <input name="q" value="${escapeAttr(state.impact.q)}" placeholder="route, table, service, symbol" />
        </label>
        <button class="button" type="submit">Find</button>
      </div>
      <div class="quick-actions">
        <button class="button secondary" type="button" data-impact-start-type="api_route">API Routes</button>
        <button class="button secondary" type="button" data-impact-start-type="function">Functions</button>
        <button class="button secondary" type="button" data-impact-start-type="service">Services</button>
        <button class="button secondary" type="button" data-impact-start-type="sql_table">SQL Tables</button>
        <button class="button secondary" type="button" data-impact-start-type="stored_procedure">Stored Procedures</button>
      </div>
      ${advancedControls(
        `<div class="toolbar">
          <label class="field">
            <span>Type</span>
            <input name="startType" value="${escapeAttr(state.impact.startType)}" placeholder="api_route" />
          </label>
          <label class="field">
            <span>Source</span>
            <input name="source" value="${escapeAttr(state.impact.source)}" />
          </label>
          <label class="field small">
            <span>Limit</span>
            <input name="searchLimit" type="number" min="1" max="100" value="${state.impact.searchLimit}" />
          </label>
        </div>`
      )}
    </form>
  `;
}

function impactTraceForm() {
  return `
    <form class="stack" data-form="impact">
      <div class="query-row">
        <label class="field query-field">
          <span>Entity ID</span>
          <input name="entityId" value="${escapeAttr(state.impact.entityId)}" />
        </label>
        <button class="button" type="submit">Trace</button>
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
    </form>
  `;
}
