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
      ${actionButton("Database Drift", "Compare SQL evidence with current metadata", "data-route-link", "database")}
    </div>
  `;
}

function workflowStarters() {
  return `
    <div class="action-grid">
      ${actionButton("Find Something", "Search routes, data objects, packages, and symbols", "data-route-link", "search")}
      ${actionButton("Blast Radius", "Trace callers and dependencies from a known entity", "data-route-link", "impact")}
      ${actionButton("Needs Attention", "Group unresolved references by likely cause", "data-route-link", "unresolved")}
      ${actionButton("Database Drift", "Compare code, SQL files, and current database metadata", "data-route-link", "database")}
      ${actionButton("Refresh Graph", "Sync sources and update loaded graph data", "data-route-link", "jobs")}
      ${actionButton("Source Map", "Open source-level ownership and dependency summaries", "data-route-link", "explore")}
    </div>
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
            <button class="button secondary" type="button" data-impact-id="${escapeAttr(item.entity_id || "")}">Trace</button>
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
