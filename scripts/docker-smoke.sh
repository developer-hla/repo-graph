#!/usr/bin/env bash
set -euo pipefail

project_name="repo-graph-smoke-$$"
api_port="${REPO_GRAPH_SMOKE_API_PORT:-18080}"
neo4j_http_port="${REPO_GRAPH_SMOKE_NEO4J_HTTP_PORT:-17475}"
neo4j_bolt_port="${REPO_GRAPH_SMOKE_NEO4J_BOLT_PORT:-17688}"
wait_attempts="${REPO_GRAPH_SMOKE_WAIT_ATTEMPTS:-90}"
base_url="http://127.0.0.1:${api_port}"
response_dir="$(mktemp -d "${TMPDIR:-/tmp}/repo-graph-smoke.XXXXXX")"

export REPO_GRAPH_API_PORT="${api_port}"
export REPO_GRAPH_NEO4J_HTTP_PORT="${neo4j_http_port}"
export REPO_GRAPH_NEO4J_BOLT_PORT="${neo4j_bolt_port}"
export REPO_GRAPH_CONFIG="${REPO_GRAPH_SMOKE_CONFIG:-/app/config/local-example.yaml}"
export GITHUB_TOKEN="${REPO_GRAPH_SMOKE_GITHUB_TOKEN:-}"
export GH_TOKEN="${REPO_GRAPH_SMOKE_GH_TOKEN:-}"

cleanup() {
  status=$?
  if [[ "${REPO_GRAPH_SMOKE_KEEP:-0}" == "1" ]]; then
    echo "Keeping Compose project ${project_name} for inspection."
  else
    docker compose -p "${project_name}" down -v --remove-orphans >/dev/null || true
  fi
  rm -rf "${response_dir}"
  exit "${status}"
}
trap cleanup EXIT

compose() {
  docker compose -p "${project_name}" "$@"
}

request() {
  local method="$1"
  local path="$2"
  local output="$3"
  local data="${4:-}"

  if [[ -n "${data}" ]]; then
    curl -fsS -X "${method}" "${base_url}${path}" \
      -H "content-type: application/json" \
      -d "${data}" \
      >"${output}"
  else
    curl -fsS -X "${method}" "${base_url}${path}" >"${output}"
  fi
}

assert_contains() {
  local file="$1"
  local pattern="$2"
  local label="$3"

  if ! grep -Eq "${pattern}" "${file}"; then
    echo "Smoke check failed: ${label}" >&2
    echo "Response from ${file}:" >&2
    cat "${file}" >&2
    exit 1
  fi
}

wait_for_health() {
  local health_file="${response_dir}/health.json"

  for _ in $(seq 1 "${wait_attempts}"); do
    if request GET /health "${health_file}" 2>/dev/null; then
      assert_contains "${health_file}" '"status"[[:space:]]*:[[:space:]]*"ok"' "health endpoint returned ok"
      return 0
    fi
    sleep 2
  done

  echo "Repo Graph did not become healthy at ${base_url}/health." >&2
  compose logs --no-color --tail=200 >&2 || true
  exit 1
}

echo "Starting Docker smoke project ${project_name} on ${base_url}."
compose up --build -d

wait_for_health

request GET /manifest "${response_dir}/manifest.json"
assert_contains "${response_dir}/manifest.json" '"service"[[:space:]]*:[[:space:]]*"repo-graph"' "manifest identifies Repo Graph"
assert_contains "${response_dir}/manifest.json" '"path"[[:space:]]*:[[:space:]]*"/build-load"' "manifest includes build-load"

request GET /ui "${response_dir}/ui.html"
assert_contains "${response_dir}/ui.html" '<title>Repo Graph</title>' "UI shell served"

request POST /build-load "${response_dir}/build-load.json" '{"strict":true}'
assert_contains "${response_dir}/build-load.json" '"status"[[:space:]]*:[[:space:]]*"built_and_loaded"' "build-load completed"
assert_contains "${response_dir}/build-load.json" '"error_count"[[:space:]]*:[[:space:]]*0' "strict build completed without errors"

request GET /stats "${response_dir}/stats.json"
assert_contains "${response_dir}/stats.json" '"entity_count"[[:space:]]*:[[:space:]]*[1-9][0-9]*' "stats reports entities"
assert_contains "${response_dir}/stats.json" '"edge_count"[[:space:]]*:[[:space:]]*[1-9][0-9]*' "stats reports edges"

request GET /scope "${response_dir}/scope.json"
assert_contains "${response_dir}/scope.json" '"loaded"[[:space:]]*:[[:space:]]*true' "scope is loaded"
assert_contains "${response_dir}/scope.json" '"api-service"' "scope includes synthetic api-service source"

echo "Docker smoke test passed."
