/* Cloudflare Turnstile widget, hand-rolled Streamlit component.
 *
 * No framework, no build step: this file + index.html ARE the bundle,
 * served as-is by Streamlit (declare_component path) on Cloud and
 * locally. It speaks the minimal Streamlit component protocol over
 * postMessage:
 *   - parent -> iframe:  {type: "streamlit:render", args: {...}}
 *   - iframe -> parent:  {isStreamlitMessage: true, type:
 *       "streamlit:componentReady" | "streamlit:setComponentValue" |
 *       "streamlit:setFrameHeight", ...}
 * The widget renders once per (sitekey, reset) pair: Streamlit fires
 * "render" on every rerun (typing in the password field, for
 * example), and re-rendering the widget there would throw the token
 * away. A new `reset` value (the app bumps it after each login /
 * signup attempt) remounts the widget for a fresh single-use token.
 */
(function () {
  "use strict";

  var FRAME_HEIGHT = 70;
  var container = null;
  var note = null;
  var widgetId = null;
  var lastRendered = null; // "sitekey|reset" of the live widget
  var currentToken = null;
  var apiReady = false;
  var apiFailed = false;
  var pendingArgs = null;

  function sendMessage(type, data) {
    var msg = { isStreamlitMessage: true, type: type };
    if (data) {
      for (var k in data) {
        if (Object.prototype.hasOwnProperty.call(data, k)) {
          msg[k] = data[k];
        }
      }
    }
    window.parent.postMessage(msg, "*");
  }

  function sendToken(token) {
    currentToken = token || null;
    sendMessage("streamlit:setComponentValue", { value: currentToken });
  }

  function showNote(show) {
    if (note) {
      note.style.display = show ? "block" : "none";
    }
  }

  function renderWidget(args) {
    var sitekey = args && args.site_key;
    var reset = args && args.reset !== undefined ? args.reset : 0;
    if (!sitekey || !container) {
      return;
    }
    var stamp = sitekey + "|" + reset;
    if (stamp === lastRendered && widgetId !== null) {
      // Same widget, e.g. a rerun from typing: keep the token.
      if (currentToken) {
        sendToken(currentToken);
      }
      return;
    }
    if (!apiReady) {
      // The API script has not arrived yet; hold the args until it
      // calls onTurnstileApiLoad. A failed load shows the note.
      pendingArgs = args;
      if (apiFailed) {
        showNote(true);
      }
      return;
    }
    showNote(false);
    if (widgetId !== null) {
      try {
        window.turnstile.remove(widgetId);
      } catch (e) {
        /* A removed widget is already gone; render fresh below. */
      }
      widgetId = null;
    }
    widgetId = window.turnstile.render(container, {
      sitekey: sitekey,
      theme: "light", // matches the app's warm off-white palette
      size: "flexible",
      callback: function (token) {
        sendToken(token);
      },
      "expired-callback": function () {
        // Tokens expire if unused; the widget refreshes itself, and
        // null here tells the app the check must be done again.
        sendToken(null);
      },
      "error-callback": function () {
        sendToken(null);
      },
    });
    lastRendered = stamp;
    pendingArgs = null;
    sendMessage("streamlit:setFrameHeight", { height: FRAME_HEIGHT });
  }

  // Called by the Turnstile API script (see ?onload= in index.html).
  window.onTurnstileApiLoad = function () {
    apiReady = true;
    if (pendingArgs) {
      renderWidget(pendingArgs);
    }
  };

  window.addEventListener("message", function (event) {
    var data = event.data || {};
    if (data.type === "streamlit:render") {
      renderWidget(data.args || {});
    }
  });

  // The API script failed to load at all (offline / blocked).
  window.addEventListener("error", function (event) {
    if (
      event &&
      event.target &&
      event.target.tagName === "SCRIPT" &&
      (event.target.src || "").indexOf("challenges.cloudflare.com") !== -1
    ) {
      apiFailed = true;
      showNote(true);
    }
  }, true);

  function init() {
    container = document.getElementById("turnstile-container");
    note = document.getElementById("turnstile-note");
    // apiVersion is REQUIRED: Streamlit rejects the handshake with
    // "Unrecognized component API version: 'undefined'" without it
    // (this bit the live app on 2026-11-06 — the widget showed a red
    // error instead of the check). Version 1 is the component API.
    sendMessage("streamlit:componentReady", {
      apiVersion: 1,
      height: FRAME_HEIGHT,
    });
    sendMessage("streamlit:setFrameHeight", { height: FRAME_HEIGHT });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
