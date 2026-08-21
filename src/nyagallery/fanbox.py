from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
import html as html_module
import json
import mimetypes
from pathlib import Path
import re
import time
from typing import Any, Callable, Iterator
from urllib.error import HTTPError
from urllib.parse import urlencode, urlparse
from urllib.request import ProxyHandler, Request, build_opener, urlopen

from nyagallery.security import ipv4_only_handlers

from nyagallery.metadata import GalleryMetadata, make_asset_key, utc_now_iso
from nyagallery.posts import GalleryPost, PostAttachment, PostStore, make_post_key
from nyagallery.storage import GalleryStorage


FANBOX_SOURCE = "fanbox"
FANBOX_API_ORIGIN = "https://api.fanbox.cc"
FANBOX_WEB_ORIGIN = "https://www.fanbox.cc"
FANBOX_LOGIN_URL = f"{FANBOX_WEB_ORIGIN}/login"
FANBOX_SESSION_COOKIE = "FANBOXSESSID"
FANBOX_PAGE_SIZE = 10
FANBOX_MAX_PAGE_SIZE = 300
FANBOX_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

_CREATOR_HANDLE_RE = re.compile(r"fanbox\.cc/@([A-Za-z0-9_-]+)")
_CREATOR_SUBDOMAIN_RE = re.compile(r"(?:https?://)?([A-Za-z0-9_-]+)\.fanbox\.cc")
_POST_URL_RE = re.compile(r"fanbox\.cc/(?:@[A-Za-z0-9_-]+/)?posts?/(\d+)")
_LEGACY_POST_URL_RE = re.compile(r"pixiv\.net/fanbox/creator/\d+/post/(\d+)")
_POST_ID_RE = re.compile(r"^\d{3,}$")
_ENTRY_ANCHOR_RE = re.compile(r'<a[^>]+href="([^"]+)"[^>]*>\s*<img', re.IGNORECASE)
_HTML_BREAK_RE = re.compile(r"</(?:p|div|br|h[1-6])>|<br\s*/?>", re.IGNORECASE)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp"}


class FanboxError(RuntimeError):
    pass


class FanboxAuthError(FanboxError):
    pass


class FanboxRateLimitError(FanboxError):
    def __init__(self, message: str = "Fanbox rate limit exceeded", *, retry_after_seconds: int | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


ProgressCallback = Callable[[dict[str, object]], None]


@dataclass(frozen=True)
class FanboxRequestOptions:
    request_delay_seconds: float = 1.0
    max_retries: int = 3
    retry_base_seconds: int = 60
    retry_max_seconds: int = 300
    download_concurrency: int = 3
    proxy_url: str = ""
    ipv4_only: bool = True


@dataclass(frozen=True)
class FanboxCredentials:
    """Fanbox authenticates with its own FANBOXSESSID; a Pixiv PHPSESSID is a different cookie on a different domain."""

    session_id: str = ""

    @property
    def is_complete(self) -> bool:
        return bool(self.session_id)

    @property
    def cookie_header(self) -> str:
        return f"{FANBOX_SESSION_COOKIE}={self.session_id}" if self.session_id else ""


@dataclass(frozen=True)
class FanboxCreator:
    creator_id: str
    user_id: str = ""
    name: str = ""
    icon_url: str = ""
    description: str = ""
    cover_image_url: str = ""
    has_adult_content: bool = False
    is_supported: bool = False

    @property
    def handle(self) -> str:
        return self.creator_id

    @property
    def display_name(self) -> str:
        return self.name or self.creator_id

    @property
    def url(self) -> str:
        return f"https://{self.creator_id}.fanbox.cc" if self.creator_id else FANBOX_WEB_ORIGIN


@dataclass(frozen=True)
class FanboxFile:
    file_id: str
    kind: str = "image"
    url: str = ""
    thumbnail_url: str = ""
    name: str = ""
    extension: str = ""
    size: int | None = None
    width: int | None = None
    height: int | None = None

    @property
    def is_image(self) -> bool:
        return self.kind == "image"

    @property
    def mime_type(self) -> str:
        guessed = mimetypes.guess_type(f"x.{self.extension}")[0] if self.extension else None
        return guessed or ("image/jpeg" if self.is_image else "application/octet-stream")

    @property
    def filename(self) -> str:
        stem = self.name or self.file_id
        return f"{stem}.{self.extension}" if self.extension else stem


@dataclass(frozen=True)
class FanboxPost:
    post_id: str
    creator: FanboxCreator
    title: str = ""
    post_type: str = "text"
    text: str = ""
    excerpt: str = ""
    published_at: str = ""
    updated_at: str = ""
    cover_image_url: str = ""
    fee_required: int = 0
    is_restricted: bool = False
    has_adult_content: bool = False
    tags: tuple[str, ...] = ()
    files: tuple[FanboxFile, ...] = ()
    like_count: int = 0
    comment_count: int = 0

    @property
    def url(self) -> str:
        return f"https://{self.creator.creator_id}.fanbox.cc/posts/{self.post_id}"

    @property
    def is_locked(self) -> bool:
        """Fanbox returns body=null for posts the current session has not unlocked."""
        return self.is_restricted and not self.files and not self.text


@dataclass(frozen=True)
class FanboxAssetResult:
    asset_key: str
    status: str
    original_path: str
    file_sha256: str
    kind: str = "image"
    duplicate_of: str | None = None


@dataclass(frozen=True)
class FanboxPostResult:
    post_id: str
    post_key: str
    status: str
    assets: tuple[FanboxAssetResult, ...] = ()
    locked: bool = False


@dataclass(frozen=True)
class FanboxPostFailure:
    target: str
    error: str
    post_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"target": self.target, "error": self.error, "post_id": self.post_id or None}


@dataclass(frozen=True)
class FanboxBatchResult:
    results: tuple[FanboxPostResult, ...] = ()
    failures: tuple[FanboxPostFailure, ...] = ()


class FanboxHTTP:
    def __init__(
        self,
        *,
        credentials: FanboxCredentials | None = None,
        timeout: int = 60,
        options: FanboxRequestOptions | None = None,
        proxy_url: str | None = None,
    ) -> None:
        self.credentials = credentials or FanboxCredentials()
        self.timeout = timeout
        self.options = options or FanboxRequestOptions()
        self.proxy_url = str(proxy_url or self.options.proxy_url or "").strip()
        self._opener = _fanbox_proxy_opener(self.proxy_url, ipv4_only=self.options.ipv4_only)
        self._last_request_at = 0.0

    def get_json(self, url: str) -> Any:
        raw = self._request(url, spaced=True)
        if not raw:
            return None
        return json.loads(raw.decode("utf-8"))

    def get_bytes(self, url: str) -> bytes:
        return self._request(url, spaced=False)

    def _request(self, url: str, *, spaced: bool = True) -> bytes:
        last_error: Exception | None = None
        attempts = max(1, self.options.max_retries + 1)
        for attempt in range(attempts):
            if spaced:
                self._wait_for_spacing()
            try:
                request = Request(url, headers=self._headers(), method="GET")
                with self._open(request) as response:
                    self._last_request_at = time.monotonic()
                    return response.read()
            except HTTPError as exc:
                self._last_request_at = time.monotonic()
                if exc.code == 429:
                    retry_after = _retry_after_seconds(exc, self.options, attempt)
                    last_error = FanboxRateLimitError(retry_after_seconds=retry_after)
                    if attempt >= attempts - 1:
                        raise last_error
                    time.sleep(retry_after)
                    continue
                if exc.code in {401, 403}:
                    raise FanboxAuthError(f"{exc.code} {url}{_error_suffix(exc)}") from exc
                raise FanboxError(f"{exc.code} {url}{_error_suffix(exc)}") from exc
            except OSError as exc:
                last_error = FanboxError(f"request failed: {url}: {exc}")
                if attempt >= attempts - 1:
                    raise last_error from exc
                time.sleep(min(2 ** attempt, self.options.retry_max_seconds))
        if last_error:
            raise last_error
        raise FanboxError(f"failed to request Fanbox URL: {url}")

    def _open(self, request: Request):
        if self._opener is not None:
            return self._opener.open(request, timeout=self.timeout)
        return urlopen(request, timeout=self.timeout)  # noqa: S310

    def _headers(self) -> dict[str, str]:
        """Fanbox rejects API calls without Origin/Referer, and pximg refuses media without a Referer."""
        headers = {
            "User-Agent": FANBOX_USER_AGENT,
            "Accept": "application/json, image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
            "Origin": FANBOX_WEB_ORIGIN,
            "Referer": f"{FANBOX_WEB_ORIGIN}/",
        }
        if self.credentials.cookie_header:
            headers["Cookie"] = self.credentials.cookie_header
        return headers

    def _wait_for_spacing(self) -> None:
        delay = max(0.0, float(self.options.request_delay_seconds))
        if delay <= 0:
            return
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < delay:
            time.sleep(delay - elapsed)


class FanboxClient:
    """Reads the Fanbox web API. Public posts need no session; paid bodies need a FANBOXSESSID."""

    def __init__(
        self,
        *,
        credentials: FanboxCredentials | None = None,
        options: FanboxRequestOptions | None = None,
        proxy_url: str | None = None,
    ) -> None:
        self.credentials = credentials or FanboxCredentials()
        self.options = options or FanboxRequestOptions()
        self.http = FanboxHTTP(credentials=self.credentials, options=self.options, proxy_url=proxy_url)

    @property
    def is_authenticated(self) -> bool:
        return self.credentials.is_complete

    def get_creator(self, target: str) -> FanboxCreator:
        creator_id = normalize_creator_id(target)
        if not creator_id:
            raise FanboxError("a Fanbox creator id is required")
        payload = self.http.get_json(f"{FANBOX_API_ORIGIN}/creator.get?{urlencode({'creatorId': creator_id})}")
        body = payload.get("body") if isinstance(payload, dict) else None
        if not isinstance(body, dict):
            raise FanboxError(f"Fanbox creator not found: {target}")
        return _creator_from_payload(body, fallback_id=creator_id)

    def get_post(self, target: str) -> FanboxPost:
        """Full post detail. Fanbox gates post.info behind a session even for free posts."""
        post_id = extract_post_id(target)
        try:
            payload = self.http.get_json(f"{FANBOX_API_ORIGIN}/post.info?{urlencode({'postId': post_id})}")
        except FanboxAuthError as exc:
            if not self.is_authenticated:
                raise FanboxAuthError(
                    f"Fanbox refused post {post_id} without a session; post bodies always require a FANBOXSESSID"
                ) from exc
            raise
        body = payload.get("body") if isinstance(payload, dict) else None
        if not isinstance(body, dict):
            raise FanboxError(f"Fanbox post not found: {post_id}")
        return _post_from_payload(body)

    def iter_creator_posts(
        self,
        creator_id: str,
        *,
        limit: int | None = None,
        stop_ids: frozenset[str] = frozenset(),
        skip_ids: frozenset[str] = frozenset(),
        page_size: int = FANBOX_PAGE_SIZE,
        max_pages: int | None = None,
        on_page: Callable[[dict[str, object]], None] | None = None,
    ) -> Iterator[FanboxPost]:
        """Page a creator's posts newest-first.

        The modern API paginates by asking post.paginateCreator for a list of pre-built page URLs, and each page
        returns summaries only — body/type are absent, so callers must hydrate through get_post for media.
        """
        handle = normalize_creator_id(creator_id)
        page_urls = self.creator_page_urls(handle)
        seen = 0
        for page, url in enumerate(page_urls, start=1):
            if max_pages is not None and page > max_pages:
                return
            payload = self.http.get_json(url)
            entries = _list_entries(payload)
            if on_page is not None:
                on_page({"page": page, "page_posts": len(entries), "page_size": normalize_page_size(page_size)})
            if not entries:
                continue
            for item in entries:
                post = _post_from_payload(item)
                if not post.post_id or post.post_id in stop_ids:
                    if post.post_id in stop_ids:
                        return
                    continue
                if post.post_id in skip_ids:
                    continue
                yield post
                seen += 1
                if limit is not None and seen >= limit:
                    return

    def creator_page_urls(self, creator_id: str) -> list[str]:
        handle = normalize_creator_id(creator_id)
        payload = self.http.get_json(f"{FANBOX_API_ORIGIN}/post.paginateCreator?{urlencode({'creatorId': handle})}")
        body = payload.get("body") if isinstance(payload, dict) else None
        urls = body.get("pageUrls") if isinstance(body, dict) else body
        return [str(url) for url in (urls or []) if str(url or "").startswith("http")]

    def iter_supporting_posts(
        self,
        *,
        limit: int | None = None,
        stop_ids: frozenset[str] = frozenset(),
        skip_ids: frozenset[str] = frozenset(),
        page_size: int = FANBOX_PAGE_SIZE,
        max_pages: int | None = None,
        on_page: Callable[[dict[str, object]], None] | None = None,
    ) -> Iterator[FanboxPost]:
        if not self.is_authenticated:
            raise FanboxAuthError("listing supported creators requires a Fanbox session")
        size = normalize_page_size(page_size)
        url = f"{FANBOX_API_ORIGIN}/post.listSupporting?{urlencode({'limit': size})}"
        seen = 0
        page = 0
        while url:
            if max_pages is not None and page >= max_pages:
                return
            payload = self.http.get_json(url)
            entries = _list_entries(payload)
            page += 1
            if on_page is not None:
                on_page({"page": page, "page_posts": len(entries), "page_size": size})
            if not entries:
                return
            for item in entries:
                post = _post_from_payload(item)
                if post.post_id in stop_ids:
                    return
                if post.post_id in skip_ids:
                    continue
                yield post
                seen += 1
                if limit is not None and seen >= limit:
                    return
            body = payload.get("body") if isinstance(payload, dict) else None
            url = str((body or {}).get("nextUrl") or "") if isinstance(body, dict) else ""

    def verify_session(self) -> dict[str, Any]:
        """Round-trips the supporting-plan endpoint so a saved session can be checked before a long crawl."""
        if not self.is_authenticated:
            raise FanboxAuthError("no Fanbox session configured")
        payload = self.http.get_json(f"{FANBOX_API_ORIGIN}/plan.listSupporting")
        body = payload.get("body") if isinstance(payload, dict) else None
        if not isinstance(body, list):
            raise FanboxAuthError("Fanbox session is not valid")
        return {"supporting_plans": len(body)}


class FanboxDownloader:
    def __init__(
        self,
        *,
        credentials: FanboxCredentials | None = None,
        timeout: int = 120,
        options: FanboxRequestOptions | None = None,
        proxy_url: str | None = None,
    ) -> None:
        base = options or FanboxRequestOptions()
        media_options = FanboxRequestOptions(
            request_delay_seconds=0.0,
            max_retries=base.max_retries,
            retry_base_seconds=base.retry_base_seconds,
            retry_max_seconds=base.retry_max_seconds,
            download_concurrency=base.download_concurrency,
            proxy_url=base.proxy_url,
        )
        self.http = FanboxHTTP(credentials=credentials, timeout=timeout, options=media_options, proxy_url=proxy_url)

    def download(self, url: str) -> bytes:
        return self.http.get_bytes(url)


class FanboxSyncService:
    """Archives Fanbox posts as gallery posts and their images/files as immutable originals."""

    def __init__(
        self,
        storage: GalleryStorage,
        post_store: PostStore | None = None,
        client: FanboxClient | None = None,
        downloader: FanboxDownloader | None = None,
        *,
        uploader_user_id: int | None = None,
        uploader_username: str | None = None,
        storage_strategy_name: str | None = None,
        download_media: bool = True,
        download_files: bool = True,
        download_concurrency: int = 3,
        name_media_by_post_id: bool = True,
        progress: ProgressCallback | None = None,
    ) -> None:
        self.storage = storage
        self.post_store = post_store or PostStore(storage.root)
        self.client = client
        self.downloader = downloader
        self.uploader_user_id = uploader_user_id
        self.uploader_username = uploader_username
        self.storage_strategy_name = storage_strategy_name
        self.download_media = download_media
        self.download_files = download_files
        self.name_media_by_post_id = name_media_by_post_id
        self.download_concurrency = max(1, int(download_concurrency or 1))
        self.progress = progress

    def sync_creator(
        self,
        target: str,
        *,
        limit: int | None = None,
        backfill: bool = True,
        page_size: int = FANBOX_PAGE_SIZE,
        max_pages: int | None = None,
    ) -> list[FanboxPostResult]:
        if self.client is None:
            raise FanboxError("Fanbox client is required for sync_creator")
        creator = self.client.get_creator(target)
        archived = self._archived_post_ids(creator)
        results: list[FanboxPostResult] = []
        counter = _RemainingCounter(total=None, archived=len(archived), limit=limit)
        self._report_progress(
            stage="creator_started",
            message="fanbox creator started",
            creator_id=creator.creator_id,
            user_id=creator.user_id,
            name=creator.display_name,
            archived_posts=len(archived),
            is_supported=creator.is_supported,
            page_size=normalize_page_size(page_size),
            max_pages=max_pages,
            progress=counter.percent(0),
        )

        def report(event: dict[str, object]) -> None:
            counter.pages += 1
            done = len(results)
            self._report_progress(
                stage="page_fetched",
                message="fanbox page fetched",
                phase="backfill" if backfill else "new",
                creator_id=creator.creator_id,
                page=event.get("page"),
                page_posts=event.get("page_posts"),
                page_size=event.get("page_size"),
                sync_count=done,
                remaining=counter.remaining(done),
                progress=counter.percent(done),
            )

        for post in self.client.iter_creator_posts(
            creator.creator_id,
            limit=limit,
            stop_ids=frozenset() if backfill else archived,
            skip_ids=archived,
            page_size=page_size,
            max_pages=max_pages,
            on_page=report,
        ):
            results.append(self.sync_post_object(self._hydrate(post), counter=counter, done=len(results)))

        self._report_progress(
            stage="creator_done",
            message="fanbox creator completed",
            creator_id=creator.creator_id,
            sync_count=len(results),
            locked_posts=len([item for item in results if item.locked]),
            progress=100,
        )
        return results

    def sync_posts(self, targets) -> FanboxBatchResult:
        """Archives a batch of post URLs or ids, keeping going past posts that cannot be read."""
        if self.client is None:
            raise FanboxError("Fanbox client is required for sync_posts")
        pending = list(dict.fromkeys(item for target in targets for item in split_batch_input(target)))
        results: list[FanboxPostResult] = []
        failures: list[FanboxPostFailure] = []
        counter = _RemainingCounter(total=len(pending), archived=0, limit=None)
        self._report_progress(
            stage="batch_started",
            message="fanbox batch started",
            target_count=len(pending),
            progress=counter.percent(0),
        )
        for index, target in enumerate(pending):
            try:
                post = self.client.get_post(target)
            except FanboxError as exc:
                failures.append(FanboxPostFailure(target=target, error=str(exc)))
                self._report_progress(
                    stage="post_failed",
                    message="fanbox post failed",
                    target=target,
                    error=str(exc),
                    sync_count=len(results),
                    progress=counter.percent(index + 1),
                )
                continue
            results.append(self.sync_post_object(post, counter=counter, done=index))
        self._report_progress(
            stage="batch_done",
            message="fanbox batch completed",
            sync_count=len(results),
            failure_count=len(failures),
            target_count=len(pending),
            progress=100,
        )
        return FanboxBatchResult(results=tuple(results), failures=tuple(failures))

    def sync_post_object(
        self,
        post: FanboxPost,
        *,
        counter: "_RemainingCounter | None" = None,
        done: int = 0,
    ) -> FanboxPostResult:
        post_key = make_post_key(FANBOX_SOURCE, post.post_id)
        existing = self.post_store.find_post(post_key)
        self._report_progress(
            stage="post_started",
            message="fanbox post started",
            post_id=post.post_id,
            creator_id=post.creator.creator_id,
            post_type=post.post_type,
            file_count=len(post.files),
            locked=post.is_locked or None,
            sync_count=done,
            progress=counter.percent(done) if counter is not None else None,
        )

        assets: list[FanboxAssetResult] = []
        attachments: list[PostAttachment] = []
        wanted = [item for item in post.files if self._wants(item)]
        contents = self._download_files(wanted) if self.download_media else {}
        for index, item in enumerate(post.files):
            content = contents.get(item.file_id)
            if content is None:
                attachments.append(_remote_attachment(item))
                continue
            asset, attachment = self._store_file(post, item, content, index)
            if asset is not None:
                assets.append(asset)
            attachments.append(attachment)

        record = _post_from_fanbox(
            post,
            attachments=tuple(attachments),
            uploader_user_id=self.uploader_user_id,
            uploader_username=self.uploader_username,
        )
        self.post_store.write_post(record)
        status = "updated" if existing is not None else "created"
        self._report_progress(
            stage="post_done",
            message="fanbox post completed",
            post_id=post.post_id,
            post_key=post_key,
            result_status=status,
            asset_count=len(assets),
            sync_count=done + 1,
            progress=counter.percent(done + 1) if counter is not None else None,
        )
        return FanboxPostResult(
            post_id=post.post_id,
            post_key=post_key,
            status=status,
            assets=tuple(assets),
            locked=post.is_locked,
        )

    def _hydrate(self, post: FanboxPost) -> FanboxPost:
        """Timeline pages carry summaries only; post.info is the sole source of bodies, and it needs a session."""
        if post.post_type != "summary" or self.client is None:
            return post
        if not self.client.is_authenticated:
            return post
        try:
            return self.client.get_post(post.post_id)
        except FanboxError as exc:
            self._report_progress(
                stage="post_locked",
                message="fanbox post detail unavailable",
                post_id=post.post_id,
                error=str(exc),
            )
            return post

    def _wants(self, item: FanboxFile) -> bool:
        return bool(item.url) and (item.is_image or self.download_files)

    def _download_files(self, pending: list[FanboxFile]) -> dict[str, bytes]:
        if not pending or self.downloader is None:
            return {}
        if len(pending) == 1 or self.download_concurrency == 1:
            return {item.file_id: data for item in pending if (data := self._download_one(item)) is not None}
        with ThreadPoolExecutor(max_workers=min(self.download_concurrency, len(pending))) as pool:
            downloaded = list(pool.map(self._download_one, pending))
        return {item.file_id: data for item, data in zip(pending, downloaded) if data is not None}

    def _download_one(self, item: FanboxFile) -> bytes | None:
        try:
            return self.downloader.download(item.url) if self.downloader is not None else None
        except FanboxError as exc:
            self._report_progress(
                stage="file_failed",
                message="fanbox media download failed",
                file_id=item.file_id,
                url=item.url,
                error=str(exc),
            )
            return None

    def _asset_identity(self, post: FanboxPost, item: FanboxFile, index: int) -> tuple[str, int | None]:
        """Post-id naming groups a post's files into <post>_p0/_p1 so the gallery pager works like Pixiv."""
        if self.name_media_by_post_id:
            return post.post_id, index
        return item.file_id, None

    def _store_file(
        self,
        post: FanboxPost,
        item: FanboxFile,
        content: bytes,
        index: int = 0,
    ) -> tuple[FanboxAssetResult | None, PostAttachment]:
        source_id, page_index = self._asset_identity(post, item, index)
        asset_key = make_asset_key(FANBOX_SOURCE, source_id, page_index)
        if self.storage.find_metadata_path(asset_key) is not None:
            metadata = self.storage.read_metadata(asset_key)
            return (
                FanboxAssetResult(
                    asset_key=asset_key,
                    status="skipped",
                    original_path=metadata.original_path,
                    file_sha256=metadata.file_sha256,
                    kind=item.kind,
                ),
                _linked_attachment(item, asset_key),
            )

        stored = self.storage.write_original(
            asset_key,
            fanbox_media_filename(post.published_at, item),
            content,
            strategy_name=self.storage_strategy_name,
            content_type=item.mime_type,
        )
        duplicate = self.storage.find_by_sha256(stored.sha256, exclude_asset_key=asset_key)
        extra: dict[str, Any] = {
            "fanbox_post_id": post.post_id,
            "fanbox_post_url": post.url,
            "fanbox_post_type": post.post_type,
            "fanbox_file_id": item.file_id,
            "fanbox_file_url": item.url,
            "fanbox_file_kind": item.kind,
            "fanbox_creator_id": post.creator.creator_id,
            "fanbox_user_id": post.creator.user_id,
            "fanbox_fee_required": post.fee_required,
        }
        if item.name:
            extra["fanbox_file_name"] = item.filename
        if item.size is not None:
            extra["fanbox_file_size"] = item.size
        metadata = GalleryMetadata(
            source=FANBOX_SOURCE,
            source_id=source_id,
            page_index=page_index,
            title=post.title or _plain_excerpt(post.text),
            artist_id=post.creator.user_id or post.creator.creator_id,
            artist_name=post.creator.display_name,
            original_url=post.url,
            crawl_time=utc_now_iso(),
            file_sha256=stored.sha256,
            original_filename=stored.filename,
            original_path=stored.relative_path,
            pixiv_tags=post.tags,
            canonical_tags=(),
            width=item.width,
            height=item.height,
            mime_type=item.mime_type,
            source_type=post.post_type,
            artwork_date=(post.published_at or "")[:10] or None,
            age_rating="r18" if post.has_adult_content else None,
            uploader_user_id=self.uploader_user_id,
            uploader_username=self.uploader_username,
            extra=extra,
        )
        self.storage.write_metadata(metadata, replace=True)
        if duplicate is not None:
            status, duplicate_of = "duplicate", duplicate.asset_key
        elif stored.was_existing:
            status, duplicate_of = "reused_original", None
        else:
            status, duplicate_of = "downloaded", None
        return (
            FanboxAssetResult(
                asset_key=asset_key,
                status=status,
                original_path=stored.relative_path,
                file_sha256=stored.sha256,
                kind=item.kind,
                duplicate_of=duplicate_of,
            ),
            _linked_attachment(item, asset_key),
        )

    def _archived_post_ids(self, creator: FanboxCreator) -> frozenset[str]:
        """Already-stored post ids for this creator; ends the newest-first walk and drives incremental re-runs."""
        return frozenset(
            post.source_id
            for post in self.post_store.iter_posts()
            if post.source == FANBOX_SOURCE and post.author_handle == creator.creator_id
        )

    def _report_progress(self, **event: object) -> None:
        if self.progress is None:
            return
        self.progress({key: value for key, value in event.items() if value is not None})


class _RemainingCounter:
    """Tracks how many posts a run still expects to fetch, for progress reporting."""

    def __init__(self, *, total: int | None, archived: int, limit: int | None) -> None:
        self.total = total if isinstance(total, int) and total > 0 else None
        self.archived = max(0, archived)
        self.limit = limit
        self.pages = 0

    def target(self) -> int | None:
        if self.limit is not None:
            return max(0, self.limit)
        return self.total

    def remaining(self, done: int) -> int | None:
        target = self.target()
        return None if target is None else max(0, target - done)

    def percent(self, done: int) -> float | None:
        target = self.target()
        if target is None:
            return None
        if target == 0:
            return 100.0
        return round(min(100.0, done / target * 100), 2)


def exchange_pixiv_cookie_for_fanbox_session(
    pixiv_cookie: str,
    *,
    headless: bool = True,
    timeout_seconds: int = 120,
    proxy_url: str | None = None,
) -> str:
    """Completes the Fanbox login chain.

    Fanbox does not accept a Pixiv cookie directly: it authenticates with its own FANBOXSESSID on .fanbox.cc,
    while Pixiv uses PHPSESSID on .pixiv.net. But https://www.fanbox.cc/login redirects to accounts.pixiv.net
    with return_to=/auth/start, so a browser already holding a valid Pixiv session gets a FANBOXSESSID issued.
    """
    from nyagallery.pixiv import _pixiv_playwright_cookies, _playwright_proxy_config

    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise FanboxAuthError(
            'Install browser login support with: python -m pip install -e ".[pixiv-login]"'
        ) from exc

    cookies = _pixiv_playwright_cookies(pixiv_cookie)
    if not cookies:
        raise FanboxAuthError("Pixiv session cookie did not contain usable cookie pairs")

    timeout_ms = max(1, int(timeout_seconds)) * 1000
    launch_kwargs: dict[str, object] = {"headless": headless}
    if proxy_url:
        launch_kwargs["proxy"] = _playwright_proxy_config(proxy_url)
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(**launch_kwargs)
            try:
                context = browser.new_context(user_agent=FANBOX_USER_AGENT)
                context.add_cookies(cookies)
                page = context.new_page()
                page.goto(FANBOX_LOGIN_URL, wait_until="domcontentloaded", timeout=timeout_ms)
                session_id = _wait_for_fanbox_session(context, page, timeout_seconds=timeout_seconds)
                if not session_id:
                    raise FanboxAuthError(
                        "Fanbox did not issue a session; the Pixiv cookie may be expired or need re-consent"
                    )
                return session_id
            finally:
                browser.close()
    except PlaywrightTimeoutError as exc:
        raise FanboxAuthError("Fanbox login timed out before a session cookie was issued") from exc
    except PlaywrightError as exc:
        raise FanboxAuthError(f"Fanbox login browser failed: {exc}") from exc


def _wait_for_fanbox_session(context: Any, page: Any, *, timeout_seconds: int) -> str:
    deadline = time.monotonic() + max(1, timeout_seconds)
    visited_home = False
    while time.monotonic() < deadline:
        for cookie in context.cookies():
            if str(cookie.get("name") or "") == FANBOX_SESSION_COOKIE and cookie.get("value"):
                return str(cookie["value"])
        current = str(getattr(page, "url", "") or "")
        if "accounts.pixiv.net" in current and not visited_home:
            # The Pixiv session is present but Fanbox has not been entered yet; nudge it through /auth/start.
            visited_home = True
            try:
                page.goto(f"{FANBOX_WEB_ORIGIN}/auth/start", wait_until="domcontentloaded", timeout=15_000)
            except Exception:  # noqa: BLE001 - navigation races are retried by the surrounding loop
                pass
        time.sleep(0.5)
    return ""


def normalize_creator_id(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    match = _CREATOR_HANDLE_RE.search(text)
    if match:
        return match.group(1)
    if "fanbox.cc" in text:
        subdomain = _CREATOR_SUBDOMAIN_RE.search(text)
        if subdomain and subdomain.group(1) not in {"www", "api", "downloads"}:
            return subdomain.group(1)
    return re.sub(r"[^A-Za-z0-9_-]+", "", text.lstrip("@"))


def extract_post_id(value: Any) -> str:
    text = str(value or "").strip()
    for pattern in (_POST_URL_RE, _LEGACY_POST_URL_RE):
        match = pattern.search(text)
        if match:
            return match.group(1)
    if _POST_ID_RE.match(text):
        return text
    raise FanboxError(f"not a valid Fanbox post URL or id: {value}")


def split_batch_input(value: Any) -> list[str]:
    return [item.strip() for item in re.split(r"[\s,，;；|｜]+", str(value or "")) if item.strip()]


def normalize_page_size(value: Any) -> int:
    try:
        size = int(value)
    except (TypeError, ValueError):
        return FANBOX_PAGE_SIZE
    return max(1, min(FANBOX_MAX_PAGE_SIZE, size))


def parse_fanbox_datetime(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S"):
        try:
            parsed = datetime.strptime(text, fmt)
        except ValueError:
            continue
        if parsed.tzinfo is None:
            return parsed.strftime("%Y-%m-%dT%H:%M:%SZ")
        return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return text


def fanbox_media_filename(published_at: str, item: FanboxFile) -> str:
    """Readable archival filename: <date>_<name or id>.<extension>."""
    stem = re.sub(r"[\\/:*?\"<>|]+", "_", item.name or item.file_id).strip(" ._") or item.file_id
    suffix = f".{item.extension}" if item.extension else ""
    prefix = (published_at or "")[:10]
    return f"{prefix}_{stem}{suffix}" if prefix else f"{stem}{suffix}"


def _creator_from_payload(body: dict[str, Any], *, fallback_id: str = "") -> FanboxCreator:
    user = body.get("user") if isinstance(body.get("user"), dict) else {}
    return FanboxCreator(
        creator_id=str(body.get("creatorId") or fallback_id),
        user_id=str(user.get("userId") or ""),
        name=str(user.get("name") or ""),
        icon_url=str(user.get("iconUrl") or ""),
        description=str(body.get("description") or ""),
        cover_image_url=str(body.get("coverImageUrl") or ""),
        has_adult_content=bool(body.get("hasAdultContent")),
        is_supported=bool(body.get("isSupported")),
    )


def _file_kind(extension: str) -> str:
    ext = str(extension or "").lower().lstrip(".")
    if ext in _IMAGE_EXTENSIONS:
        return "image"
    if ext in {"wav", "mp3", "flac"}:
        return "music"
    if ext in {"mp4", "mov", "avi"}:
        return "video"
    if ext == "zip":
        return "compressed"
    if ext in {"psd", "clip"}:
        return "ps"
    return "other"


def _image_file(data: dict[str, Any]) -> FanboxFile | None:
    url = str(data.get("originalUrl") or "")
    if not url:
        return None
    extension = str(data.get("extension") or "").lstrip(".") or Path(urlparse(url).path).suffix.lstrip(".")
    return FanboxFile(
        file_id=str(data.get("id") or Path(urlparse(url).path).stem),
        kind="image",
        url=url,
        thumbnail_url=str(data.get("thumbnailUrl") or ""),
        extension=extension,
        width=_optional_int(data.get("width")),
        height=_optional_int(data.get("height")),
    )


def _attachment_file(data: dict[str, Any]) -> FanboxFile | None:
    url = str(data.get("url") or "")
    if not url:
        return None
    extension = str(data.get("extension") or "").lstrip(".") or Path(urlparse(url).path).suffix.lstrip(".")
    return FanboxFile(
        file_id=str(data.get("id") or Path(urlparse(url).path).stem),
        kind=_file_kind(extension),
        url=url,
        name=str(data.get("name") or ""),
        extension=extension,
        size=_optional_int(data.get("size")),
    )


def _entry_files(html_text: str) -> list[FanboxFile]:
    """entry posts only ship rendered HTML; the <a href> around each <img> is the full-size original."""
    files: list[FanboxFile] = []
    seen: set[str] = set()
    for url in _ENTRY_ANCHOR_RE.findall(html_text or ""):
        target = html_module.unescape(url)
        if target in seen:
            continue
        seen.add(target)
        extension = Path(urlparse(target).path).suffix.lstrip(".")
        files.append(
            FanboxFile(
                file_id=Path(urlparse(target).path).stem,
                kind=_file_kind(extension),
                url=target,
                extension=extension,
            )
        )
    return files


def _html_to_text(html_text: str) -> str:
    broken = _HTML_BREAK_RE.sub("\n", html_text or "")
    return html_module.unescape(_HTML_TAG_RE.sub("", broken)).strip()


def _body_content(body: Any) -> tuple[str, list[FanboxFile]]:
    """Fanbox ships six body shapes; normalise them all into plain text plus an ordered file list."""
    if not isinstance(body, dict):
        return "", []
    files: list[FanboxFile] = []

    if isinstance(body.get("html"), str):
        return _html_to_text(body["html"]), _entry_files(body["html"])

    blocks = body.get("blocks")
    if isinstance(blocks, list):
        image_map = body.get("imageMap") if isinstance(body.get("imageMap"), dict) else {}
        file_map = body.get("fileMap") if isinstance(body.get("fileMap"), dict) else {}
        lines: list[str] = []
        for block in blocks:
            if not isinstance(block, dict):
                continue
            kind = str(block.get("type") or "")
            if kind == "image":
                entry = image_map.get(str(block.get("imageId") or ""))
                parsed = _image_file(entry) if isinstance(entry, dict) else None
                if parsed is not None:
                    files.append(parsed)
            elif kind == "file":
                entry = file_map.get(str(block.get("fileId") or ""))
                parsed = _attachment_file(entry) if isinstance(entry, dict) else None
                if parsed is not None:
                    files.append(parsed)
            elif block.get("text") is not None:
                lines.append(str(block.get("text") or ""))
        return "\n".join(lines).strip(), files

    text = str(body.get("text") or "")
    for item in body.get("images") or []:
        if isinstance(item, dict):
            parsed = _image_file(item)
            if parsed is not None:
                files.append(parsed)
    for item in body.get("files") or []:
        if isinstance(item, dict):
            parsed = _attachment_file(item)
            if parsed is not None:
                files.append(parsed)
    video = body.get("video")
    if isinstance(video, dict) and video.get("videoId"):
        provider = str(video.get("serviceProvider") or "")
        text = f"{text}\n[{provider}:{video['videoId']}]".strip()
    return text.strip(), files


def _list_entries(payload: Any) -> list[dict[str, Any]]:
    """post.listCreator answers with body.posts; the supporting feed still uses body.items."""
    body = payload.get("body") if isinstance(payload, dict) else None
    if isinstance(body, list):
        return [item for item in body if isinstance(item, dict)]
    if not isinstance(body, dict):
        return []
    for key in ("posts", "items"):
        value = body.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _cover_url(data: dict[str, Any]) -> str:
    cover = data.get("cover")
    if isinstance(cover, dict):
        return str(cover.get("url") or "")
    return str(data.get("coverImageUrl") or "")


def _post_from_payload(data: dict[str, Any]) -> FanboxPost:
    user = data.get("user") if isinstance(data.get("user"), dict) else {}
    creator = FanboxCreator(
        creator_id=str(data.get("creatorId") or ""),
        user_id=str(user.get("userId") or ""),
        name=str(user.get("name") or ""),
        icon_url=str(user.get("iconUrl") or ""),
        has_adult_content=bool(data.get("hasAdultContent")),
    )
    text, files = _body_content(data.get("body"))
    tags = data.get("tags")
    return FanboxPost(
        post_id=str(data.get("id") or ""),
        creator=creator,
        title=str(data.get("title") or ""),
        post_type=str(data.get("type") or "") or ("summary" if data.get("body") is None else "text"),
        text=text,
        excerpt=str(data.get("excerpt") or ""),
        published_at=parse_fanbox_datetime(data.get("publishedDatetime")),
        updated_at=parse_fanbox_datetime(data.get("updatedDatetime")),
        cover_image_url=_cover_url(data),
        fee_required=_optional_int(data.get("feeRequired")) or 0,
        is_restricted=bool(data.get("isRestricted")) or data.get("body") is None,
        has_adult_content=bool(data.get("hasAdultContent")),
        tags=tuple(str(tag) for tag in tags) if isinstance(tags, list) else (),
        files=tuple(files),
        like_count=_optional_int(data.get("likeCount")) or 0,
        comment_count=_optional_int(data.get("commentCount")) or 0,
    )


def _post_from_fanbox(
    post: FanboxPost,
    *,
    attachments: tuple[PostAttachment, ...],
    uploader_user_id: int | None,
    uploader_username: str | None,
) -> GalleryPost:
    extra: dict[str, Any] = {
        "fanbox_post_id": post.post_id,
        "fanbox_creator_id": post.creator.creator_id,
        "fanbox_post_type": post.post_type,
        "fanbox_fee_required": post.fee_required,
    }
    if post.cover_image_url:
        extra["fanbox_cover_image_url"] = post.cover_image_url
    if post.is_locked:
        extra["fanbox_locked"] = True
    if post.updated_at:
        extra["fanbox_updated_at"] = post.updated_at
    if uploader_user_id is not None:
        extra["uploader_user_id"] = uploader_user_id
    if uploader_username:
        extra["uploader_username"] = uploader_username
    body = post.text or post.excerpt
    content = f"{post.title}\n\n{body}".strip() if post.title and body else (post.title or body)
    return GalleryPost(
        source=FANBOX_SOURCE,
        source_id=post.post_id,
        author_id=post.creator.user_id,
        author_name=post.creator.display_name,
        author_handle=post.creator.creator_id,
        author_avatar_url=post.creator.icon_url,
        content=content,
        content_warning="R-18" if post.has_adult_content else "",
        posted_at=post.published_at,
        crawl_time=utc_now_iso(),
        source_url=post.url,
        visibility="supporters" if post.fee_required > 0 else "public",
        age_rating="r18" if post.has_adult_content else None,
        tags=post.tags,
        attachments=attachments,
        metrics={"likes": post.like_count, "replies": post.comment_count},
        extra=extra,
    )


def _linked_attachment(item: FanboxFile, asset_key: str) -> PostAttachment:
    return PostAttachment(
        asset_key=asset_key,
        remote_url=item.url,
        thumbnail_url=item.thumbnail_url,
        mime_type=item.mime_type,
        width=item.width,
        height=item.height,
        description=item.filename if not item.is_image else "",
    )


def _remote_attachment(item: FanboxFile) -> PostAttachment:
    return PostAttachment(
        remote_url=item.url,
        thumbnail_url=item.thumbnail_url,
        mime_type=item.mime_type,
        width=item.width,
        height=item.height,
        description=item.filename if not item.is_image else "",
    )


def _plain_excerpt(text: str) -> str:
    return " ".join((text or "").split())[:120]


def _optional_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _fanbox_proxy_opener(proxy_url: str, *, ipv4_only: bool = True):
    handlers = list(ipv4_only_handlers()) if ipv4_only else []
    url = str(proxy_url or "").strip()
    if url:
        handlers.append(ProxyHandler({"http": url, "https": url}))
    return build_opener(*handlers) if handlers else None


def _retry_after_seconds(exc: HTTPError, options: FanboxRequestOptions, attempt: int) -> int:
    header = exc.headers.get("Retry-After") if exc.headers else None
    if header:
        try:
            return max(1, min(int(float(header)), options.retry_max_seconds))
        except (TypeError, ValueError):
            pass
    backoff = options.retry_base_seconds * (2 ** attempt)
    return max(1, min(backoff, options.retry_max_seconds))


def _error_suffix(exc: HTTPError) -> str:
    try:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
    except Exception:
        return ""
    return f": {detail}" if detail else ""
