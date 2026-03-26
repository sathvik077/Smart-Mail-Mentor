"use strict";

// Content script — runs on mail.google.com
// Currently lightweight: just listens for messages from the popup/background
// so we can deep-link to a specific email thread.

chrome.runtime.onMessage.addListener((msg) => {
  if (msg.type === "OPEN_EMAIL" && msg.emailId) {
    // Gmail uses hash-based routing: #inbox/<threadId>
    window.location.hash = `#inbox/${msg.emailId}`;
  }
});
