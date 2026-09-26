# Week 1 · Step 1.6 — Sign up for Oracle Cloud (and lock the account down)

## 🎯 Goal
Create a free Oracle Cloud account now, because approval can take hours or days, and **harden it** before
anything runs on it. In week 9 Terraform will create a server there, and k3s + ArgoCD will deploy Sentinel
on it. No code in this step: it's account setup and cloud-security basics.

## 🧰 Tools in this step

### Cloud provider (Oracle Cloud Infrastructure, "OCI")
- **What it is:** a company that rents you computers, networks and storage in its data centers, which you
  control from a website or an API. Analogy: renting an apartment instead of building a house. You pick
  the size, and the landlord handles the building, power and internet.
- **Problem it solves:** Sentinel must be online 24/7 to receive GitHub webhooks. Your laptop sleeps, changes
  networks and has no public address. A cloud server doesn't.
- **Why Oracle:** its **Always Free** tier is the most generous: an **ARM (Ampere A1)** server with
  several CPUs and **12–24 GB RAM** (Oracle has changed the exact limit over time; `sentinel-project.md`
  notes 2 OCPUs / 12 GB, so check the Always Free page below for today's numbers), plus 200 GB of disk,
  free with no time limit. That's enough to run a small Kubernetes
  cluster (k3s) with all of Sentinel on it. AWS, GCP and Azure free tiers are much smaller or expire after 12 months.
  [Always Free resources](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm)

### Key words you'll see in the console
- **Region**: a physical data-center location (e.g. Frankfurt, Paris, Marseille). Your **home region** is
  chosen at sign-up and **can never be changed**, and Always Free servers only live there.
- **Tenancy**: your whole account, like the building you rent.
- **Compartment**: a folder inside the tenancy that groups resources. Permissions and budgets can be set
  per compartment. Analogy: one room per project.
- **IAM (Identity and Access Management)**: who (users, groups) can do what (policies) on which
  compartment. You'll use it in week 9 to give Terraform limited rights instead of your admin login.
- **MFA (multi-factor authentication)**: login needs your password **plus** a code from your phone app.
  Someone who steals your password alone can't get in.
- **Budget alert**: an email when spending passes an amount you choose, as a safety net against surprise bills.

### How it fits later (week 9)
```
 your laptop ── terraform apply ──▶ OCI API ──▶ creates VM (Ampere A1, home region, compartment "sentinel")
                                                     │
 git push ──▶ GitHub Actions ──▶ image to GHCR       ▼
                                   ArgoCD on k3s (on that VM) pulls & deploys Sentinel
```

## 💻 Steps (browser)

### 1. Sign up
https://signup.cloud.oracle.com/
- Use your real name, address and a **credit/debit card**. It's only for identity verification: you may
  see a small temporary hold that's released, and a Free Tier account isn't charged unless you upgrade.
- **Home region:** pick one in Europe near you. Popular regions (e.g. Frankfurt) often have *"Out of
  capacity"* errors for free ARM servers. A less crowded one (e.g. Marseille, Madrid, Milan) usually gives
  fewer problems. Remember: **this choice is permanent**.
- Approval can be instant or take a few days. If it's rejected, trying a different card is the usual fix.

Expected: an email *"Your Oracle Cloud account is fully provisioned"*, and you can log in to https://cloud.oracle.com.

### 2. Turn on MFA (do this first, before anything else)
Console → profile icon (top right) → **My profile** → **Security** / **Multi-factor authentication** → enable,
then scan the QR code with an authenticator app (Google Authenticator, Microsoft Authenticator, Authy...).

Expected: the next login asks for a 6-digit code.

### 3. Create a compartment for the project
Console → ☰ → **Identity & Security** → **Compartments** → **Create compartment**
- Name: `sentinel` · Description: `Sentinel security agent` · Parent: your root compartment.

Everything Sentinel creates goes here, so it's easy to find, give permissions on and delete in one go.

### 4. Create a budget alert
Console → ☰ → **Billing & Cost Management** → **Budgets** → **Create budget**
- Target: compartment `sentinel` (or the root) · Monthly amount: `1` (the smallest amount) · Alert at **1%** actual spend → your email.

On a free account nothing should ever cost money, so *any* email from this budget means something is wrong.

### 5. Don't create a server yet
Resist clicking **Create instance**. In week 9 you'll create it with **Terraform** (infrastructure as code:
the server is described in a file, reviewed in git, and reproducible). A server made by hand in the console
can't be rebuilt the same way and has no history.

## 📚 Key concepts
- **Shared responsibility**: Oracle secures the buildings, hardware and hypervisor. **You** secure your account
  (MFA, IAM), your network rules and your server. Most cloud breaches are account/config mistakes, not
  provider hacks.
- **Least privilege, again:** your admin login is for humans in the console. Automation (Terraform, CI)
  will get its own limited identity in week 9, the same idea as `appuser` in lesson 03.

## 🔐 Security note
- A cloud account is a **high-value target**: stolen admin access = attackers run crypto-miners on your
  bill or use your servers to attack others. MFA is not optional.
- Never commit cloud credentials (API signing keys, `~/.oci/config`). The `.env` rules from step 1.5 apply,
  and in week 9 you'll add them to `.gitignore` before creating them.
- Oracle may reclaim Always Free servers that stay **idle** for a long time. Sentinel running on k3s will
  keep it busy enough, but that's why you don't create one now and leave it empty.

## ✅ Check it works
You can tell Claude (no screenshots of keys or card details needed):
1. The account is provisioned and you can log in.
2. The login asks for an MFA code.
3. Which **home region** you chose.
4. The `sentinel` compartment exists, and the budget alert is created.

## ➡️ Next step
**Week 2: your first agent.** Run Semgrep on a test repo, then have an LLM triage the findings.
Tell Claude **"I finished step 1.6"**. If Oracle approval is still pending, say so: you can start week 2
while waiting, since the server isn't needed until week 9.
