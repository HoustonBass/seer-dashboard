// One-off discovery tool: logs into the BiblioCommons library site with a
// real account, navigates to search results for a specific title, then PAUSES
// and hands control to a human — the actual "Place a Hold" click is done by a
// person watching the visible (non-headless) browser window, never scripted
// here. See CLAUDE.md: hold-endpoint discovery is deliberately not something
// an agent does alone, since a wrong programmatic call could place a real,
// uncancelable-by-us hold. This script only logs in, searches, and listens —
// it never clicks the hold button itself.
//
// Usage: node scripts/discovery/capture-hold.mjs "<search query>"
// Reads LIBRARY_USERNAME / LIBRARY_PASSWORD / LIBRARY_BASE_URL from ../../.env

import { chromium } from "playwright";
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const repoRoot = join(__dirname, "..", "..");

const QUERY = process.argv[2] || "Pirates of the Caribbean On Stranger Tides";
const WAIT_SECONDS = 45; // generous window for a human to find the title and click Place a Hold

function loadEnv(path) {
  const out = {};
  for (const line of readFileSync(path, "utf8").split("\n")) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const eq = trimmed.indexOf("=");
    if (eq === -1) continue;
    out[trimmed.slice(0, eq)] = trimmed.slice(eq + 1);
  }
  return out;
}

const env = loadEnv(join(repoRoot, ".env"));
const BASE_URL = env.LIBRARY_BASE_URL || "https://fulcolibrary.bibliocommons.com";
const USERNAME = env.LIBRARY_USERNAME;
const PASSWORD = env.LIBRARY_PASSWORD;

if (!USERNAME || !PASSWORD) {
  console.error("LIBRARY_USERNAME / LIBRARY_PASSWORD missing from .env");
  process.exit(1);
}

const captured = [];

function redact(headers) {
  const clone = { ...headers };
  for (const key of Object.keys(clone)) {
    if (/cookie|authorization|token/i.test(key)) clone[key] = "***REDACTED***";
  }
  return clone;
}

function redactUrl(url) {
  return url.replace(/([?&]token=)[^&]+/i, "$1***REDACTED***");
}

function redactBody(raw) {
  if (!raw) return null;
  try {
    const obj = JSON.parse(raw);
    const redactKeys = (o) => {
      if (Array.isArray(o)) return o.map(redactKeys);
      if (o && typeof o === "object") {
        const out = {};
        for (const [k, v] of Object.entries(o)) {
          out[k] = /pass|pin|token|cookie/i.test(k) ? "***REDACTED***" : redactKeys(v);
        }
        return out;
      }
      return o;
    };
    return JSON.stringify(redactKeys(obj));
  } catch {
    try {
      const params = new URLSearchParams(raw);
      for (const key of params.keys()) {
        if (/pass|pin|token/i.test(key)) params.set(key, "***REDACTED***");
      }
      return params.toString();
    } catch {
      return "[unparseable]";
    }
  }
}

const browser = await chromium.launch({ headless: false });
const context = await browser.newContext();
const page = await context.newPage();

page.on("request", (req) => {
  const url = req.url();
  if (!url.includes("bibliocommons.com")) return;
  captured.push({
    phase: "request",
    method: req.method(),
    url: redactUrl(url),
    headers: redact(req.headers()),
    postData: redactBody(req.postData()),
  });
});

page.on("response", async (res) => {
  const url = res.url();
  if (!url.includes("bibliocommons.com")) return;
  const contentType = res.headers()["content-type"] || "";
  let bodySnippet = null;
  if (contentType.includes("json")) {
    try {
      bodySnippet = (await res.text()).slice(0, 4000);
    } catch {
      bodySnippet = null;
    }
  }
  captured.push({
    phase: "response",
    status: res.status(),
    url: redactUrl(url),
    contentType,
    headers: redact(res.headers()),
    bodySnippet,
  });
});

console.log(`Navigating to ${BASE_URL}/user/login ...`);
await page.goto(`${BASE_URL}/user/login`);

console.log("Filling login form...");
await page.getByLabel(/username|library card/i).fill(USERNAME);
await page.getByLabel(/pin|password/i).fill(PASSWORD);
await page.locator('input[name="commit"]').click();

console.log("Waiting for post-login navigation...");
await page.waitForLoadState("networkidle").catch(() => {});
await page.waitForTimeout(2000);

const searchUrl = `${BASE_URL}/v2/search?query=${encodeURIComponent(QUERY)}&searchType=bl`;
console.log(`Navigating to search results for "${QUERY}" ...`);
await page.goto(searchUrl);
await page.waitForLoadState("networkidle").catch(() => {});

console.log("");
console.log("=".repeat(70));
console.log(`Browser window is open. YOU click "Place a Hold" on the right`);
console.log(`title now — this script will NOT click anything for you.`);
console.log(`Capturing network traffic for the next ${WAIT_SECONDS} seconds...`);
console.log("=".repeat(70));
console.log("");

for (let remaining = WAIT_SECONDS; remaining > 0; remaining -= 5) {
  console.log(`  ${remaining}s remaining...`);
  await page.waitForTimeout(5000);
}

const outPath = join(__dirname, "captured-hold.json");
writeFileSync(outPath, JSON.stringify({ query: QUERY, captured }, null, 2));
console.log(`\nWrote ${captured.length} captured entries to ${outPath}`);

const holdRelated = captured.filter((c) => /hold/i.test(c.url));
console.log(`\n${holdRelated.length} entries with "hold" in the URL:`);
for (const entry of holdRelated) {
  console.log(JSON.stringify(entry, null, 2));
}

await browser.close();
