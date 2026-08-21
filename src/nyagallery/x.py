from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
import html
import json
import math
import mimetypes
from pathlib import Path
import re
import time
from typing import Any, Callable, Iterator
from urllib.error import HTTPError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import ProxyHandler, Request, build_opener, urlopen

from nyagallery.security import ipv4_only_handlers

from nyagallery.metadata import GalleryMetadata, make_asset_key, utc_now_iso
from nyagallery.posts import GalleryPost, PostAttachment, PostStore, make_post_key
from nyagallery.storage import GalleryStorage


X_SOURCE = "x"
X_DEFAULT_HOST = "x.com"
X_TIMELINE_PAGE_SIZE = 20
X_MAX_PAGE_SIZE = 100
X_PUBLIC_BEARER_TOKEN = (
    "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D"
    "1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
)
X_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

_BASE36_DIGITS = "0123456789abcdefghijklmnopqrstuvwxyz"
_STATUS_URL_RE = re.compile(r"(?:x|twitter)\.com/(?:i/web/)?[^/]*/?status(?:es)?/(\d+)")
_TWEET_ID_RE = re.compile(r"^\d{10,}$")
_HASHTAG_RE = re.compile(r"#(\w+)")
_BATCH_SEPARATOR_RE = re.compile(r"[\s,，;；|｜]+")
_MEDIA_HOSTS = ("https://pbs.twimg.com/", "https://video.twimg.com/")
_PHOTO_FORMATS = {".jpg": "jpg", ".jpeg": "jpg", ".png": "png", ".webp": "webp", ".gif": "gif"}
_PHOTO_MIME_TYPES = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp", "gif": "image/gif"}
_IMAGE_MAGIC = (b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n", b"RIFF", b"GIF87a", b"GIF89a")


_TOMBSTONE: dict[str, Any] = {"__tombstone__": True}


class XError(RuntimeError):
    pass


class XAuthError(XError):
    pass


class XRateLimitError(XError):
    def __init__(self, message: str = "X rate limit exceeded", *, retry_after_seconds: int | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


ProgressCallback = Callable[[dict[str, object]], None]


@dataclass(frozen=True)
class XRequestOptions:
    request_delay_seconds: float = 2.0
    max_retries: int = 3
    retry_base_seconds: int = 60
    retry_max_seconds: int = 300
    download_concurrency: int = 4
    proxy_url: str = ""
    ipv4_only: bool = True


@dataclass(frozen=True)
class XGraphqlOperations:
    """Query ids for X's private GraphQL API. X rotates these; override them in [x] when a call starts failing."""

    tweet_detail: str = "4Siu98E55GquhG52zHdY5w"
    user_by_screen_name: str = "32pL5BWe9WKeSK1MoPvFQQ"
    user_tweets: str = "V7H0Ap3_Hh2FyS75OCDO3Q"
    user_media: str = "dexO_2tohK86JDudXXG3Yw"


@dataclass(frozen=True)
class XCredentials:
    auth_token: str = ""
    ct0: str = ""

    @property
    def is_complete(self) -> bool:
        return bool(self.auth_token and self.ct0)


@dataclass(frozen=True)
class XUser:
    user_id: str
    screen_name: str
    name: str = ""
    avatar_url: str = ""
    description: str = ""
    statuses_count: int | None = None
    media_count: int | None = None
    is_protected: bool = False
    is_verified: bool = False

    @property
    def handle(self) -> str:
        return self.screen_name

    @property
    def display_name(self) -> str:
        return self.name or self.screen_name

    @property
    def profile_url(self) -> str:
        return f"https://{X_DEFAULT_HOST}/{self.screen_name}"


@dataclass(frozen=True)
class XVariant:
    url: str
    bitrate: int | None = None
    content_type: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"url": self.url, "bitrate": self.bitrate, "content_type": self.content_type}


@dataclass(frozen=True)
class XMedia:
    media_key: str
    media_type: str = "photo"
    download_url: str = ""
    download_candidates: tuple[str, ...] = ()
    poster_url: str = ""
    mime_type: str = ""
    width: int | None = None
    height: int | None = None
    duration_seconds: int | None = None
    bitrate: int | None = None
    alt_text: str = ""
    variants: tuple[XVariant, ...] = ()

    @property
    def is_video(self) -> bool:
        return self.media_type in {"video", "animated_gif"}

    @property
    def sources(self) -> tuple[str, ...]:
        return self.download_candidates or ((self.download_url,) if self.download_url else ())

    @property
    def thumbnail_url(self) -> str:
        return self.poster_url or (self.download_url if not self.is_video else "")


@dataclass(frozen=True)
class XTweet:
    tweet_id: str
    user: XUser
    created_at: str = ""
    text: str = ""
    lang: str = ""
    media: tuple[XMedia, ...] = ()
    tags: tuple[str, ...] = ()
    possibly_sensitive: bool = False
    reply_to_id: str = ""
    reply_to_screen_name: str = ""
    retweet_of_id: str = ""
    quote_of_id: str = ""
    metrics: dict[str, int] = field(default_factory=dict)

    @property
    def url(self) -> str:
        return tweet_url(self.user.screen_name, self.tweet_id)

    @property
    def reply_to_url(self) -> str:
        return tweet_url(self.reply_to_screen_name, self.reply_to_id) if self.reply_to_id else ""

    @property
    def retweet_of_url(self) -> str:
        return tweet_url("i", self.retweet_of_id) if self.retweet_of_id else ""

    @property
    def quote_of_url(self) -> str:
        return tweet_url("i", self.quote_of_id) if self.quote_of_id else ""


@dataclass(frozen=True)
class XAssetResult:
    asset_key: str
    status: str
    original_path: str
    file_sha256: str
    media_type: str = "photo"
    duplicate_of: str | None = None
    has_cover: bool = False

    @property
    def needs_transcode(self) -> bool:
        """Video originals cannot be decoded by the preview pipeline; their cover already produced the cache."""
        return self.media_type not in {"video", "animated_gif"}


@dataclass(frozen=True)
class XTweetResult:
    tweet_id: str
    post_key: str
    status: str
    assets: tuple[XAssetResult, ...] = ()


@dataclass(frozen=True)
class XPostFailure:
    target: str
    error: str
    tweet_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"target": self.target, "error": self.error, "tweet_id": self.tweet_id or None}


@dataclass(frozen=True)
class XBatchResult:
    results: tuple[XTweetResult, ...] = ()
    failures: tuple[XPostFailure, ...] = ()


class XHTTP:
    def __init__(
        self,
        *,
        credentials: XCredentials | None = None,
        timeout: int = 60,
        options: XRequestOptions | None = None,
        proxy_url: str | None = None,
    ) -> None:
        self.credentials = credentials or XCredentials()
        self.timeout = timeout
        self.options = options or XRequestOptions()
        self.proxy_url = str(proxy_url or self.options.proxy_url or "").strip()
        self._opener = _x_proxy_opener(self.proxy_url, ipv4_only=self.options.ipv4_only)
        self._last_request_at = 0.0

    def get_json(self, url: str, *, headers: dict[str, str] | None = None) -> Any:
        raw = self._request(url, headers=headers or {}, spaced=True)
        if not raw:
            return None
        return json.loads(raw.decode("utf-8"))

    def post_json(self, url: str, *, headers: dict[str, str] | None = None) -> Any:
        raw = self._request(url, data=b"", headers=headers or {}, spaced=True)
        if not raw:
            return None
        return json.loads(raw.decode("utf-8"))

    def get_bytes(self, url: str) -> bytes:
        return self._request(url, headers=self._media_headers(), spaced=False)

    def resolve_redirect(self, url: str) -> str:
        request = Request(url, headers=self._media_headers(), method="GET")
        try:
            with self._open(request) as response:
                return str(response.geturl() or url)
        except HTTPError as exc:
            return str(exc.url or url)
        except OSError as exc:
            raise XError(f"failed to resolve short URL: {url}: {exc}") from exc

    def _request(
        self,
        url: str,
        *,
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
        spaced: bool = True,
    ) -> bytes:
        last_error: Exception | None = None
        attempts = max(1, self.options.max_retries + 1)
        for attempt in range(attempts):
            if spaced:
                self._wait_for_spacing()
            try:
                request = Request(
                    url,
                    data=data,
                    headers={**self._base_headers(), **(headers or {})},
                    method="POST" if data is not None else "GET",
                )
                with self._open(request) as response:
                    self._last_request_at = time.monotonic()
                    return response.read()
            except HTTPError as exc:
                self._last_request_at = time.monotonic()
                if exc.code == 429:
                    retry_after = _retry_after_seconds(exc, self.options, attempt)
                    last_error = XRateLimitError(retry_after_seconds=retry_after)
                    if attempt >= attempts - 1:
                        raise last_error
                    time.sleep(retry_after)
                    continue
                if exc.code in {401, 403}:
                    raise XAuthError(f"{exc.code} {_short_url(url)}{_error_suffix(exc)}") from exc
                raise XError(f"{exc.code} {_short_url(url)}{_error_suffix(exc)}") from exc
            except OSError as exc:
                last_error = XError(f"request failed: {_short_url(url)}: {exc}")
                if attempt >= attempts - 1:
                    raise last_error from exc
                time.sleep(min(2 ** attempt, self.options.retry_max_seconds))
        if last_error:
            raise last_error
        raise XError(f"failed to request X URL: {_short_url(url)}")

    def _open(self, request: Request):
        if self._opener is not None:
            return self._opener.open(request, timeout=self.timeout)
        return urlopen(request, timeout=self.timeout)  # noqa: S310

    def _base_headers(self) -> dict[str, str]:
        return {"User-Agent": X_USER_AGENT, "Accept-Language": "en"}

    def _media_headers(self) -> dict[str, str]:
        return {"Accept": "image/avif,image/webp,image/apng,image/*,video/*,*/*;q=0.8"}

    def _wait_for_spacing(self) -> None:
        delay = max(0.0, float(self.options.request_delay_seconds))
        if delay <= 0:
            return
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < delay:
            time.sleep(delay - elapsed)


class XClient:
    """Reads public posts through X's syndication endpoint, falling back to guest and session GraphQL."""

    def __init__(
        self,
        *,
        credentials: XCredentials | None = None,
        options: XRequestOptions | None = None,
        operations: XGraphqlOperations | None = None,
        proxy_url: str | None = None,
    ) -> None:
        self.credentials = credentials or XCredentials()
        self.options = options or XRequestOptions()
        self.operations = operations or XGraphqlOperations()
        self.http = XHTTP(
            credentials=self.credentials,
            options=self.options,
            proxy_url=proxy_url,
        )
        self._guest_token = ""

    @property
    def is_authenticated(self) -> bool:
        return self.credentials.is_complete

    def guest_token(self) -> str:
        if self._guest_token:
            return self._guest_token
        payload = self.http.post_json(
            "https://api.x.com/1.1/guest/activate.json",
            headers={
                "Authorization": f"Bearer {X_PUBLIC_BEARER_TOKEN}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        token = str((payload or {}).get("guest_token") or "")
        if not token:
            raise XError("X did not issue a guest token")
        self._guest_token = token
        return token

    def get_tweet(self, target: str) -> XTweet:
        """A session reads repost/view counts and longform text that syndication omits, so it goes first when present."""
        tweet_id = self.resolve_tweet_id(target)
        errors: list[str] = []
        readers = [self._read_graphql, self._read_syndication]
        if not self.is_authenticated:
            readers.reverse()
        for reader in readers:
            try:
                tweet = reader(tweet_id)
            except XError as exc:
                errors.append(f"{reader.__name__.removeprefix('_read_')}: {exc}")
                continue
            if tweet is not None:
                return tweet
            errors.append(f"{reader.__name__.removeprefix('_read_')}: post not present in response")
        raise XError(f"X post {tweet_id} could not be read ({'; '.join(errors) or 'no data'})")

    def _read_syndication(self, tweet_id: str) -> XTweet | None:
        payload = self._syndication(tweet_id)
        if payload is _TOMBSTONE:
            raise XAuthError(
                "X hid this post from logged-out viewers (sensitive, protected, or withheld); "
                "save an X session (auth_token + ct0) to archive it"
            )
        return None if payload is None else _tweet_from_syndication(payload, tweet_id)

    def _read_graphql(self, tweet_id: str) -> XTweet | None:
        return _tweet_from_tweet_detail(self._graphql_tweet_detail(tweet_id), tweet_id)

    def get_user(self, screen_name: str) -> XUser:
        handle = normalize_screen_name(screen_name)
        if not handle:
            raise XError("X username is required")
        variables = {"screen_name": handle, "withSafetyModeUserFields": True}
        features = {
            "hidden_profile_likes_enabled": True,
            "hidden_profile_subscriptions_enabled": True,
            "responsive_web_graphql_exclude_directive_enabled": True,
            "verified_phone_label_enabled": False,
            "subscriptions_verification_info_is_identity_verified_enabled": True,
            "subscriptions_verification_info_verified_since_enabled": True,
            "highlights_tweets_tab_ui_enabled": True,
            "responsive_web_twitter_article_notes_tab_enabled": True,
            "creator_subscriptions_tweet_preview_api_enabled": True,
            "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
            "responsive_web_graphql_timeline_navigation_enabled": True,
        }
        payload = self._graphql(
            self.operations.user_by_screen_name,
            "UserByScreenName",
            variables,
            features,
            field_toggles={"withAuxiliaryUserLabels": False},
        )
        result = _dig(payload, "data", "user", "result")
        if not isinstance(result, dict):
            raise XError(f"X user not found: {screen_name}")
        user = _user_from_graphql(result)
        if user is None:
            raise XError(f"X user not found: {screen_name}")
        return user

    def iter_user_tweets(
        self,
        user_id: str,
        *,
        limit: int | None = None,
        cursor: str = "",
        stop_ids: frozenset[str] = frozenset(),
        skip_ids: frozenset[str] = frozenset(),
        media_only: bool = False,
        include_replies: bool = True,
        page_size: int = X_TIMELINE_PAGE_SIZE,
        max_pages: int | None = None,
        on_page: Callable[[dict[str, object]], None] | None = None,
    ) -> Iterator[XTweet]:
        """Page a user's timeline newest-first. stop_ids ends the walk; skip_ids passes over them and keeps going."""
        seen = 0
        page = 0
        size = normalize_page_size(page_size)
        operation = self.operations.user_media if media_only else self.operations.user_tweets
        name = "UserMedia" if media_only else "UserTweets"
        while True:
            if max_pages is not None and page >= max_pages:
                return
            variables: dict[str, Any] = {
                "userId": str(user_id),
                "count": size if limit is None else max(1, min(size, limit - seen)),
                "includePromotedContent": False,
                "withQuickPromoteEligibilityTweetFields": False,
                "withVoice": True,
                "withV2Timeline": True,
            }
            if not media_only:
                variables["withCommunity"] = True
            if cursor:
                variables["cursor"] = cursor
            payload = self._graphql(operation, name, variables, _TIMELINE_FEATURES, field_toggles={"withArticlePlainText": False})
            tweets, next_cursor = _timeline_page(payload, user_id)
            page += 1
            if on_page is not None:
                on_page({"page": page, "page_tweets": len(tweets), "page_size": size, "cursor": cursor})
            if not tweets:
                return
            for tweet in tweets:
                if tweet.tweet_id in stop_ids:
                    return
                if tweet.tweet_id in skip_ids:
                    continue
                if not include_replies and tweet.reply_to_id:
                    continue
                yield tweet
                seen += 1
                if limit is not None and seen >= limit:
                    return
            if not next_cursor or next_cursor == cursor:
                return
            cursor = next_cursor

    def resolve_tweet_id(self, target: str) -> str:
        text = str(target or "").strip()
        if not text:
            raise XError("an X post URL or id is required")
        if "t.co/" in text:
            text = self.http.resolve_redirect(text)
        return extract_tweet_id(text)

    def _syndication(self, tweet_id: str) -> "dict[str, Any] | None":
        url = (
            "https://cdn.syndication.twimg.com/tweet-result"
            f"?id={quote(tweet_id)}&token={quote(syndication_token(tweet_id))}&lang=en"
        )
        payload = self.http.get_json(url)
        if not isinstance(payload, dict):
            return None
        if payload.get("__typename") == "TweetTombstone" or payload.get("tombstone"):
            return _TOMBSTONE
        return payload

    def _graphql_tweet_detail(self, tweet_id: str) -> Any:
        variables = {
            "focalTweetId": tweet_id,
            "with_rux_injections": False,
            "rankingMode": "Relevance",
            "includePromotedContent": False,
            "withCommunity": True,
            "withQuickPromoteEligibilityTweetFields": True,
            "withBirdwatchNotes": True,
            "withVoice": True,
        }
        return self._graphql(
            self.operations.tweet_detail,
            "TweetDetail",
            variables,
            _TIMELINE_FEATURES,
            field_toggles={
                "withArticleRichContentState": True,
                "withArticlePlainText": False,
                "withGrokAnalyze": False,
                "withDisallowedReplyControls": False,
            },
        )

    def _graphql(
        self,
        operation_id: str,
        operation_name: str,
        variables: dict[str, Any],
        features: dict[str, Any],
        *,
        field_toggles: dict[str, Any] | None = None,
    ) -> Any:
        if not str(operation_id or "").strip():
            raise XError(f"no GraphQL query id configured for {operation_name}")
        query = {
            "variables": json.dumps(variables, separators=(",", ":")),
            "features": json.dumps(features, separators=(",", ":")),
        }
        if field_toggles:
            query["fieldToggles"] = json.dumps(field_toggles, separators=(",", ":"))
        if self.is_authenticated:
            url = f"https://{X_DEFAULT_HOST}/i/api/graphql/{operation_id}/{operation_name}?{urlencode(query)}"
            headers = {
                "Authorization": f"Bearer {X_PUBLIC_BEARER_TOKEN}",
                "Content-Type": "application/json",
                "x-csrf-token": self.credentials.ct0,
                "x-twitter-active-user": "yes",
                "x-twitter-auth-type": "OAuth2Session",
                "x-twitter-client-language": "en",
                "Cookie": f"auth_token={self.credentials.auth_token}; ct0={self.credentials.ct0};",
            }
        else:
            guest_token = self.guest_token()
            url = f"https://api.x.com/graphql/{operation_id}/{operation_name}?{urlencode(query)}"
            headers = {
                "Authorization": f"Bearer {X_PUBLIC_BEARER_TOKEN}",
                "Content-Type": "application/json",
                "x-guest-token": guest_token,
                "x-twitter-active-user": "yes",
                "x-twitter-client-language": "en",
                "Cookie": f"guest_id=v1%3A{guest_token}",
            }
        try:
            payload = self.http.get_json(url, headers=headers)
        except XAuthError:
            self._guest_token = ""
            raise
        errors = payload.get("errors") if isinstance(payload, dict) else None
        if isinstance(errors, list) and errors:
            message = next(
                (str(entry.get("message")) for entry in errors if isinstance(entry, dict) and entry.get("message")),
                "X GraphQL returned an error",
            )
            raise XError(f"{operation_name}: {message}")
        return payload


class XDownloader:
    def __init__(
        self,
        *,
        timeout: int = 120,
        options: XRequestOptions | None = None,
        proxy_url: str | None = None,
    ) -> None:
        base = options or XRequestOptions()
        media_options = XRequestOptions(
            request_delay_seconds=0.0,
            max_retries=base.max_retries,
            retry_base_seconds=base.retry_base_seconds,
            retry_max_seconds=base.retry_max_seconds,
            download_concurrency=base.download_concurrency,
            proxy_url=base.proxy_url,
        )
        self.http = XHTTP(timeout=timeout, options=media_options, proxy_url=proxy_url)

    def download(self, url: str) -> bytes:
        return self.http.get_bytes(url)


class XSyncService:
    """Archives X posts as gallery posts and their photos/videos as immutable originals."""

    def __init__(
        self,
        storage: GalleryStorage,
        post_store: PostStore | None = None,
        client: XClient | None = None,
        downloader: XDownloader | None = None,
        *,
        uploader_user_id: int | None = None,
        uploader_username: str | None = None,
        storage_strategy_name: str | None = None,
        download_media: bool = True,
        download_concurrency: int = 4,
        name_media_by_post_id: bool = True,
        max_video_bytes: int = 0,
        cover_writer: Callable[[GalleryMetadata, bytes], None] | None = None,
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
        self.max_video_bytes = max(0, int(max_video_bytes or 0))
        self.cover_writer = cover_writer
        self.progress = progress

    def sync_user(
        self,
        screen_name: str,
        *,
        limit: int | None = None,
        backfill: bool = True,
        include_replies: bool = True,
        media_only: bool = False,
        page_size: int = X_TIMELINE_PAGE_SIZE,
        max_pages: int | None = None,
    ) -> list[XTweetResult]:
        if self.client is None:
            raise XError("X client is required for sync_user")
        user = self.client.get_user(screen_name)
        archived = self._archived_tweet_ids(user)
        results: list[XTweetResult] = []
        counter = _RemainingCounter(
            total=user.media_count if media_only else user.statuses_count,
            archived=len(archived),
            limit=limit,
        )
        self._report_progress(
            stage="user_started",
            message="x user started",
            screen_name=user.screen_name,
            handle=user.handle,
            user_id=user.user_id,
            tweets_count=user.statuses_count,
            archived_tweets=len(archived),
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
                    message="x page fetched",
                    phase=phase,
                    screen_name=user.screen_name,
                    page=event.get("page"),
                    page_tweets=event.get("page_tweets"),
                    page_size=event.get("page_size"),
                    sync_count=done,
                    remaining=counter.remaining(done),
                    tweets_count=user.statuses_count,
                    progress=counter.percent(done),
                )
            return report

        walk = self.client.iter_user_tweets(
            user.user_id,
            limit=limit,
            stop_ids=frozenset() if backfill else archived,
            skip_ids=archived,
            media_only=media_only,
            include_replies=include_replies,
            page_size=page_size,
            max_pages=max_pages,
            on_page=page_reporter("backfill" if backfill else "new"),
        )
        for tweet in walk:
            results.append(self.sync_tweet(tweet, counter=counter, done=len(results)))

        self._report_progress(
            stage="user_done",
            message="x user completed",
            screen_name=user.screen_name,
            handle=user.handle,
            sync_count=len(results),
            remaining=counter.remaining(len(results)),
            tweets_count=user.statuses_count,
            progress=100,
        )
        return results

    def sync_post(self, target: str) -> XTweetResult:
        if self.client is None:
            raise XError("X client is required for sync_post")
        return self.sync_tweet(self.client.get_tweet(target))

    def sync_posts(self, targets: Sequence[str]) -> XBatchResult:
        """Archives a batch of post URLs or ids, keeping going past posts that cannot be read."""
        if self.client is None:
            raise XError("X client is required for sync_posts")
        pending = list(dict.fromkeys(item for target in targets for item in split_batch_input(target)))
        results: list[XTweetResult] = []
        failures: list[XPostFailure] = []
        counter = _RemainingCounter(total=len(pending), archived=0, limit=None)
        self._report_progress(
            stage="batch_started",
            message="x batch started",
            target_count=len(pending),
            remaining=counter.remaining(0),
            progress=counter.percent(0),
        )
        for index, target in enumerate(pending):
            try:
                tweet = self.client.get_tweet(target)
            except XError as exc:
                failures.append(XPostFailure(target=target, error=str(exc)))
                self._report_progress(
                    stage="tweet_failed",
                    message="x post failed",
                    target=target,
                    error=str(exc),
                    sync_count=len(results),
                    remaining=counter.remaining(index + 1),
                    progress=counter.percent(index + 1),
                )
                continue
            results.append(self.sync_tweet(tweet, counter=counter, done=index))
        self._report_progress(
            stage="batch_done",
            message="x batch completed",
            sync_count=len(results),
            failure_count=len(failures),
            target_count=len(pending),
            progress=100,
        )
        return XBatchResult(results=tuple(results), failures=tuple(failures))

    def sync_tweet(
        self,
        tweet: XTweet,
        *,
        counter: "_RemainingCounter | None" = None,
        done: int = 0,
    ) -> XTweetResult:
        post_key = make_post_key(X_SOURCE, tweet.tweet_id)
        existing = self.post_store.find_post(post_key)
        self._report_progress(
            stage="tweet_started",
            message="x post started",
            tweet_id=tweet.tweet_id,
            handle=tweet.user.handle,
            media_count=len(tweet.media),
            sync_count=done,
            remaining=counter.remaining(done) if counter is not None else None,
            progress=counter.percent(done) if counter is not None else None,
        )

        assets: list[XAssetResult] = []
        attachments: list[PostAttachment] = []
        contents = self._download_media(tweet) if self.download_media else {}
        for index, media in enumerate(tweet.media):
            downloaded = contents.get(media.media_key)
            if downloaded is None:
                attachments.append(_remote_attachment(media))
                continue
            content, source_url = downloaded
            asset, attachment = self._store_media(tweet, media, content, source_url, index)
            if asset is not None:
                assets.append(asset)
            attachments.append(attachment)

        post = _post_from_tweet(
            tweet,
            attachments=tuple(attachments),
            uploader_user_id=self.uploader_user_id,
            uploader_username=self.uploader_username,
        )
        self.post_store.write_post(post)
        status = "updated" if existing is not None else "created"
        self._report_progress(
            stage="tweet_done",
            message="x post completed",
            tweet_id=tweet.tweet_id,
            post_key=post_key,
            result_status=status,
            asset_count=len(assets),
            sync_count=done + 1,
            remaining=counter.remaining(done + 1) if counter is not None else None,
            progress=counter.percent(done + 1) if counter is not None else None,
        )
        return XTweetResult(
            tweet_id=tweet.tweet_id,
            post_key=post_key,
            status=status,
            assets=tuple(assets),
        )

    def _download_media(self, tweet: XTweet) -> dict[str, tuple[bytes, str]]:
        pending = [media for media in tweet.media if media.sources]
        if not pending or self.downloader is None:
            return {}
        if len(pending) == 1 or self.download_concurrency == 1:
            return {
                media.media_key: fetched
                for media in pending
                if (fetched := self._download_one(media)) is not None
            }
        with ThreadPoolExecutor(max_workers=min(self.download_concurrency, len(pending))) as pool:
            downloaded = list(pool.map(self._download_one, pending))
        return {
            media.media_key: fetched
            for media, fetched in zip(pending, downloaded)
            if fetched is not None
        }

    def _download_one(self, media: XMedia) -> tuple[bytes, str] | None:
        """Walks the quality-ordered source list so a rejected size token degrades instead of losing the file."""
        if self.downloader is None:
            return None
        errors: list[str] = []
        for url in media.sources:
            try:
                content = self.downloader.download(url)
            except XError as exc:
                errors.append(f"{url}: {exc}")
                continue
            if not looks_like_media(content, media.mime_type):
                errors.append(f"{url}: response is not {media.mime_type or 'media'}")
                continue
            if media.is_video and self.max_video_bytes and len(content) > self.max_video_bytes:
                errors.append(f"{url}: {len(content)} bytes exceeds the {self.max_video_bytes} byte video limit")
                self._report_progress(
                    stage="media_too_large",
                    message="x video exceeds the size limit",
                    media_key=media.media_key,
                    url=url,
                    bytes=len(content),
                    limit_bytes=self.max_video_bytes,
                )
                continue
            self._report_progress(
                stage="media_downloaded",
                message="x media downloaded",
                media_key=media.media_key,
                url=url,
                bytes=len(content),
                degraded=url != media.sources[0] or None,
            )
            return content, url
        self._report_progress(
            stage="media_failed",
            message="x media download failed",
            media_key=media.media_key,
            url=media.download_url,
            error="; ".join(errors) or "no source URL",
        )
        return None

    def _write_cover(self, metadata: GalleryMetadata, media: XMedia) -> bool:
        """Video originals cannot be decoded by the preview pipeline, so their poster frame drives the cache."""
        if not media.is_video or not media.poster_url or self.downloader is None or self.cover_writer is None:
            return False
        try:
            cover = self.downloader.download(_photo_url(media.poster_url, "orig"))
            if not looks_like_media(cover, "image/jpeg"):
                raise XError("poster response is not an image")
            self.cover_writer(metadata, cover)
        except (XError, OSError, ValueError) as exc:
            self._report_progress(
                stage="cover_failed",
                message="x poster cache failed",
                media_key=media.media_key,
                url=media.poster_url,
                error=str(exc),
            )
            return False
        self._report_progress(
            stage="cover_written",
            message="x poster cached as preview",
            media_key=media.media_key,
            asset_key=metadata.asset_key,
        )
        return True

    def _asset_identity(self, tweet: XTweet, media: XMedia, index: int) -> tuple[str, int | None]:
        """Post-id naming groups a tweet's media into <tweet>_p0/_p1 so the gallery pager works like Pixiv."""
        if self.name_media_by_post_id:
            return tweet.tweet_id, index
        return media.media_key, None

    def _store_media(
        self,
        tweet: XTweet,
        media: XMedia,
        content: bytes,
        source_url: str,
        index: int = 0,
    ) -> tuple[XAssetResult | None, PostAttachment]:
        source_id, page_index = self._asset_identity(tweet, media, index)
        asset_key = make_asset_key(X_SOURCE, source_id, page_index)
        source_filename = x_media_filename(tweet.created_at, media)
        if self.storage.find_metadata_path(asset_key) is not None:
            metadata = self.storage.read_metadata(asset_key)
            return (
                XAssetResult(
                    asset_key=asset_key,
                    status="skipped",
                    original_path=metadata.original_path,
                    file_sha256=metadata.file_sha256,
                    media_type=media.media_type,
                ),
                _linked_attachment(media, asset_key),
            )

        stored = self.storage.write_original(
            asset_key,
            source_filename,
            content,
            strategy_name=self.storage_strategy_name,
            content_type=media.mime_type or None,
        )
        duplicate = self.storage.find_by_sha256(stored.sha256, exclude_asset_key=asset_key)
        extra: dict[str, Any] = {
            "x_tweet_id": tweet.tweet_id,
            "x_tweet_url": tweet.url,
            "x_media_key": media.media_key,
            "x_media_type": media.media_type,
            "x_media_url": source_url or media.download_url,
            "x_media_sources": list(media.sources),
            "x_user_id": tweet.user.user_id,
            "x_screen_name": tweet.user.screen_name,
            "x_display_name": tweet.user.display_name,
        }
        if media.poster_url:
            extra["x_poster_url"] = media.poster_url
        if media.duration_seconds is not None:
            extra["x_duration_seconds"] = media.duration_seconds
        if media.bitrate is not None:
            extra["x_bitrate"] = media.bitrate
        if media.variants:
            extra["x_video_variants"] = [variant.to_dict() for variant in media.variants]
        if media.alt_text:
            extra["description"] = media.alt_text
        metadata = GalleryMetadata(
            source=X_SOURCE,
            source_id=source_id,
            page_index=page_index,
            title=_tweet_title(tweet),
            artist_id=tweet.user.user_id,
            artist_name=tweet.user.display_name,
            original_url=tweet.url,
            crawl_time=utc_now_iso(),
            file_sha256=stored.sha256,
            original_filename=stored.filename,
            original_path=stored.relative_path,
            pixiv_tags=tweet.tags,
            canonical_tags=(),
            width=media.width,
            height=media.height,
            mime_type=media.mime_type or None,
            source_type=media.media_type,
            artwork_date=(tweet.created_at or "")[:10] or None,
            age_rating="r18" if tweet.possibly_sensitive else None,
            is_animated=True if media.is_video else None,
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
            XAssetResult(
                asset_key=asset_key,
                status=status,
                original_path=stored.relative_path,
                file_sha256=stored.sha256,
                media_type=media.media_type,
                duplicate_of=duplicate_of,
                has_cover=self._write_cover(metadata, media),
            ),
            _linked_attachment(media, asset_key),
        )

    def _archived_tweet_ids(self, user: XUser) -> frozenset[str]:
        """Already-stored post ids for this author; ends the newest-first walk and anchors backfill."""
        return frozenset(
            post.source_id
            for post in self.post_store.iter_posts()
            if post.source == X_SOURCE and post.author_id == user.user_id
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


_TIMELINE_FEATURES: dict[str, Any] = {
    "rweb_video_screen_enabled": False,
    "payments_enabled": False,
    "rweb_xchat_enabled": False,
    "profile_label_improvements_pcf_label_in_post_enabled": True,
    "rweb_tipjar_consumption_enabled": True,
    "verified_phone_label_enabled": False,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "responsive_web_graphql_timeline_navigation_enabled": True,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "premium_content_api_read_enabled": False,
    "communities_web_enable_tweet_community_results_fetch": True,
    "c9s_tweet_anatomy_moderator_badge_enabled": True,
    "responsive_web_grok_analyze_button_fetch_trends_enabled": False,
    "responsive_web_grok_analyze_post_followups_enabled": True,
    "responsive_web_jetfuel_frame": True,
    "responsive_web_grok_share_attachment_enabled": True,
    "articles_preview_enabled": True,
    "responsive_web_edit_tweet_api_enabled": True,
    "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
    "view_counts_everywhere_api_enabled": True,
    "longform_notetweets_consumption_enabled": True,
    "responsive_web_twitter_article_tweet_consumption_enabled": True,
    "tweet_awards_web_tipping_enabled": False,
    "responsive_web_grok_show_grok_translated_post": False,
    "responsive_web_grok_analysis_button_from_backend": True,
    "creator_subscriptions_quote_tweet_preview_enabled": False,
    "freedom_of_speech_not_reach_fetch_enabled": True,
    "standardized_nudges_misinfo": True,
    "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
    "longform_notetweets_rich_text_read_enabled": True,
    "longform_notetweets_inline_media_enabled": True,
    "responsive_web_grok_image_annotation_enabled": True,
    "responsive_web_grok_imagine_annotation_enabled": True,
    "responsive_web_grok_community_note_auto_translation_is_enabled": False,
    "responsive_web_enhance_cards_enabled": False,
}


def split_batch_input(value: Any) -> list[str]:
    """Splits a pasted batch of post links on newlines and both ASCII and full-width list separators."""
    return [item.strip() for item in _BATCH_SEPARATOR_RE.split(str(value or "")) if item.strip()]


def normalize_screen_name(value: Any) -> str:
    text = str(value or "").strip().lstrip("@")
    if "/" in text:
        text = text.rstrip("/").rsplit("/", 1)[-1]
    return re.sub(r"[^A-Za-z0-9_]+", "", text)


def normalize_page_size(value: Any) -> int:
    try:
        size = int(value)
    except (TypeError, ValueError):
        return X_TIMELINE_PAGE_SIZE
    return max(1, min(X_MAX_PAGE_SIZE, size))


def tweet_url(screen_name: str, tweet_id: str) -> str:
    handle = normalize_screen_name(screen_name) or "i"
    return f"https://{X_DEFAULT_HOST}/{handle}/status/{tweet_id}"


def extract_tweet_id(value: Any) -> str:
    text = str(value or "").strip()
    match = _STATUS_URL_RE.search(text)
    if match:
        return match.group(1)
    if _TWEET_ID_RE.match(text):
        return text
    raise XError(f"not a valid X post URL or id: {value}")


def _short_url(url: str) -> str:
    """GraphQL URLs carry kilobytes of feature flags; the path alone identifies the call in a log line."""
    text = str(url or "")
    base, _, _query = text.partition("?")
    return base if len(text) > 200 else text


def syndication_token(tweet_id: str) -> str:
    """Reproduces X's syndication token: ((id / 1e15) * pi).toString(36) with zeros and the dot stripped."""
    value = (int(tweet_id) / 1e15) * math.pi
    return re.sub(r"(0+|\.)", "", _js_number_to_base36(value))


def _js_number_to_base36(value: float) -> str:
    """Port of V8's DoubleToRadixCString so the output matches Number.prototype.toString(36) exactly."""
    if not math.isfinite(value):
        return "0"
    negative = value < 0
    value = abs(value)
    integer_part = math.floor(value)
    fraction = value - integer_part
    delta = max(0.5 * (math.nextafter(value, math.inf) - value), math.nextafter(0.0, math.inf))
    fraction_digits: list[str] = []
    if fraction >= delta:
        while True:
            fraction *= 36
            delta *= 36
            digit = int(fraction)
            fraction_digits.append(_BASE36_DIGITS[digit])
            fraction -= digit
            if fraction > 0.5 or (fraction == 0.5 and digit & 1):
                if fraction + delta > 1:
                    integer_part += _round_base36_fraction_up(fraction_digits)
                    break
            if fraction < delta:
                break
    integer_digits: list[str] = []
    while integer_part > 0:
        integer_part, remainder = divmod(integer_part, 36)
        integer_digits.append(_BASE36_DIGITS[remainder])
    text = "".join(reversed(integer_digits)) or "0"
    if fraction_digits:
        text = f"{text}.{''.join(fraction_digits)}"
    return f"-{text}" if negative else text


def _round_base36_fraction_up(digits: list[str]) -> int:
    for index in range(len(digits) - 1, -1, -1):
        position = _BASE36_DIGITS.index(digits[index]) + 1
        if position < 36:
            digits[index] = _BASE36_DIGITS[position]
            del digits[index + 1:]
            return 0
    digits.clear()
    return 1


def x_media_filename(created_at: str, media: XMedia) -> str:
    """Readable archival filename: <date>_<media key><real extension>, MIME-derived to avoid double suffixes."""
    suffix = mimetypes.guess_extension(media.mime_type or "") or ""
    if suffix in {".jpe", ".jpeg"}:
        suffix = ".jpg"
    if not suffix:
        suffix = Path(urlparse(media.download_url).path).suffix or ""
    safe_key = re.sub(r"[\\/:*?\"<>|]+", "_", media.media_key).strip(" ._") or "media"
    date_prefix = (created_at or "")[:10]
    return f"{date_prefix}_{safe_key}{suffix}" if date_prefix else f"{safe_key}{suffix}"


def parse_x_datetime(value: Any) -> str:
    """X sends "Wed Oct 10 20:19:24 +0000 2018" on legacy payloads and ISO timestamps on syndication ones."""
    text = str(value or "").strip()
    if not text:
        return ""
    for fmt in ("%a %b %d %H:%M:%S %z %Y", "%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            parsed = datetime.strptime(text.replace("Z", "+0000"), fmt)
        except ValueError:
            continue
        return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return text


def extract_hashtags(text: str) -> tuple[str, ...]:
    seen: dict[str, None] = {}
    for match in _HASHTAG_RE.finditer(text or ""):
        seen.setdefault(match.group(1), None)
    return tuple(seen)


def is_allowed_media_url(url: str) -> bool:
    return str(url or "").startswith(_MEDIA_HOSTS)


def _photo_url(url: str, name: str = "orig") -> str:
    base = str(url or "").split("?", 1)[0]
    if not base:
        return ""
    return f"{base}?name={name}"


def photo_source_urls(media_url: str) -> tuple[str, ...]:
    """X re-encodes photos per size token, so ask for the stored format at full size first and degrade from there."""
    base = str(media_url or "").split("?", 1)[0]
    if not base:
        return ()
    suffix = Path(urlparse(base).path).suffix.lower()
    image_format = _PHOTO_FORMATS.get(suffix, "jpg")
    stem = base[: -len(suffix)] if suffix else base
    return tuple(
        dict.fromkeys(
            [
                f"{stem}?format={image_format}&name=orig",
                f"{stem}?format={image_format}&name=4096x4096",
                f"{base}?name=orig",
                f"{base}?name=large",
                base,
            ]
        )
    )


def looks_like_media(content: bytes, mime_type: str) -> bool:
    """X answers a rejected size token with an HTML error page, so verify the bytes before archiving them."""
    if len(content) < 64:
        return False
    if mime_type.startswith("image/"):
        return content.startswith(_IMAGE_MAGIC)
    if mime_type.startswith("video/"):
        return b"ftyp" in content[:64]
    return True


def _variants_from_payload(video_info: Any) -> tuple[XVariant, ...]:
    variants = video_info.get("variants") if isinstance(video_info, dict) else None
    if not isinstance(variants, list):
        return ()
    mp4 = [
        XVariant(
            url=str(item.get("url") or ""),
            bitrate=_optional_int(item.get("bitrate")),
            content_type=str(item.get("content_type") or ""),
        )
        for item in variants
        if isinstance(item, dict) and item.get("content_type") == "video/mp4" and item.get("url")
    ]
    return tuple(sorted(mp4, key=lambda variant: variant.bitrate or 0, reverse=True))


def _media_identity(data: dict[str, Any], *, index: int, tweet_id: str) -> str:
    """Syndication omits media_key, so key on the CDN filename both endpoints expose to avoid double-archiving."""
    url = str(data.get("media_url_https") or data.get("media_url") or "")
    stem = Path(urlparse(url).path).stem
    if stem:
        return stem
    for key in ("media_key", "id_str"):
        if data.get(key):
            return str(data[key])
    return f"{tweet_id}_p{index}"


def _media_from_payload(data: dict[str, Any], *, index: int, tweet_id: str) -> XMedia | None:
    media_type = str(data.get("type") or "photo")
    media_key = _media_identity(data, index=index, tweet_id=tweet_id)
    original = data.get("original_info") if isinstance(data.get("original_info"), dict) else {}
    width = _optional_int(original.get("width"))
    height = _optional_int(original.get("height"))
    alt_text = str(data.get("ext_alt_text") or data.get("altText") or "")
    poster = str(data.get("media_url_https") or data.get("media_url") or "")
    if media_type == "photo":
        if not poster:
            return None
        candidates = photo_source_urls(poster)
        return XMedia(
            media_key=media_key,
            media_type="photo",
            download_url=candidates[0] if candidates else "",
            download_candidates=candidates,
            poster_url=_photo_url(poster, "small"),
            mime_type=_photo_mime(poster),
            width=width,
            height=height,
            alt_text=alt_text,
        )
    variants = _variants_from_payload(data.get("video_info"))
    if not variants:
        return None
    duration = _optional_int((data.get("video_info") or {}).get("duration_millis"))
    return XMedia(
        media_key=media_key,
        media_type=media_type,
        download_url=variants[0].url,
        download_candidates=tuple(variant.url for variant in variants),
        poster_url=poster,
        mime_type="video/mp4",
        width=width,
        height=height,
        duration_seconds=round(duration / 1000) if duration else None,
        bitrate=variants[0].bitrate,
        alt_text=alt_text,
        variants=variants,
    )


def _photo_mime(url: str) -> str:
    suffix = Path(urlparse(str(url or "")).path).suffix.lower()
    return {".png": "image/png", ".webp": "image/webp", ".gif": "image/gif"}.get(suffix, "image/jpeg")


def _media_list(entities: Any, tweet_id: str) -> tuple[XMedia, ...]:
    items = entities if isinstance(entities, list) else []
    media: list[XMedia] = []
    seen: set[str] = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        parsed = _media_from_payload(item, index=index, tweet_id=tweet_id)
        if parsed is None or parsed.media_key in seen:
            continue
        seen.add(parsed.media_key)
        media.append(parsed)
    return tuple(media)


def _unified_card_media(binding_values: Any) -> list[dict[str, Any]]:
    """Poll/product cards hide their media in a JSON string under the unified_card binding."""
    if isinstance(binding_values, list):
        raw = next(
            (item.get("value", {}).get("string_value") for item in binding_values
             if isinstance(item, dict) and item.get("key") == "unified_card"),
            None,
        )
    elif isinstance(binding_values, dict):
        raw = _dig(binding_values, "unified_card", "string_value")
    else:
        return []
    if not raw:
        return []
    try:
        card = json.loads(raw)
    except (TypeError, ValueError):
        return []
    entities = card.get("media_entities") if isinstance(card, dict) else None
    return [item for item in (entities or {}).values() if isinstance(item, dict)] if isinstance(entities, dict) else []


def _expand_text(text: str, urls: Any, media_urls: Any) -> str:
    expanded = str(text or "")
    for item in urls if isinstance(urls, list) else []:
        if not isinstance(item, dict):
            continue
        short = str(item.get("url") or "")
        target = str(item.get("expanded_url") or item.get("unwound_url") or "")
        if short and target:
            expanded = expanded.replace(short, target)
    for item in media_urls if isinstance(media_urls, list) else []:
        short = str(item.get("url") or "") if isinstance(item, dict) else ""
        if short:
            expanded = expanded.replace(short, "")
    return html.unescape(expanded).strip()


def _hashtags_from_entities(entities: Any, text: str) -> tuple[str, ...]:
    items = entities.get("hashtags") if isinstance(entities, dict) else None
    tags = [
        str(item.get("text") or "")
        for item in (items if isinstance(items, list) else [])
        if isinstance(item, dict) and item.get("text")
    ]
    return tuple(dict.fromkeys(tags)) if tags else extract_hashtags(text)


def _user_from_graphql(result: dict[str, Any]) -> XUser | None:
    legacy = result.get("legacy") if isinstance(result.get("legacy"), dict) else {}
    core = result.get("core") if isinstance(result.get("core"), dict) else {}
    avatar = result.get("avatar") if isinstance(result.get("avatar"), dict) else {}
    user_id = str(result.get("rest_id") or legacy.get("id_str") or "")
    screen_name = normalize_screen_name(core.get("screen_name") or legacy.get("screen_name"))
    if not user_id or not screen_name:
        return None
    return XUser(
        user_id=user_id,
        screen_name=screen_name,
        name=str(core.get("name") or legacy.get("name") or ""),
        avatar_url=_large_avatar(avatar.get("image_url") or legacy.get("profile_image_url_https")),
        description=str(legacy.get("description") or ""),
        statuses_count=_optional_int(legacy.get("statuses_count")),
        media_count=_optional_int(legacy.get("media_count")),
        is_protected=bool(result.get("privacy", {}).get("protected") if isinstance(result.get("privacy"), dict) else legacy.get("protected")),
        is_verified=bool(result.get("is_blue_verified") or legacy.get("verified")),
    )


def _large_avatar(url: Any) -> str:
    text = str(url or "")
    return text.replace("_normal.", "_400x400.") if "_normal." in text else text


def _unwrap_tweet_result(result: Any) -> dict[str, Any] | None:
    if not isinstance(result, dict):
        return None
    if result.get("__typename") == "TweetWithVisibilityResults":
        inner = result.get("tweet")
        return inner if isinstance(inner, dict) else None
    if result.get("__typename") == "TweetTombstone":
        return None
    return result


def _tweet_from_graphql(result: Any) -> XTweet | None:
    tweet = _unwrap_tweet_result(result)
    if tweet is None:
        return None
    legacy = tweet.get("legacy") if isinstance(tweet.get("legacy"), dict) else {}
    tweet_id = str(tweet.get("rest_id") or legacy.get("id_str") or "")
    if not tweet_id:
        return None
    user = _user_from_graphql(_dig(tweet, "core", "user_results", "result") or {})
    if user is None:
        return None
    note = _dig(tweet, "note_tweet", "note_tweet_results", "result")
    entities = legacy.get("entities") if isinstance(legacy.get("entities"), dict) else {}
    extended = legacy.get("extended_entities") if isinstance(legacy.get("extended_entities"), dict) else {}
    if isinstance(note, dict) and note.get("text"):
        text_source = str(note.get("text") or "")
        url_entities = _dig(note, "entity_set", "urls") or entities.get("urls")
    else:
        text_source = str(legacy.get("full_text") or legacy.get("text") or "")
        url_entities = entities.get("urls")
    media_entities = extended.get("media") or entities.get("media") or []
    card_media = _unified_card_media(_dig(tweet, "card", "legacy", "binding_values"))
    return XTweet(
        tweet_id=tweet_id,
        user=user,
        created_at=parse_x_datetime(legacy.get("created_at")),
        text=_expand_text(text_source, url_entities, entities.get("media")),
        lang=str(legacy.get("lang") or ""),
        media=_media_list(list(media_entities) or card_media, tweet_id),
        tags=_hashtags_from_entities(entities, text_source),
        possibly_sensitive=bool(legacy.get("possibly_sensitive")),
        reply_to_id=str(legacy.get("in_reply_to_status_id_str") or ""),
        reply_to_screen_name=str(legacy.get("in_reply_to_screen_name") or ""),
        retweet_of_id=str(_dig(legacy, "retweeted_status_result", "result", "rest_id") or ""),
        quote_of_id=str(legacy.get("quoted_status_id_str") or ""),
        metrics=_metrics_from_legacy(legacy, tweet.get("views")),
    )


def _tweet_from_tweet_detail(payload: Any, tweet_id: str) -> XTweet | None:
    instructions = _dig(payload, "data", "threaded_conversation_with_injections_v2", "instructions") or []
    results: list[Any] = []
    for instruction in instructions if isinstance(instructions, list) else []:
        if not isinstance(instruction, dict) or instruction.get("type") != "TimelineAddEntries":
            continue
        for entry in instruction.get("entries") or []:
            result = _dig(entry, "content", "itemContent", "tweet_results", "result")
            if result:
                results.append(result)
    for result in results:
        tweet = _tweet_from_graphql(result)
        if tweet is not None and tweet.tweet_id == tweet_id:
            return tweet
    for result in results:
        tweet = _tweet_from_graphql(result)
        if tweet is not None:
            return tweet
    return None


def _timeline_page(payload: Any, user_id: str) -> tuple[list[XTweet], str]:
    instructions = _dig(payload, "data", "user", "result", "timeline_v2", "timeline", "instructions")
    if not isinstance(instructions, list):
        instructions = _dig(payload, "data", "user", "result", "timeline", "timeline", "instructions")
    tweets: list[XTweet] = []
    cursor = ""
    for instruction in instructions if isinstance(instructions, list) else []:
        if not isinstance(instruction, dict):
            continue
        entries = instruction.get("entries")
        if instruction.get("type") == "TimelineReplaceEntry":
            entry = instruction.get("entry")
            entries = [entry] if isinstance(entry, dict) else []
        for entry in entries if isinstance(entries, list) else []:
            if not isinstance(entry, dict):
                continue
            content = entry.get("content") if isinstance(entry.get("content"), dict) else {}
            if content.get("entryType") == "TimelineTimelineCursor" or content.get("cursorType") == "Bottom":
                if content.get("cursorType") == "Bottom":
                    cursor = str(content.get("value") or cursor)
                continue
            for result in _timeline_entry_results(content):
                tweet = _tweet_from_graphql(result)
                if tweet is not None:
                    tweets.append(tweet)
    return tweets, cursor


def _timeline_entry_results(content: dict[str, Any]) -> list[Any]:
    direct = _dig(content, "itemContent", "tweet_results", "result")
    if direct:
        return [direct]
    results: list[Any] = []
    for item in content.get("items") or []:
        result = _dig(item, "item", "itemContent", "tweet_results", "result")
        if result:
            results.append(result)
    return results


def _tweet_from_syndication(data: dict[str, Any], tweet_id: str) -> XTweet:
    author = data.get("user") if isinstance(data.get("user"), dict) else {}
    screen_name = normalize_screen_name(author.get("screen_name"))
    user = XUser(
        user_id=str(author.get("id_str") or ""),
        screen_name=screen_name,
        name=str(author.get("name") or ""),
        avatar_url=_large_avatar(author.get("profile_image_url_https")),
        is_verified=bool(author.get("is_blue_verified") or author.get("verified")),
    )
    entities = data.get("entities") if isinstance(data.get("entities"), dict) else {}
    media_details = data.get("mediaDetails")
    if not isinstance(media_details, list) or not media_details:
        media_details = _unified_card_media(_dig(data, "card", "binding_values"))
    if not media_details:
        media_details = _syndication_photos(data.get("photos"))
    text = str(data.get("text") or "")
    return XTweet(
        tweet_id=str(data.get("id_str") or tweet_id),
        user=user,
        created_at=parse_x_datetime(data.get("created_at")),
        text=_expand_text(text, entities.get("urls"), entities.get("media")),
        lang=str(data.get("lang") or ""),
        media=_media_list(media_details, tweet_id),
        tags=_hashtags_from_entities(entities, text),
        possibly_sensitive=bool(data.get("possibly_sensitive")),
        reply_to_id=str(data.get("in_reply_to_status_id_str") or ""),
        reply_to_screen_name=normalize_screen_name(data.get("in_reply_to_screen_name")),
        quote_of_id=str(_dig(data, "quoted_tweet", "id_str") or ""),
        metrics=_metrics_from_legacy(data, None),
    )


def _syndication_photos(photos: Any) -> list[dict[str, Any]]:
    """Older syndication payloads describe images only under `photos`, without the mediaDetails block."""
    return [
        {
            "type": "photo",
            "media_url_https": str(item.get("url") or item.get("cdnUrl") or ""),
            "original_info": {"width": item.get("width"), "height": item.get("height")},
            "ext_alt_text": str(item.get("altText") or ""),
        }
        for item in (photos if isinstance(photos, list) else [])
        if isinstance(item, dict) and (item.get("url") or item.get("cdnUrl"))
    ]


def _metrics_from_legacy(legacy: Any, views: Any) -> dict[str, int]:
    """Syndication and GraphQL name the same counters differently, so accept either spelling."""
    source = legacy if isinstance(legacy, dict) else {}
    mapping = {
        "likes": ("favorite_count", "favourites_count"),
        "reposts": ("retweet_count",),
        "replies": ("reply_count", "conversation_count"),
        "quotes": ("quote_count",),
        "bookmarks": ("bookmark_count",),
    }
    metrics: dict[str, int] = {}
    for name, keys in mapping.items():
        value = next((count for key in keys if (count := _optional_int(source.get(key))) is not None), None)
        if value is not None:
            metrics[name] = value
    view_count = _optional_int(views.get("count") if isinstance(views, dict) else None)
    if view_count is not None:
        metrics["views"] = view_count
    return metrics


def _post_from_tweet(
    tweet: XTweet,
    *,
    attachments: tuple[PostAttachment, ...],
    uploader_user_id: int | None,
    uploader_username: str | None,
) -> GalleryPost:
    extra: dict[str, Any] = {"x_tweet_id": tweet.tweet_id}
    if tweet.user.is_verified:
        extra["x_verified"] = True
    if tweet.user.description:
        extra["x_author_description"] = tweet.user.description
    if tweet.media:
        extra["x_media_types"] = sorted({media.media_type for media in tweet.media})
    if uploader_user_id is not None:
        extra["uploader_user_id"] = uploader_user_id
    if uploader_username:
        extra["uploader_username"] = uploader_username
    return GalleryPost(
        source=X_SOURCE,
        source_id=tweet.tweet_id,
        author_id=tweet.user.user_id,
        author_name=tweet.user.display_name,
        author_handle=tweet.user.screen_name,
        author_avatar_url=tweet.user.avatar_url,
        content=tweet.text,
        posted_at=tweet.created_at,
        crawl_time=utc_now_iso(),
        source_url=tweet.url,
        language=tweet.lang or None,
        visibility="followers" if tweet.user.is_protected else "public",
        age_rating="r18" if tweet.possibly_sensitive else None,
        tags=tweet.tags,
        attachments=attachments,
        reply_to_url=tweet.reply_to_url,
        repost_of_url=tweet.retweet_of_url,
        quote_of_url=tweet.quote_of_url,
        metrics=dict(tweet.metrics),
        extra=extra,
    )


def _linked_attachment(media: XMedia, asset_key: str) -> PostAttachment:
    return PostAttachment(
        asset_key=asset_key,
        remote_url=media.download_url,
        thumbnail_url=media.thumbnail_url,
        mime_type=media.mime_type or None,
        width=media.width,
        height=media.height,
        description=media.alt_text,
        is_sensitive=False,
    )


def _remote_attachment(media: XMedia) -> PostAttachment:
    return PostAttachment(
        remote_url=media.download_url,
        thumbnail_url=media.thumbnail_url,
        mime_type=media.mime_type or None,
        width=media.width,
        height=media.height,
        description=media.alt_text,
        is_sensitive=False,
    )


def _tweet_title(tweet: XTweet) -> str:
    text = " ".join((tweet.text or "").split())
    return text[:120]


def _dig(payload: Any, *keys: str) -> Any:
    current = payload
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _optional_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _x_proxy_opener(proxy_url: str, *, ipv4_only: bool = True):
    handlers = list(ipv4_only_handlers()) if ipv4_only else []
    url = str(proxy_url or "").strip()
    if url:
        handlers.append(ProxyHandler({"http": url, "https": url}))
    return build_opener(*handlers) if handlers else None


def _retry_after_seconds(exc: HTTPError, options: XRequestOptions, attempt: int) -> int:
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
