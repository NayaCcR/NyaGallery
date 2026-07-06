from __future__ import annotations

import base64
import asyncio
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
from http.cookies import SimpleCookie
import html
import inspect
import json
import os
import re
import secrets
import subprocess
import sys
import time
from typing import Any, Callable, Iterable, Protocol
from urllib.error import HTTPError
from urllib.parse import parse_qs, unquote, urlencode, urlparse, urlunparse
from urllib.request import ProxyHandler, Request, build_opener, urlopen

from nyagallery.metadata import (
    GalleryMetadata,
    make_asset_key,
    normalize_age_rating,
    normalize_date_value,
    normalize_source_type,
    optional_bool,
    utc_now_iso,
)
from nyagallery.storage import GalleryStorage, filename_from_url


PIXIV_ARTWORK_URL = "https://www.pixiv.net/artworks/{pid}"
PIXIV_AJAX_ILLUST_URL = "https://www.pixiv.net/ajax/illust/{pid}"
PIXIV_AJAX_PAGES_URL = "https://www.pixiv.net/ajax/illust/{pid}/pages"
PIXIV_AJAX_UGOIRA_URL = "https://www.pixiv.net/ajax/illust/{pid}/ugoira_meta"
PIXIV_AJAX_USER_ALL_URL = "https://www.pixiv.net/ajax/user/{uid}/profile/all"
PIXIV_AJAX_BOOKMARKS_URL = "https://www.pixiv.net/ajax/user/{uid}/illusts/bookmarks"
PIXIV_OAUTH_LOGIN_URL = "https://app-api.pixiv.net/web/v1/login"
PIXIV_OAUTH_TOKEN_URL = "https://oauth.secure.pixiv.net/auth/token"
PIXIV_OAUTH_CALLBACK_URL = "https://app-api.pixiv.net/web/v1/users/auth/pixiv/callback"
PIXIV_OAUTH_CLIENT_ID = "MOBrBDS8blbauoSck0ZfDbtuzpyT"
PIXIV_OAUTH_CLIENT_SECRET = "lsACyCD94FhDUtGTXi3QzcFE2uU1hqtDaKeqrdwj"
PIXIV_OAUTH_HASH_SECRET = "28c1fdd170a5204386cb1313c7077b34f83e4aaf4aa829ce78c231e05b0bae2c"
PIXIV_OAUTH_USER_AGENT = "PixivAndroidApp/5.0.234 (Android 11; Pixel 5)"


class PixivRateLimitError(RuntimeError):
    def __init__(self, message: str = "Pixiv rate limit exceeded", *, retry_after_seconds: int | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class PixivOAuthError(RuntimeError):
    pass


@dataclass(frozen=True)
class PixivRequestOptions:
    request_delay_seconds: float = 1.0
    max_retries: int = 3
    retry_base_seconds: int = 60
    retry_max_seconds: int = 300
    proxy_url: str = ""


class PixivClient(Protocol):
    def get_illust(self, pixiv_id: str) -> "PixivArtwork":
        ...

    def iter_user_illusts(self, user_id: str) -> Iterable["PixivArtwork"]:
        ...

    def iter_user_bookmarks(self, user_id: str, restrict: str = "public") -> Iterable["PixivArtwork"]:
        ...

    def iter_user_bookmark_ids(self, user_id: str, restrict: str = "public") -> Iterable[str]:
        ...


class Downloader(Protocol):
    def download(self, url: str) -> bytes:
        ...


ProgressCallback = Callable[[dict[str, object]], None]


@dataclass(frozen=True)
class PixivUgoiraFrame:
    file_name: str
    delay_ms: int


@dataclass(frozen=True)
class PixivPage:
    original_url: str
    filename: str | None = None
    width: int | None = None
    height: int | None = None
    mime_type: str | None = None
    is_ugoira: bool = False
    ugoira_frames: tuple[PixivUgoiraFrame, ...] = ()


@dataclass(frozen=True)
class PixivTag:
    name: str
    translated_name: str | None = None


@dataclass(frozen=True)
class PixivArtwork:
    pixiv_id: str
    title: str
    artist_id: str
    artist_name: str
    tags: tuple[str, ...]
    pages: tuple[PixivPage, ...]
    description: str = ""
    tag_details: tuple[PixivTag, ...] = ()
    source_url: str | None = None
    artwork_date: str | None = None
    pixiv_upload_date: str | None = None
    source_type: str | None = None
    age_rating: str | None = None
    is_ai_generated: bool | None = None


@dataclass(frozen=True)
class SyncAssetResult:
    asset_key: str
    status: str
    original_path: str
    metadata_path: str
    file_sha256: str
    duplicate_of: str | None = None


@dataclass(frozen=True)
class PixivOAuthStart:
    authorization_url: str
    code_verifier: str
    code_challenge: str
    state: str
    callback_url: str


@dataclass(frozen=True)
class PixivOAuthToken:
    access_token: str
    refresh_token: str
    expires_in: int | None = None
    token_type: str | None = None
    scope: str | None = None
    user: dict[str, Any] | None = None


def get_pixiv_refresh_token_with_browser(
    *,
    headless: bool = False,
    username: str | None = None,
    password: str | None = None,
    proxy_url: str | None = None,
    login_factory: Any | None = None,
) -> PixivOAuthToken:
    """Open a local browser through gppt and return Pixiv OAuth tokens."""
    username = username.strip() if isinstance(username, str) else username
    username = username or None
    password = password or None
    if headless and (not username or not password):
        raise PixivOAuthError("Headless Pixiv login requires --username and --password")

    if login_factory is None:
        try:
            from gppt import GetPixivToken
        except ImportError as exc:
            raise PixivOAuthError(
                'Install Pixiv browser login support with: python -m pip install -e ".[pixiv-login]"'
            ) from exc
        login_factory = GetPixivToken

    proxy = _effective_pixiv_proxy(proxy_url)
    try:
        client_kwargs = {"headless": headless, "username": username, "password": password}
        if proxy:
            _add_supported_proxy_kwarg(client_kwargs, login_factory, proxy)
        login_kwargs = {"headless": headless, "username": username, "password": password}
        if proxy:
            _add_supported_proxy_kwarg(login_kwargs, getattr(login_factory, "login", None), proxy)
        with _pixiv_proxy_environment(proxy):
            client = login_factory(**client_kwargs)
            _add_supported_proxy_kwarg(login_kwargs, getattr(client, "login", None), proxy)
            raw_response = _run_maybe_awaitable(client.login(**login_kwargs))
    except PixivOAuthError:
        raise
    except Exception as exc:
        raise PixivOAuthError(
            "Pixiv browser login failed. "
            "If Pixiv requires CAPTCHA, passkey, or 2FA, use the visible CLI flow "
            "`nyagallery pixiv-login-browser --plain` and paste the refresh token instead. "
            f"Detail: {exc}"
        ) from exc

    response = _pixiv_oauth_response_payload(raw_response)
    access_token = str(response.get("access_token") or "").strip()
    refresh_token = str(response.get("refresh_token") or "").strip()
    if not access_token or not refresh_token:
        raise PixivOAuthError("Pixiv browser login response did not include access_token and refresh_token")
    return PixivOAuthToken(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=_optional_int(response.get("expires_in")),
        token_type=_optional_str(response.get("token_type")),
        scope=_optional_str(response.get("scope")),
        user=response.get("user") if isinstance(response.get("user"), dict) else None,
    )


def get_pixiv_refresh_token_with_browser_worker(
    *,
    headless: bool,
    username: str | None,
    password: str | None,
    timeout_seconds: int = 180,
    proxy_url: str | None = None,
    runner: Any | None = None,
) -> PixivOAuthToken:
    """Run gppt in a child process so Playwright failures cannot break the API process."""
    payload = {
        "mode": "browser",
        "headless": headless,
        "username": username or None,
        "password": password or None,
        "proxy_url": proxy_url or "",
    }
    return _pixiv_oauth_worker(payload, timeout_seconds=timeout_seconds, runner=runner)


def _pixiv_oauth_worker(
    payload: dict[str, object],
    *,
    timeout_seconds: int,
    runner: Any | None = None,
) -> PixivOAuthToken:
    command = [sys.executable, "-m", "nyagallery.pixiv_login_worker"]
    run = runner or subprocess.run
    proxy = _effective_pixiv_proxy(payload.get("proxy_url") or payload.get("proxy"))
    run_kwargs = {
        "input": json.dumps(payload),
        "text": True,
        "capture_output": True,
        "timeout": timeout_seconds,
    }
    if proxy:
        env = os.environ.copy()
        _apply_proxy_to_env(env, proxy)
        run_kwargs["env"] = env
    try:
        completed = run(
            command,
            **run_kwargs,
        )
    except subprocess.TimeoutExpired as exc:
        raise PixivOAuthError(
            "Pixiv browser login timed out. "
            "If Pixiv requires CAPTCHA, passkey, or 2FA, use the visible CLI flow "
            "`nyagallery pixiv-login-browser --plain` and paste the refresh token instead."
        ) from exc

    stdout = str(getattr(completed, "stdout", "") or "").strip()
    stderr = str(getattr(completed, "stderr", "") or "").strip()
    if getattr(completed, "returncode", 1) != 0:
        raise PixivOAuthError(_pixiv_worker_error_message(stdout, stderr))

    try:
        response = json.loads(stdout)
    except json.JSONDecodeError as exc:
        detail = _tail(stderr or stdout)
        raise PixivOAuthError(f"Pixiv browser login returned invalid worker response: {detail}") from exc
    payload_response = _pixiv_oauth_response_payload(response)
    access_token = str(payload_response.get("access_token") or "").strip()
    refresh_token = str(payload_response.get("refresh_token") or "").strip()
    if not access_token or not refresh_token:
        raise PixivOAuthError("Pixiv browser login response did not include access_token and refresh_token")
    return PixivOAuthToken(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=_optional_int(payload_response.get("expires_in")),
        token_type=_optional_str(payload_response.get("token_type")),
        scope=_optional_str(payload_response.get("scope")),
        user=payload_response.get("user") if isinstance(payload_response.get("user"), dict) else None,
    )


def get_pixiv_refresh_token_with_cookie(
    *,
    cookie: str,
    headless: bool = True,
    timeout_seconds: int = 180,
    callback_factory: Callable[[PixivOAuthStart, str, bool, int], str] | None = None,
    http_post: Any | None = None,
    proxy_url: str | None = None,
) -> PixivOAuthToken:
    """Use an existing Pixiv web session cookie to complete OAuth and return tokens.

    This still uses Pixiv OAuth under the hood: the cookie only lets the browser
    skip interactive login and reach the app-api callback URL.
    """
    cookie_header = cookie.strip()
    if not cookie_header:
        raise PixivOAuthError("Pixiv session cookie is required")

    start = create_pixiv_oauth_start()
    if callback_factory is None:
        callback_url = _pixiv_oauth_callback_from_cookie_browser(
            start,
            cookie_header,
            headless=headless,
            timeout_seconds=timeout_seconds,
            proxy_url=proxy_url,
        )
    else:
        callback_url = callback_factory(start, cookie_header, headless, timeout_seconds)

    return exchange_pixiv_oauth_code(
        callback_url=callback_url,
        code_verifier=start.code_verifier,
        http_post=http_post,
        timeout=min(max(10, timeout_seconds), 120),
        proxy_url=proxy_url,
    )


def get_pixiv_refresh_token_with_cookie_worker(
    *,
    cookie: str,
    headless: bool = True,
    timeout_seconds: int = 180,
    proxy_url: str | None = None,
    runner: Any | None = None,
) -> PixivOAuthToken:
    """Run cookie-based OAuth in a child process to isolate Playwright failures."""
    payload = {
        "mode": "cookie",
        "cookie": cookie,
        "headless": headless,
        "timeout_seconds": timeout_seconds,
        "proxy_url": proxy_url or "",
    }
    return _pixiv_oauth_worker(payload, timeout_seconds=timeout_seconds, runner=runner)


class HTTPPixivDownloader:
    def __init__(
        self,
        *,
        timeout: int = 60,
        cookie: str = "",
        options: PixivRequestOptions | None = None,
        proxy_url: str | None = None,
    ) -> None:
        self.http = PixivHTTP(cookie=cookie, timeout=timeout, options=options, proxy_url=proxy_url)

    def download(self, url: str) -> bytes:
        return self.http.get_bytes(url)


class PixivHTTP:
    def __init__(
        self,
        *,
        cookie: str = "",
        timeout: int = 60,
        options: PixivRequestOptions | None = None,
        proxy_url: str | None = None,
    ) -> None:
        self.cookie = cookie.strip()
        self.timeout = timeout
        self.options = options or PixivRequestOptions()
        self.proxy_url = _effective_pixiv_proxy(proxy_url or self.options.proxy_url)
        self._opener = _pixiv_proxy_opener(self.proxy_url)
        self._last_request_at = 0.0

    def get_json(self, url: str) -> Any:
        return json.loads(self.get_bytes(url).decode("utf-8"))

    def get_bytes(self, url: str) -> bytes:
        last_error: Exception | None = None
        attempts = max(1, self.options.max_retries + 1)
        for attempt in range(attempts):
            self._wait_for_spacing()
            try:
                request = Request(url, headers=self._headers())
                with self._open(request) as response:
                    self._last_request_at = time.monotonic()
                    return response.read()
            except HTTPError as exc:
                self._last_request_at = time.monotonic()
                if exc.code == 429:
                    retry_after = _retry_after_seconds(exc, self.options, attempt)
                    last_error = PixivRateLimitError(retry_after_seconds=retry_after)
                    if attempt >= attempts - 1:
                        raise last_error
                    time.sleep(retry_after)
                    continue
                raise
        if last_error:
            raise last_error
        raise RuntimeError(f"failed to request Pixiv URL: {url}")

    def _open(self, request: Request):
        if self._opener is not None:
            return self._opener.open(request, timeout=self.timeout)
        return urlopen(request, timeout=self.timeout)  # noqa: S310

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json, image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
            "Referer": "https://www.pixiv.net/",
            "User-Agent": "NyaGallery/0.1 (+https://github.com/)",
        }
        if self.cookie:
            headers["Cookie"] = self.cookie
        return headers

    def _wait_for_spacing(self) -> None:
        delay = max(0.0, float(self.options.request_delay_seconds))
        if delay <= 0:
            return
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < delay:
            time.sleep(delay - elapsed)


def create_pixiv_oauth_start(*, state: str | None = None, callback_url: str | None = None) -> PixivOAuthStart:
    verifier = _pixiv_oauth_code_verifier()
    challenge = _pixiv_oauth_code_challenge(verifier)
    redirect_uri = callback_url or PIXIV_OAUTH_CALLBACK_URL
    params = {
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "client": "pixiv-android",
    }
    return PixivOAuthStart(
        authorization_url=f"{PIXIV_OAUTH_LOGIN_URL}?{urlencode(params)}",
        code_verifier=verifier,
        code_challenge=challenge,
        state=state or "",
        callback_url=redirect_uri,
    )


def exchange_pixiv_oauth_code(
    *,
    code: str | None = None,
    callback_url: str | None = None,
    code_verifier: str,
    state: str | None = None,
    http_post: Any | None = None,
    timeout: int = 30,
    proxy_url: str | None = None,
) -> PixivOAuthToken:
    if _is_pixiv_pictures_callback(callback_url):
        raise PixivOAuthError(
            "This callback belongs to pixiv.pictures, not this NyaGallery OAuth session. "
            "Open the Pixiv login link generated by NyaGallery again and copy the app-api.pixiv.net callback URL."
        )
    if _pixiv_post_redirect_target(callback_url):
        raise PixivOAuthError(
            "This is a Pixiv post-redirect URL, not the final OAuth callback. "
            "Open its return_to URL first, then copy the app-api.pixiv.net callback URL."
        )
    parsed_code, parsed_state = _pixiv_oauth_code_from_callback(callback_url)
    token_code = (code or parsed_code or "").strip()
    if not token_code:
        raise PixivOAuthError("Pixiv OAuth code is required")
    if state and parsed_state and parsed_state != state:
        raise PixivOAuthError("Pixiv OAuth state mismatch")
    verifier = code_verifier.strip()
    if not verifier:
        raise PixivOAuthError("Pixiv OAuth code_verifier is required")

    payload = {
        "client_id": PIXIV_OAUTH_CLIENT_ID,
        "client_secret": PIXIV_OAUTH_CLIENT_SECRET,
        "code": token_code,
        "code_verifier": verifier,
        "grant_type": "authorization_code",
        "include_policy": "true",
        "redirect_uri": PIXIV_OAUTH_CALLBACK_URL,
    }
    raw_response = _pixiv_oauth_post_token(payload, http_post=http_post, timeout=timeout, proxy_url=proxy_url)
    response = _pixiv_oauth_response_payload(raw_response)
    access_token = str(response.get("access_token") or "").strip()
    refresh_token = str(response.get("refresh_token") or "").strip()
    if not access_token or not refresh_token:
        raise PixivOAuthError("Pixiv OAuth response did not include access_token and refresh_token")
    return PixivOAuthToken(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=_optional_int(response.get("expires_in")),
        token_type=_optional_str(response.get("token_type")),
        scope=_optional_str(response.get("scope")),
        user=response.get("user") if isinstance(response.get("user"), dict) else None,
    )


class PixivSyncService:
    def __init__(
        self,
        storage: GalleryStorage,
        client: PixivClient | None = None,
        downloader: Downloader | None = None,
        uploader_user_id: int | None = None,
        uploader_username: str | None = None,
        storage_strategy_name: str | None = None,
        progress: ProgressCallback | None = None,
    ) -> None:
        self.storage = storage
        self.client = client
        self.downloader = downloader or HTTPPixivDownloader()
        self.uploader_user_id = uploader_user_id
        self.uploader_username = uploader_username
        self.storage_strategy_name = storage_strategy_name
        self.progress = progress

    def sync_pid(self, pixiv_id: str) -> list[SyncAssetResult]:
        if self.client is None:
            raise RuntimeError("Pixiv client is required for sync_pid")
        return self.sync_artwork(self.client.get_illust(str(pixiv_id)))

    def sync_user(self, user_id: str, *, limit: int | None = None) -> list[SyncAssetResult]:
        if self.client is None:
            raise RuntimeError("Pixiv client is required for sync_user")
        results: list[SyncAssetResult] = []
        for index, artwork in enumerate(self.client.iter_user_illusts(str(user_id))):
            if limit is not None and index >= limit:
                break
            results.extend(self.sync_artwork(artwork))
        return results

    def sync_user_bookmarks(self, user_id: str, *, restrict: str = "public", limit: int | None = None) -> list[SyncAssetResult]:
        if self.client is None:
            raise RuntimeError("Pixiv client is required for sync_user_bookmarks")
        results: list[SyncAssetResult] = []
        for index, artwork in enumerate(self.client.iter_user_bookmarks(str(user_id), restrict=restrict)):
            if limit is not None and index >= limit:
                break
            results.extend(self.sync_artwork(artwork))
        return results

    def sync_artwork(self, artwork: PixivArtwork) -> list[SyncAssetResult]:
        if not artwork.pages:
            raise ValueError(f"Pixiv artwork has no pages: {artwork.pixiv_id}")

        results: list[SyncAssetResult] = []
        multi_page = len(artwork.pages) > 1
        page_count = len(artwork.pages)
        self._report_progress(
            stage="artwork_started",
            message="pixiv artwork started",
            pixiv_id=str(artwork.pixiv_id),
            title=artwork.title,
            artist_id=str(artwork.artist_id),
            artist_name=artwork.artist_name,
            page_count=page_count,
            progress=0,
        )
        for page_number, page in enumerate(artwork.pages):
            page_index = page_number if multi_page else None
            asset_key = make_asset_key("pixiv", artwork.pixiv_id, page_index)
            source_filename = self._page_filename(artwork, page, page_index)
            metadata_path = self.storage.find_metadata_path(asset_key)
            if metadata_path is not None:
                metadata = self.storage.read_metadata(asset_key)
                results.append(
                    SyncAssetResult(
                        asset_key=asset_key,
                        status="skipped",
                        original_path=metadata.original_path,
                        metadata_path=metadata_path.as_posix(),
                        file_sha256=metadata.file_sha256,
                    )
                )
                self._report_progress(
                    stage="page_skipped",
                    message="pixiv page skipped",
                    pixiv_id=str(artwork.pixiv_id),
                    title=artwork.title,
                    asset_key=asset_key,
                    filename=metadata.original_filename,
                    page_number=page_number + 1,
                    page_count=page_count,
                    result_status="skipped",
                    sync_count=len(results),
                    progress=round(((page_number + 1) / page_count) * 100, 2),
                )
                continue

            self._report_progress(
                stage="downloading_page",
                message="downloading pixiv page",
                pixiv_id=str(artwork.pixiv_id),
                title=artwork.title,
                asset_key=asset_key,
                filename=source_filename,
                page_number=page_number + 1,
                page_count=page_count,
                sync_count=len(results),
                progress=round((page_number / page_count) * 100, 2),
            )
            content = self.downloader.download(page.original_url)
            stored = self.storage.write_original(
                asset_key,
                source_filename,
                content,
                strategy_name=self.storage_strategy_name,
                content_type=page.mime_type,
            )
            duplicate = self.storage.find_by_sha256(stored.sha256, exclude_asset_key=asset_key)
            source_type = "ugoira" if page.is_ugoira else artwork.source_type
            image_id = self._image_id(artwork, page, page_index)
            extra: dict[str, Any] = {
                "pixiv_id": str(artwork.pixiv_id),
                "pixiv_title": artwork.title,
                "pixiv_description": artwork.description,
                "pixiv_artist_id": str(artwork.artist_id),
                "pixiv_artist_name": artwork.artist_name,
                "pixiv_source_url": artwork.source_url or PIXIV_ARTWORK_URL.format(pid=artwork.pixiv_id),
                "pixiv_image_id": image_id,
                "pixiv_image_url": page.original_url,
                "pixiv_page_index": page_index,
                "pixiv_page_number": page_number + 1,
                "pixiv_page_count": len(artwork.pages),
                "pixiv_tag_details": [
                    {
                        "name": tag.name,
                        "translated_name": tag.translated_name,
                    }
                    for tag in artwork.tag_details
                ],
            }
            if artwork.artwork_date:
                extra["pixiv_create_date"] = artwork.artwork_date
            if artwork.pixiv_upload_date:
                extra["pixiv_upload_date"] = artwork.pixiv_upload_date
            if page.ugoira_frames:
                extra["ugoira_frames"] = [
                    {"file": frame.file_name, "delay": frame.delay_ms}
                    for frame in page.ugoira_frames
                ]

            metadata = GalleryMetadata(
                source="pixiv",
                source_id=str(artwork.pixiv_id),
                title=artwork.title,
                artist_id=str(artwork.artist_id),
                artist_name=artwork.artist_name,
                original_url=artwork.source_url or PIXIV_ARTWORK_URL.format(pid=artwork.pixiv_id),
                crawl_time=utc_now_iso(),
                file_sha256=stored.sha256,
                original_filename=stored.filename,
                original_path=stored.relative_path,
                pixiv_tags=tuple(artwork.tags),
                canonical_tags=(),
                page_index=page_index,
                width=page.width,
                height=page.height,
                mime_type=page.mime_type,
                artwork_date=artwork.artwork_date,
                pixiv_upload_date=artwork.pixiv_upload_date,
                source_type=source_type,
                age_rating=artwork.age_rating,
                is_ai_generated=artwork.is_ai_generated,
                is_animated=True if page.is_ugoira else None,
                uploader_user_id=self.uploader_user_id,
                uploader_username=self.uploader_username,
                extra=extra,
            )
            written_metadata_path = self.storage.write_metadata(metadata)
            if duplicate is not None:
                status = "duplicate"
                duplicate_of = duplicate.asset_key
            elif stored.was_existing:
                status = "reused_original"
                duplicate_of = None
            else:
                status = "downloaded"
                duplicate_of = None
            results.append(
                SyncAssetResult(
                    asset_key=asset_key,
                    status=status,
                    original_path=stored.relative_path,
                    metadata_path=written_metadata_path.as_posix(),
                    file_sha256=stored.sha256,
                    duplicate_of=duplicate_of,
                )
            )
            self._report_progress(
                stage="page_done",
                message="pixiv page completed",
                pixiv_id=str(artwork.pixiv_id),
                title=artwork.title,
                asset_key=asset_key,
                filename=stored.filename,
                page_number=page_number + 1,
                page_count=page_count,
                result_status=status,
                sync_count=len(results),
                progress=round(((page_number + 1) / page_count) * 100, 2),
            )
        self._report_progress(
            stage="artwork_done",
            message="pixiv artwork completed",
            pixiv_id=str(artwork.pixiv_id),
            title=artwork.title,
            page_count=page_count,
            sync_count=len(results),
            progress=100,
        )
        return results

    def _report_progress(self, **event: object) -> None:
        if self.progress is None:
            return
        self.progress({key: value for key, value in event.items() if value is not None})

    def _page_filename(self, artwork: PixivArtwork, page: PixivPage, page_index: int | None) -> str:
        if page.filename:
            return page.filename
        if page.is_ugoira:
            return f"{artwork.pixiv_id}.ugoira.zip"
        name = filename_from_url(page.original_url)
        if "." in name:
            return name
        suffix = _suffix_from_url_path(page.original_url) or ".bin"
        if page_index is None:
            return f"{artwork.pixiv_id}{suffix}"
        return f"{artwork.pixiv_id}_p{page_index}{suffix}"

    def _image_id(self, artwork: PixivArtwork, page: PixivPage, page_index: int | None) -> str:
        filename = self._page_filename(artwork, page, page_index)
        stem = os.path.basename(filename).split(".", 1)[0]
        if stem:
            return stem
        return str(artwork.pixiv_id) if page_index is None else f"{artwork.pixiv_id}_p{page_index}"


class PixivPyClient:
    """pixivpy3 adapter. The package is optional so tests can run without it."""

    def __init__(self, api: Any, *, options: PixivRequestOptions | None = None, proxy_url: str | None = None) -> None:
        self.api = api
        self.options = options or PixivRequestOptions()
        self.proxy_url = _effective_pixiv_proxy(proxy_url or self.options.proxy_url)
        self._last_request_at = 0.0

    @classmethod
    def from_refresh_token(
        cls,
        refresh_token: str | None = None,
        *,
        options: PixivRequestOptions | None = None,
        proxy_url: str | None = None,
    ) -> "PixivPyClient":
        token = refresh_token or os.environ.get("PIXIV_REFRESH_TOKEN")
        if not token:
            raise RuntimeError("PIXIV_REFRESH_TOKEN is required")
        try:
            from pixivpy3 import AppPixivAPI
        except ImportError as exc:
            raise RuntimeError("Install pixiv support with: pip install -e .[pixiv]") from exc

        proxy = _effective_pixiv_proxy(proxy_url or (options.proxy_url if options else ""))
        api = AppPixivAPI()
        _configure_pixivpy_proxy(api, proxy)
        with _pixiv_proxy_environment(proxy):
            api.auth(refresh_token=token)
        return cls(api, options=options, proxy_url=proxy)

    def get_illust(self, pixiv_id: str) -> PixivArtwork:
        response = self._call_api(self.api.illust_detail, str(pixiv_id))
        illust = _get(response, "illust", response)
        return self._convert_illust(illust)

    def iter_user_illusts(self, user_id: str) -> Iterable[PixivArtwork]:
        response = self._call_api(self.api.user_illusts, str(user_id))
        while True:
            for item in _get(response, "illusts", []) or []:
                pixiv_id = str(_get(item, "id"))
                yield self.get_illust(pixiv_id)
            next_url = _get(response, "next_url")
            if not next_url:
                break
            next_qs = self.api.parse_qs(next_url)
            response = self._call_api(self.api.user_illusts, **next_qs)

    def iter_user_bookmarks(self, user_id: str, restrict: str = "public") -> Iterable[PixivArtwork]:
        for pixiv_id in self.iter_user_bookmark_ids(user_id, restrict=restrict):
            try:
                yield self.get_illust(pixiv_id)
            except RuntimeError:
                continue

    def iter_user_bookmark_ids(self, user_id: str, restrict: str = "public") -> Iterable[str]:
        response = self._call_api(self.api.user_bookmarks_illust, str(user_id), restrict=restrict)
        while True:
            for item in _get(response, "illusts", []) or []:
                pixiv_id = str(_get(item, "id"))
                if pixiv_id:
                    yield pixiv_id
            next_url = _get(response, "next_url")
            if not next_url:
                break
            next_qs = self.api.parse_qs(next_url)
            response = self._call_api(self.api.user_bookmarks_illust, **next_qs)

    def _call_api(self, fn, *args, **kwargs):
        _wait_for_pixiv_delay(self)
        try:
            with _pixiv_proxy_environment(self.proxy_url):
                return fn(*args, **kwargs)
        except Exception as exc:
            retry_after = _exception_retry_after(exc)
            if retry_after is not None:
                raise PixivRateLimitError(retry_after_seconds=retry_after) from exc
            raise
        finally:
            self._last_request_at = time.monotonic()

    def _convert_illust(self, illust: Any) -> PixivArtwork:
        pixiv_id = str(_get(illust, "id"))
        title = str(_get(illust, "title", ""))
        user = _get(illust, "user", {})
        artist_id = str(_get(user, "id", ""))
        artist_name = str(_get(user, "name", ""))
        width = _optional_int(_get(illust, "width"))
        height = _optional_int(_get(illust, "height"))
        source_type = normalize_source_type(_get(illust, "type"))
        description = _clean_pixiv_description(
            _get(illust, "caption")
            or _get(illust, "description")
            or _get(illust, "comment")
            or ""
        )
        artwork_date = normalize_date_value(_get(illust, "create_date") or _get(illust, "date"))
        pixiv_upload_date = normalize_date_value(
            _get(illust, "upload_date")
            or _get(illust, "update_date")
            or _get(illust, "modified_date")
        )
        age_rating = _pixiv_age_rating(_get(illust, "x_restrict"))
        is_ai_generated = _pixiv_ai_generated(
            _get(illust, "illust_ai_type", _get(illust, "ai_type", _get(illust, "is_ai_generated")))
        )
        tag_details = tuple(
            PixivTag(
                name=str(_get(tag, "name", tag)),
                translated_name=_optional_str(
                    _get(tag, "translated_name")
                    or _get(tag, "translatedName")
                    or _get(tag, "translation")
                ),
            )
            for tag in (_get(illust, "tags", []) or [])
            if str(_get(tag, "name", tag)).strip()
        )
        tags = tuple(tag.name for tag in tag_details)
        pages = self._pages_for_illust(illust, pixiv_id, width, height)
        return PixivArtwork(
            pixiv_id=pixiv_id,
            title=title,
            artist_id=artist_id,
            artist_name=artist_name,
            tags=tags,
            pages=tuple(pages),
            description=description,
            tag_details=tag_details,
            source_url=PIXIV_ARTWORK_URL.format(pid=pixiv_id),
            artwork_date=artwork_date,
            pixiv_upload_date=pixiv_upload_date,
            source_type=source_type,
            age_rating=age_rating,
            is_ai_generated=is_ai_generated,
        )

    def _pages_for_illust(
        self,
        illust: Any,
        pixiv_id: str,
        width: int | None,
        height: int | None,
    ) -> list[PixivPage]:
        illust_type = str(_get(illust, "type", ""))
        if illust_type == "ugoira":
            response = self._call_api(self.api.ugoira_metadata, pixiv_id)
            metadata = _get(response, "ugoira_metadata", response)
            zip_urls = _get(metadata, "zip_urls", {})
            zip_url = _get(zip_urls, "medium") or _get(zip_urls, "original")
            if not zip_url:
                raise RuntimeError(f"ugoira metadata has no zip URL: {pixiv_id}")
            frames = tuple(
                PixivUgoiraFrame(
                    file_name=str(_get(frame, "file", "")),
                    delay_ms=int(_get(frame, "delay", 100) or 100),
                )
                for frame in (_get(metadata, "frames", []) or [])
                if str(_get(frame, "file", "")).strip()
            )
            return [
                PixivPage(
                    original_url=str(zip_url),
                    filename=f"{pixiv_id}.ugoira.zip",
                    width=width,
                    height=height,
                    mime_type="application/zip",
                    is_ugoira=True,
                    ugoira_frames=frames,
                )
            ]

        meta_pages = _get(illust, "meta_pages", []) or []
        if meta_pages:
            pages: list[PixivPage] = []
            for index, item in enumerate(meta_pages):
                image_urls = _get(item, "image_urls", {})
                url = _get(image_urls, "original") or _get(image_urls, "large")
                if not url:
                    continue
                pages.append(
                    PixivPage(
                        original_url=str(url),
                        filename=filename_from_url(str(url)) or f"{pixiv_id}_p{index}.bin",
                        width=width,
                        height=height,
                    )
                )
            return pages

        single_page = _get(illust, "meta_single_page", {}) or {}
        image_urls = _get(illust, "image_urls", {}) or {}
        url = (
            _get(single_page, "original_image_url")
            or _get(image_urls, "original")
            or _get(image_urls, "large")
        )
        if not url:
            raise RuntimeError(f"illust has no original image URL: {pixiv_id}")
        return [
            PixivPage(
                original_url=str(url),
                filename=filename_from_url(str(url)),
                width=width,
                height=height,
            )
        ]


class PixivCookieClient:
    """Pixiv web AJAX adapter using an optional temporary browser cookie string."""

    def __init__(
        self,
        cookie: str = "",
        *,
        options: PixivRequestOptions | None = None,
        http: PixivHTTP | None = None,
        proxy_url: str | None = None,
    ) -> None:
        self.http = http or PixivHTTP(cookie=cookie, options=options, proxy_url=proxy_url)

    def get_illust(self, pixiv_id: str) -> PixivArtwork:
        response = self.http.get_json(PIXIV_AJAX_ILLUST_URL.format(pid=str(pixiv_id)))
        body = _pixiv_ajax_body(response)
        return self._convert_illust(body)

    def iter_user_illusts(self, user_id: str) -> Iterable[PixivArtwork]:
        response = self.http.get_json(PIXIV_AJAX_USER_ALL_URL.format(uid=str(user_id)))
        body = _pixiv_ajax_body(response)
        ids = _pixiv_user_artwork_ids(body)
        for pixiv_id in ids:
            yield self.get_illust(pixiv_id)

    def iter_user_bookmarks(self, user_id: str, restrict: str = "public") -> Iterable[PixivArtwork]:
        for pixiv_id in self.iter_user_bookmark_ids(user_id, restrict=restrict):
            try:
                yield self.get_illust(pixiv_id)
            except RuntimeError:
                continue

    def iter_user_bookmark_ids(self, user_id: str, restrict: str = "public") -> Iterable[str]:
        offset = 0
        limit = 48
        while True:
            url = PIXIV_AJAX_BOOKMARKS_URL.format(uid=str(user_id))
            url += f"?tag=&offset={offset}&limit={limit}"
            if restrict:
                url += f"&restrict={restrict}"
            response = self.http.get_json(url)
            body = _pixiv_ajax_body(response)
            works = _get(body, "works", []) or []
            if not works:
                break
            for item in works:
                pixiv_id = str(_get(item, "id"))
                if pixiv_id:
                    yield pixiv_id
            has_next = _get(body, "hasNext", False)
            if not has_next:
                break
            offset += limit

    def _convert_illust(self, illust: Any) -> PixivArtwork:
        pixiv_id = str(_get(illust, "id") or _get(illust, "illustId"))
        title = str(_get(illust, "title", ""))
        artist_id = str(_get(illust, "userId", _get(illust, "artist_id", "")))
        artist_name = str(_get(illust, "userName", _get(illust, "artist_name", "")))
        width = _optional_int(_get(illust, "width"))
        height = _optional_int(_get(illust, "height"))
        source_type = _pixiv_web_source_type(_get(illust, "illustType", _get(illust, "type")))
        description = _clean_pixiv_description(
            _get(illust, "description")
            or _get(illust, "caption")
            or _get(illust, "comment")
            or ""
        )
        artwork_date = normalize_date_value(_get(illust, "createDate") or _get(illust, "create_date"))
        pixiv_upload_date = normalize_date_value(_get(illust, "uploadDate") or _get(illust, "upload_date"))
        age_rating = _pixiv_age_rating(_get(illust, "xRestrict", _get(illust, "x_restrict")))
        is_ai_generated = _pixiv_ai_generated(_get(illust, "aiType", _get(illust, "illust_ai_type")))
        tag_details = _pixiv_web_tag_details(_get(illust, "tags", {}))
        pages = self._pages_for_illust(illust, pixiv_id, width, height, source_type)
        return PixivArtwork(
            pixiv_id=pixiv_id,
            title=title,
            artist_id=artist_id,
            artist_name=artist_name,
            tags=tuple(tag.name for tag in tag_details),
            pages=tuple(pages),
            description=description,
            tag_details=tuple(tag_details),
            source_url=PIXIV_ARTWORK_URL.format(pid=pixiv_id),
            artwork_date=artwork_date,
            pixiv_upload_date=pixiv_upload_date,
            source_type=source_type,
            age_rating=age_rating,
            is_ai_generated=is_ai_generated,
        )

    def _pages_for_illust(
        self,
        illust: Any,
        pixiv_id: str,
        width: int | None,
        height: int | None,
        source_type: str | None,
    ) -> list[PixivPage]:
        if source_type == "ugoira":
            response = self.http.get_json(PIXIV_AJAX_UGOIRA_URL.format(pid=pixiv_id))
            body = _pixiv_ajax_body(response)
            zip_url = _get(body, "originalSrc") or _get(body, "src")
            if not zip_url:
                raise RuntimeError(f"ugoira metadata has no zip URL: {pixiv_id}")
            frames = tuple(
                PixivUgoiraFrame(
                    file_name=str(_get(frame, "file", "")),
                    delay_ms=int(_get(frame, "delay", 100) or 100),
                )
                for frame in (_get(body, "frames", []) or [])
                if str(_get(frame, "file", "")).strip()
            )
            return [
                PixivPage(
                    original_url=str(zip_url),
                    filename=f"{pixiv_id}.ugoira.zip",
                    width=width,
                    height=height,
                    mime_type="application/zip",
                    is_ugoira=True,
                    ugoira_frames=frames,
                )
            ]

        pages_response = self.http.get_json(PIXIV_AJAX_PAGES_URL.format(pid=pixiv_id))
        pages_body = _pixiv_ajax_body(pages_response)
        pages: list[PixivPage] = []
        for index, item in enumerate(pages_body or []):
            urls = _get(item, "urls", {})
            url = _get(urls, "original") or _get(urls, "regular")
            if not url:
                continue
            pages.append(
                PixivPage(
                    original_url=str(url),
                    filename=filename_from_url(str(url)) or f"{pixiv_id}_p{index}.bin",
                    width=_optional_int(_get(item, "width")) or width,
                    height=_optional_int(_get(item, "height")) or height,
                )
            )
        if pages:
            return pages

        urls = _get(illust, "urls", {}) or {}
        url = _get(urls, "original") or _get(urls, "regular")
        if not url:
            raise RuntimeError(f"illust has no original image URL: {pixiv_id}")
        return [PixivPage(original_url=str(url), filename=filename_from_url(str(url)), width=width, height=height)]


def _effective_pixiv_proxy(value: Any = None) -> str:
    return str(
        value
        or os.environ.get("NYAGALLERY_NETWORK_PROXY")
        or ""
    ).strip()


def _pixiv_proxy_opener(proxy_url: str):
    proxy = _effective_pixiv_proxy(proxy_url)
    if not proxy:
        return None
    return build_opener(ProxyHandler({"http": proxy, "https": proxy}))


def _configure_pixivpy_proxy(api: Any, proxy_url: str) -> None:
    proxy = _effective_pixiv_proxy(proxy_url)
    if not proxy:
        return
    proxies = {"http": proxy, "https": proxy}
    for attr in ("requests", "session", "_requests", "_session"):
        target = getattr(api, attr, None)
        if target is None:
            continue
        target_proxies = getattr(target, "proxies", None)
        if isinstance(target_proxies, dict):
            target_proxies.update(proxies)
            return
        try:
            setattr(target, "proxies", dict(proxies))
            return
        except Exception:
            pass
    if callable(getattr(api, "set_proxies", None)):
        api.set_proxies(proxies)
        return
    try:
        setattr(api, "proxies", dict(proxies))
    except Exception:
        pass


def _add_supported_proxy_kwarg(kwargs: dict[str, object], fn: Any, proxy_url: str) -> None:
    if fn is None or not proxy_url:
        return
    try:
        signature = inspect.signature(fn)
    except (TypeError, ValueError):
        return
    parameters = signature.parameters
    if "proxy_url" in parameters:
        kwargs["proxy_url"] = proxy_url
        return
    if "proxy" in parameters:
        kwargs["proxy"] = proxy_url
        return
    if any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in parameters.values()):
        kwargs["proxy_url"] = proxy_url


@contextmanager
def _pixiv_proxy_environment(proxy_url: str):
    proxy = _effective_pixiv_proxy(proxy_url)
    if not proxy:
        yield
        return
    keys = (
        "NYAGALLERY_NETWORK_PROXY",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    )
    previous = {key: os.environ.get(key) for key in keys}
    try:
        _apply_proxy_to_env(os.environ, proxy)
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _apply_proxy_to_env(env: dict[str, str], proxy_url: str) -> None:
    proxy = _effective_pixiv_proxy(proxy_url)
    if not proxy:
        return
    env["NYAGALLERY_NETWORK_PROXY"] = proxy
    env["HTTP_PROXY"] = proxy
    env["HTTPS_PROXY"] = proxy
    env["ALL_PROXY"] = proxy
    env["http_proxy"] = proxy
    env["https_proxy"] = proxy
    env["all_proxy"] = proxy


def _get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _pixiv_oauth_code_verifier() -> str:
    return secrets.token_urlsafe(48)


def _pixiv_oauth_code_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _pixiv_oauth_callback_from_cookie_browser(
    start: PixivOAuthStart,
    cookie_header: str,
    *,
    headless: bool,
    timeout_seconds: int,
    proxy_url: str | None = None,
) -> str:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise PixivOAuthError(
            'Install Pixiv browser login support with: python -m pip install -e ".[pixiv-login]"'
        ) from exc

    cookies = _pixiv_playwright_cookies(cookie_header)
    if not cookies:
        raise PixivOAuthError("Pixiv session cookie did not contain usable cookie pairs")

    timeout_ms = max(1, int(timeout_seconds)) * 1000
    launch_kwargs: dict[str, object] = {"headless": headless}
    proxy = _effective_pixiv_proxy(proxy_url)
    if proxy:
        launch_kwargs["proxy"] = _playwright_proxy_config(proxy)
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(**launch_kwargs)
            try:
                context = browser.new_context()
                context.add_cookies(cookies)
                page = context.new_page()
                page.goto(start.authorization_url, wait_until="domcontentloaded", timeout=timeout_ms)
                return _wait_for_pixiv_oauth_callback(page, timeout_seconds=timeout_seconds)
            finally:
                browser.close()
    except PlaywrightTimeoutError as exc:
        raise PixivOAuthError("Pixiv cookie OAuth timed out before callback URL was reached") from exc
    except PlaywrightError as exc:
        raise PixivOAuthError(f"Pixiv cookie OAuth browser failed: {exc}") from exc


def _playwright_proxy_config(proxy_url: str) -> dict[str, str]:
    try:
        parsed = urlparse(proxy_url)
        host = parsed.hostname or ""
        port = parsed.port
    except ValueError:
        return {"server": proxy_url}
    if not parsed.scheme or not parsed.netloc or not host:
        return {"server": proxy_url}
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    server = urlunparse((parsed.scheme, f"{host}{f':{port}' if port is not None else ''}", parsed.path, parsed.params, parsed.query, parsed.fragment))
    config = {"server": server}
    if parsed.username is not None:
        config["username"] = unquote(parsed.username)
    if parsed.password is not None:
        config["password"] = unquote(parsed.password)
    return config


def _wait_for_pixiv_oauth_callback(page: Any, *, timeout_seconds: int) -> str:
    deadline = time.monotonic() + max(1, timeout_seconds)
    last_url = ""
    while time.monotonic() < deadline:
        current_url = str(getattr(page, "url", "") or "")
        if current_url and current_url != last_url:
            target = _pixiv_post_redirect_target(current_url)
            if target and target != current_url:
                page.goto(target, wait_until="domcontentloaded", timeout=10_000)
                last_url = target
                continue

            code, _state = _pixiv_oauth_code_from_callback(current_url)
            if code:
                return current_url
            last_url = current_url

        page.wait_for_timeout(300)

    raise PixivOAuthError(
        "Pixiv cookie OAuth did not reach a callback URL. "
        "The cookie may be expired, incomplete, or Pixiv may require interactive login."
    )


def _pixiv_playwright_cookies(cookie_header: str) -> list[dict[str, object]]:
    jar = SimpleCookie()
    try:
        jar.load(cookie_header)
    except Exception as exc:
        raise PixivOAuthError("Pixiv session cookie could not be parsed") from exc

    cookies: list[dict[str, object]] = []
    for name, morsel in jar.items():
        value = str(morsel.value or "")
        if not name or not value:
            continue
        cookies.append(
            {
                "name": str(name),
                "value": value,
                "domain": ".pixiv.net",
                "path": "/",
                "secure": True,
                "httpOnly": False,
                "sameSite": "Lax",
            }
        )
    return cookies


def _pixiv_oauth_code_from_callback(callback_url: str | None) -> tuple[str | None, str | None]:
    text = str(callback_url or "").strip()
    if not text:
        return None, None
    parsed = urlparse(text)
    if not parsed.scheme and not parsed.netloc and "=" not in text and "?" not in text:
        return text, None
    query = parse_qs(parsed.query or parsed.fragment or text.lstrip("?"), keep_blank_values=False)
    code = (query.get("code") or [None])[0]
    state = (query.get("state") or [None])[0]
    return code, state


def _is_pixiv_pictures_callback(callback_url: str | None) -> bool:
    text = str(callback_url or "").strip()
    if not text:
        return False
    parsed = urlparse(text)
    return parsed.netloc.casefold().endswith("pixiv.pictures")


def _pixiv_post_redirect_target(callback_url: str | None) -> str | None:
    text = str(callback_url or "").strip()
    if not text:
        return None
    parsed = urlparse(text)
    if parsed.netloc.casefold() != "accounts.pixiv.net" or parsed.path != "/post-redirect":
        return None
    target = (parse_qs(parsed.query).get("return_to") or [None])[0]
    if not target:
        return None
    target_url = urlparse(target)
    if target_url.netloc.casefold() != "app-api.pixiv.net" or target_url.path != "/web/v1/users/auth/pixiv/start":
        return None
    target_query = parse_qs(target_url.query)
    clean_params = {}
    for key in ("code_challenge", "code_challenge_method", "client", "via"):
        value = (target_query.get(key) or [None])[0]
        if value:
            clean_params[key] = _trim_before_embedded_url(value)
    return f"https://app-api.pixiv.net{target_url.path}?{urlencode(clean_params)}"


def _trim_before_embedded_url(value: str) -> str:
    match = re.search(r"https?://", value, flags=re.IGNORECASE)
    return value[: match.start()] if match else value


def _pixiv_oauth_headers() -> dict[str, str]:
    return {
        "accept": "application/json",
        "content-type": "application/x-www-form-urlencoded",
        "user-agent": PIXIV_OAUTH_USER_AGENT,
    }


def _pixiv_oauth_post_token(
    payload: dict[str, str],
    *,
    http_post: Any | None = None,
    timeout: int = 30,
    proxy_url: str | None = None,
) -> Any:
    headers = _pixiv_oauth_headers()
    body = urlencode(payload).encode("utf-8")
    if http_post is not None:
        return http_post(PIXIV_OAUTH_TOKEN_URL, headers, body, timeout)
    request = Request(PIXIV_OAUTH_TOKEN_URL, data=body, headers=headers, method="POST")
    try:
        opener = _pixiv_proxy_opener(_effective_pixiv_proxy(proxy_url))
        open_response = opener.open(request, timeout=timeout) if opener is not None else urlopen(request, timeout=timeout)  # noqa: S310
        with open_response as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")
        except Exception:
            detail = str(exc)
        raise PixivOAuthError(f"Pixiv OAuth token exchange failed: HTTP {exc.code} {detail}") from exc


def _pixiv_oauth_response_payload(response: Any) -> dict[str, Any]:
    if isinstance(response, (bytes, bytearray)):
        response = json.loads(bytes(response).decode("utf-8"))
    elif isinstance(response, str):
        response = json.loads(response)
    if not isinstance(response, dict):
        raise PixivOAuthError("Pixiv OAuth token response is not JSON object")
    if "error" in response:
        raise PixivOAuthError(f"Pixiv OAuth token exchange failed: {response.get('error')}")
    nested = response.get("response")
    if isinstance(nested, dict):
        return nested
    return response


def _pixiv_worker_error_message(stdout: str, stderr: str) -> str:
    for raw in (stdout, stderr):
        text = raw.strip()
        if not text:
            continue
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            error = str(data.get("error") or "").strip()
            if error:
                return error
    detail = _tail(stderr or stdout)
    if detail:
        return f"Pixiv browser login failed: {detail}"
    return "Pixiv browser login failed"


def _tail(value: str, *, limit: int = 1200) -> str:
    text = value.strip()
    if len(text) <= limit:
        return text
    return text[-limit:]


def _run_maybe_awaitable(value: Any) -> Any:
    if not inspect.isawaitable(value):
        return value
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(value)
    if inspect.iscoroutine(value):
        value.close()
    raise PixivOAuthError("Pixiv browser login cannot run while an asyncio loop is already active")


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_str(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _clean_pixiv_description(value: Any) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</p\s*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    lines = [line.strip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    return "\n".join(line for line in lines if line).strip()


def _pixiv_age_rating(x_restrict: Any) -> str:
    rating = normalize_age_rating(x_restrict)
    return rating or "safe"


def _pixiv_ai_generated(value: Any) -> bool | None:
    if isinstance(value, int):
        return value >= 2
    text = str(value or "").strip()
    if text.isdigit():
        return int(text) >= 2
    return optional_bool(value)


def _pixiv_web_source_type(value: Any) -> str | None:
    text = str(value or "").strip().casefold()
    if text == "0":
        return "illustration"
    if text == "1":
        return "manga"
    if text == "2":
        return "ugoira"
    return normalize_source_type(value)


def _pixiv_ajax_body(response: Any) -> Any:
    if isinstance(response, dict):
        if response.get("error"):
            message = _get(response, "message", "Pixiv request failed")
            raise RuntimeError(str(message))
        if "body" in response:
            return response["body"]
    return response


def _pixiv_user_artwork_ids(body: Any) -> list[str]:
    ids: list[str] = []
    for group_name in ("illusts", "manga"):
        group = _get(body, group_name, {}) or {}
        if isinstance(group, dict):
            ids.extend(str(key) for key in group.keys() if str(key).strip())
        elif isinstance(group, list):
            ids.extend(str(_get(item, "id", item)) for item in group if str(_get(item, "id", item)).strip())
    return sorted(dict.fromkeys(ids), key=lambda value: int(value) if value.isdigit() else 0, reverse=True)


def _pixiv_web_tag_details(value: Any) -> list[PixivTag]:
    raw_tags = _get(value, "tags", value)
    details: list[PixivTag] = []
    for raw in raw_tags or []:
        name = str(_get(raw, "tag", _get(raw, "name", raw))).strip()
        if not name:
            continue
        translation = _get(raw, "translation", {}) or {}
        translated = (
            _get(raw, "translated_name")
            or _get(raw, "translatedName")
            or _get(translation, "en")
            or _get(translation, "zh")
            or _get(translation, "zh-cn")
        )
        details.append(PixivTag(name=name, translated_name=_optional_str(translated)))
    return details


def _wait_for_pixiv_delay(client: Any) -> None:
    delay = max(0.0, float(getattr(client.options, "request_delay_seconds", 0.0)))
    if delay <= 0:
        return
    elapsed = time.monotonic() - float(getattr(client, "_last_request_at", 0.0))
    if elapsed < delay:
        time.sleep(delay - elapsed)


def _retry_after_seconds(error: HTTPError, options: PixivRequestOptions, attempt: int) -> int:
    header = error.headers.get("Retry-After") if error.headers else None
    if header:
        try:
            return max(1, min(int(header), int(options.retry_max_seconds)))
        except ValueError:
            pass
    fallback = int(options.retry_base_seconds) * (2 ** max(0, attempt))
    return max(1, min(fallback, int(options.retry_max_seconds)))


def _exception_retry_after(exc: Exception) -> int | None:
    status = getattr(exc, "status", None) or getattr(exc, "status_code", None) or getattr(exc, "code", None)
    text = str(exc).lower()
    if status == 429 or "429" in text or "too many requests" in text or "rate limit" in text:
        retry_after = getattr(exc, "retry_after", None) or getattr(exc, "retry_after_seconds", None)
        try:
            return int(retry_after) if retry_after is not None else 60
        except (TypeError, ValueError):
            return 60
    return None


def _suffix_from_url_path(url: str) -> str:
    path = urlparse(url).path
    name = os.path.basename(path)
    _, dot, suffix = name.rpartition(".")
    return f".{suffix}" if dot and suffix else ""
