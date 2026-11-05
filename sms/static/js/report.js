(function () {
  "use strict";
  var button = document.getElementById("print-report");
  if (button) button.addEventListener("click", function () { window.print(); });
})();
