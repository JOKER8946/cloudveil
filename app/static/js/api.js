// Minimal API client: cookie-based auth (JWT in HttpOnly cookie) + CSRF header.
"use strict";

const CV = {
  csrf() {
    const m = document.cookie.match(/(?:^|;\s*)cv_csrf=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : "";
  },

  async request(method, url, { json, form } = {}) {
    const opts = { method, headers: {}, credentials: "same-origin" };
    if (["POST", "PUT", "PATCH", "DELETE"].includes(method)) {
      opts.headers["X-CSRF-Token"] = CV.csrf();
    }
    if (json !== undefined) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(json);
    } else if (form !== undefined) {
      opts.body = form; // FormData; browser sets multipart boundary
    }
    const res = await fetch(url, opts);
    const ct = res.headers.get("Content-Type") || "";
    let body = null;
    if (ct.includes("application/json")) body = await res.json();
    if (!res.ok) {
      const msg = body && body.error ? body.error.message : `Request failed (${res.status})`;
      const err = new Error(msg);
      err.status = res.status;
      err.code = body && body.error ? body.error.code : null;
      throw err;
    }
    return body;
  },

  get(u) { return CV.request("GET", u); },
  post(u, json) { return CV.request("POST", u, { json }); },
  patch(u, json) { return CV.request("PATCH", u, { json }); },
  del(u) { return CV.request("DELETE", u); },
  upload(u, form) { return CV.request("POST", u, { form }); },

  toast(msg, kind = "info") {
    const el = document.getElementById("toast");
    if (!el) return;
    const colors = {
      info: "bg-slate-800 text-white",
      ok: "bg-emerald-600 text-white",
      error: "bg-rose-600 text-white",
    };
    el.className = "fixed right-4 top-4 z-50 rounded-lg px-4 py-3 text-sm shadow-lg " + (colors[kind] || colors.info);
    el.textContent = msg;
    el.classList.remove("hidden");
    clearTimeout(CV._t);
    CV._t = setTimeout(() => el.classList.add("hidden"), 3500);
  },

  fmtSize(n) {
    if (n < 1024) return n + " B";
    if (n < 1024 * 1024) return (n / 1024).toFixed(1) + " KB";
    return (n / 1024 / 1024).toFixed(1) + " MB";
  },

  fmtDate(iso) {
    if (!iso) return "";
    return new Date(iso + (iso.endsWith("Z") ? "" : "Z")).toLocaleString();
  },

  esc(s) {
    const d = document.createElement("div");
    d.textContent = s == null ? "" : String(s);
    return d.innerHTML;
  },
};

window.CV = CV;
