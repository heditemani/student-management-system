// Student Management System front end. No framework, no inline code (the CSP forbids it).
// All student data is written with textContent / DOM nodes, never innerHTML.
(function () {
  "use strict";

  var SVG_NS = "http://www.w3.org/2000/svg";
  var ICONS = {
    eye: ['M2.25 12s3.25-6.75 9.75-6.75 9.75 6.75 9.75 6.75-3.25 6.75-9.75 6.75S2.25 12 2.25 12Z', 'M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6Z'],
    edit: ['M12 20h9', 'M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5Z', 'm15 5 4 4'],
    trash: ['M4 7h16', 'm5 7 1 13h12l1-13', 'M10 11v5M14 11v5', 'M9 7V4h6v3', 'M3 7h18']
  };
  var STATUS_LABELS = { active: "Active", graduated: "Graduated", suspended: "Suspended" };
  var GENDER_LABELS = { female: "Female", male: "Male", other: "Other", "": "Not specified" };
  var FIELDS = ["first_name", "last_name", "email", "phone", "student_id", "date_of_birth",
    "gender", "course", "year", "academic_year", "semester", "average", "status", "address"];

  var $ = function (id) { return document.getElementById(id); };

  var state = {
    page: 1, pageSize: 10, search: "", course: "", status: "", ordering: "-created", total: 0, pages: 1,
    average_min: "", average_max: "", year_min: "", year_max: "", academic_year: "", semester: "",
    missing_average: false, created_from: "", created_to: ""
  };
  var ROLE = document.body.getAttribute("data-role");
  var ME = (document.body.getAttribute("data-user") || "").toLowerCase();
  var CSRF = document.body.getAttribute("data-csrf") || "";
  var IS_ADMIN = ROLE === "admin";
  var editingId = null;     // null while adding
  var confirmAction = null; // runs when the confirm button is pressed
  var resetTarget = null;   // user whose password an admin is resetting
  var auditPage = 1;
  var lastFocus = null;     // element to refocus after a dialog closes
  var listRequest = 0;      // guards against out-of-order responses

  // ---------- helpers ----------
  function el(tag, props, children) {
    var node = document.createElement(tag);
    if (props) {
      Object.keys(props).forEach(function (key) {
        if (key === "text") node.textContent = props[key];
        else if (key === "class") node.className = props[key];
        else node.setAttribute(key, props[key]);
      });
    }
    (children || []).forEach(function (child) { if (child) node.appendChild(child); });
    return node;
  }

  function icon(name) {
    var svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("fill", "none");
    svg.setAttribute("stroke", "currentColor");
    svg.setAttribute("stroke-width", "1.8");
    svg.setAttribute("stroke-linecap", "round");
    svg.setAttribute("stroke-linejoin", "round");
    svg.setAttribute("aria-hidden", "true");
    ICONS[name].forEach(function (d) {
      var path = document.createElementNS(SVG_NS, "path");
      path.setAttribute("d", d);
      svg.appendChild(path);
    });
    return svg;
  }

  function initials(s) {
    return ((s.first_name || "").charAt(0) + (s.last_name || "").charAt(0)).toUpperCase() || "?";
  }

  function formatDate(value) {
    if (!value) return "";
    var d = new Date(/^\d{4}-\d{2}-\d{2}$/.test(value) ? value + "T00:00:00" : value);
    if (isNaN(d.getTime())) return "";
    return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
  }

  function formatAverage(value) {
    return value === null || value === undefined ? "–" : Number(value).toFixed(2);
  }

  function chip(status) {
    return el("span", { "class": "chip chip-" + status, text: STATUS_LABELS[status] || status });
  }

  function debounce(fn, ms) {
    var timer;
    return function () {
      var args = arguments;
      clearTimeout(timer);
      timer = setTimeout(function () { fn.apply(null, args); }, ms);
    };
  }

  // ---------- API ----------
  function ApiError(status, body) {
    this.status = status;
    this.errors = (body && body.errors) || null;
    this.detail = (body && body.detail) || null;
  }

  function api(method, path, body) {
    var options = { method: method, headers: { Accept: "application/json" } };
    if (method !== "GET") options.headers["X-CSRF-Token"] = CSRF;
    if (body !== undefined) {
      options.headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(body);
    }
    return fetch(path, options).then(function (response) {
      if (response.status === 204) return null;
      return response.json().catch(function () { return null; }).then(function (data) {
        if (response.status === 401 && path.indexOf("/api/auth/") !== 0) {
          window.location.reload(); // session expired: the server will show the sign-in page
        }
        if (!response.ok) throw new ApiError(response.status, data);
        return data;
      });
    }, function () {
      throw new ApiError(0, { detail: "Cannot reach the server. Check your connection and try again." });
    });
  }

  function messageFor(err) {
    if (err instanceof ApiError) {
      if (err.detail) return err.detail;
      if (err.errors) return Object.keys(err.errors).map(function (k) { return err.errors[k]; }).join(" ");
    }
    return "Something went wrong. Please try again.";
  }

  // ---------- toasts ----------
  function toast(message, isError) {
    var node = el("div", { "class": "toast" + (isError ? " error" : ""), text: message });
    $("toasts").appendChild(node);
    setTimeout(function () { node.remove(); }, isError ? 6000 : 3500);
  }

  // ---------- theme ----------
  function applyThemeLabel() {
    var dark = document.documentElement.getAttribute("data-theme") === "dark";
    $("theme-toggle").setAttribute("aria-label", dark ? "Switch to light theme" : "Switch to dark theme");
  }

  function toggleTheme() {
    var next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try { localStorage.setItem("sms-theme", next); } catch (e) { /* storage may be blocked */ }
    applyThemeLabel();
  }

  // ---------- dialogs ----------
  function openDialog(dialog) {
    lastFocus = document.activeElement;
    dialog.showModal();
  }

  function closeDialog(dialog) {
    if (dialog.open) dialog.close();
  }

  function openHistory(student) {
    $("history-student").textContent = student.full_name + " · " + student.student_id;
    $("history-list").textContent = "";
    $("history-empty").hidden = true;
    $("history-alert").hidden = true;
    openDialog($("history-dialog"));
    api("GET", "/api/students/" + student.id + "/history").then(function (entries) {
      var list = $("history-list");
      var previous = null;
      entries.slice().reverse().forEach(function (entry) {
        var title = entry.action.charAt(0).toUpperCase() + entry.action.slice(1);
        var details = [];
        if (entry.action === "updated" && previous) {
          FIELDS.forEach(function (field) {
            if (previous[field] !== entry.snapshot[field]) {
              var before = previous[field] === null || previous[field] === "" ? "—" : String(previous[field]);
              var after = entry.snapshot[field] === null || entry.snapshot[field] === "" ? "—" : String(entry.snapshot[field]);
              details.push(field.replace(/_/g, " ") + ": " + before + " → " + after);
            }
          });
        }
        list.appendChild(el("li", null, [
          el("div", { "class": "history-heading" }, [
            el("strong", { text: title }),
            el("span", { "class": "muted small", text: formatDateTime(entry.at) })
          ]),
          el("p", { "class": "muted small", text: entry.username ? "By " + entry.username : "System action" }),
          details.length ? el("p", { "class": "history-changes", text: details.join(" · ") }) : null
        ]));
        previous = entry.snapshot;
      });
      $("history-empty").hidden = entries.length > 0;
    }).catch(function (err) {
      $("history-alert").textContent = messageFor(err);
      $("history-alert").hidden = false;
    });
  }

  function restoreFocus() {
    if (lastFocus && document.contains(lastFocus) && lastFocus.offsetParent !== null) lastFocus.focus();
    else {
      var open = document.querySelector("dialog[open]");
      if (open) open.querySelector("[data-close]").focus();
      else $("list-title").focus();
    }
  }

  // ---------- stats + courses ----------
  function loadStats() {
    return api("GET", "/api/stats").then(function (s) {
      $("stat-total").textContent = s.total;
      $("stat-active").textContent = s.active;
      $("stat-graduated").textContent = s.graduated;
      $("stat-average").textContent = s.average === null ? "–" : Number(s.average).toFixed(1);
      $("stat-courses").textContent = "across " + s.courses + (s.courses === 1 ? " course" : " courses");
      $("stat-suspended").textContent = s.suspended + " suspended";
      var share = s.total ? Math.round((s.graduated / s.total) * 100) : 0;
      $("stat-grad-share").textContent = share + "% of all students";
      renderBars(s.by_course || []);
    }).catch(function () { /* the list shows its own error */ });
    loadAlerts();
  }

  function loadAlerts() {
    api("GET", "/api/alerts").then(function (data) {
      var panel = $("alerts-panel"), list = $("alert-items");
      list.textContent = "";
      [
        { key: "low_average", label: "Below 10/20", max: "9.99" },
        { key: "missing_average", label: "Missing average", missing: true }
      ].forEach(function (item) {
        var count = Number(data[item.key] || 0);
        if (!count) return;
        var button = el("button", {
          type: "button", "class": "alert-card",
          "aria-label": "Show " + count + " students: " + item.label
        }, [
          el("span", { "class": "alert-count", text: String(count) }),
          el("span", { "class": "alert-copy" }, [
            el("strong", { text: item.label }),
            el("span", { "class": "muted small", text: "View matching students" })
          ]),
          el("span", { "class": "alert-arrow", text: "→", "aria-hidden": "true" })
        ]);
        button.addEventListener("click", function () {
          clearFilterState();
          if (item.missing) state.missing_average = true;
          else state.average_max = item.max;
          markFiltersChanged();
          syncFilterControls();
          loadList(true);
        });
        list.appendChild(button);
      });
      panel.hidden = !list.children.length;
    }).catch(function () { /* the student list shows its own error */ });
  }

  function renderBars(byCourse) {
    var list = $("by-course");
    list.textContent = "";
    var top = byCourse.slice(0, 8);
    $("by-course-note").textContent = byCourse.length > 8
      ? "Top 8 of " + byCourse.length + " courses · Select a bar to filter."
      : "Select a bar to filter students.";
    if (!top.length) {
      list.appendChild(el("li", { "class": "muted", text: "No data yet." }));
      return;
    }
    var max = top[0].count || 1;
    top.forEach(function (item) {
      var fill = el("span", { "class": "bar-fill" });
      fill.style.width = Math.max(3, Math.round((item.count / max) * 100)) + "%"; // CSSOM: allowed by the CSP
      var button = el("button", {
        type: "button",
        "class": "course-filter",
        "data-course": item.course,
        "aria-pressed": String(item.course === state.course),
        "aria-label": "Filter by " + item.course + " (" + item.count + (item.count === 1 ? " student)" : " students)")
      }, [
        el("span", { "class": "bar-label", text: item.course }),
        el("span", { "class": "bar-track", "aria-hidden": "true" }, [fill]),
        el("span", { "class": "bar-count", text: String(item.count) })
      ]);
      button.addEventListener("click", function () {
        state.course = state.course === item.course ? "" : item.course;
        $("filter-course").value = state.course;
        state.page = 1;
        markFiltersChanged();
        syncCourseButtons();
        loadList(true);
      });
      list.appendChild(el("li", null, [button]));
    });
  }

  function syncCourseButtons() {
    Array.prototype.forEach.call(document.querySelectorAll(".course-filter"), function (button) {
      button.setAttribute("aria-pressed", String(button.getAttribute("data-course") === state.course));
    });
  }

  function loadCourses() {
    return api("GET", "/api/courses").then(function (courses) {
      var select = $("filter-course");
      var keep = state.course;
      while (select.options.length > 1) select.remove(1);
      var list = $("course-list");
      list.textContent = "";
      courses.forEach(function (name) {
        select.appendChild(el("option", { value: name, text: name }));
        list.appendChild(el("option", { value: name }));
      });
      // keep the current filter even if its course vanished, so the UI does not lie
      if (keep && courses.indexOf(keep) === -1) {
        state.course = "";
        select.value = "";
      } else {
        select.value = keep;
      }
    }).catch(function () { /* non-critical */ });
  }

  // ---------- list ----------
  function hasFilters() {
    return !!(state.search || state.course || state.status || state.average_min || state.average_max
      || state.year_min || state.year_max || state.academic_year || state.semester
      || state.missing_average || state.created_from || state.created_to);
  }

  function clearFilterState() {
    state.search = "";
    state.course = "";
    state.status = "";
    state.average_min = "";
    state.average_max = "";
    state.year_min = "";
    state.year_max = "";
    state.academic_year = "";
    state.semester = "";
    state.missing_average = false;
    state.created_from = "";
    state.created_to = "";
    state.page = 1;
  }

  function syncFilterControls() {
    $("search").value = state.search;
    $("filter-course").value = state.course;
    $("filter-status").value = state.status;
    $("filter-average-min").value = state.average_min;
    $("filter-average-max").value = state.average_max;
    $("filter-year-min").value = state.year_min;
    $("filter-year-max").value = state.year_max;
    $("filter-academic-year").value = state.academic_year;
    $("filter-semester").value = state.semester;
    $("filter-missing-average").checked = state.missing_average;
    $("filter-created-from").value = state.created_from;
    $("filter-created-to").value = state.created_to;
    $("filter-sort").value = state.ordering;
    syncCourseButtons();
  }

  function markFiltersChanged() {
    $("saved-filters").value = "";
    $("delete-filter-btn").disabled = true;
  }

  function currentFilters() {
    return {
      search: state.search, course: state.course, status: state.status, ordering: state.ordering,
      average_min: state.average_min, average_max: state.average_max,
      year_min: state.year_min, year_max: state.year_max, academic_year: state.academic_year,
      semester: state.semester, missing_average: state.missing_average,
      created_from: state.created_from, created_to: state.created_to
    };
  }

  function queryForFilters(filters) {
    var params = new URLSearchParams();
    Object.keys(filters).forEach(function (key) {
      if (filters[key] !== "" && filters[key] !== false && filters[key] !== null && filters[key] !== undefined) {
        params.set(key, String(filters[key]));
      }
    });
    return params;
  }

  function renderSkeleton() {
    var body = $("rows");
    body.textContent = "";
    for (var i = 0; i < 5; i++) {
      var tr = el("tr", { role: "row" });
      for (var c = 0; c < 6; c++) {
        tr.appendChild(el("td", { role: "cell" }, [el("span", { "class": "skeleton" + (c > 2 ? " short" : "") })]));
      }
      body.appendChild(tr);
    }
  }

  function renderRow(s) {
    var person = el("div", { "class": "person" }, [
      el("span", { "class": "avatar", "aria-hidden": "true", text: initials(s) }),
      el("div", null, [
        el("div", { "class": "person-name", text: s.full_name }),
        el("div", { "class": "person-mail", text: s.email })
      ])
    ]);

    function action(label, name, extra, handler) {
      var btn = el("button", { type: "button", "class": "icon-btn" + (extra ? " " + extra : ""), "aria-label": label + " " + s.full_name, title: label }, [icon(name)]);
      btn.addEventListener("click", handler);
      return btn;
    }

    var actions = el("div", { "class": "row-actions" }, [
      action("View", "eye", "", function () { showDetails(s); }),
      action("Edit", "edit", "", function () { openForm(s); }),
      IS_ADMIN ? action("Delete", "trash", "danger", function () { askDelete(s); }) : null
    ]);

    return el("tr", { role: "row" }, [
      el("td", { role: "cell", "class": "cell-person" }, [person]),
      el("td", { role: "cell", "data-label": "ID", "class": "mono", text: s.student_id }),
      el("td", { role: "cell", "data-label": "Course" }, [
        document.createTextNode(s.course + " · Y" + s.year
          + (s.academic_year ? " · " + s.academic_year : "")
          + (s.semester ? " · S" + s.semester : ""))
      ]),
      el("td", { role: "cell", "data-label": "Average", "class": "mono", text: formatAverage(s.average) }),
      el("td", { role: "cell", "data-label": "Status" }, [chip(s.status)]),
      el("td", { role: "cell", "class": "cell-actions" }, [actions])
    ]);
  }

  function renderPagination() {
    var nav = $("pagination");
    if (state.total === 0) { nav.hidden = true; return; }
    nav.hidden = false;
    nav.textContent = "";

    var from = (state.page - 1) * state.pageSize + 1;
    var to = Math.min(state.page * state.pageSize, state.total);
    nav.appendChild(el("p", { "class": "muted small", text: "Showing " + from + "–" + to + " of " + state.total }));
    if (state.pages <= 1) return;

    var wrap = el("div", { "class": "pages" });
    function pageButton(label, page, opts) {
      opts = opts || {};
      var attrs = { type: "button", "class": "page-btn" };
      if (opts.aria) attrs["aria-label"] = opts.aria;
      if (opts.disabled) attrs.disabled = "";
      if (opts.current) attrs["aria-current"] = "page";
      var btn = el("button", attrs, [document.createTextNode(label)]);
      btn.addEventListener("click", function () { state.page = page; loadList(true); });
      return btn;
    }

    wrap.appendChild(pageButton("‹", state.page - 1, { aria: "Previous page", disabled: state.page === 1 }));
    var start = Math.max(1, Math.min(state.page - 2, state.pages - 4));
    var end = Math.min(state.pages, start + 4);
    for (var p = start; p <= end; p++) {
      wrap.appendChild(pageButton(String(p), p, { aria: "Page " + p, current: p === state.page }));
    }
    wrap.appendChild(pageButton("›", state.page + 1, { aria: "Next page", disabled: state.page === state.pages }));
    nav.appendChild(wrap);
  }

  function renderList(data) {
    state.total = data.count;
    state.pages = Math.max(1, data.pages);
    var body = $("rows");
    body.textContent = "";
    data.results.forEach(function (s) { body.appendChild(renderRow(s)); });

    var empty = data.count === 0;
    $("table-wrap").hidden = empty;
    $("empty").hidden = !empty;
    $("list-error").hidden = true;
    if (empty) {
      var filtered = hasFilters();
      $("empty-title").textContent = filtered ? "No matching students" : "No students yet";
      $("empty-text").textContent = filtered
        ? "Try a different search or clear the filters."
        : "Add your first student to get started.";
      $("empty-action").textContent = filtered ? "Clear filters" : "Add student";
    }
    $("result-summary").textContent = data.count + (data.count === 1 ? " student" : " students") + (hasFilters() ? " found" : "");
    $("clear-filters").hidden = !hasFilters();
    renderPagination();
  }

  function loadList(scrollUp) {
    var request = ++listRequest;
    var params = new URLSearchParams({ page: state.page, page_size: state.pageSize, ordering: state.ordering });
    queryForFilters(currentFilters()).forEach(function (value, key) { params.set(key, value); });

    var region = $("list-region");
    region.setAttribute("aria-busy", "true");
    if (!$("rows").children.length) {
      $("table-wrap").hidden = false;
      renderSkeleton();
    }

    return api("GET", "/api/students?" + params.toString()).then(function (data) {
      if (request !== listRequest) return;
      // the last row of the last page was removed: step back
      if (data.results.length === 0 && data.count > 0 && state.page > 1) {
        state.page = Math.max(1, data.pages);
        return loadList();
      }
      renderList(data);
      if (scrollUp) $("list-title").scrollIntoView({ block: "start" });
    }).catch(function (err) {
      if (request !== listRequest) return;
      $("rows").textContent = "";
      $("table-wrap").hidden = true;
      $("empty").hidden = true;
      $("pagination").hidden = true;
      $("list-error").textContent = messageFor(err);
      $("list-error").hidden = false;
    }).then(function () {
      if (request === listRequest) region.setAttribute("aria-busy", "false");
    });
  }

  function refreshAll() {
    return Promise.all([loadList(), loadStats(), loadCourses()]);
  }

  function clearFilters() {
    clearFilterState();
    syncFilterControls();
    markFiltersChanged();
    loadList();
  }

  // ---------- details ----------
  function showDetails(s) {
    $("details-avatar").textContent = initials(s);
    $("details-name").textContent = s.full_name;
    $("details-id").textContent = s.student_id;

    var rows = [
      ["Email", s.email],
      ["Phone", s.phone || "–"],
      ["Date of birth", formatDate(s.date_of_birth) || "–"],
      ["Gender", GENDER_LABELS[s.gender] || "–"],
      ["Course", s.course],
      ["Year", "Year " + s.year],
      ["Academic year", s.academic_year || "–"],
      ["Semester", s.semester ? "Semester " + s.semester : "–"],
      ["Average", s.average === null ? "–" : formatAverage(s.average) + " / 20"],
      ["Status", null, chip(s.status)],
      ["Address", s.address || "–", null, true],
      ["Added", formatDate(s.created_at) || "–"]
    ];
    var list = $("details-list");
    list.textContent = "";
    rows.forEach(function (r) {
      var dd = el("dd");
      if (r[2]) dd.appendChild(r[2]); else dd.textContent = r[1];
      list.appendChild(el("div", { "class": r[3] ? "wide" : "" }, [el("dt", { text: r[0] }), dd]));
    });

    $("details-edit").onclick = function () { closeDialog($("details-dialog")); openForm(s); };
    $("details-delete").hidden = !IS_ADMIN;
    $("details-delete").onclick = function () { closeDialog($("details-dialog")); askDelete(s); };
    $("details-history").onclick = function () { openHistory(s); };
    openDialog($("details-dialog"));
  }

  // ---------- form ----------
  function fieldInput(name) { return $("f-" + name); }

  function clearErrors() {
    $("form-alert").hidden = true;
    FIELDS.forEach(function (name) {
      $("e-" + name).textContent = "";
      fieldInput(name).removeAttribute("aria-invalid");
    });
  }

  function showErrors(errors) {
    var first = null;
    Object.keys(errors).forEach(function (name) {
      var input = fieldInput(name);
      if (!input) {
        $("form-alert").textContent = errors[name];
        $("form-alert").hidden = false;
        return;
      }
      $("e-" + name).textContent = errors[name];
      input.setAttribute("aria-invalid", "true");
      if (!first) first = input;
    });
    if (first) first.focus();
  }

  function openForm(student) {
    editingId = student ? student.id : null;
    clearErrors();
    $("student-form").reset();
    $("form-title").textContent = student ? "Edit student" : "Add student";
    $("form-submit").textContent = student ? "Save changes" : "Save student";
    $("form-submit").disabled = false;
    FIELDS.forEach(function (name) {
      var value = student ? student[name] : null;
      fieldInput(name).value = value === null || value === undefined ? "" : value;
    });
    if (!student) {
      $("f-year").value = "1";
      $("f-status").value = "active";
    }
    openDialog($("form-dialog"));
    $("f-first_name").focus();
  }

  function readForm() {
    var data = {};
    FIELDS.forEach(function (name) {
      var raw = fieldInput(name).value.trim();
      if (name === "year") data[name] = raw ? parseInt(raw, 10) : null;
      else if (name === "semester") data[name] = raw ? parseInt(raw, 10) : null;
      else if (name === "average") data[name] = raw === "" ? null : raw;
      else if (name === "date_of_birth") data[name] = raw || null;
      else data[name] = raw;
    });
    return data;
  }

  function submitForm(event) {
    event.preventDefault();
    clearErrors();
    var data = readForm();

    // quick client-side check; the server validates everything again
    var missing = {};
    ["first_name", "last_name", "email", "course"].forEach(function (name) {
      if (!data[name]) missing[name] = "This field is required.";
    });
    if (Object.keys(missing).length) { showErrors(missing); return; }

    var button = $("form-submit");
    var wasEditing = editingId !== null;
    button.disabled = true;
    button.textContent = "Saving…";

    var request = wasEditing
      ? api("PUT", "/api/students/" + editingId, data)
      : api("POST", "/api/students", data);

    request.then(function (saved) {
      closeDialog($("form-dialog"));
      toast(saved.full_name + (wasEditing ? " updated." : " added."));
      if (!wasEditing) {
        // show the new record: newest first, no filters hiding it
        clearFilterState();
        state.ordering = "-created";
        syncFilterControls();
        markFiltersChanged();
      }
      return refreshAll();
    }).catch(function (err) {
      if (err instanceof ApiError && err.errors) showErrors(err.errors);
      else {
        $("form-alert").textContent = messageFor(err);
        $("form-alert").hidden = false;
      }
    }).then(function () {
      button.disabled = false;
      button.textContent = wasEditing ? "Save changes" : "Save student";
    });
  }

  // ---------- confirmation dialog (delete / disable) ----------
  function askConfirm(opts) {
    confirmAction = opts.onConfirm;
    $("confirm-title").textContent = opts.title;
    $("confirm-text").textContent = opts.text;
    $("confirm-ok").textContent = opts.button;
    $("confirm-ok").disabled = false;
    openDialog($("confirm-dialog"));
    $("confirm-dialog").querySelector("[data-close]").focus();
  }

  function runConfirm() {
    if (!confirmAction) return;
    var action = confirmAction;
    $("confirm-ok").disabled = true;
    Promise.resolve().then(action).catch(function (err) {
      toast(messageFor(err), true);
    }).then(function () {
      closeDialog($("confirm-dialog"));
    });
  }

  function askDelete(s) {
    askConfirm({
      title: "Delete student?",
      text: "This permanently removes " + s.full_name + " (" + s.student_id + "). This cannot be undone.",
      button: "Delete student",
      onConfirm: function () {
        lastFocus = $("list-title");
        return api("DELETE", "/api/students/" + s.id).then(function () {
          toast(s.full_name + " deleted.");
        }, function (err) {
          // already gone (404): nothing to undo, just refresh below
          toast(err instanceof ApiError && err.status === 404 ? "That student was already deleted." : messageFor(err), true);
        }).then(refreshAll);
      }
    });
  }

  // ---------- generic field errors ----------
  function resetErrors(fields, alertId) {
    Object.keys(fields).forEach(function (key) {
      $(fields[key][1]).textContent = "";
      $(fields[key][0]).removeAttribute("aria-invalid");
    });
    if (alertId) $(alertId).hidden = true;
  }

  function applyErrors(fields, alertId, errors) {
    var first = null;
    Object.keys(errors).forEach(function (key) {
      var f = fields[key];
      if (!f) { $(alertId).textContent = errors[key]; $(alertId).hidden = false; return; }
      $(f[1]).textContent = errors[key];
      $(f[0]).setAttribute("aria-invalid", "true");
      if (!first) first = $(f[0]);
    });
    if (first) first.focus();
  }

  function showFailure(err, fields, alertId) {
    if (err instanceof ApiError && err.errors) applyErrors(fields, alertId, err.errors);
    else { $(alertId).textContent = messageFor(err); $(alertId).hidden = false; }
  }

  // ---------- user menu, sign out ----------
  function setMenu(open) {
    $("user-pop").hidden = !open;
    $("user-btn").setAttribute("aria-expanded", String(open));
    if (open) $("user-pop").querySelector(".menu-item").focus();
  }

  function fromMenu(fn) {
    return function () {
      setMenu(false);
      $("user-btn").focus(); // so focus comes back to a visible control when the dialog closes
      fn();
    };
  }

  function signOut() {
    api("POST", "/api/auth/logout").catch(function () { /* leave anyway */ }).then(function () {
      window.location.replace("/");
    });
  }

  // ---------- export ----------
  function exportCsv() {
    var params = queryForFilters(currentFilters());
    var button = $("export-btn");
    button.disabled = true;
    fetch("/api/students/export.csv?" + params.toString(), { headers: { Accept: "text/csv" } }).then(function (response) {
      if (response.status === 401) { window.location.reload(); throw new ApiError(401, null); }
      if (!response.ok) throw new ApiError(response.status, { detail: "Export failed." });
      return response.blob();
    }).then(function (blob) {
      var url = URL.createObjectURL(blob);
      var link = el("a", { href: url, download: "students-" + new Date().toISOString().slice(0, 10) + ".csv" });
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(function () { URL.revokeObjectURL(url); }, 2000);
      toast("CSV downloaded" + (hasFilters() ? " (current filters applied)." : "."));
    }).catch(function (err) {
      if (!(err instanceof ApiError && err.status === 401)) toast(messageFor(err), true);
    }).then(function () { button.disabled = false; });
  }

  function uploadFile(path, file) {
    var form = new FormData();
    form.append("file", file);
    return fetch(path, {
      method: "POST",
      headers: { "X-CSRF-Token": CSRF, Accept: "application/json" },
      body: form
    }).then(function (response) {
      return response.json().catch(function () { return null; }).then(function (data) {
        if (response.status === 401) window.location.reload();
        if (!response.ok) throw new ApiError(response.status, data);
        return data;
      });
    }, function () {
      throw new ApiError(0, { detail: "Cannot reach the server. Check your connection and try again." });
    });
  }

  function showImportResult(result) {
    var summary = $("import-summary"), list = $("import-errors"), sample = $("import-sample");
    summary.textContent = result.valid + " valid rows · " + result.duplicates.length
      + " duplicates will be skipped · " + result.errors.length + " invalid rows will be skipped.";
    summary.hidden = false;
    list.textContent = "";
    sample.textContent = "";
    result.sample.forEach(function (item) {
      var period = item.academic_year
        ? item.academic_year + (item.semester ? " · S" + item.semester : "")
        : "No study period";
      sample.appendChild(el("li", null, [
        el("strong", { text: item.name }),
        el("span", { "class": "muted small", text: item.email + " · " + item.course + " · " + period }),
        el("span", { "class": "mono small", text: item.student_id })
      ]));
    });
    if (result.valid > result.sample.length) {
      sample.appendChild(el("li", { "class": "muted small",
        text: "Showing " + result.sample.length + " of " + result.valid + " valid rows." }));
    }
    result.duplicates.concat(result.errors).slice(0, 50).forEach(function (item) {
      var description = item.message || Object.keys(item.errors || {}).map(function (field) {
        return field.replace(/_/g, " ") + ": " + item.errors[field];
      }).join("; ");
      list.appendChild(el("li", { text: "Row " + item.row + ": " + description }));
    });
    if (result.duplicates.length + result.errors.length > 50) {
      list.appendChild(el("li", { text: "Only the first 50 skipped rows are shown." }));
    }
    $("import-submit").disabled = result.valid === 0;
  }

  var previewedImportFile = null;

  function previewImport() {
    var file = $("import-file").files[0];
    previewedImportFile = null;
    $("import-alert").hidden = true;
    $("import-summary").hidden = true;
    $("import-sample").textContent = "";
    $("import-errors").textContent = "";
    $("import-submit").disabled = true;
    if (!file) {
      $("import-alert").textContent = "Choose a CSV file first.";
      $("import-alert").hidden = false;
      return;
    }
    var button = $("import-preview");
    button.disabled = true;
    uploadFile("/api/students/import/preview", file).then(function (result) {
      if ($("import-file").files[0] !== file) return;
      previewedImportFile = file;
      showImportResult(result);
    }).catch(function (err) {
      if ($("import-file").files[0] !== file) return;
      $("import-alert").textContent = messageFor(err);
      $("import-alert").hidden = false;
    }).then(function () { button.disabled = false; });
  }

  function submitImport() {
    var file = $("import-file").files[0];
    if (!file || file !== previewedImportFile) {
      toast("Preview the selected CSV file before importing.", true);
      $("import-submit").disabled = true;
      return;
    }
    var button = $("import-submit");
    button.disabled = true;
    uploadFile("/api/students/import", file).then(function (result) {
      previewedImportFile = null;
      closeDialog($("import-dialog"));
      toast(result.created + " students imported; " + result.duplicates.length
        + " duplicates and " + result.errors.length + " invalid rows skipped.");
      return refreshAll();
    }).catch(function (err) {
      $("import-alert").textContent = messageFor(err);
      $("import-alert").hidden = false;
    }).then(function () { button.disabled = false; });
  }

  function printReport() {
    var query = queryForFilters(currentFilters());
    window.open("/reports/print?" + query.toString(), "_blank", "noopener");
  }

  function downloadBackup() {
    var button = $("backup-download");
    button.disabled = true;
    fetch("/api/backup", { headers: { Accept: "application/json" } }).then(function (response) {
      if (response.status === 401) { window.location.reload(); throw new ApiError(401, null); }
      if (!response.ok) throw new ApiError(response.status, { detail: "Backup download failed." });
      return response.blob();
    }).then(function (blob) {
      var url = URL.createObjectURL(blob);
      var link = el("a", { href: url, download: "student-management-backup-" + new Date().toISOString().slice(0, 10) + ".json" });
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(function () { URL.revokeObjectURL(url); }, 2000);
      toast("Backup downloaded. Store it somewhere safe.");
    }).catch(function (err) {
      if (!(err instanceof ApiError && err.status === 401)) toast(messageFor(err), true);
    }).then(function () { button.disabled = false; });
  }

  function restoreBackup() {
    var file = $("backup-file").files[0];
    if (!file) {
      $("backup-alert").textContent = "Choose a backup JSON file first.";
      $("backup-alert").hidden = false;
      return;
    }
    $("backup-alert").hidden = true;
    askConfirm({
      title: "Replace all student data?",
      text: "This restores " + file.name + " and replaces every current student record and history entry. User accounts will not change.",
      button: "Restore backup",
      onConfirm: function () {
        $("confirm-ok").textContent = "Restoring…";
        return uploadFile("/api/backup/restore", file).then(function (result) {
          closeDialog($("backup-dialog"));
          toast("Restored " + result.restored + " students and " + result.history + " history entries.");
          return refreshAll();
        }).catch(function (err) {
          $("backup-alert").textContent = messageFor(err);
          $("backup-alert").hidden = false;
          throw err;
        });
      }
    });
  }

  // ---------- change own password ----------
  var PW_FIELDS = {
    current_password: ["pw-current", "e-pw-current"],
    new_password: ["pw-new", "e-pw-new"],
    repeat: ["pw-repeat", "e-pw-repeat"]
  };

  function openPassword() {
    $("password-form").reset();
    resetErrors(PW_FIELDS, "password-alert");
    $("password-submit").disabled = false;
    openDialog($("password-dialog"));
    $("pw-current").focus();
  }

  function submitPassword(event) {
    event.preventDefault();
    resetErrors(PW_FIELDS, "password-alert");
    var current = $("pw-current").value, next = $("pw-new").value, repeat = $("pw-repeat").value;
    var missing = {};
    if (!current) missing.current_password = "Enter your current password.";
    if (!next) missing.new_password = "Enter a new password.";
    else if (next !== repeat) missing.repeat = "The two new passwords do not match.";
    if (Object.keys(missing).length) { applyErrors(PW_FIELDS, "password-alert", missing); return; }

    var button = $("password-submit");
    button.disabled = true;
    api("POST", "/api/auth/password", { current_password: current, new_password: next }).then(function () {
      closeDialog($("password-dialog"));
      toast("Password changed. Other devices were signed out.");
    }).catch(function (err) {
      showFailure(err, PW_FIELDS, "password-alert");
    }).then(function () { button.disabled = false; });
  }

  // ---------- manage users (admin) ----------
  var USER_FIELDS = { username: ["u-username", "e-u-username"], password: ["u-password", "e-u-password"] };
  var RESET_FIELDS = { password: ["reset-password", "e-reset-password"] };

  function userAction(label, user, extra, handler) {
    var btn = el("button", { type: "button", "class": "btn btn-ghost btn-sm" + (extra ? " " + extra : ""),
      "aria-label": label + " " + user.username, text: label });
    btn.addEventListener("click", handler);
    return btn;
  }

  function patchUser(user, body, message) {
    return api("PATCH", "/api/users/" + user.id, body).then(function () {
      toast(message);
    }, function (err) {
      toast(messageFor(err), true);
    }).then(loadUsers);
  }

  function renderUser(user) {
    var isMe = user.username.toLowerCase() === ME;
    var identity = el("div", { "class": "user-id" }, [
      el("strong", { text: user.username }),
      el("span", { "class": "role-chip role-" + user.role, text: user.role }),
      user.active ? null : el("span", { "class": "tag", text: "disabled" }),
      isMe ? el("span", { "class": "tag you", text: "you" }) : null,
      el("span", { "class": "user-last", text: user.last_login ? "Last sign-in " + (formatDateTime(user.last_login)) : "Never signed in" })
    ]);

    var role = el("select", { "aria-label": "Role of " + user.username }, [
      el("option", { value: "staff", text: "Staff" }),
      el("option", { value: "admin", text: "Admin" })
    ]);
    role.value = user.role;
    if (isMe) role.disabled = true;
    role.addEventListener("change", function () {
      patchUser(user, { role: role.value }, user.username + " is now " + role.value + ".");
    });

    var tools = el("div", { "class": "user-tools" }, [role,
      userAction("Reset password", user, "", function () { openReset(user); })]);
    if (!isMe) {
      if (user.active) {
        tools.appendChild(userAction("Disable", user, "", function () {
          askConfirm({
            title: "Disable " + user.username + "?",
            text: "They will be signed out everywhere and cannot sign in until you enable the account again.",
            button: "Disable account",
            onConfirm: function () { return patchUser(user, { active: false }, user.username + " disabled."); }
          });
        }));
      } else {
        tools.appendChild(userAction("Enable", user, "", function () {
          patchUser(user, { active: true }, user.username + " enabled.");
        }));
      }
      tools.appendChild(userAction("Delete", user, "btn-danger-outline", function () {
        askConfirm({
          title: "Delete " + user.username + "?",
          text: "The account is removed for good. Their past activity stays in the log.",
          button: "Delete user",
          onConfirm: function () {
            return api("DELETE", "/api/users/" + user.id).then(function () {
              toast(user.username + " deleted.");
            }, function (err) { toast(messageFor(err), true); }).then(loadUsers);
          }
        });
      }));
    }
    return el("li", { "class": "user-row" + (user.active ? "" : " is-disabled") }, [identity, tools]);
  }

  function loadUsers() {
    return api("GET", "/api/users").then(function (users) {
      var list = $("user-list");
      list.textContent = "";
      users.forEach(function (u) { list.appendChild(renderUser(u)); });
    }).catch(function (err) {
      $("user-alert").textContent = messageFor(err);
      $("user-alert").hidden = false;
    });
  }

  function openUsers() {
    $("user-form").reset();
    resetErrors(USER_FIELDS, "user-alert");
    openDialog($("users-dialog"));
    loadUsers();
    $("u-username").focus();
  }

  function submitUser(event) {
    event.preventDefault();
    resetErrors(USER_FIELDS, "user-alert");
    var body = { username: $("u-username").value.trim(), password: $("u-password").value, role: $("u-role").value };
    var button = $("user-submit");
    button.disabled = true;
    api("POST", "/api/users", body).then(function (created) {
      toast("User " + created.username + " created.");
      $("user-form").reset();
      return loadUsers();
    }).catch(function (err) {
      showFailure(err, USER_FIELDS, "user-alert");
    }).then(function () { button.disabled = false; });
  }

  function openReset(user) {
    resetTarget = user;
    $("reset-form").reset();
    resetErrors(RESET_FIELDS);
    $("reset-text").textContent = "Set a new password for " + user.username + ". They will be signed out on every device.";
    openDialog($("reset-dialog"));
    $("reset-password").focus();
  }

  function submitReset(event) {
    event.preventDefault();
    resetErrors(RESET_FIELDS);
    var password = $("reset-password").value;
    if (!password) { applyErrors(RESET_FIELDS, "reset-title", { password: "Enter a new password." }); return; }
    var button = $("reset-submit");
    button.disabled = true;
    api("PATCH", "/api/users/" + resetTarget.id, { password: password }).then(function () {
      closeDialog($("reset-dialog"));
      toast("Password reset for " + resetTarget.username + ".");
      return loadUsers();
    }).catch(function (err) {
      if (err instanceof ApiError && err.errors) applyErrors(RESET_FIELDS, "reset-title", err.errors);
      else toast(messageFor(err), true);
    }).then(function () { button.disabled = false; });
  }

  // ---------- activity log (admin) ----------
  var ACTION_LABELS = {
    "login": "signed in", "login.failed": "failed sign-in for", "logout": "signed out",
    "password.change": "changed their password", "student.create": "added student",
    "student.update": "updated student", "student.delete": "deleted student",
    "students.export": "exported CSV:", "user.create": "created user",
    "user.update": "updated user", "user.delete": "deleted user",
    "students.import": "imported students:", "backup.export": "downloaded backup:",
    "backup.restore": "restored backup:"
  };

  function formatDateTime(value) {
    var d = new Date(value);
    return isNaN(d.getTime()) ? "" : d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
  }

  function loadAudit(page) {
    auditPage = page;
    $("audit-alert").hidden = true;
    return api("GET", "/api/audit?page_size=15&page=" + page).then(function (data) {
      var list = $("audit-list");
      list.textContent = "";
      data.results.forEach(function (row) {
        var what = [el("span", { text: (ACTION_LABELS[row.action] || row.action) + (row.target ? " " + row.target : "") })];
        if (row.detail) what.push(el("div", { "class": "muted", text: row.detail }));
        list.appendChild(el("li", null, [
          el("span", { "class": "audit-time", text: formatDateTime(row.at) }),
          el("span", { "class": "audit-who", text: row.username || "system" }),
          el("div", { "class": "audit-what" }, what)
        ]));
      });
      $("audit-empty").hidden = data.count > 0;
      $("audit-page").textContent = "Page " + data.page + " of " + data.pages + " · " + data.count + " events";
      $("audit-newer").disabled = data.page <= 1;
      $("audit-older").disabled = data.page >= data.pages;
    }).catch(function (err) {
      $("audit-alert").textContent = messageFor(err);
      $("audit-alert").hidden = false;
    });
  }

  function openAudit() {
    openDialog($("audit-dialog"));
    loadAudit(1);
  }

  var PRESET_KEY = "sms-filter-presets";

  function readPresets() {
    try {
      var value = JSON.parse(localStorage.getItem(PRESET_KEY) || "[]");
      return Array.isArray(value) ? value.filter(function (item) {
        return item && typeof item.name === "string" && item.filters && typeof item.filters === "object";
      }).slice(0, 20) : [];
    } catch (error) {
      toast("Saved filters could not be read from this browser.", true);
      return [];
    }
  }

  function renderPresets(selected) {
    var select = $("saved-filters"), presets = readPresets();
    select.textContent = "";
    select.appendChild(el("option", { value: "", text: "Saved filters…" }));
    presets.forEach(function (preset) {
      select.appendChild(el("option", { value: preset.name, text: preset.name }));
    });
    select.value = selected || "";
    $("delete-filter-btn").disabled = !select.value;
  }

  function savePreset(name) {
    var presets = readPresets();
    var existing = presets.findIndex(function (preset) { return preset.name.toLowerCase() === name.toLowerCase(); });
    var saved = { name: name, filters: currentFilters() };
    if (existing >= 0) presets[existing] = saved;
    else if (presets.length < 20) presets.push(saved);
    else {
      toast("You can save up to 20 filters. Delete one before adding another.", true);
      return;
    }
    try {
      localStorage.setItem(PRESET_KEY, JSON.stringify(presets));
      renderPresets(name);
      toast(existing >= 0 ? "Saved filter updated." : "Filter saved in this browser.");
    } catch (error) {
      toast("Could not save this filter in the browser storage.", true);
    }
  }

  function selectPreset() {
    var preset = readPresets().find(function (item) { return item.name === $("saved-filters").value; });
    if (!preset) {
      $("delete-filter-btn").disabled = true;
      return;
    }
    clearFilterState();
    Object.keys(currentFilters()).forEach(function (key) {
      if (Object.prototype.hasOwnProperty.call(preset.filters, key)) state[key] = preset.filters[key];
    });
    state.page = 1;
    syncFilterControls();
    $("delete-filter-btn").disabled = false;
    loadList();
  }

  function deletePreset() {
    var name = $("saved-filters").value;
    if (!name) return;
    askConfirm({
      title: "Delete saved filter?",
      text: "Remove “" + name + "” from this browser?",
      button: "Delete filter",
      onConfirm: function () {
        var presets = readPresets().filter(function (preset) { return preset.name !== name; });
        try {
          localStorage.setItem(PRESET_KEY, JSON.stringify(presets));
          renderPresets();
          toast("Saved filter deleted.");
        } catch (error) {
          toast("Could not update saved filters in browser storage.", true);
        }
      }
    });
  }

  // ---------- wiring ----------
  function init() {
    applyThemeLabel();
    renderPresets();
    $("theme-toggle").addEventListener("click", toggleTheme);
    $("add-btn").addEventListener("click", function () { openForm(null); });
    $("import-btn").addEventListener("click", function () {
      $("import-file").value = "";
      previewedImportFile = null;
      $("import-summary").hidden = true;
      $("import-sample").textContent = "";
      $("import-errors").textContent = "";
      $("import-alert").hidden = true;
      $("import-submit").disabled = true;
      openDialog($("import-dialog"));
    });
    $("import-preview").addEventListener("click", previewImport);
    $("import-submit").addEventListener("click", submitImport);
    $("import-file").addEventListener("change", function () {
      previewedImportFile = null;
      $("import-summary").hidden = true;
      $("import-sample").textContent = "";
      $("import-errors").textContent = "";
      $("import-submit").disabled = true;
      $("import-alert").hidden = true;
    });
    $("report-btn").addEventListener("click", printReport);
    $("save-filter-btn").addEventListener("click", function () {
      $("preset-form").reset();
      openDialog($("preset-dialog"));
      $("preset-name").focus();
    });
    $("preset-form").addEventListener("submit", function (event) {
      event.preventDefault();
      var name = $("preset-name").value.trim();
      if (!name) return;
      savePreset(name);
      closeDialog($("preset-dialog"));
    });
    $("saved-filters").addEventListener("change", selectPreset);
    $("delete-filter-btn").addEventListener("click", deletePreset);
    $("empty-action").addEventListener("click", function () {
      if (hasFilters()) clearFilters(); else openForm(null);
    });
    $("clear-filters").addEventListener("click", clearFilters);
    $("filters").addEventListener("submit", function (e) { e.preventDefault(); });

    var onSearch = debounce(function () {
      var value = $("search").value.trim();
      if (value === state.search) return;
      state.search = value; state.page = 1; markFiltersChanged(); loadList();
    }, 300);
    $("search").addEventListener("input", onSearch);
    $("filter-course").addEventListener("change", function () {
      state.course = this.value;
      state.page = 1;
      markFiltersChanged();
      syncCourseButtons();
      loadList();
    });
    $("filter-status").addEventListener("change", function () { state.status = this.value; state.page = 1; markFiltersChanged(); loadList(); });
    $("filter-sort").addEventListener("change", function () { state.ordering = this.value; state.page = 1; markFiltersChanged(); loadList(); });
    [
      ["filter-average-min", "average_min"], ["filter-average-max", "average_max"],
      ["filter-year-min", "year_min"], ["filter-year-max", "year_max"],
      ["filter-academic-year", "academic_year"], ["filter-semester", "semester"],
      ["filter-created-from", "created_from"], ["filter-created-to", "created_to"]
    ].forEach(function (pair) {
      $(pair[0]).addEventListener("change", function () {
        state[pair[1]] = this.value;
        state.page = 1;
        markFiltersChanged();
        loadList();
      });
    });
    $("filter-missing-average").addEventListener("change", function () {
      state.missing_average = this.checked;
      state.page = 1;
      markFiltersChanged();
      loadList();
    });

    $("student-form").addEventListener("submit", submitForm);
    $("confirm-ok").addEventListener("click", runConfirm);
    $("export-btn").addEventListener("click", exportCsv);

    $("user-btn").addEventListener("click", function (e) { e.stopPropagation(); setMenu($("user-pop").hidden); });
    document.addEventListener("click", function (e) {
      if (!$("user-pop").hidden && !e.target.closest(".user-menu")) setMenu(false);
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && !$("user-pop").hidden) { setMenu(false); $("user-btn").focus(); }
    });
    $("menu-password").addEventListener("click", fromMenu(openPassword));
    $("menu-logout").addEventListener("click", signOut);
    $("password-form").addEventListener("submit", submitPassword);
    if (IS_ADMIN) {
      $("menu-users").addEventListener("click", fromMenu(openUsers));
      $("menu-audit").addEventListener("click", fromMenu(openAudit));
      $("menu-backup").addEventListener("click", fromMenu(function () {
        $("backup-file").value = "";
        $("backup-alert").hidden = true;
        openDialog($("backup-dialog"));
      }));
      $("backup-download").addEventListener("click", downloadBackup);
      $("backup-restore").addEventListener("click", restoreBackup);
      $("user-form").addEventListener("submit", submitUser);
      $("reset-form").addEventListener("submit", submitReset);
      $("audit-newer").addEventListener("click", function () { loadAudit(Math.max(1, auditPage - 1)); });
      $("audit-older").addEventListener("click", function () { loadAudit(auditPage + 1); });
    }

    Array.prototype.forEach.call(document.querySelectorAll("dialog"), function (dialog) {
      dialog.addEventListener("click", function (e) {
        var closer = e.target.closest("[data-close]");
        if (closer && dialog.contains(closer)) closeDialog(dialog);
        // click on the backdrop closes read-only dialogs (never the form, to protect typed data)
        else if (e.target === dialog && dialog.id !== "form-dialog") closeDialog(dialog);
      });
      dialog.addEventListener("close", function () {
        if (dialog.id === "confirm-dialog") confirmAction = null;
        restoreFocus();
      });
    });

    refreshAll();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
