function metric(label, value, note, healthy) {
  return `
    <div class="metric">
      <div class="metric-label">${escapeHtml(label)}</div>
      <div class="metric-value">${escapeHtml(value ?? "unknown")}</div>
      <div class="metric-note">${escapeHtml(note ?? "")}</div>
      <span class="status ${healthy ? "ok" : "warn"}">${healthy ? "available" : "check"}</span>
    </div>
  `;
}

function panel(heading, body, actions = "") {
  return `
    <section class="panel">
      <div class="panel-header">
        <h2>${escapeHtml(heading)}</h2>
        <div>${actions}</div>
      </div>
      <div class="panel-body">${body}</div>
    </section>
  `;
}

function actionButton(label, note, dataAttr, value) {
  return `
    <button class="action-button" type="button" ${dataAttr}="${escapeAttr(value)}">
      <span>${escapeHtml(label)}</span>
      <small>${escapeHtml(note)}</small>
    </button>
  `;
}

function advancedPanel(label, body) {
  return `
    <details class="advanced-panel">
      <summary>${escapeHtml(label)}</summary>
      <div class="advanced-body">${body}</div>
    </details>
  `;
}

function advancedControls(body) {
  return `
    <details class="advanced-controls">
      <summary>Advanced</summary>
      <div class="advanced-body">${body}</div>
    </details>
  `;
}

function keyValueTable(rows) {
  if (!rows.length) return emptyMarkup("No values.");
  const body = rows
    .map(
      ([key, value]) => `
        <tr>
          <th>${escapeHtml(key)}</th>
          <td>${escapeHtml(formatValue(value))}</td>
        </tr>`
    )
    .join("");
  return `<div class="table-wrap"><table><tbody>${body}</tbody></table></div>`;
}

function table(headers, rows) {
  return `
    <div class="table-wrap">
      <table>
        <thead><tr>${headers.map((header) => `<th>${escapeHtml(header)}</th>`).join("")}</tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
  `;
}

function option(value, label, selected) {
  return `<option value="${escapeAttr(value)}" ${value === selected ? "selected" : ""}>${escapeHtml(label)}</option>`;
}

function status(label, tone) {
  return `<span class="status ${escapeAttr(tone || "")}">${escapeHtml(label || "")}</span>`;
}

function loadingMarkup() {
  return `<div class="message">Loading</div>`;
}

function emptyMarkup(message) {
  return `<div class="message muted">${escapeHtml(message)}</div>`;
}

function errorMarkup(error) {
  const message = error instanceof Error ? error.message : String(error);
  return `<div class="message error">${escapeHtml(message)}</div>`;
}
