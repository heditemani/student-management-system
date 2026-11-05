// Sign-in page. No inline code (the CSP forbids it).
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };

  function themeLabel() {
    var dark = document.documentElement.getAttribute("data-theme") === "dark";
    $("theme-toggle").setAttribute("aria-label", dark ? "Switch to light theme" : "Switch to dark theme");
  }

  $("theme-toggle").addEventListener("click", function () {
    var next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try { localStorage.setItem("sms-theme", next); } catch (e) { /* storage may be blocked */ }
    themeLabel();
  });
  themeLabel();

  $("show-password").addEventListener("change", function () {
    $("password").type = this.checked ? "text" : "password";
  });

  function showError(message) {
    var box = $("login-alert");
    box.textContent = message;
    box.hidden = false;
  }

  $("login-form").addEventListener("submit", function (event) {
    event.preventDefault();
    $("login-alert").hidden = true;
    var username = $("username").value.trim();
    var password = $("password").value;
    if (!username || !password) {
      showError("Enter your username and password.");
      (username ? $("password") : $("username")).focus();
      return;
    }

    var button = $("login-submit");
    button.disabled = true;
    button.textContent = "Signing in…";

    fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ username: username, password: password })
    }).then(function (response) {
      return response.json().catch(function () { return null; }).then(function (data) {
        if (response.ok) {
          window.location.replace("/");
          return;
        }
        showError((data && data.detail) || "Sign in failed. Please try again.");
        $("password").value = "";
        $("password").focus();
        button.disabled = false;
        button.textContent = "Sign in";
      });
    }, function () {
      showError("Cannot reach the server. Check your connection and try again.");
      button.disabled = false;
      button.textContent = "Sign in";
    });
  });
})();
