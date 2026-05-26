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
          <td><button class="button secondary" type="button" data-impact-id="${escapeAttr(item.entity_id)}">Trace</button></td>
          <td>${escapeHtml(item.entity_type || "")}</td>
          <td>${escapeHtml(item.name || "")}</td>
          <td>${escapeHtml(item.source_name || "")}</td>
          <td class="mono">${escapeHtml(item.file_path || "")}</td>
        </tr>`
    )
    .join("");
  return table(["", "", "Type", "Name", "Source", "File"], rows);
}

function impactStartResultsTable(items) {
  if (!items.length) return emptyMarkup("No matching start entities.");
  const rows = items
    .map(
      (item) => `
        <tr>
          <td class="row-actions">
            <button class="button secondary" type="button" data-impact-start-id="${escapeAttr(item.entity_id || "")}">
              Use
            </button>
            <button class="button secondary" type="button" data-entity-id="${escapeAttr(item.entity_id || "")}">Open</button>
          </td>
          <td>${escapeHtml(item.entity_type || "")}</td>
          <td>${escapeHtml(item.name || "")}</td>
          <td>${escapeHtml(item.source_name || "")}</td>
          <td class="mono">${escapeHtml(item.file_path || "")}</td>
          <td>${escapeHtml(item.line_number || "")}</td>
        </tr>`
    )
    .join("");
  return table(["", "Type", "Name", "Source", "File", "Line"], rows);
}

function impactMarkup(payload) {
  const entity = payload.entity || {};
  const summary = payload.summary || {};
  return `
    <div class="grid three">
      ${metric("Affected Sources", numberValue(payload.affected_source_count), "grouped by source", true)}
      ${metric("Paths", numberValue(summary.path_count || payload.count), "returned paths", true)}
      ${metric("Max Depth", numberValue(summary.max_observed_depth || payload.depth), `${payload.direction || ""} / ${payload.profile || ""}`, true)}
    </div>
    ${coverageWarningsPanel(payload.coverage)}
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
        const evidence = [edge.file_path, edge.line_number, edge.parser]
          .filter((value) => value)
          .join(" : ");
        return `
          <tr>
            <td>${pathIndex + 1}</td>
            <td>${escapeHtml(step.index || "")}</td>
            <td>${impactEndpointCell(from, edge.from_type, edge.from_name, edge.source_name)}</td>
            <td>${status(edge.edge_type || "unknown", "")}</td>
            <td>${impactEndpointCell(to, edge.to_type, edge.to_name, "")}</td>
            <td class="mono">${escapeHtml(evidence)}</td>
            <td class="row-actions">
              ${fromId ? `<button class="button secondary" type="button" data-entity-id="${escapeAttr(fromId)}">From</button>` : ""}
              ${toId ? `<button class="button secondary" type="button" data-entity-id="${escapeAttr(toId)}">To</button>` : ""}
              ${snippetButton(sourceName, edge.file_path, edge.line_number)}
            </td>
          </tr>`;
      })
    )
    .join("");
  return table(["Path", "Step", "From", "Edge", "To", "Evidence", ""], rows);
}

function impactEndpointCell(entity, fallbackType, fallbackName, fallbackSource) {
  const type = entity.entity_type || entity.target_type || fallbackType || "";
  const name = entity.name || fallbackName || "";
  const source = entity.source_name || fallbackSource || "";
  return `
    <div class="stack tight">
      <span>${escapeHtml(name)}</span>
      <span class="muted">${escapeHtml([type, source].filter((value) => value).join(" / "))}</span>
    </div>
  `;
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
