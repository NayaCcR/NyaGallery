from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import json
import mimetypes
from pathlib import Path
import re
import time
from typing import Any, Callable, Iterator
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import ProxyHandler, Request, build_opener, urlopen

from nyagallery.metadata import GalleryMetadata, make_asset_key, utc_now_iso
from nyagallery.posts import GalleryPost, PostAttachment, PostStore, make_post_key
from nyagallery.security import OutboundRequestError, assert_outbound_url, ipv4_only_handlers
from nyagallery.storage import GalleryStorage


MISSKEY_DEFAULT_HOST = "misskey.io"
MISSKEY_NOTES_PAGE_SIZE = 100
MISSKEY_SOURCE = "misskey"
_HASHTAG_RE = re.compile(r"#(\w+)")


class MisskeyError(RuntimeError):
    pass


class MisskeyRateLimitError(MisskeyError):
    def __init__(self, message: str = "Misskey rate limit exceeded", *, retry_after_seconds: int | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


ProgressCallback = Callable[[dict[str, object]], None]


@dataclass(frozen=True)
class MisskeyRequestOptions:
    request_delay_seconds: float = 1.0
    max_retries: int = 3
    retry_base_seconds: int = 60
    retry_max_seconds: int = 300
    download_concurrency: int = 5
    proxy_url: str = ""
    max_download_bytes: int = 256 * 1024 * 1024
    allow_private_hosts: bool = False
    ipv4_only: bool = True


@dataclass(frozen=True)
class MisskeyUser:
    user_id: str
    username: str
    name: str = ""
    host: str = ""
    avatar_url: str = ""
    notes_count: int | None = None

    @property
    def handle(self) -> str:
        return f"{self.username}@{self.host}" if self.host else self.username

    @property
    def display_name(self) -> str:
        return self.name or self.username


@dataclass(frozen=True)
class MisskeyFile:
    file_id: str
    name: str = ""
    mime_type: str = ""
    url: str = ""
    thumbnail_url: str = ""
    size: int | None = None
    width: int | None = None
    height: int | None = None
    comment: str = ""
    is_sensitive: bool = False


@dataclass(frozen=True)
class MisskeyNote:
    note_id: str
    user: MisskeyUser
    created_at: str = ""
    text: str = ""
    cw: str = ""
    files: tuple[MisskeyFile, ...] = ()
    reply_id: str = ""
    renote_id: str = ""
    visibility: str = "public"
    tags: tuple[str, ...] = ()
    replies_count: int = 0
    renote_count: int = 0
    reactions_count: int = 0
    host: str = MISSKEY_DEFAULT_HOST
    origin: str = f"https://{MISSKEY_DEFAULT_HOST}"

    @property
    def url(self) -> str:
        return f"{self.origin}/notes/{self.note_id}"

    def note_url(self, note_id: str) -> str:
        return f"{self.origin}/notes/{note_id}"


@dataclass(frozen=True)
class MisskeyAssetResult:
    asset_key: str
    status: str
    original_path: str
    file_sha256: str
    duplicate_of: str | None = None


@dataclass(frozen=True)
class MisskeyNoteResult:
    note_id: str
    post_key: str
    status: str
    assets: tuple[MisskeyAssetResult, ...] = ()


class MisskeyHTTP:
    def __init__(
        self,
        *,
        token: str = "",
        host: str = MISSKEY_DEFAULT_HOST,
        timeout: int = 60,
        options: MisskeyRequestOptions | None = None,
        proxy_url: str | None = None,
    ) -> None:
        self.token = token.strip()
        self.host = normalize_misskey_host(host)
        self.origin = misskey_origin(host)
        self.timeout = timeout
        self.options = options or MisskeyRequestOptions()
        self.proxy_url = str(proxy_url or self.options.proxy_url or "").strip()
        self._opener = _misskey_opener(self.proxy_url, ipv4_only=self.options.ipv4_only)
        self._last_request_at = 0.0

    @property
    def api_base(self) -> str:
        return f"{self.origin}/api"

    def post_json(self, endpoint: str, body: dict[str, Any]) -> Any:
        payload = dict(body)
        if self.token:
            payload.setdefault("i", self.token)
        data = json.dumps(payload).encode("utf-8")
        raw = self._request(
            f"{self.api_base}/{endpoint.strip('/')}",
            data=data,
            content_type="application/json",
            spaced=True,
        )
        if not raw:
            return None
        return json.loads(raw.decode("utf-8"))

    def get_bytes(self, url: str) -> bytes:
        return self._request(url, spaced=False)

    def _request(
        self,
        url: str,
        *,
        data: bytes | None = None,
        content_type: str = "",
        spaced: bool = True,
    ) -> bytes:
        try:
            url = assert_outbound_url(
                url,
                allow_private=self.options.allow_private_hosts,
                ipv4_only=self.options.ipv4_only,
            )
        except OutboundRequestError as exc:
            raise MisskeyError(str(exc)) from exc
        last_error: Exception | None = None
        attempts = max(1, self.options.max_retries + 1)
        for attempt in range(attempts):
            if spaced:
                self._wait_for_spacing()
            try:
                request = Request(url, data=data, headers=self._headers(content_type), method="POST" if data else "GET")
                with self._open(request) as response:
                    self._last_request_at = time.monotonic()
                    return self._read_capped(response, url)
            except HTTPError as exc:
                self._last_request_at = time.monotonic()
                if exc.code == 429:
                    retry_after = _retry_after_seconds(exc, self.options, attempt)
                    last_error = MisskeyRateLimitError(retry_after_seconds=retry_after)
                    if attempt >= attempts - 1:
                        raise last_error
                    time.sleep(retry_after)
                    continue
                detail = _error_detail(exc)
                raise MisskeyError(f"{exc.code} {url}{f': {detail}' if detail else ''}") from exc
            except OSError as exc:
                last_error = MisskeyError(f"request failed: {url}: {exc}")
                if attempt >= attempts - 1:
                    raise last_error from exc
                time.sleep(min(2 ** attempt, self.options.retry_max_seconds))
        if last_error:
            raise last_error
        raise MisskeyError(f"failed to request Misskey URL: {url}")

    def _read_capped(self, response, url: str) -> bytes:
        cap = max(0, int(self.options.max_download_bytes or 0))
        if not cap:
            return response.read()
        body = response.read(cap + 1)
        if len(body) > cap:
            raise MisskeyError(f"response exceeds {cap} bytes: {url}")
        return body

    def _open(self, request: Request):
        if self._opener is not None:
            return self._opener.open(request, timeout=self.timeout)
        return urlopen(request, timeout=self.timeout)  # noqa: S310

    def _headers(self, content_type: str = "") -> dict[str, str]:
        headers = {
            "Accept": "application/json, image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
            "User-Agent": "NyaGallery/0.1 (+https://github.com/NayaCcR/NyaGallery)",
        }
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    def _wait_for_spacing(self) -> None:
        delay = max(0.0, float(self.options.request_delay_seconds))
        if delay <= 0:
            return
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < delay:
            time.sleep(delay - elapsed)


class MisskeyClient:
    def __init__(
        self,
        *,
        token: str = "",
        host: str = MISSKEY_DEFAULT_HOST,
        options: MisskeyRequestOptions | None = None,
        proxy_url: str | None = None,
    ) -> None:
        self.host = normalize_misskey_host(host)
        self.origin = misskey_origin(host)
        self.options = options or MisskeyRequestOptions()
        self.http = MisskeyHTTP(token=token, host=host, options=self.options, proxy_url=proxy_url)

    def get_user(self, username: str) -> MisskeyUser:
        handle = str(username or "").strip().lstrip("@")
        if not handle:
            raise MisskeyError("Misskey username is required")
        local, _, remote = handle.partition("@")
        data = self.http.post_json("users/show", {"username": local, "host": remote or None})
        if not isinstance(data, dict) or not data.get("id"):
            raise MisskeyError(f"Misskey user not found: {username}")
        return _user_from_payload(data, default_host=self.host)

    def iter_user_notes(
        self,
        user_id: str,
        *,
        limit: int | None = None,
        until_id: str = "",
        stop_ids: frozenset[str] = frozenset(),
        include_replies: bool = True,
        page_size: int = MISSKEY_NOTES_PAGE_SIZE,
        max_pages: int | None = None,
        on_page: Callable[[dict[str, object]], None] | None = None,
    ) -> Iterator[MisskeyNote]:
        """Page a user's notes newest-first. until_id resumes older than that id; stop_ids ends the walk."""
        seen = 0
        page = 0
        cursor = str(until_id or "")
        size = normalize_page_size(page_size)
        while True:
            if max_pages is not None and page >= max_pages:
                return
            body: dict[str, Any] = {
                "userId": str(user_id),
                "limit": size if limit is None else max(1, min(size, limit - seen)),
                "includeReplies": include_replies,
            }
            if cursor:
                body["untilId"] = cursor
            payload = self.http.post_json("users/notes", body)
            notes = payload if isinstance(payload, list) else []
            page += 1
            if on_page is not None:
                on_page({"page": page, "page_notes": len(notes), "page_size": size, "until_id": cursor})
            if not notes:
                return
            for item in notes:
                if not isinstance(item, dict) or not item.get("id"):
                    continue
                if str(item["id"]) in stop_ids:
                    return
                yield _note_from_payload(item, default_host=self.host, origin=self.origin)
                seen += 1
                if limit is not None and seen >= limit:
                    return
            cursor = str(notes[-1].get("id") or "")
            if not cursor:
                return


class MisskeyDownloader:
    def __init__(
        self,
        *,
        host: str = MISSKEY_DEFAULT_HOST,
        timeout: int = 60,
        options: MisskeyRequestOptions | None = None,
        proxy_url: str | None = None,
    ) -> None:
        self.origin = misskey_origin(host)
        base = options or MisskeyRequestOptions()
        media_options = MisskeyRequestOptions(
            request_delay_seconds=0.0,
            max_retries=base.max_retries,
            retry_base_seconds=base.retry_base_seconds,
            retry_max_seconds=base.retry_max_seconds,
            download_concurrency=base.download_concurrency,
            proxy_url=base.proxy_url,
        )
        self.http = MisskeyHTTP(host=host, timeout=timeout, options=media_options, proxy_url=proxy_url)

    def download(self, url: str) -> bytes:
        return self.http.get_bytes(url)


class MisskeySyncService:
    """Archives Misskey notes as gallery posts and their media as immutable originals."""

    def __init__(
        self,
        storage: GalleryStorage,
        post_store: PostStore | None = None,
        client: MisskeyClient | None = None,
        downloader: MisskeyDownloader | None = None,
        *,
        uploader_user_id: int | None = None,
        uploader_username: str | None = None,
        storage_strategy_name: str | None = None,
        download_media: bool = True,
        download_concurrency: int = 5,
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
        self.download_concurrency = max(1, int(download_concurrency or 1))
        self.name_media_by_post_id = name_media_by_post_id
        self.progress = progress

    def sync_user(
        self,
        username: str,
        *,
        limit: int | None = None,
        backfill: bool = True,
        include_replies: bool = True,
        page_size: int = MISSKEY_NOTES_PAGE_SIZE,
        max_pages: int | None = None,
    ) -> list[MisskeyNoteResult]:
        if self.client is None:
            raise MisskeyError("Misskey client is required for sync_user")
        user = self.client.get_user(username)
        archived = self._archived_note_ids(user)
        oldest = min(archived) if archived else ""
        results: list[MisskeyNoteResult] = []
        counter = _RemainingCounter(
            total=user.notes_count,
            archived=len(archived),
            limit=limit,
        )
        self._report_progress(
            stage="user_started",
            message="misskey user started",
            username=user.username,
            handle=user.handle,
            user_id=user.user_id,
            notes_count=user.notes_count,
            archived_notes=len(archived),
            remaining=counter.remaining(0),
            page_size=normalize_page_size(page_size),
            max_pages=max_pages,
            progress=counter.percent(0),
        )

        def page_reporter(phase: str):
            def report(event: dict[str, object]) -> None:
                counter.pages += 1
                done = len(results)
                self._report_progress(
                    stage="page_fetched",
                    message="misskey page fetched",
                    phase=phase,
                    username=user.username,
                    page=event.get("page"),
                    page_notes=event.get("page_notes"),
                    page_size=event.get("page_size"),
                    sync_count=done,
                    remaining=counter.remaining(done),
                    notes_count=user.notes_count,
                    progress=counter.percent(done),
                )
            return report

        for note in self.client.iter_user_notes(
            user.user_id,
            limit=limit,
            stop_ids=archived,
            include_replies=include_replies,
            page_size=page_size,
            max_pages=max_pages,
            on_page=page_reporter("new"),
        ):
            results.append(self.sync_note(note, counter=counter, done=len(results)))

        if archived and backfill and (limit is None or len(results) < limit):
            pages_left = None if max_pages is None else max(0, max_pages - counter.pages)
            for note in self.client.iter_user_notes(
                user.user_id,
                limit=None if limit is None else limit - len(results),
                until_id=oldest,
                stop_ids=archived,
                include_replies=include_replies,
                page_size=page_size,
                max_pages=pages_left,
                on_page=page_reporter("backfill"),
            ):
                results.append(self.sync_note(note, counter=counter, done=len(results)))

        self._report_progress(
            stage="user_done",
            message="misskey user completed",
            username=user.username,
            handle=user.handle,
            sync_count=len(results),
            remaining=counter.remaining(len(results)),
            notes_count=user.notes_count,
            progress=100,
        )
        return results

    def sync_note(
        self,
        note: MisskeyNote,
        *,
        counter: "_RemainingCounter | None" = None,
        done: int = 0,
    ) -> MisskeyNoteResult:
        post_key = make_post_key(MISSKEY_SOURCE, note.note_id)
        existing = self.post_store.find_post(post_key)
        self._report_progress(
            stage="note_started",
            message="misskey note started",
            note_id=note.note_id,
            handle=note.user.handle,
            file_count=len(note.files),
            sync_count=done,
            remaining=counter.remaining(done) if counter is not None else None,
            progress=counter.percent(done) if counter is not None else None,
        )

        assets: list[MisskeyAssetResult] = []
        attachments: list[PostAttachment] = []
        contents = self._download_files(note) if self.download_media else {}
        for index, file in enumerate(note.files):
            content = contents.get(file.file_id)
            if content is None:
                attachments.append(_remote_attachment(file))
                continue
            asset, attachment = self._store_file(note, file, content, index)
            if asset is not None:
                assets.append(asset)
            attachments.append(attachment)

        post = _post_from_note(
            note,
            attachments=tuple(attachments),
            uploader_user_id=self.uploader_user_id,
            uploader_username=self.uploader_username,
        )
        self.post_store.write_post(post)
        status = "updated" if existing is not None else "created"
        self._report_progress(
            stage="note_done",
            message="misskey note completed",
            note_id=note.note_id,
            post_key=post_key,
            result_status=status,
            asset_count=len(assets),
            sync_count=done + 1,
            remaining=counter.remaining(done + 1) if counter is not None else None,
            progress=counter.percent(done + 1) if counter is not None else None,
        )
        return MisskeyNoteResult(
            note_id=note.note_id,
            post_key=post_key,
            status=status,
            assets=tuple(assets),
        )

    def _download_files(self, note: MisskeyNote) -> dict[str, bytes]:
        pending = [file for file in note.files if file.url]
        if not pending:
            return {}
        if self.downloader is None:
            return {}
        if len(pending) == 1 or self.download_concurrency == 1:
            return {file.file_id: content for file in pending if (content := self._download_one(file)) is not None}
        with ThreadPoolExecutor(max_workers=min(self.download_concurrency, len(pending))) as pool:
            downloaded = list(pool.map(self._download_one, pending))
        return {
            file.file_id: content
            for file, content in zip(pending, downloaded)
            if content is not None
        }

    def _download_one(self, file: MisskeyFile) -> bytes | None:
        try:
            return self.downloader.download(file.url) if self.downloader is not None else None
        except MisskeyError as exc:
            self._report_progress(
                stage="file_failed",
                message="misskey media download failed",
                file_id=file.file_id,
                url=file.url,
                error=str(exc),
            )
            return None

    def _store_file(
        self,
        note: MisskeyNote,
        file: MisskeyFile,
        content: bytes,
        index: int = 0,
    ) -> tuple[MisskeyAssetResult | None, PostAttachment]:
        source_id, page_index = self._asset_identity(note, file, index)
        asset_key = make_asset_key(MISSKEY_SOURCE, source_id, page_index)
        source_filename = misskey_media_filename(note.created_at, file)
        existing_metadata_path = self.storage.find_metadata_path(asset_key)
        if existing_metadata_path is not None:
            metadata = self.storage.read_metadata(asset_key)
            return (
                MisskeyAssetResult(
                    asset_key=asset_key,
                    status="skipped",
                    original_path=metadata.original_path,
                    file_sha256=metadata.file_sha256,
                ),
                _linked_attachment(file, asset_key),
            )

        stored = self.storage.write_original(
            asset_key,
            source_filename,
            content,
            strategy_name=self.storage_strategy_name,
            content_type=file.mime_type or None,
        )
        duplicate = self.storage.find_by_sha256(stored.sha256, exclude_asset_key=asset_key)
        extra: dict[str, Any] = {
            "misskey_note_id": note.note_id,
            "misskey_note_url": note.url,
            "misskey_file_id": file.file_id,
            "misskey_file_url": file.url,
            "misskey_file_name": file.name,
            "misskey_user_id": note.user.user_id,
            "misskey_user_handle": note.user.handle,
            "misskey_host": note.host,
        }
        if file.comment:
            extra["description"] = file.comment
        if note.cw:
            extra["misskey_cw"] = note.cw
        metadata = GalleryMetadata(
            source=MISSKEY_SOURCE,
            source_id=source_id,
            page_index=page_index,
            title=_note_title(note),
            artist_id=note.user.user_id,
            artist_name=note.user.display_name,
            original_url=note.url,
            crawl_time=utc_now_iso(),
            file_sha256=stored.sha256,
            original_filename=stored.filename,
            original_path=stored.relative_path,
            pixiv_tags=note.tags,
            canonical_tags=(),
            width=file.width,
            height=file.height,
            mime_type=file.mime_type or None,
            artwork_date=(note.created_at or "")[:10] or None,
            age_rating="r18" if file.is_sensitive else None,
            uploader_user_id=self.uploader_user_id,
            uploader_username=self.uploader_username,
            extra=extra,
        )
        self.storage.write_metadata(metadata, replace=True)
        if duplicate is not None:
            status = "duplicate"
            duplicate_of = duplicate.asset_key
        elif stored.was_existing:
            status = "reused_original"
            duplicate_of = None
        else:
            status = "downloaded"
            duplicate_of = None
        return (
            MisskeyAssetResult(
                asset_key=asset_key,
                status=status,
                original_path=stored.relative_path,
                file_sha256=stored.sha256,
                duplicate_of=duplicate_of,
            ),
            _linked_attachment(file, asset_key),
        )

    def _asset_identity(self, note: MisskeyNote, file: MisskeyFile, index: int) -> tuple[str, int | None]:
        """Post-id naming groups a note's media into <note>_p0/_p1 so the gallery pager works like Pixiv."""
        if self.name_media_by_post_id:
            return note.note_id, index
        return file.file_id, None

    def _archived_note_ids(self, user: MisskeyUser) -> frozenset[str]:
        """Already-stored note ids for this author; ends the newest-first walk and anchors backfill."""
        return frozenset(
            post.source_id
            for post in self.post_store.iter_posts()
            if post.source == MISSKEY_SOURCE and post.author_id == user.user_id
        )

    def _report_progress(self, **event: object) -> None:
        if self.progress is None:
            return
        self.progress({key: value for key, value in event.items() if value is not None})


class _RemainingCounter:
    """Tracks how many notes a run still expects to fetch, for progress reporting."""

    def __init__(self, *, total: int | None, archived: int, limit: int | None) -> None:
        self.total = total if isinstance(total, int) and total > 0 else None
        self.archived = max(0, archived)
        self.limit = limit
        self.pages = 0

    def target(self) -> int | None:
        if self.limit is not None:
            return max(0, self.limit)
        if self.total is None:
            return None
        return max(0, self.total - self.archived)

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


def normalize_misskey_host(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return MISSKEY_DEFAULT_HOST
    if "://" in text:
        parsed = urlparse(text)
        text = parsed.netloc or parsed.path
    return text.strip("/").casefold() or MISSKEY_DEFAULT_HOST


def misskey_origin(value: Any) -> str:
    """Base URL for a Misskey instance. Honours an explicit scheme so self-hosted http works."""
    text = str(value or "").strip()
    if not text:
        return f"https://{MISSKEY_DEFAULT_HOST}"
    scheme = "https"
    if "://" in text:
        parsed = urlparse(text)
        scheme = parsed.scheme or "https"
        text = parsed.netloc or parsed.path
    return f"{scheme}://{text.strip('/')}"


def normalize_page_size(value: Any) -> int:
    try:
        size = int(value)
    except (TypeError, ValueError):
        return MISSKEY_NOTES_PAGE_SIZE
    return max(1, min(MISSKEY_NOTES_PAGE_SIZE, size))


def misskey_media_filename(created_at: str, file: MisskeyFile) -> str:
    """Readable archival filename: <date>_<name><real extension>, MIME-derived to avoid double suffixes."""
    suffix = mimetypes.guess_extension(file.mime_type or "") or ""
    if suffix in {".jpe", ".jpeg"}:
        suffix = ".jpg"
    if not suffix:
        suffix = Path(urlparse(file.url).path).suffix or Path(file.name or "").suffix or ""
    stem = Path(file.name or "").stem.split(".")[0]
    safe_stem = re.sub(r"[\\/:*?\"<>|]+", "_", stem).strip(" ._") or file.file_id
    date_prefix = (created_at or "")[:10]
    return f"{date_prefix}_{safe_stem}{suffix}" if date_prefix else f"{safe_stem}{suffix}"


def extract_hashtags(text: str) -> tuple[str, ...]:
    seen: dict[str, None] = {}
    for match in _HASHTAG_RE.finditer(text or ""):
        seen.setdefault(match.group(1), None)
    return tuple(seen)


def _user_from_payload(data: dict[str, Any], *, default_host: str) -> MisskeyUser:
    return MisskeyUser(
        user_id=str(data["id"]),
        username=str(data.get("username") or ""),
        name=str(data.get("name") or ""),
        host=str(data.get("host") or "") or default_host,
        avatar_url=str(data.get("avatarUrl") or ""),
        notes_count=data.get("notesCount") if isinstance(data.get("notesCount"), int) else None,
    )


def _note_from_payload(data: dict[str, Any], *, default_host: str, origin: str = "") -> MisskeyNote:
    user_payload = data.get("user") if isinstance(data.get("user"), dict) else {}
    user = _user_from_payload({"id": "", **user_payload}, default_host=default_host)
    text = str(data.get("text") or "")
    tags = data.get("tags")
    return MisskeyNote(
        note_id=str(data["id"]),
        user=user,
        created_at=str(data.get("createdAt") or ""),
        text=text,
        cw=str(data.get("cw") or ""),
        files=tuple(_file_from_payload(item) for item in (data.get("files") or []) if isinstance(item, dict)),
        reply_id=str(data.get("replyId") or ""),
        renote_id=str(data.get("renoteId") or ""),
        visibility=str(data.get("visibility") or "public"),
        tags=tuple(str(tag) for tag in tags) if isinstance(tags, list) and tags else extract_hashtags(text),
        replies_count=_int_or_zero(data.get("repliesCount")),
        renote_count=_int_or_zero(data.get("renoteCount")),
        reactions_count=_reaction_total(data.get("reactions")),
        host=default_host,
        origin=origin or misskey_origin(default_host),
    )


def _file_from_payload(data: dict[str, Any]) -> MisskeyFile:
    properties = data.get("properties") if isinstance(data.get("properties"), dict) else {}
    return MisskeyFile(
        file_id=str(data.get("id") or ""),
        name=str(data.get("name") or ""),
        mime_type=str(data.get("type") or ""),
        url=str(data.get("url") or ""),
        thumbnail_url=str(data.get("thumbnailUrl") or ""),
        size=data.get("size") if isinstance(data.get("size"), int) else None,
        width=properties.get("width") if isinstance(properties.get("width"), int) else None,
        height=properties.get("height") if isinstance(properties.get("height"), int) else None,
        comment=str(data.get("comment") or ""),
        is_sensitive=bool(data.get("isSensitive")),
    )


def _post_from_note(
    note: MisskeyNote,
    *,
    attachments: tuple[PostAttachment, ...],
    uploader_user_id: int | None,
    uploader_username: str | None,
) -> GalleryPost:
    extra: dict[str, Any] = {
        "misskey_host": note.host,
        "misskey_note_id": note.note_id,
    }
    if note.user.avatar_url:
        extra["misskey_avatar_url"] = note.user.avatar_url
    if uploader_user_id is not None:
        extra["uploader_user_id"] = uploader_user_id
    if uploader_username:
        extra["uploader_username"] = uploader_username
    return GalleryPost(
        source=MISSKEY_SOURCE,
        source_id=note.note_id,
        author_id=note.user.user_id,
        author_name=note.user.display_name,
        author_handle=note.user.handle,
        author_avatar_url=note.user.avatar_url,
        content=note.text,
        content_warning=note.cw,
        posted_at=note.created_at,
        crawl_time=utc_now_iso(),
        source_url=note.url,
        visibility=note.visibility,
        age_rating="r18" if any(file.is_sensitive for file in note.files) else None,
        tags=note.tags,
        attachments=attachments,
        reply_to_url=note.note_url(note.reply_id) if note.reply_id else "",
        repost_of_url=note.note_url(note.renote_id) if note.renote_id else "",
        metrics={
            "likes": note.reactions_count,
            "reposts": note.renote_count,
            "replies": note.replies_count,
        },
        extra=extra,
    )


def _linked_attachment(file: MisskeyFile, asset_key: str) -> PostAttachment:
    return PostAttachment(
        asset_key=asset_key,
        remote_url=file.url,
        thumbnail_url=file.thumbnail_url,
        mime_type=file.mime_type or None,
        width=file.width,
        height=file.height,
        description=file.comment,
        is_sensitive=file.is_sensitive,
    )


def _remote_attachment(file: MisskeyFile) -> PostAttachment:
    return PostAttachment(
        remote_url=file.url,
        thumbnail_url=file.thumbnail_url,
        mime_type=file.mime_type or None,
        width=file.width,
        height=file.height,
        description=file.comment,
        is_sensitive=file.is_sensitive,
    )


def _note_title(note: MisskeyNote) -> str:
    text = " ".join((note.cw or note.text or "").split())
    return text[:120]


def _reaction_total(value: Any) -> int:
    if not isinstance(value, dict):
        return 0
    return sum(count for count in value.values() if isinstance(count, int))


def _int_or_zero(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _misskey_opener(proxy_url: str, *, ipv4_only: bool = True):
    handlers = list(ipv4_only_handlers()) if ipv4_only else []
    url = str(proxy_url or "").strip()
    if url:
        handlers.append(ProxyHandler({"http": url, "https": url}))
    return build_opener(*handlers) if handlers else None


def _retry_after_seconds(exc: HTTPError, options: MisskeyRequestOptions, attempt: int) -> int:
    header = exc.headers.get("Retry-After") if exc.headers else None
    if header:
        try:
            return max(1, min(int(float(header)), options.retry_max_seconds))
        except (TypeError, ValueError):
            pass
    backoff = options.retry_base_seconds * (2 ** attempt)
    return max(1, min(backoff, options.retry_max_seconds))


def _error_detail(exc: HTTPError) -> str:
    try:
        return exc.read().decode("utf-8", errors="replace")[:300]
    except Exception:
        return ""
