# Week 1 · Step 1.0 — Getting started: tools + repo structure

## 🎯 Goal of this step
Install the tools you need, check they work, turn this folder into a Git repository,
and create the empty folder structure of Sentinel (a **monorepo**).
No application code yet — this is the foundation everything else stands on.

## 📚 Concepts you need
- **Git** — a tool that records the history of your files (like "save points" in a game).
  Each save point is a **commit**. [Docs](https://git-scm.com/doc)
- **Python virtual environment (venv)** — a private box of Python packages for one project,
  so projects don't break each other. We'll use it in step 1.1. [Docs](https://docs.python.org/3/library/venv.html)
- **Docker** — packs an app and everything it needs into a **container**, a lightweight isolated
  box that runs the same on any machine. [Docs](https://docs.docker.com/get-started/)
- **Monorepo** — one Git repository that holds several parts of a project (frontend, API, agents...)
  instead of one repo per part. Easier to keep everything in sync for a solo project.

## 🧩 The code
Nothing to program yet — only commands. The target structure (from `sentinel-project.md`, section 7):

```
personal_project/
├── apps/web/          # Next.js dashboard       (week 7)
├── apps/api/          # FastAPI gateway         (week 1)
├── agents/            # LangGraph graphs        (week 5)
├── mcp-servers/       # scanner wrappers        (week 5)
├── sandbox/           # sandbox runner image    (week 6)
├── evals/             # test repos + attacks    (week 4, 10)
├── infra/terraform/   # Oracle VM provisioning  (week 9)
└── deploy/helm/       # Helm charts for ArgoCD  (week 9)
```

Git does **not** track empty folders. The usual trick is to put an empty file called
`.gitkeep` in each one so Git has something to save.

## ✍️ Your TODOs
1. **Install** (skip what you already have):
   - Git — https://git-scm.com/download/win
   - Python **3.12** — https://www.python.org/downloads/ (tick *"Add python.exe to PATH"*)
   - Docker Desktop — https://www.docker.com/products/docker-desktop/ (needs WSL 2 on Windows; the installer guides you)
   - VS Code — https://code.visualstudio.com/ (+ the *Python* extension)
2. **Configure Git** with your name and email (once per machine):
   ```bash
   git config --global user.name "Your Name"
   git config --global user.email "you@example.com"
   ```
3. **Turn this folder into a repo** — open a terminal in `personal_project/` and run `git init`.
4. **Create the folders** above, each with a `.gitkeep` file inside.
   - TODO(student): find the command for your shell. Hint: in Git Bash, `mkdir -p` creates nested
     folders and `touch` creates an empty file. Try doing it for `apps/api` first, then the rest.
5. **First commit** — add everything and commit with a clear message, e.g.
   `chore: initial monorepo structure and tutorial files`.
   - TODO(student): which two git commands do you need? (Hint: one *stages*, one *saves*.)

## ✅ How to check it works
```bash
git --version
python --version
docker --version
docker run hello-world
git log --oneline
```
Expected output (versions may differ slightly):
```
git version 2.4x.x
Python 3.12.x
Docker version 2x.x.x, build ...
Hello from Docker!  ...(more text)...
a1b2c3d chore: initial monorepo structure and tutorial files
```

## ⚠️ Common mistakes
- `python` opens the Microsoft Store → Python isn't on PATH. Reinstall with "Add to PATH" ticked, or disable the alias in *Settings → Apps → App execution aliases*.
- `docker run hello-world` fails → Docker Desktop isn't running yet (start it and wait for the whale icon to be steady).
- Running `git init` in the wrong folder (e.g. your Desktop). Check with `pwd` first.

## 🔐 Security note
From day one: **secrets (API keys, passwords) never go into Git.** Once committed, they stay in the
history even if you delete the file. In step 1.5 we'll set up a `.gitignore` and `.env` properly.

## 🤔 Check your understanding
1. Why do we need a `.gitkeep` file in empty folders?
2. What's the difference between `git add` and `git commit`?
3. In your own words: why would we run the API inside a Docker container instead of directly on Windows?

## ➡️ Next step
**1.1 — Python virtual environment + first FastAPI "hello world".**
When you're done, tell Claude: *"I finished step 1.0"* and paste the output of the check commands
plus your answers to the questions above.
