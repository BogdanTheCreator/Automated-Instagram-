# Auto-uploading to YouTube

This sets up hands-off uploads of your long-form Video Packs to **your own**
YouTube channel, running on GitHub's servers. It uses the official YouTube Data
API v3 — the same mechanism schedulers like TubeBuddy/Hootsuite use.

> **Read this first — the "private video" rule.** Until your Google API project
> passes a one-time **compliance audit**, every video uploaded through the API is
> **forced to Private** by YouTube and *cannot* be flipped to Public via the API.
> This is a YouTube policy, not a bug. Two honest options:
>
> 1. **Review-then-publish (recommended, works today):** let the workflow upload
>    as Private/Unlisted, then you open YouTube Studio, glance at it, and click
>    Public. ~10 seconds of human work, full quality control.
> 2. **Fully public auto-posting:** submit the
>    [YouTube API Audit form](https://support.google.com/youtube/contact/yt_api_form)
>    once. After approval, set `privacy: public` and it posts publicly unattended.

## One-time setup (~10 minutes)

### 1. Create a Google Cloud project + enable the API
1. Go to <https://console.cloud.google.com/> → create a project.
2. **APIs & Services → Library →** search **"YouTube Data API v3" → Enable**.

### 2. Create an OAuth client
1. **APIs & Services → OAuth consent screen:** choose **External**, fill the
   basics, and add your own Google account under **Test users**.
2. **APIs & Services → Credentials → Create credentials → OAuth client ID →**
   Application type: **Desktop app**. Copy the **Client ID** and **Client secret**.

### 3. Mint a refresh token (once, on your computer)
```bash
export YT_CLIENT_ID="...apps.googleusercontent.com"
export YT_CLIENT_SECRET="..."
python3 -m social.cli --youtube-auth
```
Open the printed URL, approve access, paste the code back. It prints a
**refresh token** — copy it.

### 4. Add GitHub secrets
**Repo → Settings → Secrets and variables → Actions → New repository secret:**

| Secret | Value |
|--------|-------|
| `YT_CLIENT_ID` | the OAuth client id |
| `YT_CLIENT_SECRET` | the OAuth client secret |
| `YT_REFRESH_TOKEN` | the token printed in step 3 |

Optional: `OPENAI_API_KEY` (richer scripts), `PEXELS_API_KEY` (better imagery).

## Run it
**Actions tab → "Upload to YouTube" → Run workflow.** Leave `privacy` as
`private` (or `unlisted`) until your API project is audited. The video is built,
rendered, and uploaded to your channel; the kit (script/SEO/thumbnail) is also
saved as a downloadable artifact.

To run weekly automatically, uncomment the `schedule:` block in
`.github/workflows/youtube-upload.yml`.

## Try it locally first
```bash
# build + render a pack, then dry-run the upload (no creds needed for dry run)
python3 -m social.cli --videopack --brand betrayal_revenge --render --out yt_out
python3 -m social.cli --youtube-upload --kit yt_out/<dated-folder> --dry-run
```

## Notes
- `videos.insert` costs ~100 quota units; the default 10,000/day quota allows
  plenty of uploads.
- The uploaded title/description/tags come straight from the pack's `seo.md`
  (`content_package.json`), so your SEO is applied automatically.
- The thumbnail (`thumbnail.jpg`) is in the artifact; setting a **custom**
  thumbnail via the API requires a verified channel, so apply it in YouTube
  Studio when you publish (or we can add `thumbnails.set` later).
