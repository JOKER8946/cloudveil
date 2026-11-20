// Role-aware dashboard: student / officer / admin.
"use strict";

(async function () {
  let me;
  try {
    me = (await CV.get("/api/auth/me")).user;
  } catch {
    window.location.href = "/";
    return;
  }

  document.getElementById("loading").classList.add("hidden");
  renderNav(me);

  if (me.role === "student") initStudent();
  else if (me.role === "officer") initOfficer();
  else if (me.role === "admin") initAdmin();

  function renderNav(user) {
    const nav = document.getElementById("nav-user");
    nav.classList.remove("hidden");
    nav.innerHTML =
      `<span class="rounded bg-veil-600 px-2 py-0.5 text-xs uppercase">${CV.esc(user.role)}</span>` +
      `<span class="text-veil-50/90">${CV.esc(user.email)}</span>` +
      `<button id="logout" class="rounded bg-white/10 px-2 py-1 hover:bg-white/20">Log out</button>`;
    document.getElementById("logout").addEventListener("click", async () => {
      try { await CV.post("/api/auth/logout", {}); } catch {}
      window.location.href = "/";
    });
  }

  // ---------------- STUDENT ----------------
  function initStudent() {
    document.getElementById("view-student").classList.remove("hidden");
    const input = document.getElementById("file-input");
    const zone = document.getElementById("dropzone");
    const chosen = document.getElementById("chosen-file");

    zone.addEventListener("click", () => input.click());
    zone.addEventListener("dragover", (e) => { e.preventDefault(); zone.classList.add("border-veil-500"); });
    zone.addEventListener("dragleave", () => zone.classList.remove("border-veil-500"));
    zone.addEventListener("drop", (e) => {
      e.preventDefault();
      zone.classList.remove("border-veil-500");
      if (e.dataTransfer.files.length) { input.files = e.dataTransfer.files; chosen.textContent = input.files[0].name; }
    });
    input.addEventListener("change", () => { chosen.textContent = input.files.length ? input.files[0].name : ""; });

    document.getElementById("upload-form").addEventListener("submit", (e) => {
      e.preventDefault();
      if (!input.files.length) { CV.toast("Choose a file first.", "error"); return; }
      uploadWithProgress(input.files[0], document.getElementById("category").value);
    });

    setupShareModal();
    loadMyFiles();
  }

  function uploadWithProgress(file, category) {
    const fd = new FormData();
    fd.append("category", category);
    fd.append("file", file);
    const wrap = document.getElementById("progress-wrap");
    const bar = document.getElementById("progress-bar");
    wrap.classList.remove("hidden");
    bar.style.width = "0%";

    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/files");
    xhr.setRequestHeader("X-CSRF-Token", CV.csrf());
    xhr.withCredentials = true;
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) bar.style.width = Math.round((e.loaded / e.total) * 100) + "%";
    };
    xhr.onload = () => {
      wrap.classList.add("hidden");
      if (xhr.status === 201) {
        CV.toast("Encrypted & uploaded.", "ok");
        document.getElementById("file-input").value = "";
        document.getElementById("chosen-file").textContent = "";
        loadMyFiles();
      } else {
        let msg = "Upload failed.";
        try { msg = JSON.parse(xhr.responseText).error.message; } catch {}
        CV.toast(msg, "error");
      }
    };
    xhr.onerror = () => { wrap.classList.add("hidden"); CV.toast("Upload failed.", "error"); };
    xhr.send(fd);
  }

  async function loadMyFiles() {
    const { files } = await CV.get("/api/files");
    const body = document.getElementById("my-files");
    if (!files.length) { body.innerHTML = `<tr><td colspan="7" class="py-4 text-slate-400">No documents yet.</td></tr>`; return; }
    body.innerHTML = files.map((f) => `
      <tr class="border-b last:border-0">
        <td class="py-2 font-medium">🔒 ${CV.esc(f.original_name)}</td>
        <td>${CV.esc(f.category)}</td>
        <td>${CV.fmtSize(f.size_bytes)}</td>
        <td class="font-mono text-xs text-slate-400">${CV.esc(f.sha256_short)}</td>
        <td>${CV.esc(f.primary_region || "")}</td>
        <td class="text-xs text-slate-500">${CV.fmtDate(f.created_at)}</td>
        <td class="whitespace-nowrap text-right">
          <button data-dl="${f.id}" data-name="${CV.esc(f.original_name)}" class="text-veil-600 hover:underline">Download</button>
          <button data-share="${f.id}" class="ml-2 text-veil-600 hover:underline">Share</button>
          <button data-del="${f.id}" class="ml-2 text-rose-600 hover:underline">Delete</button>
        </td>
      </tr>`).join("");

    body.querySelectorAll("[data-dl]").forEach((b) =>
      b.addEventListener("click", () => downloadFile(b.dataset.dl, b.dataset.name)));
    body.querySelectorAll("[data-share]").forEach((b) =>
      b.addEventListener("click", () => openShare(b.dataset.share)));
    body.querySelectorAll("[data-del]").forEach((b) =>
      b.addEventListener("click", () => deleteFile(b.dataset.del)));
  }

  async function deleteFile(id) {
    if (!confirm("Delete this document? This cannot be undone.")) return;
    try { await CV.del(`/api/files/${id}`); CV.toast("Deleted.", "ok"); loadMyFiles(); }
    catch (e) { CV.toast(e.message, "error"); }
  }

  function setupShareModal() {
    const modal = document.getElementById("share-modal");
    document.getElementById("share-cancel").addEventListener("click", () => modal.classList.add("hidden"));
    document.getElementById("share-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const id = document.getElementById("share-file-id").value;
      const email = document.getElementById("share-email").value.trim();
      const expiryRaw = document.getElementById("share-expiry").value;
      const payload = { grantee_email: email };
      if (expiryRaw) payload.expires_at = new Date(expiryRaw).toISOString();
      try {
        await CV.post(`/api/files/${id}/share`, payload);
        CV.toast("Shared.", "ok");
        modal.classList.add("hidden");
      } catch (err) { CV.toast(err.message, "error"); }
    });
  }

  function openShare(id) {
    document.getElementById("share-file-id").value = id;
    document.getElementById("share-email").value = "";
    document.getElementById("share-expiry").value = "";
    document.getElementById("share-modal").classList.remove("hidden");
    document.getElementById("share-modal").classList.add("flex");
  }

  async function downloadFile(id, name) {
    try {
      const res = await fetch(`/api/files/${id}/download`, { credentials: "same-origin" });
      if (!res.ok) {
        CV.toast(res.status === 409 ? "Integrity check failed." : "Download failed.", "error");
        return;
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = name || "download";
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
    } catch { CV.toast("Download failed.", "error"); }
  }

  // ---------------- OFFICER ----------------
  async function initOfficer() {
    document.getElementById("view-officer").classList.remove("hidden");
    const { files } = await CV.get("/api/files/shared");
    const body = document.getElementById("shared-files");
    if (!files.length) { body.innerHTML = `<tr><td colspan="5" class="py-4 text-slate-400">Nothing shared with you yet.</td></tr>`; return; }
    body.innerHTML = files.map((f) => `
      <tr class="border-b last:border-0">
        <td class="py-2 font-medium">🔒 ${CV.esc(f.original_name)}</td>
        <td>${CV.esc(f.category)}</td>
        <td>${CV.fmtSize(f.size_bytes)}</td>
        <td class="text-xs text-slate-500">${CV.fmtDate(f.created_at)}</td>
        <td class="text-right"><button data-dl="${f.id}" data-name="${CV.esc(f.original_name)}" class="text-veil-600 hover:underline">Download</button></td>
      </tr>`).join("");
    body.querySelectorAll("[data-dl]").forEach((b) =>
      b.addEventListener("click", () => downloadFile(b.dataset.dl, b.dataset.name)));
  }

  // ---------------- ADMIN ----------------
  function initAdmin() {
    document.getElementById("view-admin").classList.remove("hidden");
    const tabs = document.querySelectorAll(".admin-tab");
    const panels = { users: "admin-users", audit: "admin-audit", stats: "admin-stats" };
    tabs.forEach((t) => t.addEventListener("click", () => {
      tabs.forEach((x) => { x.classList.remove("bg-veil-600", "text-white"); x.classList.add("bg-slate-100", "text-slate-600"); });
      t.classList.add("bg-veil-600", "text-white"); t.classList.remove("bg-slate-100", "text-slate-600");
      Object.values(panels).forEach((id) => document.getElementById(id).classList.add("hidden"));
      document.getElementById(panels[t.dataset.tab]).classList.remove("hidden");
      if (t.dataset.tab === "audit") loadAudit();
      if (t.dataset.tab === "stats") loadStats();
    }));
    loadUsers();
  }

  async function loadUsers() {
    const { users } = await CV.get("/api/admin/users");
    const body = document.getElementById("admin-users-body");
    const roles = ["student", "officer", "admin"];
    body.innerHTML = users.map((u) => `
      <tr class="border-b last:border-0">
        <td class="py-2">${CV.esc(u.full_name)}</td>
        <td class="text-slate-500">${CV.esc(u.email)}</td>
        <td>
          <select data-role="${u.id}" class="rounded border border-slate-300 px-1 py-0.5 text-sm">
            ${roles.map((r) => `<option value="${r}" ${r === u.role ? "selected" : ""}>${r}</option>`).join("")}
          </select>
        </td>
        <td>${u.is_active ? "✅" : "🚫"}</td>
        <td class="text-right"><button data-toggle="${u.id}" data-active="${u.is_active}" class="text-veil-600 hover:underline">${u.is_active ? "Deactivate" : "Activate"}</button></td>
      </tr>`).join("");

    body.querySelectorAll("[data-role]").forEach((sel) =>
      sel.addEventListener("change", async () => {
        try { await CV.patch(`/api/admin/users/${sel.dataset.role}`, { role: sel.value }); CV.toast("Role updated.", "ok"); }
        catch (e) { CV.toast(e.message, "error"); }
      }));
    body.querySelectorAll("[data-toggle]").forEach((b) =>
      b.addEventListener("click", async () => {
        try { await CV.patch(`/api/admin/users/${b.dataset.toggle}`, { is_active: b.dataset.active !== "true" }); loadUsers(); }
        catch (e) { CV.toast(e.message, "error"); }
      }));
  }

  let auditPage = 1;
  function initAuditFilter() {
    const sel = document.getElementById("audit-action");
    if (sel.options.length) return;
    const actions = ["", "LOGIN", "LOGIN_FAILED", "LOGOUT", "UPLOAD", "DOWNLOAD", "DOWNLOAD_DENIED",
      "SHARE", "REVOKE", "DELETE", "INTEGRITY_FAIL", "KEY_UNWRAP_FAIL", "ADMIN_ACTION"];
    sel.innerHTML = actions.map((a) => `<option value="${a}">${a || "All actions"}</option>`).join("");
    sel.addEventListener("change", () => { auditPage = 1; loadAudit(); });
    document.getElementById("audit-prev").addEventListener("click", () => { if (auditPage > 1) { auditPage--; loadAudit(); } });
    document.getElementById("audit-next").addEventListener("click", () => { auditPage++; loadAudit(); });
  }

  async function loadAudit() {
    initAuditFilter();
    const action = document.getElementById("audit-action").value;
    const data = await CV.get(`/api/admin/audit?page=${auditPage}${action ? "&action=" + action : ""}`);
    auditPage = data.page;
    document.getElementById("audit-page").textContent = `${data.page} / ${Math.max(1, data.pages)}`;
    const body = document.getElementById("admin-audit-body");
    body.innerHTML = data.items.map((r) => `
      <tr class="border-b last:border-0">
        <td class="py-2 text-xs text-slate-500">${CV.fmtDate(r.created_at)}</td>
        <td>${r.user_id ?? "—"}</td>
        <td><span class="font-mono text-xs">${CV.esc(r.action)}</span></td>
        <td>${statusBadge(r.status)}</td>
        <td class="text-xs text-slate-400">${CV.esc(r.ip || "")}</td>
        <td class="font-mono text-xs text-slate-400">${r.file_id ? CV.esc(r.file_id.slice(0, 8)) : ""}</td>
      </tr>`).join("") || `<tr><td colspan="6" class="py-4 text-slate-400">No entries.</td></tr>`;
  }

  function statusBadge(s) {
    const c = s === "success" ? "bg-emerald-100 text-emerald-700" : s === "denied" ? "bg-amber-100 text-amber-700" : "bg-rose-100 text-rose-700";
    return `<span class="rounded px-1.5 py-0.5 text-xs ${c}">${CV.esc(s)}</span>`;
  }

  const charts = {};
  async function loadStats() {
    const s = await CV.get("/api/admin/stats");
    makeChart("chart-uploads", "bar",
      s.uploads_by_day.map((d) => d.day), [{ label: "Uploads", data: s.uploads_by_day.map((d) => d.count) }]);
    makeChart("chart-downloads", "doughnut", ["Downloads", "Denials"],
      [{ data: [s.downloads_vs_denials.downloads, s.downloads_vs_denials.denials] }]);
    makeChart("chart-actions", "bar", Object.keys(s.actions_by_type), [{ label: "Count", data: Object.values(s.actions_by_type) }]);
    makeChart("chart-storage", "bar", Object.keys(s.storage_by_category), [{ label: "Bytes", data: Object.values(s.storage_by_category) }]);
  }

  function makeChart(id, type, labels, datasets) {
    const palette = ["#4f6ef7", "#3b55e0", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6"];
    datasets.forEach((d, i) => {
      d.backgroundColor = type === "bar" ? palette[i % palette.length] : palette;
      d.borderWidth = 0;
    });
    if (charts[id]) charts[id].destroy();
    charts[id] = new Chart(document.getElementById(id), {
      type,
      data: { labels, datasets },
      options: { responsive: true, plugins: { legend: { display: type !== "bar" } }, scales: type === "bar" ? { y: { beginAtZero: true } } : {} },
    });
  }
})();
