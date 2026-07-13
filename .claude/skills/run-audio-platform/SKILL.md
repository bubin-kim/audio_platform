---
name: run-audio-platform
description: Build, run, and browser-drive the Audio Dataset Platform (FastAPI backend + Next.js frontend). Use when asked to start the app, run the backend or frontend, take a screenshot of the UI, or click through a user flow (create project, upload, cut, export).
---

This is a two-process web app (FastAPI backend on :8100, Next.js frontend
on :3100). `chromium-cli` is not installed in this environment, so drive it
with the Playwright REPL at `.claude/skills/run-audio-platform/driver.mjs`
— it manages both dev servers (`up`/`down`) and drives the system-installed
Google Chrome headlessly (`launch`, `nav`, `click`, `ss`, ...). A scripted
`smoke` command runs the whole golden path (create project → upload → cut →
export → dashboard) and screenshots each step.

All paths below are relative to the repo root (`audio_platform/`).

## Prerequisites

Already on this machine: `uv` (backend), `npm`/Node 18+ (frontend), and
Google Chrome.app. Nothing else to install at the OS level.

## Setup

```bash
cd .claude/skills/run-audio-platform
npm install   # installs Playwright's JS package into the skill dir only —
               # does NOT touch backend/ or frontend/'s own dependencies.
               # Uses the already-installed Chrome via channel:"chrome",
               # so this does not download a Chromium binary.
```

## Run (agent path)

One-shot golden-path smoke test — starts both servers on an isolated temp
SQLite DB, clicks through create-project → upload → cut → export →
dashboard, screenshots each step, tears everything down:

```bash
cd .claude/skills/run-audio-platform
node driver.mjs smoke
```

Screenshots land in `.claude/skills/run-audio-platform/screenshots/`.

**스크린샷 보존 규칙 (사용자 확정, 2026-07-13, N=20):** `smoke_01`~`smoke_04`는
파일명이 고정이라 재실행 시 덮어쓰므로 정리 대상이 아니다. 수동 REPL로 찍은
스크린샷(`sil_*`, `feat_*` 등 임의 이름)만 **최근 20개를 유지**한다 — 새 스크린샷을
찍은 뒤 수동분이 20개를 넘으면 오래된 것부터 지운다:

```bash
cd .claude/skills/run-audio-platform
ls -t screenshots/*.png | grep -v '/smoke_0[1-4]_' | tail -n +21 | xargs rm --
```

(macOS BSD xargs는 입력이 비면 rm을 실행하지 않으므로 20개 이하일 때도 안전하다.)

For anything beyond the golden path (a specific page, a specific form,
checking a bugfix), drive it interactively. Piped input works — each line
runs to completion before the next starts:

```bash
cd .claude/skills/run-audio-platform
cat <<'EOF' | node driver.mjs
up
launch
nav /projects
wait text=새 프로젝트
ss projects-page
quit
EOF
node driver.mjs down   # always stop the servers when you're done exploring
```

### Commands

| command | what it does |
|---|---|
| `up` | start backend (isolated temp SQLite db) + frontend, wait until both respond. If both are ALREADY responding (e.g. `scripts/dev.sh`), it reuses them and records that fact |
| `down` | stop what `up` started, sweep ports 8100/3100, delete the temp db. Servers that were merely *reused* (or never started by the driver) are left running — it will never kill the user's own dev servers |
| `launch` | launch headless Chrome (`channel: "chrome"`) + a page |
| `nav <path>` | go to `http://localhost:3100<path>` |
| `ss [name]` | full-page screenshot → `screenshots/<name>.png` |
| `click <css-selector>` | click the first match |
| `click-text <text>` | click the first element containing this text |
| `fill <selector> <value>` | fill a text/number input |
| `select <selector> <value>` | choose a `<select>` option by value |
| `check <selector>` | check a checkbox |
| `wait <selector>` | wait up to 15s for a selector (`text=...` works too) |
| `drop <selector> <file>` | simulate dropping a file onto a drop-zone element — see Gotchas, this is NOT the same as file-input upload |
| `eval <js>` | `page.evaluate(js)`, prints the JSON result |
| `text [selector]` | print `innerText` (whole page if no selector) |
| `smoke` | run the full scripted golden path (see below) |
| `quit` | close the browser (does not stop the servers — run `down` too) |

`node driver.mjs up` / `down` also work as one-shot shell commands (no REPL).

## Run (human path)

```bash
./scripts/dev.sh   # one terminal: backend :8100 (--reload) + frontend :3100 (HMR), Ctrl-C stops both
# open http://localhost:3100
```

Both servers hot-reload on save (uvicorn `--reload`, `next dev`). Uses your
normal local `backend/audio_platform.db` and `data/`, unlike the driver's
`up`, which is isolated per run. Equivalent manual form:

```bash
cd backend && uv run alembic upgrade head && uv run uvicorn app.main:app --reload --port 8100
cd frontend && npm run dev   # separate terminal
```

Note: running `smoke` while dev.sh servers are up reuses them — the smoke
test's project/upload data lands in your real dev db (it warns about this).

## Test

```bash
cd backend && uv run pytest -q     # 전부 통과해야 정상 (개수는 계속 늘어난다)
cd frontend && npm run build       # type-checks + builds
```

---

## Gotchas

- **`page.setInputFiles()` looked like it silently no-op'd here — the real
  cause was an app bug, since fixed.** `UploadForm.tsx`'s onChange passed
  the *live* `FileList` into a deferred React state updater, then reset
  `input.value = ""` — emptying the FileList before the updater read it.
  So every Browse-Files-path injection (setInputFiles, filechooser
  intercept, manual change dispatch) appeared to "not work" with `.files`
  at length 0 and no error. Fixed by snapshotting `Array.from(files)`
  synchronously in `addFiles()`. The driver's `drop` command (synthetic
  `DragEvent` + `DataTransfer` at the drop zone) was never affected and
  remains the verified upload path; setInputFiles should work now too,
  but `drop` is what the smoke test exercises.

- **`execSync(..., { stdio: "inherit" })` inside the driver will silently
  kill a piped REPL script.** The alembic migration call used to inherit
  stdio; since the driver's own stdin is the piped heredoc, the child
  process shared (and disturbed) fd 0, and every command after `up` in a
  piped script got dropped with no error. Fixed by piping the child's
  stdio instead of inheriting it — don't reintroduce `stdio: "inherit"`
  for any child process spawned while a script might be piped to the
  driver's stdin.

- **readline's `"close"` event is not guaranteed to fire after all
  buffered `"line"` events have been emitted.** With a heredoc, this
  raced an event-based command queue and dropped every command after the
  first one queued. The driver instead reads all of stdin up front for
  non-TTY input and runs the lines in a plain sequential `for` loop —
  don't switch this back to an event-driven `rl.on("line", ...)` handler
  for the piped-input path without re-verifying against a multi-line
  heredoc.

- **A crashed/killed driver run leaves orphaned servers** (backend +
  frontend are spawned `detached` so they survive the driver process
  dying, e.g. from an agent's own command timeout). `up` sweeps ports
  8100/3100 before starting *when the servers aren't healthy*; `down`
  kills and sweeps *only when its state file proves the driver started
  them* — it deliberately never kills healthy servers it didn't start
  (those are the user's own dev servers, e.g. `scripts/dev.sh`). If an
  orphan half-lives on a port after a killed run and `down` declines to
  act, clear it manually: `lsof -i :3100 -sTCP:LISTEN -t | xargs kill`.

- **`node driver.mjs smoke` takes ~30-45s** (migrations + two dev-server
  cold starts + a full click-through). Give it a generous timeout if
  you're invoking it from something with its own timeout — a killed
  `smoke` run leaves the servers up (see previous point).

- **Don't run `npm run build` while a `next dev` server is running.** The
  production build rewrites `.next/` under the dev server's feet; pages
  then 500 intermittently with `Cannot find module './NNN.js'` (from
  `.next/server/webpack-runtime.js`). Fix: stop the dev server,
  `rm -rf frontend/.next`, start it again. If you need a type-check while
  dev servers are up, that's the safe moment to *not* have them up.

## Troubleshooting

- **Frontend "port 3100 in use, trying 3101":** a previous run's
  `next-server` child survived. Find and kill it:
  `lsof -i :3100 -sTCP:LISTEN -t | xargs kill`. (`down` only sweeps ports
  for servers the driver itself started.)
- **`smoke` fails at the "커팅 시작" step / `input[type="number"]` not
  found:** the smoke script's seed project defines `distance_m` as a
  `"number"` field, which renders `<input type="number">`, not `type=
  "text"`. If you change the smoke script's label schema, match the
  selector to the field's actual rendered input type.
- **`up` hangs on `waitForHttp`:** check the backend/frontend log paths
  printed by `up` (they're in `$TMPDIR`, not this directory).
