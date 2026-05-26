function handleDocumentClick(event) {
  const routeLink = event.target.closest("[data-route-link]");
  if (routeLink) {
    navigateToRoute(routeLink.dataset.routeLink, {});
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
  const unresolvedFilterButton = event.target.closest("[data-unresolved-filter]");
  if (unresolvedFilterButton) {
    state.unresolved = {
      source: unresolvedFilterButton.dataset.unresolvedSourceValue || "",
      type: unresolvedFilterButton.dataset.unresolvedTypeValue || "",
      limit: 50,
      examples: 3,
    };
    navigateToRoute("unresolved");
    return;
  }
  const databaseCodeSourceButton = event.target.closest("[data-database-code-source]");
  if (databaseCodeSourceButton) {
    state.database = {
      source: databaseCodeSourceButton.dataset.databaseCodeSource || "",
      databaseSource: state.database.databaseSource,
      limit: 50,
      examples: 3,
    };
    navigateToRoute("database");
    return;
  }
  const databaseSourceButton = event.target.closest("[data-database-source]");
  if (databaseSourceButton) {
    state.database = {
      source: state.database.source,
      databaseSource: databaseSourceButton.dataset.databaseSource || "",
      limit: 50,
      examples: 3,
    };
    navigateToRoute("database");
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
    navigateToRoute("relationships");
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
    navigateToRoute("impact");
    return;
  }
  const impactStartTypeButton = event.target.closest("[data-impact-start-type]");
  if (impactStartTypeButton) {
    state.impact.startType = impactStartTypeButton.dataset.impactStartType || "";
    state.impact.q = "";
    navigateToRoute("impact");
    return;
  }
  const impactStartButton = event.target.closest("[data-impact-start-id]");
  if (impactStartButton) {
    state.impact.entityId = impactStartButton.dataset.impactStartId || "";
    navigateToRoute("impact");
    return;
  }
  const impactButton = event.target.closest("[data-impact-id]");
  if (impactButton) {
    state.impact.entityId = impactButton.dataset.impactId;
    navigateToRoute("impact");
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
    navigateToRoute("search");
  }
  if (form.dataset.form === "entity") {
    state.entity = {
      id: stringField(data, "entityId"),
      limit: numberField(data, "limit", 50),
    };
    navigateToRoute("entity");
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
    navigateToRoute("relationships");
  }
  if (form.dataset.form === "unresolved") {
    state.unresolved = {
      source: stringField(data, "source"),
      type: stringField(data, "type"),
      limit: numberField(data, "limit", 50),
      examples: numberField(data, "examples", 3),
    };
    navigateToRoute("unresolved");
  }
  if (form.dataset.form === "database") {
    state.database = {
      source: stringField(data, "source"),
      databaseSource: stringField(data, "databaseSource"),
      limit: numberField(data, "limit", 50),
      examples: numberField(data, "examples", 3),
    };
    navigateToRoute("database");
  }
  if (form.dataset.form === "impact-search") {
    state.impact = {
      ...state.impact,
      q: stringField(data, "q"),
      startType: stringField(data, "startType"),
      source: stringField(data, "source"),
      searchLimit: numberField(data, "searchLimit", 10),
    };
    navigateToRoute("impact");
  }
  if (form.dataset.form === "impact") {
    state.impact = {
      ...state.impact,
      entityId: stringField(data, "entityId"),
      direction: stringField(data, "direction") || "in",
      profile: stringField(data, "profile") || "impact",
      type: stringField(data, "type"),
      depth: numberField(data, "depth", 2),
      limit: numberField(data, "limit", 100),
    };
    navigateToRoute("impact");
  }
}
