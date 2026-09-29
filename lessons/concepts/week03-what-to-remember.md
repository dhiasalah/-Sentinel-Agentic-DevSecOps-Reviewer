# Week 3: what to remember (from zero)

## 🗺️ In plain words
In week 3 Sentinel went from "a tool you run by hand" to "a bot that reacts on its own when someone opens a PR".
To get there we needed four things: an **identity** for the bot (GitHub App), a way to **hear** GitHub (webhooks),
a way to **read the code safely** (installation token), and a way to **do slow work without making GitHub wait**
(Redis queue + worker). This page keeps the ideas you should remember, with everyday examples.

**What you'll see when it all works:** you push a commit, and 10–60 s later the worker terminal prints the security report.
Nobody typed a command.

---

## The whole week in one picture

```
You push to a PR
   │
   ▼
GitHub ──"PR #5 changed" + signature──► API              (3.2: is this really GitHub?)
                                         │ note: "scan PR #5 @ 1144551"
                                         ▼
                                       Redis to-do list    (3.4: remember the work)
                                         │
                                         ▼
                                       Worker             (3.4: do the slow work)
                                         │ asks GitHub for a 1-hour key   (3.1 + 3.3)
                                         │ downloads the code, scans it
                                         ▼
                                       Report in the logs (week 4: as a PR comment)
```

---

## 1. GitHub App = the bot's own identity (3.1)

**Remember:** a bot should **not** use *your* password or *your* token. It gets its own identity, with only the rights it needs.

**Everyday example:** a cleaning company working in an office building. They don't borrow the manager's badge (which opens
everything). The building gives them **their own badge** that opens only the floors they clean, only during working hours.

| Word | Plain meaning |
|---|---|
| **Private key** (`.pem`) | The company's official stamp. Kept in a safe, never sent anywhere. |
| **App JWT** | A letter stamped with it: "I am Sentinel", valid 10 min. Proves *who*, opens nothing. |
| **Installation** | The contract "user X let Sentinel into repos A and B". |
| **Installation token** | A key card for **one repo**, **read-only**, **1 hour**. This opens the code. |

**Security idea: least privilege.** Give the minimum. If the key card is stolen, the thief gets one repo, read-only, for less than an hour.
Compare that with a personal token, which is your whole account for months.

**Seen live:** our token request failed with **422** because the App had never actually been given "Contents: read".
GitHub **refuses to hand out more than the owner agreed to**. That's the rule protecting us.

---

## 2. Webhooks = GitHub calls *you* (3.2)

**Remember:** instead of asking GitHub every minute "anything new?" (**polling**), GitHub sends you a message when something happens (**push**).

**Everyday example:** instead of refreshing a delivery-tracking page all day, you get an SMS: *"Your package has arrived."*

**Signature (HMAC):** anyone on the internet can send a fake "PR opened" message to your API. So GitHub signs every message with a
secret only you both know, and you check the signature before trusting anything in it.
Like a wax seal on a letter: if the seal doesn't match, you throw the letter away.

**smee.io:** your laptop can't be reached from the internet, so smee acts as a relay. GitHub → smee → your laptop.

---

## 3. Clone safely (3.3)

**Remember:** code from a PR is **untrusted**. It could be written by an attacker.
- We download **one exact commit**, into a **temporary folder**, and **always delete it** after.
- The token is passed in a hidden way (an environment variable), **never in the URL**, so it never shows up in logs or saved files.
- Inputs like repo name and commit are checked with strict rules (regex) before they touch the `git` command.

---

## 4. Redis + worker: the big one (3.4)

### The problem
GitHub waits only **10 seconds** for your API to answer. A scan takes **10–60 seconds**. If the API tried to scan before answering,
GitHub would give up and mark the delivery as failed.

### The solution: split "taking the order" from "doing the work"

**Everyday example: a restaurant.**
- The **waiter** (= API) takes your order, writes it on a ticket, pins it on the kitchen rail, and says "coming soon!". That takes 10 seconds.
- The **ticket rail** (= Redis queue) holds the orders, in order.
- The **cook** (= worker) takes the next ticket, cooks (slow), then takes the next one.
- If the cook goes on a break, tickets **wait on the rail**; nothing is forgotten. If 20 customers arrive at once, the waiter still
  answers everyone fast; the tickets just pile up.

That's exactly what you saw live: the PR #5 job **sat in Redis while no worker was running**, then got scanned as soon as the worker started.

| Piece | Restaurant | Sentinel |
|---|---|---|
| API | waiter | `POST /webhooks/github`, replies `202` in milliseconds |
| Queue | ticket rail | Redis list `sentinel:jobs` |
| Job | ticket | `{"repo": ..., "pr": 5, "head_sha": ...}` |
| Worker | cook | `python -m sentinel.worker` → `scan_pr` |

### What is Redis, really?
A very fast storage that lives **in memory** (RAM). You put small things in, you get them out in about a millisecond.
It's used for: **queues** (our case), **caches** ("remember this answer for 5 minutes"), **counters** ("how many requests from this
IP?"), **sessions** ("this user is logged in").

### Real apps that work this way
| App | The fast part (answers you) | The slow part (worker, later) |
|---|---|---|
| **YouTube** | "Upload complete!" | Converting your video into 144p…4K |
| **Online shop** | "Order confirmed!" | Sending the email, the invoice PDF, telling the warehouse |
| **Instagram** | Your photo appears | Making thumbnails, checking for banned content |
| **Bank** | "Transfer requested" | Fraud checks, the real transfer |
| **"Forgot password"** | "Check your inbox" | Actually sending the email |
| **Sentinel** | `202 Accepted` to GitHub | Download code, Semgrep, LLM triage |

**Rule of thumb:** if a task is **slow**, **can fail and be retried**, or **the user doesn't need the result right now**, it goes to a
queue + worker.

### The three safety tricks we added
1. **No lost jobs (processing list).** When the cook takes a ticket, they don't throw it away; they pin it on "in progress". If the cook
   faints (crash / Ctrl+C), the ticket is still there, and on restart it goes back on the rail. → `BLMOVE` + `requeue_stale`.
2. **Dead-letter list.** A ticket that can't be cooked (bad order) goes to a "problems" box instead of blocking the kitchen or vanishing.
   → `sentinel:jobs:dead`.
3. **No double work / replay attacks.** If the same order arrives twice (GitHub redelivers, or an attacker re-sends a captured
   message), we recognise it by its fingerprint (hash of the body) and ignore it. → `SET ... NX`.
   We use the **body**, not the delivery-ID header, because the signature protects only the body: an attacker can change headers freely.

### Security bonus: separation
The waiter never holds the safe's key. The API (reachable from the internet) only knows the webhook secret. The worker holds the
powerful keys (GitHub private key, LLM keys) and **nobody can connect to it**. Break into the API and you still can't read code or spend
LLM credits.

---

## 5. Words to know

| Word | One-line meaning |
|---|---|
| Webhook | An HTTP message a service sends you when something happens |
| HMAC signature | Proof a message came from someone who knows the shared secret and wasn't modified |
| JWT | A signed, short-lived "ID card" |
| Least privilege | Give the minimum rights, for the minimum time |
| Queue | A to-do list: first in, first out |
| Worker | A background program that takes jobs from the queue and does them |
| Async processing | Answer now, do the work later |
| Dead-letter queue | Where failed jobs go to be inspected |
| Idempotent | Safe to do twice (scanning twice = fine; posting the same comment twice = annoying) |
| Replay attack | Re-sending a real, captured message to trigger the action again |

---

## Check yourself (answers below)
1. Why can't the API just run the scan itself before answering GitHub?
2. The worker is stopped and 3 PRs are opened. What happens?
3. Why do we de-duplicate on the body hash, not on `X-GitHub-Delivery`?

<details><summary>Answers</summary>

1. GitHub waits 10 s, and a scan takes up to 60 s. Also, the internet-facing API would have to hold all the secret keys.
2. 3 jobs wait in `sentinel:jobs`. When the worker starts, it scans them one by one, oldest first.
3. The signature covers only the body. An attacker can re-send a signed body with a new, made-up delivery ID.
</details>
