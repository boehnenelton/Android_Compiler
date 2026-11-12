/* ==========================================================================
   Android Compiler Web UI Client Logic
   Author: Elton Boehnen · License: PolyForm-Noncommercial-1.0.0
   ========================================================================== */

let isBuilding = false;
let pollTimer = null;
let currentActiveTarget = null;

document.addEventListener("DOMContentLoaded", () => {
  refreshAll();
  fetchLog();
});

function refreshAll() {
  loadStatus();
  loadTargets();
  loadArtifacts();
}

function showToast(msg, duration = 3000) {
  const toast = document.getElementById("toast-msg");
  if (!toast) return;
  toast.textContent = msg;
  toast.style.display = "block";
  setTimeout(() => {
    toast.style.display = "none";
  }, duration);
}

// ─── Status & Chamber Target ────────────────────────────────────────────────
async function loadStatus() {
  try {
    const res = await fetch("/api/status");
    const data = await res.json();
    if (data.status !== "ok") return;

    renderActiveTarget(data.active_target);
    renderDiagnostics(data.environment);
    handleBuildStatus(data.build);
  } catch (err) {
    console.error("loadStatus error:", err);
  }
}

function renderActiveTarget(target) {
  currentActiveTarget = target;
  const emptyMsg = document.getElementById("target-empty-msg");
  const metaGrid = document.getElementById("target-meta");
  const dockPill = document.getElementById("dock-target-name");

  if (!target) {
    emptyMsg.style.display = "block";
    metaGrid.style.display = "none";
    dockPill.textContent = "Target: None";
    return;
  }

  emptyMsg.style.display = "none";
  metaGrid.style.display = "grid";
  dockPill.textContent = `Target: ${target.name}`;

  document.getElementById("meta-name").textContent = target.name;
  document.getElementById("meta-pkg").textContent = target.package_name || "—";
  document.getElementById("meta-path").textContent = target.path;
  document.getElementById("meta-builds").textContent = target.build_count || 0;

  const statusBadge = document.getElementById("meta-status");
  statusBadge.textContent = target.last_status || "Ready";
  statusBadge.className = "badge";
  if (target.last_status === "success") {
    statusBadge.classList.add("badge-success");
  } else if (target.last_status === "failed") {
    statusBadge.classList.add("badge-error");
  } else {
    statusBadge.classList.add("badge-warning");
  }

  const apkContainer = document.getElementById("meta-apk-container");
  if (target.last_apk) {
    apkContainer.style.display = "flex";
    document.getElementById("meta-apk").textContent = `${target.last_apk} (${target.last_apk_size || "—"})`;
  } else {
    apkContainer.style.display = "none";
  }
}

function renderDiagnostics(env) {
  const container = document.getElementById("settings-diagnostics");
  if (!container || !env) return;

  const errorsHtml = (env.errors || []).length > 0
    ? `<div style="color: #DE2626; margin-top: 8px;"><strong>Issues:</strong><br>${env.errors.join("<br>")}</div>`
    : `<div style="color: #16A34A; margin-top: 8px;">[✓] All required build tools verified.</div>`;

  container.innerHTML = `
    <p><strong>Environment State:</strong></p>
    <ul style="margin: 8px 0 8px 20px; line-height: 1.6;">
      <li><strong>JAVA_HOME:</strong> <code>${env.java_home}</code></li>
      <li><strong>ANDROID_HOME:</strong> <code>${env.android_home}</code></li>
      <li><strong>System Gradle:</strong> ${env.has_gradle ? "Detected" : "Missing"}</li>
      <li><strong>Runtime Valid:</strong> ${env.valid ? "Yes" : "No"}</li>
    </ul>
    ${errorsHtml}
    <div style="margin-top: 14px; padding-top: 8px; border-top: 1px solid #E2E8F0; font-size: 0.75rem; color: #64748B;">
      Android Compiler Suite · Elton Boehnen · boehnenelton2024@gmail.com<br>
      PolyForm Noncommercial License 1.0.0
    </div>
  `;
}

// ─── Target Selection ────────────────────────────────────────────────────────
async function loadTargets() {
  const container = document.getElementById("targets-container");
  try {
    const res = await fetch("/api/targets");
    const data = await res.json();
    if (!data.targets || data.targets.length === 0) {
      container.innerHTML = '<p class="empty-state">No Android projects found in scanned roots.</p>';
      return;
    }

    container.innerHTML = data.targets.map(t => `
      <div class="target-row ${t.is_active ? 'active' : ''}">
        <div class="target-info">
          <span class="target-title">${escapeHtml(t.name)} ${t.is_active ? '<span class="badge badge-success">ACTIVE</span>' : ''}</span>
          <span class="target-sub">${escapeHtml(t.path)}</span>
        </div>
        <button class="btn btn-sm ${t.is_active ? 'btn-outline' : 'btn-primary'}" onclick="selectTarget('${escapeHtml(t.path)}')">
          ${t.is_active ? 'Reload' : 'Load Target'}
        </button>
      </div>
    `).join("");
  } catch (err) {
    container.innerHTML = `<p class="empty-state" style="color: red;">Failed to load targets: ${err.message}</p>`;
  }
}

async function selectTarget(pathOrName) {
  try {
    const res = await fetch("/api/target/select", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ target: pathOrName })
    });
    const data = await res.json();
    if (res.ok) {
      showToast(data.message);
      refreshAll();
    } else {
      showToast(`Error: ${data.message}`);
    }
  } catch (err) {
    showToast(`Failed to select target: ${err.message}`);
  }
}

async function clearTarget() {
  try {
    const res = await fetch("/api/target/clear", { method: "POST" });
    const data = await res.json();
    showToast(data.message);
    refreshAll();
  } catch (err) {
    showToast(`Failed to clear target: ${err.message}`);
  }
}

function loadCustomTarget() {
  const input = document.getElementById("custom-path-input");
  const val = (input.value || "").trim();
  if (!val) {
    showToast("Please enter a directory path");
    return;
  }
  selectTarget(val);
  input.value = "";
}

// ─── Build Execution ─────────────────────────────────────────────────────────
async function triggerBuild(action) {
  if (!currentActiveTarget) {
    showToast("Please load a target into chamber first!");
    return;
  }

  try {
    const res = await fetch("/api/build", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: action })
    });
    const data = await res.json();
    if (res.ok) {
      showToast(data.message);
      startPolling();
    } else {
      showToast(`Build failed: ${data.message}`);
    }
  } catch (err) {
    showToast(`Execution error: ${err.message}`);
  }
}

function handleBuildStatus(build) {
  if (!build) return;
  const timerBox = document.getElementById("build-timer-box");
  const timerText = document.getElementById("build-timer-text");

  if (build.is_building) {
    isBuilding = true;
    timerBox.style.display = "inline-flex";
    timerText.textContent = `${build.current_action.toUpperCase()}: ${build.elapsed_seconds}s`;
    if (!pollTimer) startPolling();
  } else {
    if (isBuilding) {
      // Just transitioned from building to idle
      isBuilding = false;
      timerBox.style.display = "none";
      stopPolling();
      loadArtifacts();
      fetchLog();
      showToast("Build finished!");
    } else {
      timerBox.style.display = "none";
    }
  }
}

function startPolling() {
  if (pollTimer) clearInterval(pollTimer);
  isBuilding = true;
  document.getElementById("build-timer-box").style.display = "inline-flex";
  pollTimer = setInterval(async () => {
    await fetchLog();
    await loadStatus();
  }, 1500);
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

// ─── Log Console ─────────────────────────────────────────────────────────────
async function fetchLog() {
  try {
    const res = await fetch("/api/build/log?lines=150");
    const data = await res.json();
    if (data.status === "ok") {
      const consoleEl = document.getElementById("log-console");
      consoleEl.textContent = data.log || "No log content.";
      const autoscroll = document.getElementById("autoscroll-chk").checked;
      if (autoscroll) {
        consoleEl.scrollTop = consoleEl.scrollHeight;
      }
    }
  } catch (err) {
    console.error("fetchLog error:", err);
  }
}

function clearLogDisplay() {
  document.getElementById("log-console").textContent = "Log view cleared.";
}

// ─── Artifacts & Installation ────────────────────────────────────────────────
async function loadArtifacts() {
  const container = document.getElementById("artifacts-container");
  try {
    const res = await fetch("/api/artifacts");
    const data = await res.json();
    if (!data.artifacts || data.artifacts.length === 0) {
      container.innerHTML = '<p class="empty-state">No compiled APK artifacts found.</p>';
      return;
    }

    container.innerHTML = data.artifacts.map(a => `
      <div class="artifact-row">
        <div>
          <div class="artifact-name">${escapeHtml(a.name)} <span class="badge ${a.variant === 'release' ? 'badge-warning' : 'badge-success'}">${a.variant.toUpperCase()}</span></div>
          <div class="artifact-meta">Size: ${a.size_human} · Created: ${a.created_at.substring(0, 19).replace('T', ' ')}</div>
        </div>
        <div class="artifact-actions">
          <button class="btn btn-sm btn-outline" onclick="installApk('${escapeHtml(a.path)}')">Install</button>
          <a class="btn btn-sm btn-primary" href="/download/${encodeURIComponent(a.name)}" download>Download</a>
        </div>
      </div>
    `).join("");
  } catch (err) {
    container.innerHTML = `<p class="empty-state" style="color: red;">Failed to load artifacts: ${err.message}</p>`;
  }
}

async function installApk(apkPath = null) {
  try {
    const res = await fetch("/api/install", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ apk_path: apkPath })
    });
    const data = await res.json();
    if (res.ok) {
      showToast(data.message);
    } else {
      showToast(`Install error: ${data.message}`);
    }
  } catch (err) {
    showToast(`Install failed: ${err.message}`);
  }
}

// ─── Drawer & Settings Modals ────────────────────────────────────────────────
function toggleDrawer() {
  const drawer = document.getElementById("side-drawer");
  drawer.classList.toggle("open");
}

function toggleSettings() {
  const modal = document.getElementById("settings-modal");
  modal.style.display = modal.style.display === "none" ? "flex" : "none";
}

function escapeHtml(str) {
  if (!str) return "";
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
