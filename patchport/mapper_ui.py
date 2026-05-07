"""Browser-based visual file mapping UI.

Starts a local HTTP server, opens the default browser, and waits for the
user to confirm or edit the suggested file mapping.  Returns the confirmed
list of MappingCandidate objects.
"""

import http.server
import json
import socket
import threading
import webbrowser

from .mapper import MappingCandidate


def _find_free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def show_mapping_ui(
    candidates: list[MappingCandidate],
    target_files: list[str],
) -> list[MappingCandidate]:
    """Open browser mapping UI and return the confirmed mapping.

    Blocks until the user clicks "Confirm" in the browser.
    """
    result_holder: list[list[MappingCandidate]] = []
    done = threading.Event()
    port = _find_free_port()
    ui_data = _build_ui_data(candidates, target_files)

    class _Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *_): pass  # silence request logs

        def do_GET(self):
            if self.path == "/":
                self._send(200, "text/html; charset=utf-8", _HTML.encode())
            elif self.path == "/data":
                self._send(200, "application/json", json.dumps(ui_data).encode())
            else:
                self.send_error(404)

        def do_POST(self):
            if self.path == "/confirm":
                n = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(n))
                result_holder.append(_parse_result(body, candidates))
                self._send(200, "application/json", b'{"ok":true}')
                done.set()
            else:
                self.send_error(404)

        def _send(self, code, ctype, body):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", len(body))
            self.end_headers()
            self.wfile.write(body)

    server = http.server.HTTPServer(("127.0.0.1", port), _Handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()

    webbrowser.open(f"http://127.0.0.1:{port}/")
    done.wait()
    server.shutdown()

    return result_holder[0]


def _build_ui_data(
    candidates: list[MappingCandidate], target_files: list[str]
) -> dict:
    return {
        "upstream": [
            {
                "path": c.upstream_path,
                "score": round(c.score, 3),
                "is_binary": c.is_binary,
                "suggested_target": c.target_path,
            }
            for c in candidates
        ],
        "target": sorted(target_files),
    }


def _parse_result(body: dict, original: list[MappingCandidate]) -> list[MappingCandidate]:
    score_map = {c.upstream_path: c.score for c in original}
    binary_map = {c.upstream_path: c.is_binary for c in original}
    result = []
    for item in body.get("mappings", []):
        up = item["upstream_path"]
        tgt = item.get("target_path") or None
        is_bin = binary_map.get(up, False)
        action = "skip" if tgt is None else ("overwrite" if is_bin else "merge")
        result.append(
            MappingCandidate(
                upstream_path=up,
                target_path=tgt,
                score=score_map.get(up, 0.0),
                is_binary=is_bin,
                action=action,
            )
        )
    return result


# ---------------------------------------------------------------------------
# Embedded HTML/JS — single-page app, no external dependencies
# ---------------------------------------------------------------------------

_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>patchport — File Mapping</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#0f1117;color:#e2e8f0;height:100vh;display:flex;flex-direction:column;overflow:hidden}
header{padding:14px 28px;border-bottom:1px solid #1e2535;display:flex;align-items:center;gap:14px;flex-shrink:0}
header h1{font-size:15px;font-weight:700;color:#fff;letter-spacing:-.01em}
header p{font-size:11px;color:#64748b;margin-top:2px}
.workspace{display:flex;flex:1;position:relative;overflow:hidden;min-height:0}
.panel{flex:1;overflow-y:auto;padding:18px 16px 80px;display:flex;flex-direction:column;gap:5px}
.panel-title{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:#475569;margin-bottom:10px;padding-bottom:8px;border-bottom:1px solid #1e2535;flex-shrink:0}
.divider{width:1px;background:#1e2535;flex-shrink:0}
/* nodes */
.node{background:#141824;border:1.5px solid #222d45;border-radius:8px;padding:9px 14px;cursor:pointer;position:relative;transition:border-color .12s,background .12s;display:flex;flex-direction:column;gap:2px;min-height:50px;justify-content:center}
.node:hover{border-color:#3b4d6e;background:#172032}
.node.selected{border-color:#3b82f6!important;background:#162040!important;box-shadow:0 0 0 3px rgba(59,130,246,.15)}
.node.mapped{border-color:#22c55e}
.node.unmapped{opacity:.38}
.node.binary-node{border-color:#7c3aed}
.node-name{font-size:12px;font-weight:500;color:#e2e8f0;word-break:break-all}
.node-dir{font-size:11px;color:#475569;margin-top:1px;word-break:break-all}
.badges{display:flex;gap:4px;margin-top:4px;flex-wrap:wrap}
.badge{font-size:10px;font-weight:600;padding:1px 7px;border-radius:4px;letter-spacing:.03em}
.badge-hi{background:#14532d;color:#4ade80}
.badge-mid{background:#422006;color:#fbbf24}
.badge-lo{background:#1f2937;color:#6b7280}
.badge-bin{background:#3b0764;color:#c4b5fd}
/* ports */
.port{position:absolute;width:14px;height:14px;border-radius:50%;background:#1e2b45;border:2px solid #2a3d5e;cursor:crosshair;z-index:3;transition:background .12s,border-color .12s,transform .12s}
.port:hover{background:#3b82f6;border-color:#3b82f6;transform:scale(1.3)}
.port-r{right:-7px;top:50%;transform:translateY(-50%)}
.port-r:hover{transform:translateY(-50%) scale(1.3)}
.port-l{left:-7px;top:50%;transform:translateY(-50%)}
.port-l:hover{transform:translateY(-50%) scale(1.3)}
.port.active{background:#3b82f6;border-color:#3b82f6}
/* SVG overlay */
#svg{position:absolute;top:0;left:0;width:100%;height:100%;pointer-events:none;overflow:visible}
.link{stroke-width:2;fill:none;pointer-events:stroke;cursor:pointer;transition:stroke-width .1s,opacity .1s}
.link:hover{stroke-width:4;opacity:1!important}
.link-preview{stroke:#3b82f6;stroke-width:1.5;fill:none;stroke-dasharray:7 4;opacity:.65;pointer-events:none}
/* footer */
footer{position:fixed;bottom:0;left:0;right:0;padding:12px 28px;border-top:1px solid #1e2535;background:#0f1117;display:flex;align-items:center;justify-content:space-between;z-index:10}
.hint{font-size:11px;color:#475569;line-height:1.6}
.hint kbd{background:#1e2535;border:1px solid #2a3558;border-radius:3px;padding:1px 5px;font-size:10px}
.btn{border:none;border-radius:8px;padding:9px 26px;font-size:13px;font-weight:600;cursor:pointer;transition:.12s}
.btn-confirm{background:#3b82f6;color:#fff}
.btn-confirm:hover{background:#2563eb}
.btn-confirm:active{background:#1d4ed8}
/* done overlay */
.overlay{position:fixed;inset:0;background:rgba(15,17,23,.92);display:flex;align-items:center;justify-content:center;z-index:100}
.overlay-box{text-align:center;padding:40px}
.overlay-box svg{margin-bottom:16px}
.overlay-box p{color:#4ade80;font-size:17px;font-weight:600}
.overlay-box small{color:#475569;font-size:12px;display:block;margin-top:6px}
</style>
</head>
<body>
<header>
  <div>
    <h1>patchport &mdash; File Mapping</h1>
    <p>Connect upstream files to your local files. Unconnected upstream files will be skipped.</p>
  </div>
</header>
<div class="workspace" id="ws">
  <div class="panel" id="lp">
    <div class="panel-title">Upstream &mdash; changed files</div>
  </div>
  <div class="divider"></div>
  <div class="panel" id="rp">
    <div class="panel-title">Your files &mdash; target</div>
  </div>
  <svg id="svg">
    <g id="links"></g>
    <path id="preview" class="link-preview" style="display:none"/>
  </svg>
</div>
<footer>
  <div class="hint">
    <kbd>click</kbd> upstream &rarr; <kbd>click</kbd> target to connect &nbsp;&middot;&nbsp;
    drag from upstream node to target &nbsp;&middot;&nbsp;
    <kbd>click line</kbd> to remove
  </div>
  <button class="btn btn-confirm" onclick="doConfirm()">Confirm mapping</button>
</footer>
<div class="overlay" id="done-overlay" style="display:none">
  <div class="overlay-box">
    <svg width="48" height="48" fill="none" viewBox="0 0 48 48">
      <circle cx="24" cy="24" r="22" stroke="#22c55e" stroke-width="3"/>
      <path d="M14 24l8 8 12-14" stroke="#22c55e" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>
    <p>Mapping confirmed!</p>
    <small>You can close this tab — patchport is applying the diff.</small>
  </div>
</div>
<script>
'use strict';
const st = { mappings: {}, selected: null };
let uData = [], tData = [];
const upEls = new Map();   // path → DOM element
const tgEls = new Map();   // path → DOM element
const ws = document.getElementById('ws');

fetch('/data').then(r => r.json()).then(data => {
  uData = data.upstream;
  tData = data.target;
  for (const u of uData) st.mappings[u.path] = u.suggested_target || null;
  buildNodes();
  requestAnimationFrame(redraw);
});

// ── Build DOM nodes ──────────────────────────────────────────────────────────
function buildNodes() {
  const lp = document.getElementById('lp');
  const rp = document.getElementById('rp');

  for (const u of uData) {
    const el = makeNode(u.path, 'upstream');
    const name = lastName(u.path);
    const dir  = dirPart(u.path);
    el.innerHTML =
      `<div class="node-name">${esc(name)}</div>` +
      (dir ? `<div class="node-dir">${esc(dir)}/</div>` : '') +
      `<div class="badges">${u.is_binary ? badgeBin() : badgeConf(u.score)}</div>` +
      `<div class="port port-r" id="pr-${idx(u.path,'u')}"></div>`;

    el.querySelector('.port').addEventListener('mousedown', e => {
      e.stopPropagation();
      startDrag(e, u.path);
    });
    el.addEventListener('click', e => {
      if (e.target.classList.contains('port')) return;
      upClick(u.path);
    });
    upEls.set(u.path, el);
    lp.appendChild(el);
  }

  for (const t of tData) {
    const el = makeNode(t, 'target');
    const name = lastName(t);
    const dir  = dirPart(t);
    el.innerHTML =
      `<div class="port port-l" id="pl-${idx(t,'t')}"></div>` +
      `<div class="node-name">${esc(name)}</div>` +
      (dir ? `<div class="node-dir">${esc(dir)}/</div>` : '');
    el.addEventListener('click', e => {
      if (e.target.classList.contains('port')) return;
      tgClick(t);
    });
    tgEls.set(t, el);
    rp.appendChild(el);
  }
  styleNodes();
}

function makeNode(path, type) {
  const el = document.createElement('div');
  el.className = 'node';
  el.dataset.path = path;
  el.dataset.type = type;
  return el;
}

// ── Styling ──────────────────────────────────────────────────────────────────
function styleNodes() {
  const used = new Set(Object.values(st.mappings).filter(Boolean));

  for (const u of uData) {
    const el = upEls.get(u.path);
    if (!el) continue;
    el.className = 'node' + (u.is_binary ? ' binary-node' : '');
    if (st.selected === u.path) el.classList.add('selected');
    else if (st.mappings[u.path]) el.classList.add('mapped');
    else el.classList.add('unmapped');
  }

  for (const t of tData) {
    const el = tgEls.get(t);
    if (!el) continue;
    el.className = 'node' + (used.has(t) ? ' mapped' : '');
  }
}

// ── Click interaction ────────────────────────────────────────────────────────
function upClick(path) {
  st.selected = st.selected === path ? null : path;
  styleNodes();
}

function tgClick(path) {
  if (!st.selected) return;
  const up = st.selected;
  if (st.mappings[up] === path) {
    st.mappings[up] = null;
  } else {
    // 1 upstream ↔ 1 target: clear any existing mapping to this target
    for (const k in st.mappings) { if (st.mappings[k] === path && k !== up) st.mappings[k] = null; }
    st.mappings[up] = path;
  }
  st.selected = null;
  styleNodes();
  redraw();
}

// ── Drag interaction ─────────────────────────────────────────────────────────
function startDrag(evt, upPath) {
  const preview = document.getElementById('preview');
  const src = portXY(upEls.get(upPath), 'right');
  preview.style.display = '';

  const onMove = e => {
    const r = ws.getBoundingClientRect();
    preview.setAttribute('d', curve(src.x, src.y, e.clientX - r.left, e.clientY - r.top));
  };
  const onUp = e => {
    preview.style.display = 'none';
    document.removeEventListener('mousemove', onMove);
    document.removeEventListener('mouseup', onUp);
    const hit = document.elementFromPoint(e.clientX, e.clientY);
    const tgNode = hit && hit.closest('[data-type="target"]');
    if (tgNode) {
      const tPath = tgNode.dataset.path;
      for (const k in st.mappings) { if (st.mappings[k] === tPath && k !== upPath) st.mappings[k] = null; }
      st.mappings[upPath] = tPath;
      st.selected = null;
      styleNodes();
      redraw();
    }
  };
  document.addEventListener('mousemove', onMove);
  document.addEventListener('mouseup', onUp);
}

// ── SVG drawing ───────────────────────────────────────────────────────────────
function redraw() {
  const g = document.getElementById('links');
  g.innerHTML = '';
  const wr = ws.getBoundingClientRect();
  for (const u of uData) {
    const tgt = st.mappings[u.path];
    if (!tgt) continue;
    const upEl = upEls.get(u.path);
    const tgEl = tgEls.get(tgt);
    if (!upEl || !tgEl) continue;
    const src = portXY(upEl, 'right');
    const dst = portXY(tgEl, 'left');
    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path.setAttribute('d', curve(src.x, src.y, dst.x, dst.y));
    path.setAttribute('class', 'link');
    path.setAttribute('stroke', lineColor(u.score, u.is_binary));
    path.setAttribute('opacity', '0.72');
    path.dataset.up = u.path;
    path.addEventListener('click', () => {
      st.mappings[u.path] = null;
      styleNodes();
      redraw();
    });
    g.appendChild(path);
  }
}

function portXY(nodeEl, side) {
  const r = nodeEl.getBoundingClientRect();
  const wr = ws.getBoundingClientRect();
  return {
    x: side === 'right' ? r.right - wr.left : r.left - wr.left,
    y: r.top + r.height / 2 - wr.top,
  };
}

function curve(x1, y1, x2, y2) {
  const cx = Math.abs(x2 - x1) * 0.5;
  return `M${x1},${y1} C${x1+cx},${y1} ${x2-cx},${y2} ${x2},${y2}`;
}

function lineColor(score, isBinary) {
  if (isBinary) return '#a855f7';
  if (score >= 0.8) return '#22c55e';
  if (score >= 0.5) return '#f59e0b';
  return '#64748b';
}

// Redraw on panel scroll or window resize
document.getElementById('lp').addEventListener('scroll', redraw);
document.getElementById('rp').addEventListener('scroll', redraw);
window.addEventListener('resize', redraw);

// ── Confirm ───────────────────────────────────────────────────────────────────
function doConfirm() {
  const mappings = Object.entries(st.mappings).map(([up, tgt]) => ({
    upstream_path: up, target_path: tgt || null,
  }));
  fetch('/confirm', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mappings }),
  }).then(() => {
    document.getElementById('done-overlay').style.display = 'flex';
  });
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function lastName(p) { return p.split('/').pop(); }
function dirPart(p) { const i = p.lastIndexOf('/'); return i >= 0 ? p.slice(0, i) : ''; }
function esc(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
function badgeConf(score) {
  const pct = Math.round((score || 0) * 100);
  if (score >= 0.8) return `<span class="badge badge-hi">${pct}%</span>`;
  if (score >= 0.5) return `<span class="badge badge-mid">${pct}%</span>`;
  return `<span class="badge badge-lo">${pct > 0 ? pct+'%' : 'new'}</span>`;
}
function badgeBin() { return '<span class="badge badge-bin">binary</span>'; }
// Stable index for port element IDs (avoids CSS-selector issues with slashes)
const _idxCache = new Map();
let _idxN = 0;
function idx(path, prefix) {
  const k = prefix + path;
  if (!_idxCache.has(k)) _idxCache.set(k, _idxN++);
  return _idxCache.get(k);
}
</script>
</body>
</html>
"""
