// 아산시 홍보 사업 성과 분석 시스템 — 웹서버 (Node 18+ 표준 모듈만 사용)
"use strict";
const http = require("http");
const https = require("https");
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");

const PORT = Number(process.env.PORT) || 3000;
const ROOT = path.resolve(__dirname, "dashboard");
const ADMIN_ID = process.env.ADMIN_ID || "";
const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD || "";
const GITHUB_TOKEN = process.env.GITHUB_TOKEN || "";
const GITHUB_REPO = process.env.GITHUB_REPO || "";
const WORKFLOW = process.env.GITHUB_WORKFLOW || "daily.yml";
const PUBLIC_URL = (process.env.PUBLIC_URL || "").replace(/\/+$/, "");
// 쿠키 서명 키: 비밀번호에서 파생(재시작해도 세션 유지), 비밀번호가 없으면 무작위
const SECRET = process.env.SESSION_SECRET ||
  (ADMIN_PASSWORD ? crypto.createHash("sha256").update("asan-session:" + ADMIN_ID + ":" + ADMIN_PASSWORD).digest("hex")
                  : crypto.randomBytes(32).toString("hex"));
const SESSION_MS = 8 * 60 * 60 * 1000;
const COOLDOWN_MS = 10 * 60 * 1000;

const TYPES = {
  ".html": "text/html; charset=utf-8", ".js": "application/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
  ".webp": "image/webp", ".svg": "image/svg+xml", ".ico": "image/x-icon", ".txt": "text/plain; charset=utf-8",
  ".woff2": "font/woff2",
};

process.on("uncaughtException", (e) => console.error("[uncaughtException]", e));
process.on("unhandledRejection", (e) => console.error("[unhandledRejection]", e));

// ── 유틸 ──────────────────────────────────────────────
function send(res, code, body, headers = {}) {
  const h = Object.assign({
    "X-Content-Type-Options": "nosniff", "Referrer-Policy": "strict-origin-when-cross-origin",
    "X-Frame-Options": "SAMEORIGIN",
  }, headers);
  if (typeof body === "object" && !Buffer.isBuffer(body)) {
    body = JSON.stringify(body);
    h["Content-Type"] = "application/json; charset=utf-8";
    h["Cache-Control"] = "no-store";
  }
  res.writeHead(code, h);
  res.end(body);
}
function clientIp(req) {
  const cf = req.headers["cf-connecting-ip"];
  if (cf) return String(cf).trim();
  const xff = req.headers["x-forwarded-for"];
  if (xff) { const parts = String(xff).split(",").map((s) => s.trim()).filter(Boolean); if (parts.length) return parts[parts.length - 1]; }
  return req.socket.remoteAddress || "unknown";
}
function isHttps(req) { return String(req.headers["x-forwarded-proto"] || "").split(",")[0].trim() === "https" || !!req.socket.encrypted; }
function origin(req) {
  if (PUBLIC_URL) return PUBLIC_URL;
  const host = String(req.headers["x-forwarded-host"] || req.headers.host || "localhost").split(",")[0].trim().replace(/[^A-Za-z0-9.\-:\[\]]/g, "");
  return (isHttps(req) ? "https" : "http") + "://" + host;
}
function safeEqual(a, b) {
  const ha = crypto.createHash("sha256").update(String(a)).digest();
  const hb = crypto.createHash("sha256").update(String(b)).digest();
  return crypto.timingSafeEqual(ha, hb);
}
function readBody(req, limit = 4096) {
  return new Promise((resolve, reject) => {
    let size = 0; const chunks = [];
    req.on("data", (c) => { size += c.length; if (size > limit) { reject(new Error("too large")); req.destroy(); } else chunks.push(c); });
    req.on("end", () => resolve(Buffer.concat(chunks).toString("utf8")));
    req.on("error", reject);
  });
}

// ── 세션(HMAC 서명 쿠키) ───────────────────────────────
function sign(v) { return crypto.createHmac("sha256", SECRET).update(v).digest("base64url"); }
function makeCookie(req) {
  const exp = Date.now() + SESSION_MS;
  const payload = Buffer.from(JSON.stringify({ u: ADMIN_ID, exp })).toString("base64url");
  const v = payload + "." + sign(payload);
  return `asan_admin=${v}; Path=/; HttpOnly; SameSite=Strict; Max-Age=${SESSION_MS / 1000}` + (isHttps(req) ? "; Secure" : "");
}
function clearCookie(req) { return "asan_admin=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0" + (isHttps(req) ? "; Secure" : ""); }
function isAdmin(req) {
  if (!ADMIN_ID || !ADMIN_PASSWORD) return false;
  const m = /(?:^|;\s*)asan_admin=([A-Za-z0-9_\-]+)\.([A-Za-z0-9_\-]+)/.exec(req.headers.cookie || "");
  if (!m) return false;
  const expected = sign(m[1]);
  if (expected.length !== m[2].length || !crypto.timingSafeEqual(Buffer.from(expected), Buffer.from(m[2]))) return false;
  try { const p = JSON.parse(Buffer.from(m[1], "base64url").toString("utf8")); return p.u === ADMIN_ID && p.exp > Date.now(); }
  catch { return false; }
}

// ── 무차별 대입 방지 ──────────────────────────────────
const fails = new Map();         // ip → {n, until, first}
let globalFails = [];            // 실패 시각 목록(1시간)
let globalLockUntil = 0;
function lockState(ip) {
  const now = Date.now();
  if (globalLockUntil > now) return { locked: true, wait: globalLockUntil - now };
  const f = fails.get(ip);
  if (f && f.until > now) return { locked: true, wait: f.until - now };
  return { locked: false };
}
function recordFail(ip) {
  const now = Date.now();
  const f = fails.get(ip) || { n: 0, until: 0 };
  if (f.until && f.until <= now) { f.n = 0; f.until = 0; }
  f.n += 1;
  if (f.n >= 5) { f.until = now + 15 * 60 * 1000; f.n = 0; }
  fails.set(ip, f);
  globalFails = globalFails.filter((t) => now - t < 60 * 60 * 1000);
  globalFails.push(now);
  if (globalFails.length >= 20) { globalLockUntil = now + 60 * 60 * 1000; globalFails = []; }
}
setInterval(() => { const now = Date.now(); for (const [k, v] of fails) if (v.until < now && v.n === 0) fails.delete(k); }, 10 * 60 * 1000).unref();

// ── GitHub API ────────────────────────────────────────
function gh(method, apiPath, body) {
  return new Promise((resolve, reject) => {
    const data = body ? JSON.stringify(body) : null;
    const req = https.request({
      hostname: "api.github.com", path: apiPath, method,
      headers: {
        "Authorization": "Bearer " + GITHUB_TOKEN, "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "asan-news-dashboard",
        ...(data ? { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(data) } : {}),
      },
      timeout: 15000,
    }, (res) => {
      let s = ""; res.on("data", (c) => (s += c));
      res.on("end", () => { let j = null; try { j = s ? JSON.parse(s) : null; } catch {} resolve({ status: res.statusCode, json: j }); });
    });
    req.on("timeout", () => req.destroy(new Error("timeout")));
    req.on("error", reject);
    if (data) req.write(data);
    req.end();
  });
}
let lastDispatch = 0;
async function latestRun() {
  const r = await gh("GET", `/repos/${GITHUB_REPO}/actions/workflows/${encodeURIComponent(WORKFLOW)}/runs?per_page=1`);
  const run = r.json && r.json.workflow_runs && r.json.workflow_runs[0];
  return run ? { id: run.id, status: run.status, conclusion: run.conclusion, created_at: run.created_at, event: run.event, url: run.html_url } : null;
}
function deployedGenerated() {
  try {
    const head = fs.readFileSync(path.join(ROOT, "data.js"), "utf8").slice(0, 4000);
    const m = /"generated":"([^"]+)"/.exec(head);
    return m ? m[1] : null;
  } catch { return null; }
}

// ── API ──────────────────────────────────────────────
async function handleApi(req, res, pathname) {
  const ip = clientIp(req);
  if (pathname === "/api/me" && req.method === "GET") {
    return send(res, 200, { admin: isAdmin(req), configured: !!(ADMIN_ID && ADMIN_PASSWORD), canRefresh: !!(GITHUB_TOKEN && GITHUB_REPO) });
  }
  if (pathname === "/api/login" && req.method === "POST") {
    if (!ADMIN_ID || !ADMIN_PASSWORD) return send(res, 503, { ok: false, error: "관리자 계정이 설정되지 않았습니다(ADMIN_ID / ADMIN_PASSWORD 환경변수)." });
    const ls = lockState(ip);
    if (ls.locked) return send(res, 429, { ok: false, error: `로그인 시도가 너무 많습니다. ${Math.ceil(ls.wait / 60000)}분 후 다시 시도하세요.` });
    let body;
    try { body = JSON.parse(await readBody(req)); } catch { return send(res, 400, { ok: false, error: "잘못된 요청입니다." }); }
    const idOk = safeEqual(body && body.id || "", ADMIN_ID);
    const pwOk = safeEqual(body && body.password || "", ADMIN_PASSWORD);
    if (!(idOk && pwOk)) { recordFail(ip); return send(res, 401, { ok: false, error: "아이디 또는 비밀번호가 올바르지 않습니다." }); }
    fails.delete(ip);
    return send(res, 200, { ok: true, canRefresh: !!(GITHUB_TOKEN && GITHUB_REPO) }, { "Set-Cookie": makeCookie(req) });
  }
  if (pathname === "/api/logout" && req.method === "POST") {
    return send(res, 200, { ok: true }, { "Set-Cookie": clearCookie(req) });
  }
  if (pathname === "/api/refresh" && req.method === "POST") {
    if (!isAdmin(req)) return send(res, 401, { ok: false, error: "관리자 로그인이 필요합니다." });
    if (!GITHUB_TOKEN || !GITHUB_REPO) return send(res, 503, { ok: false, error: "GITHUB_TOKEN / GITHUB_REPO 환경변수가 없어 갱신할 수 없습니다." });
    const now = Date.now();
    if (now - lastDispatch < COOLDOWN_MS) return send(res, 429, { ok: false, error: `최근에 갱신을 요청했습니다. ${Math.ceil((COOLDOWN_MS - (now - lastDispatch)) / 60000)}분 후 다시 시도하세요.` });
    try {
      const run = await latestRun();
      if (run && (run.status === "queued" || run.status === "in_progress")) return send(res, 409, { ok: false, error: "이미 갱신이 실행 중입니다." });
      const r = await gh("POST", `/repos/${GITHUB_REPO}/actions/workflows/${encodeURIComponent(WORKFLOW)}/dispatches`, { ref: "main" });
      if (r.status !== 204) return send(res, 502, { ok: false, error: `GitHub 실행 요청 실패(${r.status}).` });
      lastDispatch = now;
      return send(res, 200, { ok: true });
    } catch (e) { return send(res, 502, { ok: false, error: "GitHub 연결 실패: " + e.message }); }
  }
  if (pathname === "/api/refresh-status" && req.method === "GET") {
    if (!isAdmin(req)) return send(res, 401, { ok: false, error: "관리자 로그인이 필요합니다." });
    let run = null;
    if (GITHUB_TOKEN && GITHUB_REPO) { try { run = await latestRun(); } catch {} }
    return send(res, 200, { ok: true, run, generated: deployedGenerated() });
  }
  return send(res, 404, { ok: false, error: "없는 API입니다." });
}

// ── 정적 파일 ─────────────────────────────────────────
function serveFile(req, res, file) {
  fs.stat(file, (err, st) => {
    if (err || !st.isFile()) return send(res, 404, "404 Not Found", { "Content-Type": "text/plain; charset=utf-8" });
    const ext = path.extname(file).toLowerCase();
    const type = TYPES[ext] || "application/octet-stream";
    const noCache = ext === ".html" || ext === ".js";
    const headers = { "Content-Type": type, "Cache-Control": noCache ? "no-cache" : "public, max-age=86400" };
    if (ext === ".html") {
      fs.readFile(file, "utf8", (e, txt) => {
        if (e) return send(res, 500, "500", { "Content-Type": "text/plain" });
        send(res, 200, req.method === "HEAD" ? "" : txt.split("%%ORIGIN%%").join(origin(req)), headers);
      });
    } else {
      headers["Content-Length"] = st.size;
      res.writeHead(200, Object.assign({ "X-Content-Type-Options": "nosniff" }, headers));
      if (req.method === "HEAD") return res.end();
      fs.createReadStream(file).pipe(res);
    }
  });
}

const server = http.createServer(async (req, res) => {
  try {
    const rawPath = (req.url || "/").split("?")[0];
    let pathname;
    try { pathname = decodeURIComponent(rawPath); } catch { return send(res, 400, "400 Bad Request", { "Content-Type": "text/plain; charset=utf-8" }); }
    if (pathname.includes("\0")) return send(res, 400, "400 Bad Request", { "Content-Type": "text/plain; charset=utf-8" });

    if (pathname.startsWith("/api/")) return await handleApi(req, res, pathname);
    if (req.method !== "GET" && req.method !== "HEAD") return send(res, 405, "405 Method Not Allowed", { "Content-Type": "text/plain; charset=utf-8", "Allow": "GET, HEAD" });
    if (pathname === "/healthz") return send(res, 200, { ok: true });
    if (pathname === "/admin/") return send(res, 301, "", { Location: "/admin" });
    if (pathname === "/admin") return serveFile(req, res, path.join(ROOT, "index.html"));

    let rel = pathname === "/" ? "/index.html" : pathname;
    if (rel.endsWith("/")) rel += "index.html";
    const file = path.resolve(ROOT, "." + rel);
    if (!file.startsWith(ROOT + path.sep)) return send(res, 403, "403 Forbidden", { "Content-Type": "text/plain; charset=utf-8" });
    if (path.basename(file).startsWith(".")) return send(res, 404, "404 Not Found", { "Content-Type": "text/plain; charset=utf-8" });
    serveFile(req, res, file);
  } catch (e) {
    console.error("[request]", e);
    if (!res.headersSent) send(res, 500, "500 Internal Server Error", { "Content-Type": "text/plain; charset=utf-8" });
  }
});

server.listen(PORT, () => console.log(`아산시 홍보 성과 대시보드: http://localhost:${PORT}  (관리자: /admin)`));
