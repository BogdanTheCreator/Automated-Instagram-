"""
publisher.py — publish a Reel (or image) to YOUR OWN Instagram account via the
official Instagram Graph API.

This is the same mechanism legitimate schedulers (Buffer, Later, Meta's own
Business Suite) use: it posts your original content to your own Business/Creator
account. It does not touch followers, engagement, or anyone else's account.

The Graph API publishes video from a **public URL** in two steps:
    1. create a media container:  POST /{ig_user_id}/media
       (media_type=REELS, video_url=..., caption=...)
    2. poll the container until status_code == FINISHED
    3. publish it:                POST /{ig_user_id}/media_publish (creation_id)

Everything here uses only the Python standard library (urllib), so there is
nothing to install. All network calls fail soft and return a structured result.

Required credentials (set as environment variables / GitHub Secrets):
    IG_USER_ID        your Instagram *Business* account id (a number)
    IG_ACCESS_TOKEN   a long-lived access token with instagram_content_publish

See SETUP_AUTOPOST.md for how to obtain these with screenshots-level steps.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Dict, List, Optional

GRAPH = "https://graph.facebook.com"
DEFAULT_API_VERSION = "v21.0"


@dataclass
class PublishResult:
    ok: bool
    media_id: Optional[str] = None
    creation_id: Optional[str] = None
    message: str = ""
    steps: List[str] = field(default_factory=list)

    def log(self, line: str) -> "PublishResult":
        self.steps.append(line)
        return self


def _post(url: str, params: Dict[str, str], timeout: int = 60) -> Dict[str, object]:
    data = urllib.parse.urlencode(params).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get(url: str, params: Dict[str, str], timeout: int = 30) -> Dict[str, object]:
    full = url + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(full, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _error_text(exc: urllib.error.HTTPError) -> str:
    try:
        body = json.loads(exc.read().decode("utf-8"))
        err = body.get("error", {})
        return f"{err.get('code')}: {err.get('message')} ({err.get('error_user_msg', '')})".strip()
    except Exception:
        return f"HTTP {exc.code}"


class InstagramPublisher:
    def __init__(self, ig_user_id: str, access_token: str,
                 api_version: str = DEFAULT_API_VERSION) -> None:
        self.ig_user_id = ig_user_id
        self.token = access_token
        self.api = api_version
        self.base = f"{GRAPH}/{api_version}"

    # -- diagnostics -------------------------------------------------------- #
    def verify(self) -> PublishResult:
        """Confirm the token + account id work before attempting to post."""
        res = PublishResult(ok=False)
        try:
            me = _get(f"{self.base}/{self.ig_user_id}",
                      {"fields": "username,account_type", "access_token": self.token})
            uname = me.get("username")
            atype = me.get("account_type", "?")
            return PublishResult(ok=True, message=f"Connected as @{uname} ({atype}).")
        except urllib.error.HTTPError as exc:
            return res.log(f"verify failed: {_error_text(exc)}")
        except (urllib.error.URLError, ValueError, TimeoutError) as exc:
            return res.log(f"verify failed: {exc}")

    # -- reels -------------------------------------------------------------- #
    def publish_reel(self, video_url: str, caption: str,
                     share_to_feed: bool = True,
                     cover_url: Optional[str] = None,
                     poll_seconds: int = 180) -> PublishResult:
        res = PublishResult(ok=False)
        # 1) create container
        params = {
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption,
            "share_to_feed": "true" if share_to_feed else "false",
            "access_token": self.token,
        }
        if cover_url:
            params["cover_url"] = cover_url  # custom thumbnail for the grid
        try:
            container = _post(f"{self.base}/{self.ig_user_id}/media", params)
        except urllib.error.HTTPError as exc:
            return res.log(f"container create failed: {_error_text(exc)}")
        except (urllib.error.URLError, ValueError, TimeoutError) as exc:
            return res.log(f"container create failed: {exc}")

        creation_id = str(container.get("id", ""))
        if not creation_id:
            return res.log(f"no creation id in response: {container}")
        res.creation_id = creation_id
        res.log(f"container created: {creation_id}")

        # 2) poll until the video is processed
        deadline = time.time() + poll_seconds
        status = ""
        while time.time() < deadline:
            try:
                st = _get(f"{self.base}/{creation_id}",
                          {"fields": "status_code,status", "access_token": self.token})
            except urllib.error.HTTPError as exc:
                return res.log(f"status check failed: {_error_text(exc)}")
            except (urllib.error.URLError, ValueError, TimeoutError) as exc:
                return res.log(f"status check failed: {exc}")
            status = str(st.get("status_code", ""))
            if status == "FINISHED":
                res.log("media processed (FINISHED)")
                break
            if status == "ERROR":
                return res.log(f"media processing error: {st.get('status')}")
            time.sleep(5)
        else:
            return res.log(f"timed out waiting for processing (last status: {status or 'unknown'})")

        # 3) publish
        try:
            published = _post(f"{self.base}/{self.ig_user_id}/media_publish",
                              {"creation_id": creation_id, "access_token": self.token})
        except urllib.error.HTTPError as exc:
            return res.log(f"publish failed: {_error_text(exc)}")
        except (urllib.error.URLError, ValueError, TimeoutError) as exc:
            return res.log(f"publish failed: {exc}")

        media_id = str(published.get("id", ""))
        if not media_id:
            return res.log(f"no media id after publish: {published}")
        res.ok = True
        res.media_id = media_id
        return res.log(f"published! media id: {media_id}")

    def publish_image(self, image_url: str, caption: str) -> PublishResult:
        """Single-image post fallback (e.g. a cover/carousel slide)."""
        res = PublishResult(ok=False)
        try:
            container = _post(f"{self.base}/{self.ig_user_id}/media",
                              {"image_url": image_url, "caption": caption,
                               "access_token": self.token})
            creation_id = str(container.get("id", ""))
            res.creation_id = creation_id
            published = _post(f"{self.base}/{self.ig_user_id}/media_publish",
                              {"creation_id": creation_id, "access_token": self.token})
            media_id = str(published.get("id", ""))
            if media_id:
                res.ok = True
                res.media_id = media_id
                return res.log(f"image published: {media_id}")
            return res.log(f"no media id: {published}")
        except urllib.error.HTTPError as exc:
            return res.log(f"image publish failed: {_error_text(exc)}")
        except (urllib.error.URLError, ValueError, TimeoutError) as exc:
            return res.log(f"image publish failed: {exc}")



# --------------------------------------------------------------------------- #
# Long-lived token refresh
# --------------------------------------------------------------------------- #

@dataclass
class TokenResult:
    ok: bool
    token: Optional[str] = None
    expires_in: Optional[int] = None
    message: str = ""


def refresh_long_lived_token(app_id: str, app_secret: str, current_token: str,
                             api_version: str = DEFAULT_API_VERSION) -> TokenResult:
    """Exchange a still-valid long-lived token for a fresh one (~60 more days).

    Facebook long-lived user tokens last about 60 days. Calling this while the
    token is still valid resets that clock, so running it on the daily schedule
    means the token effectively never expires. Requires the app id + secret
    (from your Meta app's Settings -> Basic).
    """
    if not (app_id and app_secret and current_token):
        return TokenResult(ok=False, message="missing app_id / app_secret / current token")
    params = {
        "grant_type": "fb_exchange_token",
        "client_id": app_id,
        "client_secret": app_secret,
        "fb_exchange_token": current_token,
    }
    try:
        data = _get(f"{GRAPH}/{api_version}/oauth/access_token", params)
    except urllib.error.HTTPError as exc:
        return TokenResult(ok=False, message=f"refresh failed: {_error_text(exc)}")
    except (urllib.error.URLError, ValueError, TimeoutError) as exc:
        return TokenResult(ok=False, message=f"refresh failed: {exc}")

    token = str(data.get("access_token", ""))
    if not token:
        return TokenResult(ok=False, message=f"no token in response: {data}")
    expires = data.get("expires_in")
    return TokenResult(ok=True, token=token,
                       expires_in=int(expires) if expires else None,
                       message="refreshed long-lived token")
