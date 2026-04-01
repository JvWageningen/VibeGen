"""Web dashboard for the iterative improvement loop.

Pure-stdlib HTTP server serving a single-page app with Chart.js.
No external web framework dependencies.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, ClassVar
from urllib.parse import parse_qs, urlparse

from ._improve_state import (
    _load_improve_state,
    _save_improve_state,
)

# ---------------------------------------------------------------------------
# Dashboard HTML (inline single-page app)
# ---------------------------------------------------------------------------

_DASHBOARD_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>VibeGen Improve Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto,
         sans-serif; background: #0d1117; color: #c9d1d9; }
  .header { background: #161b22; padding: 12px 20px; border-bottom: 1px solid #30363d;
             display: flex; align-items: center; gap: 16px; }
  .header h1 { font-size: 18px; color: #58a6ff; }
  .status-bar { display: flex; gap: 12px; flex-wrap: wrap; }
  .pill { background: #21262d; padding: 4px 10px; border-radius: 12px;
          font-size: 13px; border: 1px solid #30363d; }
  .pill.green { border-color: #238636; color: #3fb950; }
  .pill.yellow { border-color: #9e6a03; color: #d29922; }
  .pill.red { border-color: #da3633; color: #f85149; }
  .tabs { display: flex; background: #161b22; border-bottom: 1px solid #30363d; }
  .tab { padding: 10px 20px; cursor: pointer; border-bottom: 2px solid transparent;
         font-size: 14px; color: #8b949e; }
  .tab.active { color: #58a6ff; border-bottom-color: #58a6ff; }
  .tab:hover { color: #c9d1d9; }
  .content { padding: 20px; max-width: 1200px; margin: 0 auto; }
  .panel { display: none; }
  .panel.active { display: block; }
  .card { background: #161b22; border: 1px solid #30363d; border-radius: 8px;
          padding: 16px; margin-bottom: 16px; }
  .card h3 { color: #58a6ff; margin-bottom: 12px; font-size: 15px; }
  .chart-container { position: relative; height: 250px; margin-bottom: 16px; }
  .grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th, td { padding: 8px 12px; text-align: left; border-bottom: 1px solid #21262d; }
  th { color: #8b949e; font-weight: 600; }
  .v-improvement { color: #3fb950; }
  .v-neutral { color: #d29922; }
  .v-regression { color: #f85149; }
  .v-reverted { text-decoration: line-through; opacity: 0.6; }
  textarea { width: 100%; min-height: 80px; background: #0d1117;
             border: 1px solid #30363d; color: #c9d1d9; border-radius: 6px;
             padding: 8px; font-family: inherit; resize: vertical; }
  button { background: #21262d; color: #c9d1d9; border: 1px solid #30363d;
           padding: 8px 16px; border-radius: 6px; cursor: pointer;
           font-size: 13px; }
  button:hover { background: #30363d; }
  button.primary { background: #238636; border-color: #238636; color: #fff; }
  button.danger { background: #da3633; border-color: #da3633; color: #fff; }
  button.warning { background: #9e6a03; border-color: #9e6a03; color: #fff; }
  .btn-group { display: flex; gap: 8px; margin-top: 12px; }
  pre { background: #0d1117; border: 1px solid #30363d; border-radius: 6px;
        padding: 12px; overflow-x: auto; font-size: 12px; max-height: 500px;
        overflow-y: auto; white-space: pre-wrap; word-break: break-word; }
  select { background: #0d1117; color: #c9d1d9; border: 1px solid #30363d;
           padding: 6px 10px; border-radius: 6px; }
  .task-display { background: #0d1117; padding: 12px; border-radius: 6px;
                  border-left: 3px solid #58a6ff; margin-bottom: 12px;
                  font-style: italic; }
  @media (max-width: 768px) { .grid-2 { grid-template-columns: 1fr; } }
</style>
</head>
<body>

<div class="header">
  <h1>VibeGen Improve</h1>
  <div class="status-bar" id="statusBar">
    <span class="pill" id="pillIter">Iter: -</span>
    <span class="pill" id="pillStatus">Status: -</span>
    <span class="pill" id="pillBranch">Branch: -</span>
    <span class="pill" id="pillVerdict">Last: -</span>
    <span class="pill" id="pillBest">Best: -</span>
  </div>
</div>

<div class="tabs">
  <div class="tab active" onclick="switchTab('overview')">Overview</div>
  <div class="tab" onclick="switchTab('control')">Control</div>
  <div class="tab" onclick="switchTab('history')">History</div>
  <div class="tab" onclick="switchTab('logs')">Logs</div>
</div>

<div class="content">
  <!-- OVERVIEW TAB -->
  <div class="panel active" id="panel-overview">
    <div class="grid-2">
      <div class="card">
        <h3>Verdict Timeline</h3>
        <div class="chart-container"><canvas id="chartVerdict"></canvas></div>
      </div>
      <div class="card">
        <h3>Cumulative Improvements</h3>
        <div class="chart-container"><canvas id="chartCumulative"></canvas></div>
      </div>
    </div>
    <div class="card">
      <h3>Iteration Summary</h3>
      <div id="summaryTable"></div>
    </div>
  </div>

  <!-- CONTROL TAB -->
  <div class="panel" id="panel-control">
    <div class="card">
      <h3>Current Task</h3>
      <div class="task-display" id="taskDisplay">Loading...</div>
    </div>
    <div class="card">
      <h3>Notes for Claude</h3>
      <textarea id="noteInput"
        placeholder="Add guidance for the next iteration..."
      ></textarea>
      <div class="btn-group">
        <button class="primary" onclick="sendNote()">Add Note</button>
      </div>
    </div>
    <div class="card">
      <h3>Loop Controls</h3>
      <div class="btn-group">
        <button class="warning" onclick="sendAction('pause')">Pause</button>
        <button class="primary" onclick="sendAction('resume')">Resume</button>
        <button class="danger" onclick="sendAction('stop')">Stop</button>
        <button onclick="sendAction('merge')">Merge to Main</button>
      </div>
    </div>
    <div class="card">
      <h3>Update Task</h3>
      <textarea id="taskInput" placeholder="New task description..."></textarea>
      <div class="btn-group">
        <button class="primary" onclick="updateTask()">Update Task</button>
      </div>
    </div>
  </div>

  <!-- HISTORY TAB -->
  <div class="panel" id="panel-history">
    <div class="card">
      <h3>Iteration History</h3>
      <div id="historyTable"></div>
    </div>
  </div>

  <!-- LOGS TAB -->
  <div class="panel" id="panel-logs">
    <div class="card">
      <h3>Logs</h3>
      <div style="margin-bottom:12px;">
        <select id="logSelect" onchange="loadLog()">
          <option value="changelog">Changelog</option>
        </select>
      </div>
      <pre id="logContent">Select a log to view...</pre>
    </div>
  </div>
</div>

<script>
let chartVerdict = null, chartCumulative = null;
const COLORS = {improvement:'#3fb950', neutral:'#d29922', regression:'#f85149'};

function switchTab(name) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  event.target.classList.add('active');
  document.getElementById('panel-' + name).classList.add('active');
}

async function api(method, path, body) {
  const opts = {method, headers:{'Content-Type':'application/json'}};
  if (body) opts.body = JSON.stringify(body);
  const r = await fetch(path, opts);
  return r.json();
}

async function refreshStatus() {
  try {
    const s = await api('GET', '/api/status');
    document.getElementById('pillIter').textContent = 'Iter: ' + s.iteration;
    const st = document.getElementById('pillStatus');
    st.textContent = 'Status: ' + s.status;
    const sm = s.status==='running'?'green'
      :s.status==='paused'?'yellow':'';
    st.className = 'pill ' + sm;
    const br = s.branch_name||'-';
    document.getElementById('pillBranch').textContent =
      'Branch: ' + br;
    const lv = document.getElementById('pillVerdict');
    const last = s.last_verdict || '-';
    lv.textContent = 'Last: ' + last;
    const vc = last==='improvement'?'green'
      :last==='regression'?'red':'yellow';
    lv.className = 'pill ' + vc;
    document.getElementById('pillBest').textContent =
      'Best: iter ' + (s.best_iteration||0);
    document.getElementById('taskDisplay').textContent = s.task || '(no task)';
    updateLogSelect(s.iteration);
  } catch(e) {}
}

function updateLogSelect(maxIter) {
  const sel = document.getElementById('logSelect');
  const cur = sel.value;
  const opts = ['<option value="changelog">Changelog</option>'];
  for (let i = maxIter; i >= 1; i--) {
    opts.push('<option value="' + i + '">Iteration ' + i + '</option>');
  }
  sel.innerHTML = opts.join('');
  if (cur) sel.value = cur;
}

async function refreshHistory() {
  try {
    const h = await api('GET', '/api/history');
    updateCharts(h.history || []);
    updateHistoryTable(h.history || []);
    updateSummaryTable(h.history || []);
  } catch(e) {}
}

function updateCharts(history) {
  const labels = history.map(r => 'Iter ' + r.iteration);
  const verdictColors = history.map(r => COLORS[r.verdict] || COLORS.neutral);

  // Verdict timeline (bar chart with colored bars)
  const ctx1 = document.getElementById('chartVerdict').getContext('2d');
  if (chartVerdict) chartVerdict.destroy();
  chartVerdict = new Chart(ctx1, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label: 'Verdict',
        data: history.map(() => 1),
        backgroundColor: verdictColors,
        borderWidth: 0,
        borderRadius: 4,
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: { y: { display: false }, x: { ticks: { color: '#8b949e' } } }
    }
  });

  // Cumulative improvements
  let cum = 0;
  const cumData = history.map(r => {
    if (r.verdict === 'improvement') cum++; return cum;
  });
  const ctx2 = document.getElementById('chartCumulative').getContext('2d');
  if (chartCumulative) chartCumulative.destroy();
  chartCumulative = new Chart(ctx2, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: 'Improvements',
        data: cumData,
        borderColor: '#3fb950',
        backgroundColor: 'rgba(63,185,80,0.1)',
        fill: true,
        tension: 0.3,
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        y: { beginAtZero: true, ticks: { color: '#8b949e' } },
        x: { ticks: { color: '#8b949e' } }
      }
    }
  });
}

function updateHistoryTable(history) {
  if (!history.length) {
    document.getElementById('historyTable').innerHTML = '<p>No iterations yet.</p>';
    return;
  }
  let html = '<table><tr><th>Iter</th><th>Verdict</th><th>Changes</th>'
    + '<th>Reasoning</th><th>Commit</th></tr>';
  for (const r of history.slice().reverse()) {
    const vc = 'v-' + r.verdict + (r.reverted ? ' v-reverted' : '');
    const sha = r.commit_sha ? r.commit_sha.substring(0,7) : '-';
    html += '<tr><td>' + r.iteration + '</td>'
      + '<td class="' + vc + '">' + r.verdict + (r.reverted?' (reverted)':'') + '</td>'
      + '<td>' + esc(r.changes_summary) + '</td>'
      + '<td>' + esc(r.verdict_reasoning) + '</td>'
      + '<td><code>' + sha + '</code></td></tr>';
  }
  html += '</table>';
  document.getElementById('historyTable').innerHTML = html;
}

function updateSummaryTable(history) {
  const imp = history.filter(r => r.verdict === 'improvement').length;
  const neu = history.filter(r => r.verdict === 'neutral').length;
  const reg = history.filter(r => r.verdict === 'regression').length;
  const rev = history.filter(r => r.reverted).length;
  document.getElementById('summaryTable').innerHTML =
    '<p><span class="v-improvement">Improvements: ' + imp + '</span> | '
    + '<span class="v-neutral">Neutral: ' + neu + '</span> | '
    + '<span class="v-regression">Regressions: ' + reg + '</span> | '
    + 'Reverted: ' + rev + ' | Total: ' + history.length + '</p>';
}

function esc(s) {
  if (!s) return '';
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

async function sendNote() {
  const text = document.getElementById('noteInput').value.trim();
  if (!text) return;
  await api('POST', '/api/note', {text});
  document.getElementById('noteInput').value = '';
  alert('Note added');
}

async function sendAction(action) {
  if (action === 'stop' && !confirm('Stop the improvement loop?')) return;
  if (action === 'merge' && !confirm('Merge improvement branch to main?')) return;
  await api('POST', '/api/action', {action});
  refreshStatus();
}

async function updateTask() {
  const text = document.getElementById('taskInput').value.trim();
  if (!text) return;
  await api('POST', '/api/task', {task: text});
  document.getElementById('taskInput').value = '';
  refreshStatus();
}

async function loadLog() {
  const sel = document.getElementById('logSelect').value;
  try {
    const data = await api('GET', '/api/logs?iter=' + sel);
    document.getElementById('logContent').textContent = data.content || '(empty)';
  } catch(e) {
    document.getElementById('logContent').textContent = 'Failed to load log.';
  }
}

// Auto-refresh
refreshStatus();
refreshHistory();
setInterval(refreshStatus, 15000);
setInterval(refreshHistory, 30000);
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------


class _ImproveHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the improvement dashboard."""

    project_path: ClassVar[Path]

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        """Suppress default access logging."""

    def do_GET(self) -> None:  # noqa: N802
        """Handle GET requests."""
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path == "/":
            self._send_html(_DASHBOARD_HTML)
        elif path == "/api/status":
            self._handle_status()
        elif path == "/api/history":
            self._handle_history()
        elif path == "/api/logs":
            self._handle_logs(qs)
        elif path == "/api/diff":
            self._handle_diff(qs)
        else:
            self._send_json({"error": "not found"}, 404)

    def do_POST(self) -> None:  # noqa: N802
        """Handle POST requests."""
        path = urlparse(self.path).path

        if path == "/api/note":
            self._handle_note()
        elif path == "/api/action":
            self._handle_action()
        elif path == "/api/task":
            self._handle_task()
        else:
            self._send_json({"error": "not found"}, 404)

    # --- GET handlers ---

    def _handle_status(self) -> None:
        """Return current loop status."""
        state = _load_improve_state(self.project_path)
        last_verdict = ""
        if state.history:
            last_verdict = state.history[-1].verdict
        self._send_json(
            {
                "iteration": state.iteration,
                "status": state.status,
                "branch_name": state.branch_name,
                "base_branch": state.base_branch,
                "task": state.task,
                "last_verdict": last_verdict,
                "best_iteration": state.best_iteration,
                "consecutive_regressions": state.consecutive_regressions,
                "consecutive_stalls": state.consecutive_stalls,
                "mode": state.mode,
                "max_iterations": state.max_iterations,
                "started_at": state.started_at,
            }
        )

    def _handle_history(self) -> None:
        """Return full iteration history."""
        state = _load_improve_state(self.project_path)
        history = []
        for rec in state.history:
            history.append(
                {
                    "iteration": rec.iteration,
                    "verdict": rec.verdict,
                    "verdict_reasoning": rec.verdict_reasoning,
                    "changes_summary": rec.changes_summary,
                    "commit_sha": rec.commit_sha,
                    "reverted": rec.reverted,
                    "timestamp": rec.timestamp,
                }
            )
        self._send_json({"history": history})

    def _handle_logs(self, qs: dict[str, list[str]]) -> None:
        """Return log content for a specific iteration or changelog."""
        iter_val = qs.get("iter", ["changelog"])[0]
        if iter_val == "changelog":
            log_path = self.project_path / ".vibegen/improve/CHANGELOG.md"
        else:
            log_path = self.project_path / f".vibegen/improve/logs/iter_{iter_val}.txt"
        content = ""
        if log_path.exists():
            content = log_path.read_text(encoding="utf-8")
        self._send_json({"content": content})

    def _handle_diff(self, qs: dict[str, list[str]]) -> None:
        """Return git diff for a specific iteration commit."""
        from ._io import _run_cmd

        iter_val = qs.get("iter", [""])[0]
        state = _load_improve_state(self.project_path)
        sha = ""
        for rec in state.history:
            if str(rec.iteration) == iter_val:
                sha = rec.commit_sha
                break
        if not sha:
            self._send_json({"diff": "(no commit found)"})
            return
        result = _run_cmd(
            ["git", "diff", f"{sha}~1..{sha}"],
            cwd=self.project_path,
            capture_output=True,
            check=False,
        )
        self._send_json({"diff": (result.stdout or "")[:10000]})

    # --- POST handlers ---

    def _handle_note(self) -> None:
        """Add a note for Claude."""
        body = self._read_body()
        text = body.get("text", "").strip()
        if not text:
            self._send_json({"error": "empty note"}, 400)
            return
        state = _load_improve_state(self.project_path)
        state.notes_for_claude.append(text)
        _save_improve_state(self.project_path, state)
        self._send_json({"ok": True})

    def _handle_action(self) -> None:
        """Handle loop control actions."""
        body = self._read_body()
        action = body.get("action", "")
        state = _load_improve_state(self.project_path)

        if action == "pause":
            state.status = "paused"
            _save_improve_state(self.project_path, state)
            self._send_json({"ok": True, "status": "paused"})
        elif action == "resume":
            state.status = "running"
            _save_improve_state(self.project_path, state)
            self._send_json({"ok": True, "status": "running"})
        elif action == "stop":
            state.status = "done"
            _save_improve_state(self.project_path, state)
            self._send_json({"ok": True, "status": "done"})
        elif action == "merge":
            self._send_json({"ok": True, "message": "Merge will happen on loop exit"})
            state.status = "done"
            _save_improve_state(self.project_path, state)
        else:
            self._send_json({"error": f"unknown action: {action}"}, 400)

    def _handle_task(self) -> None:
        """Update the task description."""
        body = self._read_body()
        task = body.get("task", "").strip()
        if not task:
            self._send_json({"error": "empty task"}, 400)
            return
        state = _load_improve_state(self.project_path)
        state.task = task
        _save_improve_state(self.project_path, state)
        self._send_json({"ok": True})

    # --- Response helpers ---

    def _send_json(self, data: Any, status: int = 200) -> None:
        """Send a JSON response.

        Args:
            data: Data to serialize.
            status: HTTP status code.
        """
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str) -> None:
        """Send an HTML response.

        Args:
            html: HTML content string.
        """
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> dict[str, Any]:
        """Read and parse the JSON request body.

        Returns:
            Parsed JSON dict, or empty dict on error.
        """
        try:
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length)
            result: dict[str, Any] = json.loads(raw) if raw else {}
            return result
        except Exception:  # noqa: BLE001
            return {}


# ---------------------------------------------------------------------------
# Server lifecycle
# ---------------------------------------------------------------------------


def _start_webui(project_path: Path, port: int) -> ThreadingHTTPServer:
    """Start the web dashboard on a background daemon thread.

    Args:
        project_path: Project root directory.
        port: HTTP port to listen on.

    Returns:
        The running server instance.
    """
    _ImproveHandler.project_path = project_path
    server = ThreadingHTTPServer(("", port), _ImproveHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def _stop_webui(server: ThreadingHTTPServer) -> None:
    """Shut down the web dashboard server.

    Args:
        server: Server instance returned by ``_start_webui``.
    """
    server.shutdown()
