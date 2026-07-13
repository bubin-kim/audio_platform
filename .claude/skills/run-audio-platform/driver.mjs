// REPL driver for the Audio Dataset Platform (FastAPI backend + Next.js
// frontend). No chromium-cli in this environment, so this adapts the
// electron.md REPL pattern to a plain web app: `chromium.launch({channel:
// "chrome"})` drives the system-installed Google Chrome instead of
// downloading Chromium, and `up`/`down` manage the two dev-server
// processes the browser needs to have something to talk to.
//
// Usage:
//   node driver.mjs            # REPL — "help" for commands
//   node driver.mjs up|down    # one-shot: start/stop backend+frontend
//   node driver.mjs smoke      # one-shot: up -> golden path -> down
import { chromium } from "playwright";
import { spawn, execSync } from "node:child_process";
import * as readline from "node:readline";
import * as fs from "node:fs";
import * as path from "node:path";
import * as os from "node:os";
import { fileURLToPath } from "node:url";

process.on("unhandledRejection", (e) => console.error("UNHANDLED REJECTION:", e));
process.on("uncaughtException", (e) => console.error("UNCAUGHT EXCEPTION:", e));

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, "../../..");
const BACKEND_DIR = path.join(REPO_ROOT, "backend");
const FRONTEND_DIR = path.join(REPO_ROOT, "frontend");
const STATE_FILE = path.join(__dirname, ".driver-state.json");
const SHOT_DIR = process.env.SCREENSHOT_DIR || path.join(__dirname, "screenshots");
fs.mkdirSync(SHOT_DIR, { recursive: true });

const BACKEND_URL = "http://localhost:8100";
const FRONTEND_URL = "http://localhost:3100";

let browser = null;
let page = null;

// --- process lifecycle (backend + frontend) ---

function killPort(port) {
  try {
    const pids = execSync(`lsof -i :${port} -sTCP:LISTEN -t`, { stdio: ["ignore", "pipe", "ignore"] })
      .toString()
      .trim()
      .split("\n")
      .filter(Boolean);
    for (const pid of pids) {
      try {
        process.kill(Number(pid), "SIGKILL");
      } catch {}
    }
  } catch {
    // lsof exits non-zero when nothing is listening — fine.
  }
}

async function waitForHttp(url, timeoutMs) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const res = await fetch(url);
      if (res.ok || res.status === 404) return true; // server responding at all
    } catch {}
    await new Promise((r) => setTimeout(r, 500));
  }
  return false;
}

function spawnLogged(cmd, args, opts) {
  const logPath = opts.logPath;
  const logFd = fs.openSync(logPath, "a");
  const child = spawn(cmd, args, {
    cwd: opts.cwd,
    env: opts.env,
    detached: true,
    stdio: ["ignore", logFd, logFd],
  });
  child.unref();
  return child;
}

async function up() {
  const already = (await fetch(BACKEND_URL + "/health").then((r) => r.ok).catch(() => false))
    && (await fetch(FRONTEND_URL).then((r) => r.ok).catch(() => false));
  if (already) {
    // Someone else's servers (e.g. scripts/dev.sh) — reuse but never kill.
    console.log("up: backend+frontend already responding, reusing (down will leave them running).");
    fs.writeFileSync(STATE_FILE, JSON.stringify({ reused: true }, null, 2));
    return { reused: true };
  }

  // Stray `next dev`/`uvicorn` from a previous crashed run silently bumps
  // the frontend to :3101 instead of failing loudly — always clear first.
  killPort(8100);
  killPort(3100);

  const runId = `audio-platform-driver-${Date.now()}`;
  const dbPath = path.join(os.tmpdir(), `${runId}.db`);
  const dataDir = path.join(os.tmpdir(), `${runId}-data`);
  const backendLog = path.join(os.tmpdir(), `${runId}-backend.log`);
  const frontendLog = path.join(os.tmpdir(), `${runId}-frontend.log`);
  const dbUrl = `sqlite:///${dbPath}`;

  console.log("up: running alembic migrations on isolated temp db:", dbPath);
  // NOT stdio:"inherit" — that shares fd 0 with this process, and when the
  // driver is fed a piped script (heredoc), the child process can steal or
  // truncate the parent's own stdin, silently killing the REPL right after
  // this call returns (readline never sees the rest of the piped commands).
  console.log(
    execSync("uv run alembic upgrade head", {
      cwd: BACKEND_DIR,
      env: { ...process.env, DATABASE_URL: dbUrl },
      stdio: ["ignore", "pipe", "pipe"],
    }).toString(),
  );

  console.log("up: starting backend (uvicorn :8100)...");
  const backendChild = spawnLogged("uv", ["run", "uvicorn", "app.main:app", "--port", "8100"], {
    cwd: BACKEND_DIR,
    env: { ...process.env, DATABASE_URL: dbUrl, DATA_DIR: dataDir },
    logPath: backendLog,
  });
  if (!(await waitForHttp(BACKEND_URL + "/health", 30_000))) {
    console.log("up: FAILED — backend did not come up. Log:", backendLog);
    throw new Error("backend failed to start");
  }
  console.log("up: backend ready.");

  const envLocal = path.join(FRONTEND_DIR, ".env.local");
  if (!fs.existsSync(envLocal)) {
    fs.copyFileSync(path.join(FRONTEND_DIR, ".env.local.example"), envLocal);
  }

  console.log("up: starting frontend (next dev :3100)...");
  const frontendChild = spawnLogged("npm", ["run", "dev"], {
    cwd: FRONTEND_DIR,
    env: process.env,
    logPath: frontendLog,
  });
  if (!(await waitForHttp(FRONTEND_URL, 40_000))) {
    console.log("up: FAILED — frontend did not come up. Log:", frontendLog);
    throw new Error("frontend failed to start");
  }
  console.log("up: frontend ready.");

  fs.writeFileSync(
    STATE_FILE,
    JSON.stringify(
      {
        backendPid: backendChild.pid,
        frontendPid: frontendChild.pid,
        dbPath,
        dataDir,
        backendLog,
        frontendLog,
      },
      null,
      2,
    ),
  );
  console.log("up: done. backend log:", backendLog, "| frontend log:", frontendLog);
  return { reused: false };
}

async function down() {
  if (!fs.existsSync(STATE_FILE)) {
    // No record of anything we started — a healthy server on 8100/3100 is
    // the user's own dev server (scripts/dev.sh); never kill it blindly.
    console.log("down: nothing started by the driver — leaving any running servers alone.");
    return;
  }
  const state = JSON.parse(fs.readFileSync(STATE_FILE, "utf8"));
  fs.rmSync(STATE_FILE, { force: true });
  if (state.reused) {
    console.log("down: servers were already running before `up` — left untouched.");
    return;
  }
  for (const pid of [state.backendPid, state.frontendPid]) {
    try {
      process.kill(-pid, "SIGKILL"); // negative pid = whole process group
    } catch {
      try {
        process.kill(pid, "SIGKILL");
      } catch {}
    }
  }
  for (const p of [state.dbPath, state.dataDir]) {
    try {
      fs.rmSync(p, { recursive: true, force: true });
    } catch {}
  }
  // `npm run dev` spawns a detached `next-server` child that survives
  // killing the parent — sweep by port too, or the next `up` silently
  // lands on :3101 (see Gotchas). Only safe here: this state file proves
  // the driver itself started these servers.
  killPort(8100);
  killPort(3100);
  console.log("down: stopped.");
}

// --- browser REPL commands ---

function resolveWavFixture() {
  // Reuses backend's numpy/soundfile (already a project dependency) to
  // synthesize a short test wav rather than committing a binary fixture.
  const out = path.join(os.tmpdir(), "driver-fixture.wav");
  execSync(
    `uv run python -c "` +
      `import numpy as np, soundfile as sf; ` +
      `t = np.linspace(0, 6, 6*8000, endpoint=False); ` +
      `w = (0.2*np.sin(2*np.pi*300*t)).astype(np.float32); ` +
      `sf.write('${out}', w, 8000, subtype='PCM_16')"`,
    { cwd: BACKEND_DIR },
  );
  return out;
}

const COMMANDS = {
  async up() {
    await up();
  },

  async down() {
    await down();
  },

  async launch() {
    if (browser) return console.log("already launched");
    browser = await chromium.launch({ channel: "chrome", headless: true });
    page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
    console.log("launched (system Chrome via channel:chrome).");
  },

  async nav(p) {
    if (!page) return console.log("ERROR: launch first");
    await page.goto(FRONTEND_URL + (p || "/"), { waitUntil: "networkidle" });
    console.log("nav ->", page.url());
  },

  async ss(name) {
    if (!page) return console.log("ERROR: launch first");
    const f = path.join(SHOT_DIR, (name || `ss-${Date.now()}`) + ".png");
    await page.screenshot({ path: f, fullPage: true });
    console.log("screenshot:", f);
  },

  async click(sel) {
    if (!page) return console.log("ERROR: launch first");
    await page.locator(sel).first().click();
    console.log("click", sel, "-> OK");
  },

  async "click-text"(text) {
    if (!page) return console.log("ERROR: launch first");
    await page.getByText(text, { exact: false }).first().click();
    console.log("click-text", JSON.stringify(text), "-> OK");
  },

  async fill(rest) {
    if (!page) return console.log("ERROR: launch first");
    const sp = rest.indexOf(" ");
    const sel = sp === -1 ? rest : rest.slice(0, sp);
    const value = sp === -1 ? "" : rest.slice(sp + 1);
    await page.locator(sel).first().fill(value);
    console.log("fill", sel, "->", JSON.stringify(value));
  },

  async select(rest) {
    if (!page) return console.log("ERROR: launch first");
    const [sel, value] = rest.split(/\s+/);
    await page.locator(sel).first().selectOption(value);
    console.log("select", sel, "->", value);
  },

  async check(sel) {
    if (!page) return console.log("ERROR: launch first");
    await page.locator(sel).first().check();
    console.log("check", sel, "-> OK");
  },

  async wait(sel) {
    if (!page) return console.log("ERROR: launch first");
    try {
      await page.waitForSelector(sel, { timeout: 15_000 });
      console.log("found:", sel);
    } catch {
      console.log("TIMEOUT:", sel);
    }
  },

  // Playwright's setInputFiles()/filechooser interception silently no-ops
  // on this app's hidden <input type=file> under headless channel:chrome
  // (files.length stays 0, no error thrown) — see Gotchas. This dispatches
  // the same DragEvent+DataTransfer a real drag-and-drop produces, aimed
  // at the drop-zone element, which the app's onDrop handler picks up.
  async drop(rest) {
    if (!page) return console.log("ERROR: launch first");
    const sp = rest.indexOf(" ");
    const sel = sp === -1 ? rest : rest.slice(0, sp);
    const filePath = sp === -1 ? "" : rest.slice(sp + 1);
    const b64 = fs.readFileSync(filePath).toString("base64");
    const fileName = path.basename(filePath);
    await page.locator(sel).first().evaluate(
      (zone, { b64data, fileName }) => {
        const bin = atob(b64data);
        const bytes = new Uint8Array(bin.length);
        for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
        const file = new File([bytes], fileName, { type: "audio/wav" });
        const dt = new DataTransfer();
        dt.items.add(file);
        zone.dispatchEvent(new DragEvent("drop", { bubbles: true, cancelable: true, dataTransfer: dt }));
      },
      { b64data: b64, fileName },
    );
    console.log("drop", fileName, "-> ", sel);
  },

  async eval(expr) {
    if (!page) return console.log("ERROR: launch first");
    try {
      console.log(JSON.stringify(await page.evaluate(expr)));
    } catch (e) {
      console.log("ERROR:", e.message);
    }
  },

  async text(sel) {
    if (!page) return console.log("ERROR: launch first");
    console.log(
      await page.evaluate((s) => (s ? document.querySelector(s) : document.body)?.innerText ?? "(null)", sel || null),
    );
  },

  async smoke() {
    await runSmoke();
  },

  async quit() {
    if (browser) await browser.close().catch(() => {});
    browser = null;
    page = null;
  },

  help() {
    console.log("commands:", Object.keys(COMMANDS).join(", "));
  },
};

// --- scripted golden path: create project -> upload -> cut -> export -> dashboard ---

async function addLabelField(pg, { key, type, required, options }) {
  await pg.getByText("+ 라벨 필드 추가").click();
  const rows = pg.locator("div.rounded-md.border.border-border.p-2");
  const row = rows.last();
  await row.locator("input").first().fill(key);
  if (type !== "string") await row.locator("select").selectOption(type);
  if (required) await row.locator('input[type="checkbox"]').check();
  if (type === "enum" && options) await row.locator("input").last().fill(options.join(","));
}

async function runSmoke() {
  const { reused } = await up();
  if (reused) {
    console.log(
      "smoke: WARNING — reusing already-running servers; test data (project/upload) " +
        "will be written into THEIR database, not an isolated temp db.",
    );
  }
  if (!browser) await COMMANDS.launch();
  const pg = page;

  await pg.goto(FRONTEND_URL + "/projects", { waitUntil: "networkidle" });
  await pg.locator("form input").nth(0).fill("Driver Smoke Test");
  await pg.getByRole("button", { name: "🚗 Vehicle" }).click();
  await addLabelField(pg, { key: "distance_m", type: "number", required: true });
  await pg.getByRole("button", { name: "프로젝트 생성" }).click();
  await pg.waitForURL(/\/projects\/\d+$/);
  await pg.screenshot({ path: path.join(SHOT_DIR, "smoke_01_project_detail.png"), fullPage: true });

  await pg.goto(FRONTEND_URL + "/upload", { waitUntil: "networkidle" });
  await pg.locator("select").first().selectOption({ label: "Driver Smoke Test" });
  const wav = resolveWavFixture();
  const zone = pg.getByText("Drop files here").locator("..");
  const b64 = fs.readFileSync(wav).toString("base64");
  await zone.evaluate(
    (el, { b64data, fileName }) => {
      const bin = atob(b64data);
      const bytes = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
      const file = new File([bytes], fileName, { type: "audio/wav" });
      const dt = new DataTransfer();
      dt.items.add(file);
      el.dispatchEvent(new DragEvent("drop", { bubbles: true, cancelable: true, dataTransfer: dt }));
    },
    { b64data: b64, fileName: "smoke.wav" },
  );
  await pg.waitForSelector("text=smoke.wav");
  await pg.getByRole("button", { name: "업로드" }).click();
  await pg.waitForSelector("text=데이터셋으로 이동");
  await pg.screenshot({ path: path.join(SHOT_DIR, "smoke_02_upload_result.png"), fullPage: true });

  await pg.getByText("데이터셋으로 이동").click();
  await pg.waitForURL(/\/datasets\/\d+$/);
  // distance_m is a "number" field -> LabelValuesForm renders <input type="number">.
  await pg.locator('input[type="number"]').first().fill("10");
  await pg.getByRole("button", { name: "커팅 시작" }).click();
  await pg.waitForSelector("text=done", { timeout: 20_000 });
  await pg.waitForTimeout(1000);
  await pg.getByRole("button", { name: "CSV 내보내기" }).click();
  await pg.waitForSelector("text=다운로드", { timeout: 20_000 });
  await pg.screenshot({ path: path.join(SHOT_DIR, "smoke_03_dataset_after_export.png"), fullPage: true });

  await pg.goto(FRONTEND_URL + "/", { waitUntil: "networkidle" });
  await pg.waitForSelector("text=총 세그먼트 수");
  await pg.screenshot({ path: path.join(SHOT_DIR, "smoke_04_dashboard.png"), fullPage: true });

  console.log("SMOKE OK — screenshots in", SHOT_DIR);
}

// --- entry point: one-shot CLI or interactive REPL ---

const arg = process.argv[2];
if (arg === "up" || arg === "down") {
  (arg === "up" ? up() : down()).then(() => process.exit(0)).catch((e) => {
    console.error("FAILED:", e.message);
    process.exit(1);
  });
} else if (arg === "smoke") {
  runSmoke()
    .then(async () => {
      await COMMANDS.quit();
      await down();
      process.exit(0);
    })
    .catch(async (e) => {
      console.error("SMOKE FAILED:", e.message);
      await COMMANDS.quit().catch(() => {});
      await down().catch(() => {});
      process.exit(1);
    });
} else {
  await runRepl();
}

async function runCommandLine(line) {
  const [cmd, ...rest] = line.trim().split(/\s+/);
  if (!cmd) return;
  const fn = COMMANDS[cmd];
  if (!fn) {
    console.log("unknown:", cmd, "- try: help");
    return;
  }
  try {
    await fn(rest.join(" "));
  } catch (e) {
    console.log("ERROR:", e.message);
  }
}

async function runRepl() {
  if (!process.stdin.isTTY) {
    // Piped input (heredoc, or another process writing a script to our
    // stdin): readline's "close" event is not guaranteed to fire only
    // after every buffered "line" event has been emitted — in practice it
    // can fire as soon as the pipe EOFs, well before readline has parsed
    // the rest of the buffered lines. That raced our command queue and
    // silently dropped every command after the first (see Gotchas). Read
    // stdin to completion ourselves and run the lines in a plain
    // sequential loop instead — no event-ordering ambiguity possible.
    const chunks = [];
    for await (const chunk of process.stdin) chunks.push(chunk);
    const lines = Buffer.concat(chunks).toString("utf8").split("\n");
    for (const line of lines) {
      if (!line.trim()) continue;
      console.log("driver>", line);
      await runCommandLine(line);
      if (line.trim().split(/\s+/)[0] === "quit") break;
    }
    process.exit(0);
    return;
  }

  const rl = readline.createInterface({ input: process.stdin, output: process.stdout, prompt: "driver> " });
  rl.prompt();
  for await (const line of rl) {
    await runCommandLine(line);
    if (line.trim().split(/\s+/)[0] === "quit") break;
    rl.prompt();
  }
  await COMMANDS.quit();
  process.exit(0);
}
