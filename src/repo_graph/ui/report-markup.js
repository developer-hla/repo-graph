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

function databaseReconciliationMarkup(report) {
  const summary = report.summary || {};
  const items = report.items || [];
  return `
    <div class="grid three">
      ${metric("Current DB Objects", numberValue(summary.current_database_entity_count), "metadata entities", true)}
      ${metric("Code SQL Refs", numberValue(summary.code_sql_reference_count), "application references", true)}
      ${metric("Drift Groups", numberValue(summary.group_count), "items needing review", true)}
      ${metric("Returned", numberValue(summary.returned_group_count), "visible groups", true)}
      ${metric("DB Metadata Edges", numberValue(summary.database_metadata_edge_count), "catalog relationships", true)}
      ${metric("Evidence", summary.database_evidence_present ? "current" : "missing", "database metadata", summary.database_evidence_present)}
    </div>
    ${databaseEvidenceNotice(summary)}
    ${databaseSampleNotice(report)}
    ${panel("Drift Summary", databaseClassificationGroupsTable(report.classification_groups || []))}
    <div class="grid two">
      ${panel("Source Hotspots", databaseSourceHotspotsTable(report.source_hotspots || []))}
      ${panel("Target Hotspots", databaseTargetHotspotsTable(report.target_hotspots || []))}
    </div>
    ${panel("Drift Items", databaseReconciliationItemsTable(items))}
  `;
}

function databaseEvidenceNotice(summary) {
  if (summary.database_evidence_present) return "";
  return emptyMarkup("No current database metadata found. Code-only and schema-drift checks need a database metadata source.");
}

function databaseSampleNotice(report) {
  const notices = [];
  if (report.entity_sample_truncated) notices.push(`Entity sample reached ${report.entity_sample_limit}`);
  if (report.edge_sample_truncated) notices.push(`Relationship sample reached ${report.edge_sample_limit}`);
  if (!notices.length) return "";
  return `<div class="message">${inlineList(notices)}</div>`;
}

function databaseClassificationGroupsTable(items) {
  if (!items.length) return emptyMarkup("No database drift groups.");
  const rows = items
    .map(
      (item) => `
        <tr>
          <td>${status(databaseClassificationLabel(item.classification), databaseClassificationTone(item.classification))}</td>
          <td>${numberValue(item.count)}</td>
          <td>${numberValue(item.group_count)}</td>
          <td>${inlineList(item.source_names || [])}</td>
          <td>${inlineList(item.database_sources || [])}</td>
          <td>${escapeHtml(item.recommended_action || "")}</td>
        </tr>`
    )
    .join("");
  return table(["Class", "Edges/Objects", "Groups", "Code Sources", "DB Sources", "Recommended Action"], rows);
}

function databaseSourceHotspotsTable(items) {
  if (!items.length) return emptyMarkup("No source hotspots.");
  const rows = items
    .map(
      (item) => `
        <tr>
          <td>${escapeHtml(item.source_name || "")}</td>
          <td>${numberValue(item.count)}</td>
          <td>${inlineList((item.classifications || []).map(databaseClassificationLabel))}</td>
          <td>${inlineList(item.target_names || [])}</td>
          <td class="row-actions">
            <button class="button secondary" type="button" data-search-source="${escapeAttr(item.source_name || "")}">Search</button>
            <button class="button secondary" type="button" data-database-code-source="${escapeAttr(item.source_name || "")}">Code Source</button>
            <button class="button secondary" type="button" data-database-source="${escapeAttr(item.source_name || "")}">DB Source</button>
          </td>
        </tr>`
    )
    .join("");
  return table(["Source", "Count", "Classes", "Targets", ""], rows);
}

function databaseTargetHotspotsTable(items) {
  if (!items.length) return emptyMarkup("No target hotspots.");
  const rows = items
    .map(
      (item) => `
        <tr>
          <td class="mono">${escapeHtml(item.target_name || "")}</td>
          <td>${escapeHtml(item.target_type || "")}</td>
          <td>${numberValue(item.count)}</td>
          <td>${inlineList((item.classifications || []).map(databaseClassificationLabel))}</td>
          <td class="row-actions">
            <button class="button secondary" type="button" data-search-query="${escapeAttr(item.target_name || "")}">Search</button>
          </td>
        </tr>`
    )
    .join("");
  return table(["Target", "Type", "Count", "Classes", ""], rows);
}

function databaseReconciliationItemsTable(items) {
  if (!items.length) return emptyMarkup("No database drift items.");
  const rows = items
    .map((item) => {
      const sourceNames = item.source_names || [];
      const databaseSources = item.database_sources || [];
      const evidenceTypes = item.evidence_types || [];
      const edgeType = evidenceTypes.find((value) => value !== "current_database") || "";
      return `
        <tr>
          <td>${status(databaseClassificationLabel(item.classification), databaseClassificationTone(item.classification))}</td>
          <td>
            <div class="mono">${escapeHtml(item.target_name || "")}</div>
            <div class="muted">${escapeHtml(item.target_type || "")}</div>
          </td>
          <td>${numberValue(item.count)}</td>
          <td>${inlineList(sourceNames)}</td>
          <td>${inlineList(databaseSources)}</td>
          <td>
            ${inlineList(evidenceTypes)}
            ${inlineList(item.current_database_types || [])}
          </td>
          <td>${escapeHtml(item.recommended_action || "")}</td>
          <td>${databaseExamplesDetails(item.examples || [])}</td>
          <td class="row-actions">
            <button class="button secondary" type="button" data-search-query="${escapeAttr(item.target_name || "")}">Search</button>
            ${relationshipFilterButton("Evidence", {
              fromSource: sourceNames[0] || databaseSources[0] || "",
              type: edgeType,
              toType: item.target_type,
              limit: 100,
            })}
          </td>
        </tr>`;
    })
    .join("");
  return table(["Class", "Target", "Count", "Code Sources", "DB Sources", "Evidence", "Action", "Examples", ""], rows);
}

function databaseExamplesDetails(examples) {
  if (!examples.length) return "";
  return `
    <details>
      <summary>${numberValue(examples.length)} examples</summary>
      ${databaseExamplesTable(examples)}
    </details>
  `;
}

function databaseExamplesTable(examples) {
  const rows = examples
    .map((example) => {
      const sourceName = example.source_name || "";
      const target =
        example.raw_target || example.normalized_target || example.full_name || example.name || example.to_name || "";
      return `
        <tr>
          <td>${escapeHtml(example.kind || "")}</td>
          <td>${escapeHtml(sourceName)}</td>
          <td class="mono">${escapeHtml(example.file_path || "")}</td>
          <td>${escapeHtml(example.line_number || "")}</td>
          <td>${escapeHtml(example.parser || example.metadata_source || "")}</td>
          <td class="mono">${escapeHtml(target)}</td>
          <td class="row-actions">
            ${snippetButton(sourceName, example.file_path, example.line_number)}
            ${example.entity_id ? `<button class="button secondary" type="button" data-entity-id="${escapeAttr(example.entity_id)}">Entity</button>` : ""}
            ${example.edge_type
              ? relationshipFilterButton("Edges", {
                  fromSource: sourceName,
                  type: example.edge_type,
                  limit: 100,
                })
              : ""}
          </td>
        </tr>`;
    })
    .join("");
  return table(["Kind", "Source", "File", "Line", "Parser", "Target", ""], rows);
}

function databaseClassificationLabel(classification) {
  return (
    {
      code_only_reference: "Code Only",
      unresolved_database_reference: "Unresolved DB Ref",
      schema_drift: "Schema Drift",
      migration_only_object: "Migration Only",
      database_only_object: "DB Only",
    }[classification] || classification
  );
}

function databaseClassificationTone(classification) {
  if (classification === "code_only_reference" || classification === "schema_drift") return "bad";
  if (
    classification === "unresolved_database_reference" ||
    classification === "migration_only_object" ||
    classification === "database_only_object"
  ) {
    return "warn";
  }
  return "";
}
