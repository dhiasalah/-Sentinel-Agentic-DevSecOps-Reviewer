# Week 4 · Step 4.3 — Record the first demo GIF

## 🗺️ In plain words: what we're doing today

Sentinel works, but right now only you have seen it work. A recruiter opening your GitHub will give it **about 10 seconds**. Today we record
a **short silent animation (GIF)** of the whole story: someone opens a pull request with dangerous code, and a few seconds later Sentinel's
security report appears on it. We put that GIF at the top of the README. No new code today, just staging, recording, trimming and a
privacy check, because anything visible in a frame becomes public forever.

**Example:** at the end, the first thing people see on `github.com/dhiasalah/<repo>` is a ~20-second loop: PR diff with `shell=True` →
worker terminal printing `done, 2 issue(s)` → the PR conversation with the **Sentinel security report** comment.

## 🎯 Goal

`docs/demo/sentinel-pr-comment.gif` (under 5 MB) embedded at the top of `README.md`, plus an `.mp4` of the same recording (kept outside the repo) for LinkedIn in week 10.
This closes the **week 4 deliverable: "working bot on real PRs"**, with proof.

## 🧰 Tools in this step

- **ScreenToGif**: a free, open-source screen recorder *and* frame editor for Windows. Think of it as a camera plus scissors: you record,
  then delete the boring frames (waiting for the LLM) one by one. It solves "a 60-second real run is too long and too heavy to watch".
  Sentinel needs it for the README now and the LinkedIn post in week 10. [screentogif.com](https://www.screentogif.com/)
- **A demo PR in `sentinel-playground`**: a tiny, deliberately vulnerable change made for the camera, not the benchmark. The benchmark measures;
  the demo **shows**. Keep them separate so tuning one never affects the other.

```
browser: open PR ──► GitHub ──► smee ──► API :8000 ──► Redis ──► worker (scan + triage) ──► comment on PR
   ▲                                                                                               │
   └────────────────── ScreenToGif records this window region, you trim the waiting ◄──────────────┘
```

---

## 💻 Commands

### 1. Install ScreenToGif
```powershell
winget install --id NickeManarin.ScreenToGif -e
```
Expected: `Successfully installed`. (If `winget` asks to accept source terms, type `Y`.)

### 2. Prepare the demo PR (in the browser, before recording)
In `sentinel-playground` on GitHub: **Add file → Create new file**, name `app/tools.py`, paste:
```python
import subprocess

import requests
from flask import Flask, request

app = Flask(__name__)


@app.route("/ping")
def ping():
    host = request.args.get("host", "")
    return subprocess.check_output(f"ping -c 1 {host}", shell=True, text=True)


@app.route("/preview")
def preview():
    return requests.get(request.args["url"], timeout=5).text
```
Choose **"Create a new branch for this commit and start a pull request"**, branch name `demo/tools`, click **Propose changes**, but
**don't click "Create pull request" yet**. That click is the first scene of the GIF.
Two bugs that anyone understands in one glance (command injection, SSRF) make a comment short enough to read in a GIF. The benchmark's 15 bugs
would produce a wall of text.

### 3. Start the pipeline (4 terminals, from the repo root)
```powershell
# Terminal 1: API + Redis
docker compose up -d
curl.exe http://127.0.0.1:8000/ready
```
Expected: `{"status":"ready"}`
```powershell
# Terminal 2: smee forwarder (keep this one OFF camera: the channel URL is a secret-ish address)
npx smee-client --url https://smee.io/YOUR_CHANNEL --target http://127.0.0.1:8000/webhooks/github
```
Expected: `Connected`
```powershell
# Terminal 3: the worker (this one IS on camera)
cd agents; .\.venv\Scripts\Activate.ps1
python -m sentinel.worker
```
Expected: `worker ready, waiting for jobs on sentinel:jobs`
Before recording, do one **dry run** on an old PR (push an empty commit or Redeliver a delivery) to warm up Docker/Semgrep and check that
Gemini/Groq answer. A demo that crashes on camera wastes the take.

### 4. Arrange the screen
- Browser on the left ~60%, worker terminal on the right ~40%, both inside a **1280×720** area (ScreenToGif shows the size while you drag).
- Terminal font size ~16, dark theme, window cleared (`cls`) right before recording.
- Browser: close other tabs, hide the bookmarks bar (`Ctrl+Shift+B`), zoom 110–125% so code is readable in a small GIF.

---

## 🎬 Storyboard (target 15–25 s after trimming)

| # | On screen | Real time | Keep in GIF |
|---|---|---|---|
| 1 | PR page: title "Add network tools", click **Create pull request** | 3 s | 3 s |
| 2 | Files changed: the `shell=True` line and the `requests.get(...)` line | 3 s | 3 s |
| 3 | Worker terminal: `scanning ...#N`, then `done, 2 issue(s)`, then `report comment created` | 30–60 s | **~4 s** (delete the waiting frames) |
| 4 | Back to **Conversation**, refresh: Sentinel's comment appears, scroll slowly through it | 8 s | 8 s |
| 5 | Hold the final frame (the comment) | — | 2 s (set a long delay on the last frame) |

Recording: ScreenToGif → **Recorder** → drag the frame over your 1280×720 area → **15 fps** → `F7` start/pause, `F8` stop.
**Pause (`F7`) while the worker is waiting** instead of recording 60 s of nothing. That's easier than deleting 800 frames later.

Editing (ScreenToGif **Editor**):
- Delete dead frames: select a range → `Delete`.
- **Edit → Reduce frame count** (keep 1 of every 2) if the file is big.
- Optional title card: **Image → Title frame**, e.g. *"Sentinel: AI security review on every PR"*.
- Last frame: right-click → **Override delay** → 2000 ms.

Export:
- **File → Save as → Gif**, encoder **ScreenToGif (2.0)** or **FFmpeg**, `Looped`, save as `docs\demo\sentinel-pr-comment.gif`.
- Also **Save as → Video (mp4)** into `Videos\`, **outside the repo**, for LinkedIn (week 10). Videos are ~10× smaller and sharper than GIFs.

---

## 🧩 Code, piece by piece

### 1. Put the GIF at the top of the README
**Where:** `README.md`, right under the first paragraph (the one ending "...posts a security report as a comment on the PR.")
```markdown
![Sentinel reviewing a pull request: the PR adds shell=True and an unchecked requests.get, and Sentinel posts a security report comment](docs/demo/sentinel-pr-comment.gif)
```
A relative path works on GitHub and in any clone, and doesn't depend on an external host that can disappear. The alt text isn't decoration:
it's what screen readers read and what shows if the image fails. So it says **what happens**, not "demo gif".

---

## 📚 Key concepts
- **Show, don't claim**: "working bot on real PRs" is a claim; a 20 s loop of a real PR is evidence. Pair it with the benchmark number from
  4.2 (evidence of *how well*).
- **Demo ≠ benchmark**: the demo is picked to be clear (2 obvious bugs). The benchmark is picked to be fair (hard cases + decoys). Never present
  the demo as the accuracy.
- **Binary files in git are forever**: every version of a GIF stays in history and in every clone. Commit it once, keep it small (< 5 MB),
  and replace it rarely (e.g. week 10). Larger media belongs in releases or Git LFS.

## 🔐 Security note: redaction checklist (check every frame before saving)
A published GIF is like a public screenshot: it gets cached, forked and indexed, and deleting the file later doesn't remove it from git history.
- ❌ No `.env`, `.pem` path contents, API keys, or `ghs_...` / `eyJ...` tokens anywhere (editor tabs, terminal scrollback).
- ❌ No **smee channel URL**. Anyone who has it can read your webhook payloads and try replays (your HMAC + de-dup stop the replays, but don't advertise the address).
- ❌ No personal tabs, email, GitHub notification counts, other repos' names, or the taskbar clock/Wi-Fi name if you don't want them public.
- ✅ OK to show: repo name, PR number, installation-free logs (`scanning dhiasalah/sentinel-playground#N @ abc1234`), the commit SHA.
- The playground code is deliberately vulnerable: fine to show, **never deploy it**.

## ✅ Check it works
```powershell
Get-Item docs\demo\sentinel-pr-comment.gif | Select-Object Name, @{n="MB";e={[math]::Round($_.Length/1MB,2)}}
```
Expected: one line with `MB` **under 5**.

Then preview the README locally in VS Code (`Ctrl+Shift+V` on `README.md`): the GIF plays at the top.

Commit and push:
```powershell
git add docs/demo/sentinel-pr-comment.gif README.md
git commit -m "docs: demo GIF of Sentinel reviewing a real PR"
git push
```
Open your repo on GitHub: the GIF loops at the top of the README.

**Worth thinking about:** the demo PR is one you wrote *knowing* Sentinel catches it. What would a sceptical reviewer ask after watching it, and
which number from 4.2 answers them?

## ➡️ Next step
Week 4 done 🎉. Week 5: move the pipeline into LangGraph and add Trivy, gitleaks and Checkov as MCP servers, the three scanners
whose absence the benchmark already measured (V04, V14, V15).
Tell Claude "I finished step 4.3, please review" and share the repo link or the GIF size.
