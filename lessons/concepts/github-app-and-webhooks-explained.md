# GitHub App + webhooks, explained from zero (lessons 3.1 and 3.2)

Read this slowly, one part at a time. No new words without an explanation.
One story runs through the whole page: **Sentinel is a cleaning company, and GitHub is a big office building.**

---

## Part 1: What were we trying to do?

In week 2, Sentinel only worked when **you** typed `python -m sentinel scan ...` on your laptop.

The goal of week 3: when **anyone** opens a Pull Request, Sentinel wakes up **by itself**, scans the code, and (week 4) writes a comment.

For that, three questions must be answered:
1. **Who is Sentinel on GitHub?** It needs an identity. → *3.1: the GitHub App*
2. **How does Sentinel know a PR was opened?** Someone must tell it. → *3.1 + 3.2: webhooks*
3. **How does Sentinel know the message is real?** Anyone could lie. → *3.2: the signature (HMAC)*

---

## Part 2: The GitHub App = the cleaning company's badge (3.1)

### Why not just use your password?
You could give Sentinel your GitHub password (or a "Personal Access Token", which is almost the same thing).
But then Sentinel **is you**: it can delete any of your repos, on every project, forever.
If Sentinel gets hacked, the attacker is you.

**Analogy:** giving the cleaner **your own house keys**, for every house you own, with no end date.

### What a GitHub App is instead
A GitHub App is a **separate robot account** with a **badge**. The badge says exactly:
- **which doors it can open** = *permissions*. You ticked only:
  - `Contents: Read`: it can *read* code (to scan it)
  - `Pull requests: Read and write`: it can *comment* on PRs (week 4)
  - everything else: **No access**
- **which buildings it can enter** = *installations*. You installed it on `sentinel-playground` only.

That's **least privilege**: give only what is needed, nothing more.

### What you actually clicked
| You did | In the story |
|---|---|
| Created the app `sentinel-dhia` | Registered the cleaning company |
| Ticked permissions | Wrote on the badge which doors it may open |
| Installed it on `sentinel-playground` | Signed a contract with one client |
| Downloaded the `.pem` file | Received the company's **master stamp** |
| Got the **App ID** | The company's registration number |

---

## Part 3: The `.pem` key and the JWT = the company stamp (3.1)

### The `.pem` file
It's a **private key**: a secret file only you have. GitHub has the matching **public key**.
- Private key = a **stamp** only you own.
- Public key = a **photo of the stamp** that GitHub keeps, so it can check your stamp marks.

GitHub can *check* your stamp but can't *make* it. So even if GitHub were hacked, nobody could copy your stamp.
This is called **asymmetric** keys: two different halves, one secret, one public.

**That's why** we put it in `C:\Users\USER\.sentinel\` (outside the project) and added `*.pem` to `.gitignore`.
Your repo is public: if the `.pem` got committed, anyone could act as your app.

### The JWT (the stamped note)
You never send the `.pem` itself to GitHub. Instead, your code writes a tiny note and stamps it:

> "I am app **sentinel-dhia**. This note is valid for **9 minutes**." 🔏 *(stamped with the .pem)*

That stamped note is a **JWT** (JSON Web Token). GitHub looks at the stamp, compares it with the photo it has, and says "OK, it's really you."

Why only 9 minutes? If someone steals the note, it's useless very quickly.

### Your bug in 3.1 (a good lesson)
Your `.env` still had `GITHUB_APP_ID=123456` (the example). So your note said "I am app 123456",
GitHub compared your stamp with **app 123456's** photo, and they didn't match. → `401`.
Changing it to your real App ID fixed it. **The check works exactly as designed.**

### What the test `get_app_info` proved
Calling `GET /app` with your JWT returned `sentinel-dhia`. Translation: *"GitHub recognises your stamp."*

---

## Part 4: Master key vs room key (3.1, used in 3.3)

The JWT alone can do almost nothing. It can only say "I'm the company, give me a **room key** for contract #X".

| | Master key (JWT from `.pem`) | Room key (installation token) |
|---|---|---|
| Lives | 9 minutes (the note), but the `.pem` stamp lives **forever** | **1 hour** |
| Opens | nothing directly, only "give me a room key" | the repos of **one** installation |
| If stolen | attacker makes room keys for **every** client | attacker gets **one** client for **≤ 1 hour** |

The **installation_id** (yours: `165735765`) is the **contract number**. It tells GitHub *which client* the room key is for.
You don't look it up: **GitHub writes it in every webhook**.

---

## Part 5: Webhooks = the doorbell (3.1)

### Two ways to know something happened
- **Polling**: you phone the building every minute: "anything new? anything new?" Slow and wasteful.
- **Webhook**: the building **rings your doorbell** when something happens. Instant.

A webhook is just GitHub doing an **HTTP POST** (sending a message) to an address you chose, with details inside:
```
POST <your address>
X-GitHub-Event: pull_request             ← what kind of event
X-GitHub-Delivery: e4172860-...          ← unique id of this message
X-Hub-Signature-256: sha256=9ab3...      ← the seal (Part 7)

{ "action": "opened", "pull_request": { "number": 4, "head": { "sha": "eb4bc40..." } },
  "repository": { "full_name": "dhiasalah/sentinel-playground" }, "installation": { "id": 165735765 } }
```

In 3.1 you opened a PR and **saw this message appear on smee.io**: the doorbell rang.

---

## Part 6: smee = the PO box (3.1 + 3.2)

Your API runs at `127.0.0.1:8000`, which means "this same computer". GitHub can't ring a doorbell on your laptop:
- `127.0.0.1` from GitHub's side means *GitHub's own server*;
- your home router blocks visitors from the internet.

smee.io gives you a **public PO box**. GitHub drops the letter there. The **smee client** on your laptop goes out,
collects the letter, and carries it to your API. Going *out* is allowed; only strangers coming *in* are blocked.

```
GitHub ──► smee.io (public PO box) ◄── smee-client (your laptop) ──► your API :8000
```
Your first try in 3.2 showed nothing because the smee client **wasn't running**: letters were waiting in the PO box with nobody to carry them.

In week 9 Sentinel lives on a real server with a public address, and smee disappears.

---

## Part 7: The seal (HMAC) = "is this letter really from GitHub?" (3.2)

### The danger
The PO box is **public**. Anyone can drop a fake letter: *"PR opened, go scan `evil/repo`!"*
Without a check, Sentinel would believe it: wasted AI money, scanning attacker code, etc.

### The fix: a shared secret + a seal
In 3.1 you generated a **webhook secret** (64 random characters) and gave it to **GitHub and to your `.env`**. Nobody else has it.

For every letter, GitHub computes:
```
seal = HMAC(secret, letter)   →   "sha256=9ab3..."
```
HMAC is a **blender**: put the secret + the exact letter in, get a fingerprint out.
- Same secret + same letter → **always the same** fingerprint.
- Change **one comma** in the letter → **completely different** fingerprint.
- Without the secret → you **can't** produce the right fingerprint.

Your API does the same blend with its copy of the secret and compares:

| Situation | Your API computes | Result |
|---|---|---|
| Real letter from GitHub | same fingerprint | ✅ `202 Accepted` |
| Fake letter, no seal | nothing to compare | ❌ `401` |
| Fake letter, made-up seal | different fingerprint | ❌ `401` |
| Real letter, attacker changed PR number | different fingerprint | ❌ `401` |

Those four rows are **exactly your 4 attack tests** in `test_webhooks.py`.

### HMAC vs JWT: two different stamps
- **JWT (3.1)**: *you* prove who you are *to GitHub*. Two different keys (private + public).
- **HMAC (3.2)**: *GitHub* proves who it is *to you*. **One shared** secret, both sides have the same copy (**symmetric**).

---

## Part 8: Small details in your code, and why they matter (3.2)

| Code | Plain words | Why |
|---|---|---|
| `body = await request.body()` then check, **then** `json.loads` | Check the seal **before** opening the envelope | Don't touch a stranger's letter until you know who sent it. And the seal is on the exact bytes: re-formatting would break it |
| `hmac.compare_digest(...)` instead of `==` | Compare in always the same time | `==` stops at the first wrong character. A hacker could time it and guess the seal letter by letter (**timing attack**) |
| `if not secret: return False` | Empty secret = refuse everything | An empty secret is a key **everyone** has. "Fail closed" = when in doubt, say no |
| `detail="invalid signature"` | Vague error | Don't tell an attacker *which* part was wrong |
| Only `opened` / `synchronize` / `reopened` | Only react when the **code** changes | A title edit or a new label doesn't need a new scan |
| Return `202` fast | "Got it, I'll do it later" | GitHub waits max **10 seconds**. A scan takes longer → a queue does the work (3.4) |
| Log only repo, PR number, SHA, ids | Don't log the PR title | The PR author writes the title. It could contain fake log lines or tricks for the AI |

---

## Part 9: The risk still open: replay

The seal proves "GitHub sent this", but **not when**. Since your smee channel is public, someone can
**copy a real sealed letter and drop it again 100 times**. The seal is still valid → 100 scans → your AI quota burns.

Fix in 3.4: remember each `X-GitHub-Delivery` id in Redis. Seen it already? Ignore it.

---

## Part 10: The whole picture on one screen

```
                     3.1                                   3.2                               3.3 / 3.4 (next)
 you open a PR ──► GitHub ──letter + seal──► smee.io ──► smee-client ──► API checks seal ──► queue ──► worker
                                                                          ✅ 202 / ❌ 401                 │
                                                                                                        │
       GitHub ◄── "give me a room key for contract 165735765" ── JWT (stamped with .pem) ◄──────────────┘
          └──► room key (1 h, read-only, 1 repo) ──► download commit eb4bc40 ──► Semgrep + AI ──► (week 4) PR comment
```

## Mini glossary
| Word | One-line meaning |
|---|---|
| GitHub App | A robot account with a limited badge |
| Installation / `installation_id` | One contract between your app and one account (yours: `165735765`) |
| `.pem` private key | The master stamp. Keep outside the repo, never share |
| JWT | A short note stamped with the `.pem`: "I am app X, valid 9 min" |
| Installation token | A 1-hour room key for one installation |
| Webhook | GitHub rings your doorbell with an HTTP POST |
| smee.io | A public PO box that forwards GitHub's letters to your laptop |
| Webhook secret | A password shared by GitHub and you, used to seal letters |
| HMAC | The "blender" that makes a seal from secret + letter |
| `401` / `202` | "Who are you? Rejected" / "Accepted, will do later" |
