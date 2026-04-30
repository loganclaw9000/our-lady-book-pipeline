---
# Front-matter required so Jekyll renders Liquid {{ site.feedback_worker_url }} below.
---
// feedback.js — handles reader feedback form submissions.
// Tries the configured Cloudflare Worker first; on any failure
// (worker unconfigured, CORS, network) falls back to a mailto: draft so
// the visitor's input is not lost.
(function () {
  // Worker URL is injected by Jekyll from docs/_config.yml at build time.
  // If the placeholder is left untouched we treat it as unconfigured.
  var WORKER_URL = "{{ site.feedback_worker_url | default: '' }}";
  var FALLBACK_MAILTO = "{{ site.feedback_mailto | default: 'pauljflogan+ourlady@gmail.com' }}";

  function statusEl(form) {
    return form.querySelector(".reader-feedback-status");
  }

  function disable(form, on) {
    Array.prototype.forEach.call(
      form.querySelectorAll("button, select, textarea, input"),
      function (el) { el.disabled = on; }
    );
  }

  function buildMailtoFallback(payload) {
    var lines = [
      "Chapter: " + payload.chapter,
      "Kind: " + payload.kind,
      "",
      "What you want to say:",
      payload.body || "",
      "",
      "Optional contact: " + (payload.contact || "(none)"),
    ];
    var subject = "[reader feedback] " + payload.chapter + ": " + payload.kind;
    var url = "mailto:" + FALLBACK_MAILTO
      + "?subject=" + encodeURIComponent(subject)
      + "&body=" + encodeURIComponent(lines.join("\n"));
    return url;
  }

  window.submitReaderFeedback = function (evt) {
    evt.preventDefault();
    var form = evt.target;
    var fd = new FormData(form);
    var payload = {
      chapter: fd.get("chapter") || "general",
      kind: fd.get("kind") || "other",
      body: fd.get("body") || "",
      contact: fd.get("contact") || "",
    };
    var status = statusEl(form);
    if (status) status.textContent = " sending…";

    var workerConfigured = WORKER_URL && WORKER_URL.indexOf("REPLACE") === -1;

    function fallback(reason) {
      if (status) status.textContent = " " + reason + " — opening email instead.";
      window.location.href = buildMailtoFallback(payload);
    }

    if (!workerConfigured) {
      fallback("server not configured");
      return false;
    }

    disable(form, true);
    fetch(WORKER_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
      .then(function (r) {
        return r.json().then(function (j) { return { status: r.status, json: j }; });
      })
      .then(function (resp) {
        disable(form, false);
        if (resp.status === 200 && resp.json && resp.json.ok) {
          if (status) {
            status.textContent = " ✓ submitted (issue #" + resp.json.issue_number + ")";
          }
          form.reset();
        } else {
          var why = (resp.json && resp.json.error) || ("http " + resp.status);
          fallback("submit failed (" + why + ")");
        }
      })
      .catch(function () {
        disable(form, false);
        fallback("network error");
      });
    return false;
  };
})();
