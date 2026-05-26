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

function coverageWarningStrip(coverage) {
  const warnings = coverage?.warnings || [];
  if (!warnings.length || coverage.status === "ok") return "";
  const sourceName = coverage.source_name || "";
  const warningText = warnings
    .slice(0, 2)
    .map((warning) => warning.message)
    .join(" ");
  return `
    <div class="coverage-strip">
      <div>
        <strong>Coverage warnings</strong>
        <span>${escapeHtml(warningText)}</span>
      </div>
      ${coverageUnresolvedButton("Review", sourceName, "")}
    </div>
  `;
}

function coverageWarningsPanel(coverage) {
  return panel("Coverage Warnings", coverageWarningsMarkup(coverage));
}

function coverageWarningsMarkup(coverage) {
  if (!coverage) return emptyMarkup("Coverage has not been checked.");
  const sourceName = coverage.source_name || "";
  const warnings = coverage.warnings || [];
  if (coverage.status === "unknown") {
    return emptyMarkup(warnings[0]?.message || "Coverage could not be checked for this entity.");
  }
  if (coverage.status === "ok" || !warnings.length) {
    return emptyMarkup(`No unresolved references found for ${sourceName || "this source"}.`);
  }
  const rows = warnings
    .map(
      (warning) => `
        <tr>
          <td>${status(warning.severity || "info", coverageSeverityTone(warning.severity))}</td>
          <td>${escapeHtml(warning.message || "")}</td>
          <td>${numberValue(warning.count)}</td>
          <td>${escapeHtml(warning.edge_type || warning.classification || "")}</td>
          <td class="row-actions">
            ${coverageUnresolvedButton("Open Triage", sourceName, warning.edge_type || "")}
          </td>
        </tr>`
    )
    .join("");
  return `
    <div class="stack">
      <div class="message">
        Known impact paths may be incomplete while ${coverageCountLabel(coverage)} unresolved
        references remain in ${escapeHtml(sourceName || "this source")}.
      </div>
      ${table(["Level", "Warning", "Count", "Filter", ""], rows)}
    </div>
  `;
}

function coverageUnresolvedButton(label, sourceName, edgeType) {
  return `
    <button
      class="button secondary"
      type="button"
      data-unresolved-filter="true"
      data-unresolved-source-value="${escapeAttr(sourceName || "")}"
      data-unresolved-type-value="${escapeAttr(edgeType || "")}"
    >${escapeHtml(label)}</button>
  `;
}

function coverageSeverityTone(severity) {
  if (severity === "warning") return "warn";
  if (severity === "error") return "bad";
  return "";
}

function coverageCountLabel(coverage) {
  const count = numberValue(coverage.unresolved_edge_count);
  return coverage.edge_sample_truncated ? `at least ${count}` : count;
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
    ${coverageWarningStrip(payload.coverage)}
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
        ${actionButton("Blast Radius", "Trace dependency blast radius", "data-impact-id", entityId)}
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

function neighborsTable(items) {
  if (!items.length) return emptyMarkup("No neighbors.");
  const rows = items
    .map((item) => {
      const edge = item.edge || {};
      const neighbor = item.neighbor || {};
      const entityId = neighbor.entity_id || "";
      const actions = entityId
        ? `<button class="button secondary" type="button" data-entity-id="${escapeAttr(entityId)}">Open</button>
           <button class="button secondary" type="button" data-impact-id="${escapeAttr(entityId)}">Trace</button>`
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
