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
    title: "Blast Radius",
    meta: "Trace blast radius from an entity",
    render: renderImpact,
  },
  unresolved: {
    title: "Unresolved",
    meta: "Find missing sources, parser gaps, and ambiguous targets",
    render: renderUnresolved,
  },
  database: {
    title: "Database",
    meta: "Compare code and SQL evidence with current database metadata",
    render: renderDatabaseReconciliation,
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
  database: {
    source: "",
    databaseSource: "",
    limit: 50,
    examples: 3,
  },
  impact: {
    entityId: "",
    q: "",
    startType: "",
    source: "",
    searchLimit: 10,
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
  return parseHashRoute().routeName;
}

function renderRoute() {
  const { routeName, params } = parseHashRoute();
  hydrateRouteState(routeName, params);
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

function parseHashRoute() {
  const rawHash = window.location.hash.replace(/^#/, "");
  const [rawRoute, rawQuery = ""] = rawHash.split("?", 2);
  const routeName = routes[rawRoute] ? rawRoute : "overview";
  return { routeName, params: new URLSearchParams(rawQuery) };
}

function hydrateRouteState(routeName, params) {
  if (routeName === "search") {
    state.search = {
      q: stringParam(params, "q"),
      type: stringParam(params, "type"),
      source: stringParam(params, "source"),
      limit: numberParam(params, "limit", 25),
    };
  }
  if (routeName === "unresolved") {
    state.unresolved = {
      source: stringParam(params, "source"),
      type: stringParam(params, "type"),
      limit: numberParam(params, "limit", 50),
      examples: numberParam(params, "examples", 3),
    };
  }
  if (routeName === "database") {
    state.database = {
      source: stringParam(params, "source"),
      databaseSource: stringParam(params, "databaseSource"),
      limit: numberParam(params, "limit", 50),
      examples: numberParam(params, "examples", 3),
    };
  }
  if (routeName === "impact") {
    state.impact = {
      entityId: stringParam(params, "entityId"),
      q: stringParam(params, "q"),
      startType: stringParam(params, "startType"),
      source: stringParam(params, "source"),
      searchLimit: numberParam(params, "searchLimit", 10),
      direction: stringParam(params, "direction", "in") || "in",
      profile: stringParam(params, "profile", "impact") || "impact",
      type: stringParam(params, "type"),
      depth: numberParam(params, "depth", 2),
      limit: numberParam(params, "limit", 100),
    };
  }
  if (routeName === "entity") {
    state.entity = {
      id: stringParam(params, "id", stringParam(params, "entityId")),
      limit: numberParam(params, "limit", 50),
    };
  }
  if (routeName === "source") {
    state.source = {
      name: stringParam(params, "name"),
      limit: numberParam(params, "limit", 50),
    };
  }
  if (routeName === "relationships") {
    state.relationships = {
      fromSource: stringParam(params, "fromSource"),
      toSource: stringParam(params, "toSource"),
      type: stringParam(params, "type"),
      fromType: stringParam(params, "fromType"),
      toType: stringParam(params, "toType"),
      resolved: stringParam(params, "resolved"),
      limit: numberParam(params, "limit", 100),
    };
    state.snippet = {
      source: stringParam(params, "snippetSource"),
      path: stringParam(params, "snippetPath"),
      line: numberParam(params, "snippetLine", 1),
      context: numberParam(params, "snippetContext", 3),
    };
  }
  if (routeName === "explore") {
    state.explore.limit = numberParam(params, "limit", 50);
  }
}

function stringParam(params, name, fallback = "") {
  return params.has(name) ? (params.get(name) || "").trim() : fallback;
}

function numberParam(params, name, fallback) {
  if (!params.has(name)) return fallback;
  const value = Number(params.get(name));
  return Number.isFinite(value) && value > 0 ? value : fallback;
}
