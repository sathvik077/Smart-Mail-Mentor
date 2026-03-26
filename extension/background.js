"use strict";

// Service worker for Smart Mail Mentor.
// Handles badge updates and message routing between popup and tabs.

const API = "http://localhost:8000";

// Check backend health when the extension starts
chrome.runtime.onInstalled.addListener(async () => {
  await checkBackend();
});

chrome.runtime.onStartup.addListener(async () => {
  await checkBackend();
});

async function checkBackend() {
  try {
    const resp = await fetch(`${API}/health`, { signal: AbortSignal.timeout(3000) });
    if (resp.ok) {
      chrome.action.setBadgeText({ text: "" });
    }
  } catch {
    // Backend not running — show a subtle indicator
    chrome.action.setBadgeText({ text: "!" });
    chrome.action.setBadgeBackgroundColor({ color: "#e37400" });
  }
}

// Allow popup / content scripts to send messages to background
chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.type === "OPEN_URL") {
    chrome.tabs.create({ url: msg.url });
    sendResponse({ ok: true });
  }
  return true; // keep channel open for async
});
