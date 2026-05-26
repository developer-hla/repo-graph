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

async function runDatabaseReconciliation() {
  const params = new URLSearchParams();
  if (state.database.source) params.set("source", state.database.source);
  if (state.database.databaseSource) params.set("database_source", state.database.databaseSource);
  params.set("limit", String(state.database.limit));
  params.set("examples", String(state.database.examples));
  const target = document.querySelector("#database-results");
  const result = await fetchMaybe(`/reports/database-reconciliation?${params}`);
  target.innerHTML = result.ok ? databaseReconciliationMarkup(result.data) : errorMarkup(result.error);
}

async function runImpactEntitySearch() {
  const target = document.querySelector("#impact-start-results");
  if (!target) return;
  if (!impactStartSearchActive()) {
    target.innerHTML = emptyMarkup("Search for a graph entity.");
    return;
  }
  const params = new URLSearchParams();
  if (state.impact.q) params.set("q", state.impact.q);
  if (state.impact.startType) params.set("type", state.impact.startType);
  if (state.impact.source) params.set("source", state.impact.source);
  params.set("limit", String(state.impact.searchLimit));
  target.innerHTML = loadingMarkup();
  const result = await fetchMaybe(`/entities/search?${params}`);
  target.innerHTML = result.ok
    ? panel("Matching Start Entities", impactStartResultsTable(result.data.items || []))
    : errorMarkup(result.error);
}

function impactStartSearchActive() {
  return Boolean(state.impact.q || state.impact.startType || state.impact.source);
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
