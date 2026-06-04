"""
youtube.py — upload a finished video to YOUR OWN YouTube channel via the
official YouTube Data API v3 (videos.insert), using only the Python standard
library (no google client libraries to install).

How it works
------------
The Data API uses OAuth 2.0. You authorize ONCE (locally, in a browser) to mint
a long-lived **refresh token**; after that, uploads run unattended by exchanging
that refresh token for short-lived access tokens. The three secrets the
automation needs are therefore:

    YT_CLIENT_ID       OAuth client id      (Google Cloud console)
    YT_CLIENT_SECRET   OAuth client secret  (Google Cloud console)
    YT_REFRESH_TOKEN   minted once via `python -m social.cli --youtube-auth`

Upload is a resumable upload: we POST the metadata + start a session, then PUT
the bytes. videos.insert costs ~100 quota units (default 10,000/day).

IMPORTANT — the "private video" rule
------------------------------------
Videos uploaded by an **unverified** API project are forced to *private* and
cannot be appealed; you must pass a one-time YouTube API compliance audit to
publish publicly. Until then this uploader defaults to `privacyStatus=private`
(or `unlisted` if you ask), which is actually a good fit for a review-then-
publish workflow: the video lands on your channel, you glance at it, and flip it
to Public in YouTube Studio. See:
https://developers.google.com/youtube/v3/docs/videos/insert

Everything here fails soft and returns a structured result; nothing raises.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Dict, List, Optional

OAUTH_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
OAUTH_TOKEN = "https://oauth2.googleapis.com/token"
UPLOAD_URL = ("https://www.googleapis.com/upload/youtube/v3/videos"
              "?uploadType=resumable&part=snippet,status")
# Full read/write access to the authenticated user's YouTube account.
SCOPE = "https://www.googleapis.com/auth/youtube.upload"
# "Out-of-band" / manual-copy redirect for headless one-time auth.
OOB_REDIRECT = "urn:ietf:wg:oauth:2.0:oob"


@dataclass
class UploadResult:
    ok: bool
    video_id: Optional[str] = None
    url: Optional[str] = None
    message: str = ""
    steps: List[str] = field(default_factory=list)

    def log(self, line: str) -> "UploadResult":
        self.steps.append(line)
        return self


def _http_json(url: str, data: Optional[bytes] = None,
               headers: Optional[Dict[str, str]] = None,
               method: Optional[str] = None, timeout: int = 60) -> Dict[str, object]:
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8")
        return json.loads(body) if body else {}


def _err(exc: urllib.error.HTTPError) -> str:
    try:
        body = json.loads(exc.read().decode("utf-8"))
        e = body.get("error", {})
        if isinstance(e, dict):
            return f"{e.get('code', exc.code)}: {e.get('message', '')}".strip()
        return f"{exc.code}: {body.get('error_description', e)}"
    except Exception:
        return f"HTTP {exc.code}"


# --------------------------------------------------------------------------- #
# One-time interactive auth: mint a refresh token
# --------------------------------------------------------------------------- #

def build_auth_url(client_id: str) -> str:
    params = {
        "client_id": client_id,
        "redirect_uri": OOB_REDIRECT,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",      # ask for a refresh token
        "prompt": "consent",           # force a refresh token even on re-auth
    }
    return OAUTH_AUTH + "?" + urllib.parse.urlencode(params)


def exchange_code_for_refresh_token(client_id: str, client_secret: str,
                                    code: str) -> Dict[str, object]:
    data = urllib.parse.urlencode({
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": OOB_REDIRECT,
        "grant_type": "authorization_code",
    }).encode("utf-8")
    try:
        return _http_json(OAUTH_TOKEN, data=data,
                          headers={"Content-Type": "application/x-www-form-urlencoded"},
                          method="POST")
    except urllib.error.HTTPError as exc:
        return {"error": _err(exc)}


def access_token_from_refresh(client_id: str, client_secret: str,
                              refresh_token: str) -> Optional[str]:
    """Exchange a refresh token for a short-lived access token (or None)."""
    data = urllib.parse.urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }).encode("utf-8")
    try:
        out = _http_json(OAUTH_TOKEN, data=data,
                         headers={"Content-Type": "application/x-www-form-urlencoded"},
                         method="POST")
        return str(out.get("access_token") or "") or None
    except urllib.error.HTTPError:
        return None


# --------------------------------------------------------------------------- #
# Upload
# --------------------------------------------------------------------------- #

class YouTubeUploader:
    def __init__(self, client_id: str, client_secret: str, refresh_token: str) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token

    def _access_token(self) -> Optional[str]:
        return access_token_from_refresh(self.client_id, self.client_secret,
                                         self.refresh_token)

    def upload(self, video_path: str, title: str, description: str,
               tags: Optional[List[str]] = None, category_id: str = "22",
               privacy_status: str = "private",
               made_for_kids: bool = False) -> UploadResult:
        """Resumable-upload a local video file. privacy_status is forced to a
        non-public value for unverified API projects (see module docstring)."""
        res = UploadResult(ok=False)
        if not os.path.exists(video_path):
            return res.log(f"video not found: {video_path}")
        if privacy_status not in ("private", "unlisted", "public"):
            privacy_status = "private"

        token = self._access_token()
        if not token:
            return res.log("could not obtain access token (check YT_CLIENT_ID/"
                           "YT_CLIENT_SECRET/YT_REFRESH_TOKEN)")
        res.log("access token obtained")

        # YouTube limits title<=100 chars and tags total length; keep it safe.
        meta = {
            "snippet": {
                "title": (title or "Untitled")[:100],
                "description": description or "",
                "tags": (tags or [])[:30],
                "categoryId": category_id,
            },
            "status": {
                "privacyStatus": privacy_status,
                "selfDeclaredMadeForKids": made_for_kids,
            },
        }
        meta_bytes = json.dumps(meta).encode("utf-8")
        size = os.path.getsize(video_path)

        # 1) start a resumable session
        try:
            req = urllib.request.Request(
                UPLOAD_URL, data=meta_bytes, method="POST",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json; charset=UTF-8",
                    "X-Upload-Content-Type": "video/*",
                    "X-Upload-Content-Length": str(size),
                },
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                session_url = resp.headers.get("Location")
        except urllib.error.HTTPError as exc:
            return res.log(f"failed to start upload session: {_err(exc)}")
        except (urllib.error.URLError, ValueError, TimeoutError) as exc:
            return res.log(f"failed to start upload session: {exc}")
        if not session_url:
            return res.log("no resumable session URL returned")
        res.log(f"resumable session started ({size} bytes)")

        # 2) upload the bytes in one PUT (files here are modest; simple + robust)
        try:
            with open(video_path, "rb") as fh:
                body = fh.read()
            put = urllib.request.Request(
                session_url, data=body, method="PUT",
                headers={"Content-Type": "video/*", "Content-Length": str(size)},
            )
            with urllib.request.urlopen(put, timeout=600) as resp:
                out = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return res.log(f"upload failed: {_err(exc)}")
        except (urllib.error.URLError, ValueError, TimeoutError) as exc:
            return res.log(f"upload failed: {exc}")

        vid = str(out.get("id", ""))
        if not vid:
            return res.log(f"no video id in response: {out}")
        res.ok = True
        res.video_id = vid
        res.url = f"https://youtu.be/{vid}"
        return res.log(f"uploaded! {res.url}  (privacy: {privacy_status})")
