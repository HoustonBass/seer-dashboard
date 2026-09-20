// One-off discovery tool: logs into the BiblioCommons library site with a real
// account, records every network request/response, and dumps them to a JSON
// file so we can pick out the real auth/search endpoints by hand.
//
// Usage: node scripts/discovery/capture-login.mjs
// Reads LIBRARY_USERNAME / LIBRARY_PASSWORD / LIBRARY_BASE_URL from ../../.env

import { chromium } from "playwright";
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const repoRoot = join(__dirname, "..", "..");

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

// /sso/web?token=<JWT> carries live bc_access_token/session_id values in the
// JWT payload itself (base64, unencrypted) — redact the whole query string,
// not just header fields, or a capture file leaks live credentials.
function redactUrl(url) {
  return url.replace(/([?&]token=)[^&]+/i, "$1***REDACTED***");
}

const browser = await chromium.launch({ headless: false });
const context = await browser.newContext();
const page = await context.newPage();

function redactPostData(postData) {
  if (!postData) return null;
  try {
    const params = new URLSearchParams(postData);
    for (const key of params.keys()) {
      if (/pass|pin/i.test(key)) params.set(key, "***REDACTED***");
    }
    return params.toString();
  } catch {
    return "[unparseable, not urlencoded]";
  }
}

page.on("request", (req) => {
  const url = req.url();
  if (!url.includes("bibliocommons.com")) return;
  captured.push({
    phase: "request",
    method: req.method(),
    url: redactUrl(url),
    headers: redact(req.headers()),
    postData: redactPostData(req.postData()),
  });
});

page.on("response", async (res) => {
  const url = res.url();
  if (!url.includes("bibliocommons.com")) return;
  const contentType = res.headers()["content-type"] || "";
  let bodySnippet = null;
  if (contentType.includes("json")) {
    try {
      const text = await res.text();
      bodySnippet = text.slice(0, 2000);
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
await page.waitForTimeout(3000);

console.log("Logged in. Now running a search to capture that API too...");
await page.goto(`${BASE_URL}/v2/search?query=brooklyn&searchType=bl`);
await page.waitForLoadState("networkidle").catch(() => {});
await page.waitForTimeout(3000);

const cookies = (await context.cookies()).map((c) => ({
  name: c.name,
  domain: c.domain,
  httpOnly: c.httpOnly,
  secure: c.secure,
  sameSite: c.sameSite,
  value: "***REDACTED***",
}));

const outPath = join(__dirname, "captured-login.json");
writeFileSync(outPath, JSON.stringify({ captured, cookies }, null, 2));
console.log(`Wrote ${captured.length} captured entries + ${cookies.length} cookie names to ${outPath}`);

await browser.close();
