# Auto-posting to Instagram — setup guide

This makes your account post **by itself on a schedule**, running entirely on
GitHub's servers. **You do not need Python, Node, or anything installed on your
computer.** You only fill in a few settings once.

There are two routes. Pick the one that fits you.

---

## Route 1 — Fully automated (this repo's workflow)

Instagram only allows automatic posting through its official **Graph API**, which
needs a few one-time things. Every serious scheduler (Buffer, Later, Hootsuite)
relies on the exact same API — they just hide the setup behind their own UI.

### What you need first
1. An Instagram **Business** or **Creator** account (free — switch in the IG app:
   Settings → Account type and tools → Switch to professional account).
2. A **Facebook Page** linked to that Instagram account (free to create).
3. Your **GitHub repo set to Public** (Settings → General → Danger Zone →
   Change visibility). This is required so Instagram can fetch the video file.

### Step A — Get your two credentials
You need an `IG_USER_ID` and an `IG_ACCESS_TOKEN`.

The quickest path uses Meta's **Graph API Explorer**:
1. Go to [developers.facebook.com](https://developers.facebook.com/) and create a
   free app (type: *Business*).
2. Open the **Graph API Explorer**, select your app, and click *Generate Access
   Token*. When prompted, grant these permissions:
   `instagram_basic`, `instagram_content_publish`, `pages_show_list`,
   `pages_read_engagement`, `business_management`.
3. Exchange it for a **long-lived token** (short ones expire in ~1 hour) using
   Meta's [Access Token Tool](https://developers.facebook.com/tools/debug/accesstoken/)
   — long-lived user tokens last ~60 days.
4. Find your **Instagram Business account id**: in the Graph API Explorer run
   `me/accounts` to get your Page id, then `{page-id}?fields=instagram_business_account`.
   The number it returns is your `IG_USER_ID`.

> This part is genuinely the fiddly bit — it's Meta's process, not ours. Take it
> slow; you only do it once (then once every ~60 days to refresh the token).

### Step B — Add them to GitHub (a simple form, no code)
In your repository on GitHub:
1. **Settings → Secrets and variables → Actions → New repository secret.**
2. Add:
   - `IG_USER_ID` = the number from Step A
   - `IG_ACCESS_TOKEN` = your long-lived token
   - `OPENAI_API_KEY` = *(optional)* for AI-written scripts
3. *(Optional)* Under the **Variables** tab add `BRAND` =
   `ai_income` / `privacy` / `money` / `longevity`.

### Step C — Turn it on and test safely
1. Go to the **Actions** tab → enable workflows if prompted.
2. Click **Auto-post to Instagram → Run workflow**. Leave *Dry run* = **true** the
   first time: it will render the video and show exactly what it *would* post,
   without posting. Download the result from the run's *Artifacts*.
3. Happy with it? Run again with *Dry run* = **false** to post for real, or just
   wait — it runs automatically every day at 13:00 UTC (change the `cron` line in
   `.github/workflows/autopost.yml`).

That's it. From then on it posts on its own.

### Step D (optional) — make the token never expire
Long-lived tokens last ~60 days. To refresh automatically so you never touch it
again, add three more secrets:
- `IG_APP_ID` and `IG_APP_SECRET` — from your Meta app → **Settings → Basic**.
- `GH_PAT` — a GitHub [Personal Access Token](https://github.com/settings/tokens)
  with permission to write Actions **Secrets** on this repo (fine-grained token:
  *Repository → Secrets → Read and write*).

With those set, every daily run refreshes the token and saves it back, resetting
the 60-day clock. Leave them out and you'll just re-paste the token every couple
of months — your choice.

> **Covers:** each post also gets a branded cover image for your profile grid. If
> you add `OPENAI_API_KEY`, the cover uses AI-generated background art; otherwise
> it's a clean branded gradient. No setup needed either way.

---

## Route 2 — No API at all (simplest, semi-automated)

If the Meta setup feels like too much right now, skip the API entirely:

1. Generate a month of content (the Colab notebook produces a zip of MP4s +
   captions — see the README).
2. Open **Meta Business Suite** (free, official: business.facebook.com) →
   **Planner** → upload each Reel, paste the caption from `post.md`, and pick a
   date/time. It will publish them for you on schedule.

This is "set it and forget it" without any tokens — you just do the uploads once
a month. Tools like **Buffer** or **Later** work the same way with a friendlier
calendar if you prefer.

---

## Good to know
- **Rate limit:** Instagram allows ~25 API posts per 24 hours — plenty for daily.
- **Token expiry:** long-lived tokens last ~60 days; refresh in the Access Token
  Tool and update the `IG_ACCESS_TOKEN` secret.
- **This posts YOUR content to YOUR account.** It does not buy followers, fake
  engagement, or touch anyone else — it's the same mechanism as any scheduler.
- **Check it ran:** the Actions tab shows each run's log and a downloadable copy
  of the day's content kit.
