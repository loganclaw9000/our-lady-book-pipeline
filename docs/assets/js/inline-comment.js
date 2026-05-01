---
# Front-matter so Jekyll renders Liquid {{ site.feedback_worker_url }} below.
---
// inline-comment.js — text-selection commenting on chapter pages.
// Visitor highlights any text → floating "💬 comment" button → modal form
// with chapter + paragraph anchor + selected quote prefilled. POSTs to the
// same Cloudflare Worker as the page-level feedback form (or falls back to
// mailto:). Same GitHub-Issues read-back path.
(function () {
  var WORKER_URL = "{{ site.feedback_worker_url | default: '' }}";
  var FALLBACK_MAILTO = "{{ site.feedback_mailto | default: 'pauljflogan+ourlady@gmail.com' }}";

  // Derive a stable chapter identifier from the URL.
  function chapterIdFromUrl() {
    var m = window.location.pathname.match(/chapter_(\d+)/i);
    if (m) return "Chapter " + parseInt(m[1], 10);
    if (/retrospective/i.test(window.location.pathname)) {
      var rm = window.location.pathname.match(/chapter_(\d+)/i);
      if (rm) return "Chapter " + parseInt(rm[1], 10) + " retrospective";
    }
    return "general";
  }

  // Find the main content container that holds prose paragraphs.
  function contentRoot() {
    return document.querySelector("main") ||
           document.querySelector("section.main-content") ||
           document.querySelector("article") ||
           document.body;
  }

  // Assign stable IDs to <p> nodes. Skips nodes that already have an id.
  function assignParagraphIds() {
    var root = contentRoot();
    if (!root) return;
    var paras = root.querySelectorAll("p");
    var slug = chapterIdFromUrl().toLowerCase().replace(/ /g, "-");
    for (var i = 0; i < paras.length; i++) {
      if (!paras[i].id) {
        paras[i].id = slug + "-p" + i;
      }
    }
  }

  // The closest paragraph element containing this node.
  function closestParagraph(node) {
    while (node && node !== document.body) {
      if (node.nodeType === 1 && node.tagName === "P") return node;
      node = node.parentNode;
    }
    return null;
  }

  // Build a tooltip with 2 buttons positioned at the end of the user's selection.
  function makeTooltip() {
    var wrap = document.createElement("div");
    wrap.id = "inline-comment-tooltip";
    wrap.style.cssText = [
      "position:absolute",
      "z-index:9999",
      "display:none",
      "gap:4px",
      "background:transparent",
    ].join(";");
    var commonBtnCss = [
      "padding:4px 10px",
      "border:1px solid #555",
      "background:#fffae0",
      "color:#222",
      "border-radius:4px",
      "font-size:13px",
      "cursor:pointer",
      "box-shadow:0 1px 3px rgba(0,0,0,0.2)",
    ].join(";");
    var commentBtn = document.createElement("button");
    commentBtn.type = "button";
    commentBtn.id = "inline-comment-tooltip-comment";
    commentBtn.textContent = "💬 comment";
    commentBtn.style.cssText = commonBtnCss;
    wrap.appendChild(commentBtn);
    document.body.appendChild(wrap);
    return wrap;
  }

  // Build a modal container; lazy-injected on first use.
  function makeModal() {
    var overlay = document.createElement("div");
    overlay.id = "inline-comment-overlay";
    overlay.style.cssText = [
      "position:fixed",
      "inset:0",
      "background:rgba(0,0,0,0.4)",
      "z-index:10000",
      "display:none",
      "align-items:center",
      "justify-content:center",
    ].join(";");
    overlay.innerHTML = (
      '<div id="inline-comment-modal" style="background:#fff;color:#222;padding:1.2em 1.5em;border-radius:6px;max-width:560px;width:90%;box-shadow:0 4px 16px rgba(0,0,0,0.3);">' +
      '<h3 style="margin-top:0">Comment on this passage</h3>' +
      '<div id="inline-comment-quote" style="border-left:3px solid #888;padding:0.4em 0.8em;background:#f5f5f5;margin:0.6em 0;font-style:italic;font-size:0.95em;max-height:120px;overflow:auto;"></div>' +
      '<form id="inline-comment-form" onsubmit="return submitInlineComment(event)">' +
        '<label>Kind:<br>' +
        '<select name="kind">' +
          '<option>praise / what worked</option>' +
          '<option>critique / what did not work</option>' +
          '<option>factual or continuity error</option>' +
          '<option>voice / prose suggestion</option>' +
          '<option>bug or site issue</option>' +
          '<option>other</option>' +
        '</select>' +
        '</label><br><br>' +
        '<label>Your comment:<br>' +
        '<textarea name="body" rows="5" cols="60" required style="width:100%;box-sizing:border-box"></textarea>' +
        '</label><br><br>' +
        '<label>Optional contact (blank = anonymous):<br>' +
        '<input type="text" name="contact" maxlength="200" style="width:100%;box-sizing:border-box">' +
        '</label><br><br>' +
        '<div style="display:flex;gap:0.5em;align-items:center">' +
          '<button type="submit">Submit</button>' +
          '<button type="button" id="inline-comment-cancel">Cancel</button>' +
          '<span id="inline-comment-status" style="font-size:0.9em;color:#555"></span>' +
        '</div>' +
      '</form>' +
      '</div>'
    );
    document.body.appendChild(overlay);
    overlay.addEventListener("click", function (e) {
      if (e.target === overlay) hideModal();
    });
    document.getElementById("inline-comment-cancel").addEventListener("click", hideModal);
    return overlay;
  }

  var tooltip;
  var modal;
  var ctx = { quote: "", anchor: "", chapter: "" };

  function hideTooltip() {
    if (tooltip) tooltip.style.display = "none";
  }

  function showModal(quote, anchor, chapter) {
    if (!modal) modal = makeModal();
    ctx.quote = quote;
    ctx.anchor = anchor;
    ctx.chapter = chapter;
    document.getElementById("inline-comment-quote").textContent = quote;
    document.getElementById("inline-comment-status").textContent = "";
    var form = document.getElementById("inline-comment-form");
    if (form) form.reset();
    modal.style.display = "flex";
  }

  function hideModal() {
    if (modal) modal.style.display = "none";
  }

  document.addEventListener("DOMContentLoaded", function () {
    assignParagraphIds();
    tooltip = makeTooltip();

    document.addEventListener("mouseup", function () {
      var sel = window.getSelection();
      if (!sel || sel.isCollapsed) {
        hideTooltip();
        return;
      }
      var text = sel.toString().trim();
      if (text.length < 4) {
        hideTooltip();
        return;
      }
      // Confirm selection lives inside main content.
      var anchorNode = sel.anchorNode;
      var p = closestParagraph(anchorNode);
      if (!p || !contentRoot().contains(p)) {
        hideTooltip();
        return;
      }
      var rect = sel.getRangeAt(0).getBoundingClientRect();
      tooltip.style.top = (window.scrollY + rect.bottom + 4) + "px";
      tooltip.style.left = (window.scrollX + rect.left) + "px";
      tooltip.style.display = "flex";
      var anchor = p.id || "";
      var chapter = chapterIdFromUrl();
      document.getElementById("inline-comment-tooltip-comment").onclick = function () {
        showModal(text, anchor, chapter);
        hideTooltip();
        if (sel.removeAllRanges) sel.removeAllRanges();
      };
    });

    document.addEventListener("scroll", hideTooltip, true);
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") {
        hideTooltip();
        hideModal();
      }
    });
  });

  function buildMailtoFallback(payload) {
    var lines = [
      "Chapter: " + payload.chapter,
      "Paragraph anchor: " + payload.anchor,
      "Kind: " + payload.kind,
      "",
      "Quoted passage:",
      "> " + (payload.quote || "").replace(/\n/g, "\n> "),
      "",
      "Comment:",
      payload.body || "",
      "",
      "Optional contact: " + (payload.contact || "(none)"),
    ];
    var subject = "[reader inline comment] " + payload.chapter + ": " + payload.kind;
    return "mailto:" + FALLBACK_MAILTO
      + "?subject=" + encodeURIComponent(subject)
      + "&body=" + encodeURIComponent(lines.join("\n"));
  }

  window.submitInlineComment = function (evt) {
    evt.preventDefault();
    var form = document.getElementById("inline-comment-form");
    var fd = new FormData(form);
    var statusEl = document.getElementById("inline-comment-status");
    var anchorUrl = ctx.anchor
      ? window.location.pathname + "#" + ctx.anchor
      : window.location.pathname;
    var bodyText = (fd.get("body") || "").toString();
    var quoted = (ctx.quote || "").split("\n").map(function (l) { return "> " + l; }).join("\n");
    var combinedBody = (
      "**Anchor:** [" + (ctx.anchor || "(none)") + "](" + anchorUrl + ")\n\n" +
      "**Quoted passage:**\n" + quoted + "\n\n" +
      "**Comment:**\n" + bodyText
    );
    var payload = {
      chapter: ctx.chapter,
      kind: (fd.get("kind") || "other").toString(),
      body: combinedBody,
      contact: (fd.get("contact") || "").toString(),
      // For richer mailto fallback only:
      quote: ctx.quote,
      anchor: ctx.anchor,
    };

    var workerConfigured = WORKER_URL && WORKER_URL.indexOf("REPLACE") === -1;
    if (!workerConfigured) {
      statusEl.textContent = "server not configured — opening email";
      window.location.href = buildMailtoFallback(payload);
      return false;
    }

    statusEl.textContent = " sending…";
    fetch(WORKER_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        chapter: payload.chapter,
        kind: payload.kind,
        body: payload.body,
        contact: payload.contact,
      }),
    })
      .then(function (r) {
        return r.json().then(function (j) { return { status: r.status, json: j }; });
      })
      .then(function (resp) {
        if (resp.status === 200 && resp.json && resp.json.ok) {
          statusEl.textContent = " ✓ submitted (issue #" + resp.json.issue_number + ")";
          setTimeout(hideModal, 1200);
        } else {
          var why = (resp.json && resp.json.error) || ("http " + resp.status);
          statusEl.textContent = " submit failed (" + why + ") — opening email";
          setTimeout(function () {
            window.location.href = buildMailtoFallback(payload);
          }, 600);
        }
      })
      .catch(function () {
        statusEl.textContent = " network error — opening email";
        setTimeout(function () {
          window.location.href = buildMailtoFallback(payload);
        }, 600);
      });
    return false;
  };
})();
