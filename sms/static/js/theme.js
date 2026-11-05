// Runs in <head> before the page paints, so the saved theme shows without a flash.
(function () {
  var theme = null;
  try {
    theme = localStorage.getItem("sms-theme");
  } catch (e) {}
  if (theme !== "light" && theme !== "dark") {
    theme = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  document.documentElement.setAttribute("data-theme", theme);
})();
