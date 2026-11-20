// Login / register page logic.
"use strict";

(function () {
  const tabLogin = document.getElementById("tab-login");
  const tabRegister = document.getElementById("tab-register");
  const formLogin = document.getElementById("form-login");
  const formRegister = document.getElementById("form-register");

  const activeCls = ["text-white", "bg-veil-600"];
  const idleCls = ["text-slate-600"];

  function show(which) {
    const loginActive = which === "login";
    formLogin.classList.toggle("hidden", !loginActive);
    formRegister.classList.toggle("hidden", loginActive);
    tabLogin.classList.toggle("bg-veil-600", loginActive);
    tabLogin.classList.toggle("text-white", loginActive);
    tabLogin.classList.toggle("text-slate-600", !loginActive);
    tabRegister.classList.toggle("bg-veil-600", !loginActive);
    tabRegister.classList.toggle("text-white", !loginActive);
    tabRegister.classList.toggle("text-slate-600", loginActive);
  }

  tabLogin.addEventListener("click", () => show("login"));
  tabRegister.addEventListener("click", () => show("register"));

  formLogin.addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = e.target;
    try {
      await CV.post("/api/auth/login", {
        email: f.email.value.trim(),
        password: f.password.value,
      });
      window.location.href = "/app";
    } catch (err) {
      CV.toast(err.status === 423 ? "Account locked, try later." : "Invalid email or password.", "error");
    }
  });

  formRegister.addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = e.target;
    try {
      await CV.post("/api/auth/register", {
        full_name: f.full_name.value.trim(),
        email: f.email.value.trim(),
        password: f.password.value,
      });
      CV.toast("Account created — signing you in…", "ok");
      await CV.post("/api/auth/login", {
        email: f.email.value.trim(),
        password: f.password.value,
      });
      window.location.href = "/app";
    } catch (err) {
      CV.toast(err.message || "Registration failed.", "error");
    }
  });

  // If already signed in, skip to the app.
  CV.get("/api/auth/me").then(() => (window.location.href = "/app")).catch(() => {});
})();
