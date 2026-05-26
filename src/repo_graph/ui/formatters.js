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
