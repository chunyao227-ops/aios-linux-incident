"use strict";

const state = {
  incidents: [],
  selectedId: null,
  pollTimer: null,
};

const $ = (id) => document.getElementById(id);

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload?.error?.message || `HTTP ${response.status}`);
  }
  return payload;
}

function clear(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
}

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function formatSeconds(value) {
  if (!Number.isFinite(value)) return "—";
  return `${value.toFixed(2)}s`;
}

function formatPercent(value) {
  return Number.isFinite(value) ? `${(value * 100).toFixed(2)}%` : "—";
}

function formatTime(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN", { hour12: false });
}

function agentType(value) {
  const text = String(value || "").toLowerCase();
  if (text.includes("log")) return "LogAgent";
  if (text.includes("metric")) return "MetricsAgent";
  if (text.includes("config")) return "ConfigAgent";
  if (text.includes("depend")) return "DependencyAgent";
  if (text.includes("repair")) return "RepairAgent";
  if (text.includes("verifier")) return "VerifierAgent";
  if (text.includes("coordinator")) return "CoordinatorAgent";
  return value || "UnknownAgent";
}

async function loadHistory({ preserveSelection = false } = {}) {
  const data = await api("/api/v1/incidents");
  state.incidents = data.incidents;
  $("history-count").textContent = String(state.incidents.length);
  renderHistory();
  if (!preserveSelection && !state.selectedId && state.incidents.length) {
    selectIncident(state.incidents[0].incident_id);
  }
}

function renderHistory() {
  const list = $("incident-list");
  clear(list);
  if (!state.incidents.length) {
    list.append(element("p", "muted", "暂无运行记录"));
    return;
  }
  for (const item of state.incidents) {
    const button = element("button", "incident-item");
    button.type = "button";
    if (item.incident_id === state.selectedId) button.classList.add("active");
    button.append(element("strong", "", item.service));
    button.append(element("span", "", `${item.state} · ${item.incident_id}`));
    button.append(element("span", "", formatTime(item.created_at)));
    button.addEventListener("click", () => selectIncident(item.incident_id));
    list.append(button);
  }
}

async function selectIncident(incidentId) {
  state.selectedId = incidentId;
  renderHistory();
  await refreshSelected();
  startPolling();
}

async function refreshSelected() {
  if (!state.selectedId) return;
  try {
    const [status, dag, events] = await Promise.all([
      api(`/api/v1/incidents/${encodeURIComponent(state.selectedId)}`),
      api(`/api/v1/incidents/${encodeURIComponent(state.selectedId)}/dag`),
      api(`/api/v1/incidents/${encodeURIComponent(state.selectedId)}/events`),
    ]);
    $("empty-state").hidden = true;
    $("incident-view").hidden = false;
    renderStatus(status);
    renderDag(dag);
    renderEvents(events.events);
  } catch (error) {
    showFormMessage(error.message);
  }
}

function renderStatus(status) {
  $("incident-id").textContent = status.incident_id;
  $("incident-objective").textContent = `Run ${status.run_id}`;
  const stateNode = $("run-state");
  stateNode.textContent = status.state;
  stateNode.className = `status ${status.state}`;
  $("current-task-count").textContent = String(status.current_tasks.length);
  $("completed-task-count").textContent = String(status.completed_tasks.length);
  $("elapsed-time").textContent = `${status.elapsed_seconds}s`;
  $("repair-attempt").textContent = String(status.repair_attempt);
  $("cancel-incident").disabled = ["SUCCESS", "UNRESOLVED", "BLOCKED", "ABORTED", "CANCELLED"].includes(status.state);
}

function renderDag(dag) {
  const grid = $("dag-grid");
  clear(grid);
  for (const node of dag.nodes) {
    const card = element("article", "dag-node");
    card.append(element("strong", "", `${node.task_id} · ${node.task_type}`));
    card.append(element("small", "", `Agent: ${node.agent_type}`));
    card.append(element("small", "", `依赖: ${node.depends_on.join(", ") || "无"}`));
    const badge = element("span", `status ${node.status}`, node.status);
    card.append(badge);
    grid.append(card);
  }
}

function renderEvents(events) {
  $("event-count").textContent = `${events.length} 个事件`;
  const messageEvents = events.filter((event) => event.event_type === "MESSAGE_SENT");
  const edgeCounts = new Map();
  for (const event of messageEvents) {
    const from = event.details?.from_agent_type || agentType(event.details?.from_agent || event.agent_id);
    const to = event.details?.to_agent_type || agentType(event.details?.to_agent);
    const key = `${from}\u0000${to}`;
    edgeCounts.set(key, (edgeCounts.get(key) || 0) + 1);
  }
  const pairKeys = new Set();
  for (const key of edgeCounts.keys()) {
    const [from, to] = key.split("\u0000");
    const reverse = `${to}\u0000${from}`;
    if (edgeCounts.has(reverse) && from < to) pairKeys.add(`${from}<->${to}`);
  }
  $("bidirectional-count").textContent = `${pairKeys.size} 对`;
  const interactionList = $("interaction-list");
  clear(interactionList);
  if (!messageEvents.length) {
    interactionList.append(element("p", "muted", "当前 Trace 尚无 Agent 消息"));
  } else {
    for (const [key, count] of [...edgeCounts.entries()].sort()) {
      const [from, to] = key.split("\u0000");
      const row = element("div", "interaction-row");
      row.append(element("span", "", `${from} → ${to}`));
      row.append(element("strong", "", `${count} 条`));
      interactionList.append(row);
    }
  }

  const timeline = $("event-timeline");
  clear(timeline);
  for (const event of [...events].reverse()) {
    timeline.append(timelineItem(event));
  }

  const repairEvents = events.filter((event) =>
    /REPAIR|VERIFICATION|VERIFIED|FEEDBACK/.test(event.event_type)
  );
  const repairList = $("repair-verification-list");
  clear(repairList);
  if (!repairEvents.length) {
    repairList.append(element("p", "muted", "当前 Trace 尚无修复或验证事件"));
  } else {
    for (const event of [...repairEvents].reverse()) {
      repairList.append(timelineItem(event));
    }
  }
}

function timelineItem(event) {
  const item = element("div", "timeline-item");
  item.append(element("time", "", formatTime(event.timestamp)));
  item.append(element("strong", "", event.event_type));
  const detail = [event.task_id, event.agent_id, event.status].filter(Boolean).join(" · ");
  item.append(element("span", "", detail));
  if (event.duration_ms !== null && event.duration_ms !== undefined) {
    item.append(element("span", "", `${event.duration_ms} ms`));
  }
  return item;
}

async function loadBenchmark() {
  try {
    const data = await api("/api/v1/benchmarks/latest");
    if (!data.available || !data.summary) {
      $("benchmark-environment").textContent = "无真实数据";
      $("benchmark-note").textContent = data.error || "尚未生成基准数据";
      return;
    }
    const summary = data.summary;
    $("benchmark-environment").textContent = summary.environment;
    const metrics = $("benchmark-summary");
    clear(metrics);
    appendMetric(metrics, "平均提速", formatPercent(summary.average_speedup));
    appendMetric(metrics, "最低场景", formatPercent(summary.minimum_speedup));
    appendMetric(metrics, "正确性保持", summary.correctness_preserved ? "是" : "否");
    appendMetric(metrics, "有效样本/模式", String(summary.samples_per_mode));
    const tbody = $("benchmark-rows");
    clear(tbody);
    for (const row of summary.comparisons) {
      const tr = document.createElement("tr");
      const values = [
        row.scenario_id.toUpperCase(),
        formatSeconds(row.serial.median_seconds),
        formatSeconds(row.parallel.median_seconds),
        formatPercent(row.median_speedup),
        `${formatPercent(row.serial.correctness_rate)} / ${formatPercent(row.parallel.correctness_rate)}`,
      ];
      for (const value of values) {
        tr.append(element("td", "", value));
      }
      tbody.append(tr);
    }
    $("benchmark-note").textContent =
      `原始数据：${data.raw_path}。本地 Ollama 数据仅用于开发验证。`;
  } catch (error) {
    $("benchmark-note").textContent = error.message;
  }
}

function appendMetric(container, label, value) {
  const card = element("article", "metric");
  card.append(element("span", "", label));
  card.append(element("strong", "", value));
  container.append(card);
}

function showFormMessage(message) {
  $("form-message").textContent = message || "";
}

async function createIncident(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const service = form.get("service").trim();
  const payload = {
    objective: form.get("objective").trim(),
    target: {
      host: form.get("host").trim(),
      service,
      environment: form.get("environment").trim(),
    },
    allowed_scope: {
      read_paths: [form.get("log_path").trim(), form.get("config_path").trim()],
      write_paths: [form.get("config_path").trim()],
      allowed_services: [service],
    },
    time_budget_seconds: 600,
    max_repair_attempts: 2,
    success_criteria: [
      "process_and_port_check",
      "health_endpoint",
      "smoke_test",
      "regression_test",
    ],
  };
  try {
    showFormMessage("");
    const created = await api("/api/v1/incidents", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    await loadHistory({ preserveSelection: true });
    await selectIncident(created.incident_id);
  } catch (error) {
    showFormMessage(error.message);
  }
}

async function cancelIncident() {
  if (!state.selectedId) return;
  try {
    await api(`/api/v1/incidents/${encodeURIComponent(state.selectedId)}/cancel`, {
      method: "POST",
    });
    await Promise.all([loadHistory({ preserveSelection: true }), refreshSelected()]);
  } catch (error) {
    showFormMessage(error.message);
  }
}

function startPolling() {
  if (state.pollTimer) clearInterval(state.pollTimer);
  state.pollTimer = setInterval(refreshSelected, 3000);
}

async function refreshAll() {
  try {
    await loadHistory({ preserveSelection: true });
    await Promise.all([refreshSelected(), loadBenchmark()]);
  } catch (error) {
    showFormMessage(error.message);
  }
}

$("incident-form").addEventListener("submit", createIncident);
$("cancel-incident").addEventListener("click", cancelIncident);
$("refresh-all").addEventListener("click", refreshAll);

Promise.all([loadHistory(), loadBenchmark()]).catch((error) => showFormMessage(error.message));
