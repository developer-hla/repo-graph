function navigateToRoute(routeName, params = routeParams(routeName)) {
  if (!routes[routeName]) return;
  writeHashRoute(routeName, params);
}

function writeHashRoute(routeName, params = {}) {
  const nextHash = hashForRoute(routeName, params);
  if (window.location.hash === nextHash) {
    renderRoute();
  } else {
    window.location.hash = nextHash;
  }
}

function hashForRoute(routeName, params = {}) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      query.set(key, String(value));
    }
  });
  const queryText = query.toString();
  return queryText ? `#${routeName}?${queryText}` : `#${routeName}`;
}

function routeParams(routeName) {
  if (routeName === "search") return compactParams(state.search);
  if (routeName === "unresolved") return compactParams(state.unresolved);
  if (routeName === "database") return compactParams(state.database);
  if (routeName === "impact") return compactParams(state.impact);
  if (routeName === "entity") return compactParams({ id: state.entity.id, limit: state.entity.limit });
  if (routeName === "source") return compactParams({ name: state.source.name, limit: state.source.limit });
  if (routeName === "relationships") {
    return compactParams({
      ...state.relationships,
      snippetSource: state.snippet.source,
      snippetPath: state.snippet.path,
      snippetLine: state.snippet.line,
      snippetContext: state.snippet.context,
    });
  }
  if (routeName === "explore") return compactParams(state.explore);
  return {};
}

function compactParams(params) {
  return Object.fromEntries(
    Object.entries(params || {}).filter(([_key, value]) => value !== undefined && value !== null && value !== "")
  );
}
