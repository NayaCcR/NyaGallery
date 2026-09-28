from __future__ import annotations

import argparse
import getpass
import json
import os
from pathlib import Path

from sqlalchemy import select

from nyagallery.config import (
    DEFAULT_CONFIG_FILENAME,
    NyaGalleryConfig,
    apply_config_environment,
    config_to_dict,
    load_config,
    network_proxy_for,
    read_config_file_data,
    save_config_file,
)
from nyagallery.db import (
    AssetModel,
    UserModel,
    create_engine_for_url,
    create_user,
    default_database_url,
    encrypt_stored_pixiv_credentials,
    init_database,
    issue_api_token,
    get_security_settings,
    make_session_factory,
    now_utc,
    rebuild_database,
    rebuild_posts,
    set_user_password,
    update_security_settings,
)
from nyagallery.auth import hash_password
from nyagallery.importers import LskyProImporter, NyaGalleryV1Importer, copy_assets_read_only
from nyagallery.media import MediaGenerator, media_limits_from_config
from nyagallery.metadata_backend import (
    convert_file_to_database,
    convert_metadata_backend,
    import_assets_to_database,
    metadata_backend,
)
from nyagallery.misskey import (
    MisskeyClient,
    MisskeyDownloader,
    MisskeyRequestOptions,
    MisskeySyncService,
    normalize_page_size,
)
from nyagallery.fanbox import (
    FanboxClient,
    FanboxCredentials,
    FanboxDownloader,
    FanboxRequestOptions,
    FanboxSyncService,
    exchange_pixiv_cookie_for_fanbox_session,
    normalize_creator_id,
    normalize_page_size as normalize_fanbox_page_size,
    split_batch_input as fanbox_split_batch_input,
)
from nyagallery.x import (
    XClient,
    XCredentials,
    XDownloader,
    XGraphqlOperations,
    XRequestOptions,
    XSyncService,
    normalize_page_size as normalize_x_page_size,
    normalize_screen_name,
    split_batch_input,
)
from nyagallery.posts import PostStore, ensure_sample_posts, link_sample_post_media, sample_posts
from nyagallery.pixiv import (
    PixivOAuthError,
    HTTPPixivDownloader,
    PixivCookieClient,
    PixivPyClient,
    PixivRequestOptions,
    PixivSyncService,
    create_pixiv_oauth_start,
    exchange_pixiv_oauth_code,
    get_pixiv_refresh_token_with_browser,
)
from nyagallery.storage import GalleryStorage
from nyagallery.tags import TagCatalog
from nyagallery.secret_crypto import generate_secret_key, secret_encryption_enabled


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nyagallery")
    parser.add_argument("--config", default=None, help="Path to nyagallery.toml.")
    parser.add_argument("--storage", default=None, help="Storage root directory.")
    parser.add_argument("--database-url", default=None, help="SQLAlchemy database URL.")
    parser.add_argument("--network-proxy", default=None, help="Default HTTP/HTTPS proxy URL for source requests.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    secret_key_cmd = subparsers.add_parser("generate-secret-key", help="Generate a deployment secret key for encrypted credentials.")
    secret_key_cmd.add_argument("--json", action="store_true", help="Print as a JSON object.")

    sync_pid = subparsers.add_parser("pixiv-sync-pid", help="Sync one Pixiv artwork by PID.")
    sync_pid.add_argument("pid")
    sync_pid.add_argument("--auth-mode", default="auto", help="auto, public, refresh_token, or cookie.")
    sync_pid.add_argument("--refresh-token", default=None)
    sync_pid.add_argument("--cookie", default=None)
    sync_pid.add_argument("--network-proxy", dest="command_network_proxy", default=None, help="Default HTTP/HTTPS proxy URL for source requests.")
    sync_pid.add_argument("--storage-strategy", default=None, help="Original storage strategy name.")
    sync_pid.add_argument("--generate-cache", action="store_true")
    sync_pid.add_argument("--rebuild-db", action="store_true")

    sync_user = subparsers.add_parser("pixiv-sync-user", help="Sync Pixiv artworks by user UID.")
    sync_user.add_argument("uid")
    sync_user.add_argument("--limit", type=int, default=None)
    sync_user.add_argument("--auth-mode", default="auto", help="auto, public, refresh_token, or cookie.")
    sync_user.add_argument("--refresh-token", default=None)
    sync_user.add_argument("--cookie", default=None)
    sync_user.add_argument("--network-proxy", dest="command_network_proxy", default=None, help="Default HTTP/HTTPS proxy URL for source requests.")
    sync_user.add_argument("--storage-strategy", default=None, help="Original storage strategy name.")
    sync_user.add_argument("--generate-cache", action="store_true")
    sync_user.add_argument("--rebuild-db", action="store_true")

    pixiv_login = subparsers.add_parser(
        "pixiv-login-browser",
        help="Open a local browser through gppt and print a Pixiv refresh token.",
    )
    pixiv_login.add_argument("--headless", action="store_true", help="Run browser headlessly; requires --username and --password.")
    pixiv_login.add_argument("--username", default=None, help="Pixiv account ID or email for headless/auto-filled login.")
    pixiv_login.add_argument("--password", default=None, help="Pixiv password for headless/auto-filled login.")
    pixiv_login.add_argument("--network-proxy", dest="command_network_proxy", default=None, help="Default HTTP/HTTPS proxy URL for source requests.")
    pixiv_login.add_argument("--plain", action="store_true", help="Print only the refresh token.")

    oauth_start = subparsers.add_parser(
        "pixiv-oauth-start",
        help="Print a Pixiv OAuth URL and code verifier for manual login on another machine.",
    )
    oauth_start.add_argument("--state", default=None)
    oauth_start.add_argument("--plain-url", action="store_true", help="Print only the login URL.")

    oauth_exchange = subparsers.add_parser(
        "pixiv-oauth-exchange",
        help="Exchange a Pixiv OAuth callback URL or code for a refresh token.",
    )
    oauth_exchange.add_argument("--code-verifier", required=True)
    oauth_exchange.add_argument("--callback-url", default=None)
    oauth_exchange.add_argument("--code", default=None)
    oauth_exchange.add_argument("--state", default=None)
    oauth_exchange.add_argument("--network-proxy", dest="command_network_proxy", default=None, help="Default HTTP/HTTPS proxy URL for source requests.")
    oauth_exchange.add_argument("--plain", action="store_true", help="Print only the refresh token.")

    init_tags = subparsers.add_parser("init-tags", help="Create the default tag catalog.")
    init_tags.add_argument("--replace", action="store_true")

    setup = subparsers.add_parser("setup", help="Initialize storage, tags, database, admin user, and API token.")
    setup.add_argument("--username", default="admin")
    setup.add_argument("--role", default="admin", choices=("developer", "admin", "editor", "viewer", "guest"))
    setup.add_argument("--password", default=None)
    setup.add_argument("--replace-tags", action="store_true")
    setup.add_argument("--skip-metadata-migration", action="store_true")
    setup.add_argument("--generate-cache", action="store_true")

    migrate_metadata = subparsers.add_parser("migrate-metadata", help="Rewrite per-asset metadata JSON files into creator-grouped JSON files.")
    migrate_metadata.add_argument("--keep-legacy", action="store_true", help="Keep legacy per-asset JSON files in place.")

    convert_cmd = subparsers.add_parser("convert", help="Convert metadata primary mode with backup and SHA256 verification.")
    convert_cmd.add_argument("--from", dest="from_mode", choices=("file", "database"), required=True)
    convert_cmd.add_argument("--to", dest="to_mode", choices=("file", "database"), required=True)
    convert_cmd.add_argument("--output", required=False, help="Destination sidecar directory for file mode.")
    convert_cmd.add_argument("--backup", default=None, help="Backup directory (defaults beside destination).")
    convert_cmd.add_argument("--confirm", action="store_true", help="Perform the write; otherwise print a dry-run plan.")

    import_cmd = subparsers.add_parser("import", help="Import an image-host export into file storage or the database.")
    import_cmd.add_argument("source", help="Source metadata file or database.")
    import_cmd.add_argument("--source-type", choices=("auto", "nyagallery_v1", "lsky_pro"), default="auto")
    import_cmd.add_argument("--source-root", default=None, help="Root containing immutable source originals.")
    import_cmd.add_argument("--target", choices=("file", "database"), default="file", help="Primary target for imported metadata.")
    import_cmd.add_argument("--output", required=False, help="Staging directory for file target (defaults to the configured storage root).")
    import_cmd.add_argument("--hardlink", action="store_true", help="Hardlink originals when the filesystem supports it.")
    import_cmd.add_argument("--confirm", action="store_true", help="Perform the write; otherwise print a dry-run report.")

    misskey_sync = subparsers.add_parser(
        "misskey-sync-user",
        help="Archive a Misskey user's notes as posts and their media as gallery assets.",
    )
    misskey_sync.add_argument("username", help="Misskey username, optionally user@host.")
    misskey_sync.add_argument("-t", "--token", default=None, help="API token (also reads MISSKEY_TOKEN or [misskey].token).")
    misskey_sync.add_argument("--host", default=None, help="Misskey host (default: misskey.io or [misskey].host).")
    misskey_sync.add_argument("--limit", type=int, default=None, help="Maximum notes to fetch this run.")
    misskey_sync.add_argument("--page-size", type=int, default=None, help="Notes per API request (1-100).")
    misskey_sync.add_argument("--max-pages", type=int, default=None, help="Maximum API pages to walk.")
    misskey_sync.add_argument("--no-media", action="store_true", help="Store note text only, keeping remote media URLs.")
    misskey_sync.add_argument("--no-backfill", action="store_true", help="Skip walking older notes than the archive.")
    misskey_sync.add_argument("--no-replies", action="store_true", help="Exclude replies.")
    misskey_sync.add_argument("--download-concurrency", type=int, default=None, help="Parallel media downloads.")
    misskey_sync.add_argument("--request-delay", type=float, default=None, help="Seconds between API requests.")
    misskey_sync.add_argument("--storage-strategy", default=None, help="Original storage strategy for downloaded media.")
    misskey_sync.add_argument("--generate-cache", action="store_true", help="Generate previews/thumbs after syncing.")
    misskey_sync.add_argument("--dry-run", action="store_true", help="Print what would be archived without writing.")

    for name, help_text in (
        ("x-sync-user", "Archive an X user's posts as posts and their photos/videos as gallery assets."),
        ("x-sync-posts", "Archive one or more X post URLs or ids as posts and gallery assets."),
    ):
        x_sync = subparsers.add_parser(name, help=help_text)
        if name == "x-sync-user":
            x_sync.add_argument("username", help="X username, with or without the leading @.")
            x_sync.add_argument("--limit", type=int, default=None, help="Maximum posts to fetch this run.")
            x_sync.add_argument("--page-size", type=int, default=None, help="Posts per timeline request (1-100).")
            x_sync.add_argument("--max-pages", type=int, default=None, help="Maximum timeline pages to walk.")
            x_sync.add_argument("--media-only", action="store_true", help="Walk the media tab instead of all posts.")
            x_sync.add_argument("--no-backfill", action="store_true", help="Stop at the newest already-archived post.")
            x_sync.add_argument("--no-replies", action="store_true", help="Exclude replies.")
        else:
            x_sync.add_argument("targets", nargs="+", help="Post URLs or ids; each may also be a separated list.")
        x_sync.add_argument("--auth-token", default=None, help="Session auth_token (also reads X_AUTH_TOKEN or [x].auth_token).")
        x_sync.add_argument("--ct0", default=None, help="Session ct0 CSRF token (also reads X_CT0 or [x].ct0).")
        x_sync.add_argument("--no-media", action="store_true", help="Store post text only, keeping remote media URLs.")
        x_sync.add_argument("--download-concurrency", type=int, default=None, help="Parallel media downloads.")
        x_sync.add_argument("--request-delay", type=float, default=None, help="Seconds between API requests.")
        x_sync.add_argument("--storage-strategy", default=None, help="Original storage strategy for downloaded media.")
        x_sync.add_argument("--generate-cache", action="store_true", help="Generate previews/thumbs after syncing.")
        x_sync.add_argument("--dry-run", action="store_true", help="Print what would be archived without writing.")

    fanbox_login = subparsers.add_parser(
        "fanbox-login",
        help="Derive a FANBOXSESSID from a Pixiv session cookie (Fanbox will not accept the Pixiv cookie directly).",
    )
    fanbox_login.add_argument("-c", "--cookie", default=None, help="Pixiv session cookie (also reads [pixiv].cookie).")
    fanbox_login.add_argument("--show-browser", action="store_true", help="Run the exchange with a visible browser.")
    fanbox_login.add_argument("--timeout", type=int, default=120, help="Seconds to wait for the session cookie.")

    for name, help_text in (
        ("fanbox-sync-creator", "Archive a FANBOX creator's posts as posts and their media as gallery assets."),
        ("fanbox-sync-posts", "Archive one or more FANBOX post URLs or ids."),
    ):
        fanbox_sync = subparsers.add_parser(name, help=help_text)
        if name == "fanbox-sync-creator":
            fanbox_sync.add_argument("creator", help="Creator id, @handle, or creator URL.")
            fanbox_sync.add_argument("--limit", type=int, default=None, help="Maximum posts to fetch this run.")
            fanbox_sync.add_argument("--page-size", type=int, default=None, help="Posts per list request (1-300).")
            fanbox_sync.add_argument("--max-pages", type=int, default=None, help="Maximum list pages to walk.")
            fanbox_sync.add_argument("--no-backfill", action="store_true", help="Stop at the newest archived post.")
        else:
            fanbox_sync.add_argument("targets", nargs="+", help="Post URLs or ids; each may also be a separated list.")
        fanbox_sync.add_argument("-s", "--session", default=None, help="FANBOXSESSID (also reads FANBOXSESSID or [fanbox].session_id).")
        fanbox_sync.add_argument("--no-media", action="store_true", help="Store post text only, keeping remote URLs.")
        fanbox_sync.add_argument("--no-files", action="store_true", help="Skip non-image attachments.")
        fanbox_sync.add_argument("--download-concurrency", type=int, default=None, help="Parallel media downloads.")
        fanbox_sync.add_argument("--request-delay", type=float, default=None, help="Seconds between API requests.")
        fanbox_sync.add_argument("--storage-strategy", default=None, help="Original storage strategy for downloaded media.")
        fanbox_sync.add_argument("--generate-cache", action="store_true", help="Generate previews/thumbs after syncing.")
        fanbox_sync.add_argument("--dry-run", action="store_true", help="Print what would be archived without writing.")

    posts_seed = subparsers.add_parser("posts-seed", help="Write the sample posts and index them into the database.")
    posts_seed.add_argument("--force", action="store_true", help="Write the sample posts again even if seeding already ran.")

    rebuild_db = subparsers.add_parser("rebuild-db", help="Rebuild the database index from metadata JSON.")
    rebuild_db.add_argument("--generate-cache", action="store_true")
    rebuild_db.add_argument("--merge", action="store_true", help="Do not clear existing asset rows before import.")

    media = subparsers.add_parser("generate-cache", help="Generate AVIF previews/thumbs and animated WebP ugoira cache.")
    media.add_argument("asset_key", nargs="?")

    create_user_cmd = subparsers.add_parser("create-user", help="Create an API user.")
    create_user_cmd.add_argument("username")
    create_user_cmd.add_argument("--role", default="viewer", choices=("developer", "admin", "editor", "viewer", "guest"))
    create_user_cmd.add_argument("--password", default=None)

    token_cmd = subparsers.add_parser("issue-token", help="Issue a bearer API token for a user.")
    token_cmd.add_argument("username")
    token_cmd.add_argument("--label", default="")

    password_cmd = subparsers.add_parser("set-password", help="Set or reset a user's web login password.")
    password_cmd.add_argument("username")
    password_cmd.add_argument("--password", default=None)

    security_cmd = subparsers.add_parser("security-config", help="Show or update non-UI security settings.")
    security_cmd.add_argument("--csrf-origin-check", choices=("on", "off"), default=None)
    security_cmd.add_argument("--trust-proxy-headers", choices=("on", "off"), default=None)
    security_cmd.add_argument("--viewer-api-whitelist-enabled", choices=("on", "off"), default=None)
    security_cmd.add_argument("--trusted-origin", action="append", default=None, help="Replace trusted origins; repeat for multiple values.")
    security_cmd.add_argument("--clear-trusted-origins", action="store_true")
    security_cmd.add_argument("--viewer-api-whitelist", action="append", default=None, help="Replace viewer API whitelist; repeat for multiple values.")
    security_cmd.add_argument("--clear-viewer-api-whitelist", action="store_true")

    serve = subparsers.add_parser("serve", help="Run the FastAPI service with uvicorn.")
    serve.add_argument("--host", default=None)
    serve.add_argument("--port", type=int, default=None)
    serve.add_argument("--access-log", action="store_true", help="Enable uvicorn per-request access logs.")
    serve.add_argument("--network-proxy", dest="command_network_proxy", default=None, help="Default HTTP/HTTPS proxy URL for source requests.")

    args = parser.parse_args(argv)
    network_proxy = getattr(args, "command_network_proxy", None) or args.network_proxy
    if network_proxy:
        os.environ["NYAGALLERY_NETWORK_PROXY"] = network_proxy
    config = load_config(args.config)
    apply_config_environment(config)
    storage = GalleryStorage(
        args.storage or config.core.storage,
        default_strategy=config.original_storage.default_strategy,
        strategies=config.original_storage.strategies,
    )
    storage.ensure()
    database_url = args.database_url or config.core.database_url or default_database_url(storage)

    if args.command == "generate-secret-key":
        key = generate_secret_key()
        if args.json:
            print(json.dumps({"secret_key": key, "env": "NYAGALLERY_SECRET_KEY"}, ensure_ascii=False, indent=2))
        else:
            print(key)
        return 0

    if args.command == "setup":
        config = _ensure_setup_config(args, config, storage)
        apply_config_environment(config)
        result = _setup(args, storage, database_url)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.command == "init-tags":
        path = storage.tags_dir / "catalog.json"
        if path.exists() and not args.replace:
            raise SystemExit(f"tag catalog already exists: {path}")
        TagCatalog.default().save(path)
        print(path.as_posix())
        return 0

    if args.command == "pixiv-login-browser":
        try:
            token = get_pixiv_refresh_token_with_browser(
                headless=args.headless,
                username=args.username,
                password=args.password,
                proxy_url=network_proxy_for(config, "pixiv"),
            )
        except PixivOAuthError as exc:
            raise SystemExit(str(exc)) from exc
        if args.plain:
            print(token.refresh_token)
        else:
            print(
                json.dumps(
                    {
                        "access_token": token.access_token,
                        "refresh_token": token.refresh_token,
                        "expires_in": token.expires_in,
                        "token_type": token.token_type,
                        "scope": token.scope,
                        "user": token.user,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        return 0

    if args.command == "pixiv-oauth-start":
        start = create_pixiv_oauth_start(state=args.state)
        if args.plain_url:
            print(start.authorization_url)
        else:
            print(
                json.dumps(
                    {
                        "authorization_url": start.authorization_url,
                        "code_verifier": start.code_verifier,
                        "code_challenge": start.code_challenge,
                        "state": start.state,
                        "callback_url": start.callback_url,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        return 0

    if args.command == "pixiv-oauth-exchange":
        try:
            token = exchange_pixiv_oauth_code(
                code=args.code,
                callback_url=args.callback_url,
                code_verifier=args.code_verifier,
                state=args.state,
                proxy_url=network_proxy_for(config, "pixiv"),
            )
        except PixivOAuthError as exc:
            raise SystemExit(str(exc)) from exc
        if args.plain:
            print(token.refresh_token)
        else:
            print(
                json.dumps(
                    {
                        "access_token": token.access_token,
                        "refresh_token": token.refresh_token,
                        "expires_in": token.expires_in,
                        "token_type": token.token_type,
                        "scope": token.scope,
                        "user": token.user,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        return 0

    if args.command == "migrate-metadata":
        result = storage.migrate_metadata_to_groups(archive_legacy=not args.keep_legacy)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.command == "convert":
        if args.from_mode == args.to_mode:
            raise SystemExit("--from and --to must select different metadata backends")
        output_path = Path(args.output) if args.output else None
        backup = Path(args.backup) if args.backup else (output_path.parent / "backups" if output_path else storage.root / "backups")
        if args.to_mode == "database":
            if args.from_mode != "file":
                raise SystemExit("database to database conversion is not supported")
            engine = create_engine_for_url(database_url)
            init_database(engine)
            with make_session_factory(engine)() as session:
                result = convert_file_to_database(
                    source=metadata_backend("file", storage=storage),
                    session=session,
                    storage=storage,
                    catalog=_load_catalog(storage),
                    backup_root=backup,
                    confirm=args.confirm,
                )
            engine.dispose()
        elif args.from_mode == "database":
            output_path = output_path or storage.metadata_dir
            engine = create_engine_for_url(database_url)
            init_database(engine)
            with make_session_factory(engine)() as session:
                source = metadata_backend("database", storage=storage, session=session)
                result = convert_metadata_backend(
                    source=source,
                    destination=output_path,
                    backup_root=backup,
                    confirm=args.confirm,
                )
            engine.dispose()
        else:
            output_path = output_path or storage.metadata_dir
            result = convert_metadata_backend(
                source=metadata_backend("file", storage=storage),
                destination=output_path,
                backup_root=backup,
                confirm=args.confirm,
            )
        if args.confirm:
            config_path = config.path or Path(args.config or DEFAULT_CONFIG_FILENAME)
            if config_path.exists():
                config_backup = backup / config_path.name
                config_backup.parent.mkdir(parents=True, exist_ok=True)
                config_backup.write_bytes(config_path.read_bytes())
                result["config_backup"] = config_backup.as_posix()
            config_data = read_config_file_data(config_path)
            core_data = dict(config_data.get("core") or {})
            core_data["metadata_mode"] = args.to_mode
            config_data["core"] = core_data
            save_config_file(config_data, config_path)
            result["metadata_mode"] = args.to_mode
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.command == "import":
        source_path = Path(args.source)
        importer = {
            "nyagallery_v1": NyaGalleryV1Importer(),
            "lsky_pro": LskyProImporter(),
        }.get(args.source_type)
        if importer is None:
            importer = LskyProImporter() if source_path.suffix.casefold() in {".db", ".sqlite", ".sqlite3"} else NyaGalleryV1Importer()
        assets = importer.read_source(source_path, {"upload_root": args.source_root})
        if not args.confirm:
            print(json.dumps({"status": "dry_run", "source": importer.detect_source(source_path), "target": args.target, "assets": len(assets)}, ensure_ascii=False, indent=2))
            return 0
        source_root = Path(args.source_root) if args.source_root else source_path.parent
        output = Path(args.output) if args.output else storage.root
        if args.target == "file" and args.output is None:
            output = storage.root
        if args.target == "file":
            metadata_dir = output / "metadata"
            metadata_dir.mkdir(parents=True, exist_ok=True)
            destination_root = output / "original"
        else:
            destination_root = storage.original_dir
        report = copy_assets_read_only(
            assets,
            source_root=source_root,
            destination_root=destination_root,
            hardlink=args.hardlink,
            storage_prefix="original",
        )
        if report.failures:
            for path in report.created_paths:
                candidate = Path(path)
                if candidate.exists():
                    candidate.unlink()
            raise SystemExit("import failed: " + "; ".join(report.failures))
        if args.target == "file":
            try:
                for asset in report.assets:
                    (metadata_dir / f"{asset.asset_id.removeprefix('sha256:')}.json").write_text(
                        json.dumps(asset.to_dict(), ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8",
                    )
            except Exception:
                for path in report.created_paths:
                    candidate = Path(path)
                    if candidate.exists():
                        candidate.unlink()
                raise
            result = report.to_dict()
            result["status"] = "imported"
            result["target"] = "file"
        else:
            engine = create_engine_for_url(database_url)
            init_database(engine)
            try:
                with make_session_factory(engine)() as session:
                    result = import_assets_to_database(
                        report.assets,
                        session=session,
                        storage=storage,
                        catalog=_load_catalog(storage),
                    )
            except Exception:
                for path in report.created_paths:
                    candidate = Path(path)
                    if candidate.exists():
                        candidate.unlink()
                raise
            finally:
                engine.dispose()
            result.update(report.to_dict())
            result["status"] = "imported"
            result["target"] = "database"
            config_path = config.path or Path(args.config or DEFAULT_CONFIG_FILENAME)
            config_backup = storage.root / "backups" / "import-config.toml"
            config_backed_up = False
            if config_path.exists():
                config_backup.parent.mkdir(parents=True, exist_ok=True)
                config_backup.write_bytes(config_path.read_bytes())
                config_backed_up = True
            config_data = read_config_file_data(config_path)
            core_data = dict(config_data.get("core") or {})
            core_data["metadata_mode"] = "database"
            config_data["core"] = core_data
            try:
                save_config_file(config_data, config_path)
            except Exception:
                if config_backed_up:
                    config_path.write_bytes(config_backup.read_bytes())
                raise
            result["config_backup"] = config_backup.as_posix() if config_backed_up else None
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.command == "misskey-sync-user":
        token = args.token or config.misskey.token
        if not token:
            print("error: provide --token, set MISSKEY_TOKEN, or configure [misskey].token")
            return 2
        options = MisskeyRequestOptions(
            request_delay_seconds=(
                args.request_delay if args.request_delay is not None else config.misskey.default_request_delay_seconds
            ),
            download_concurrency=args.download_concurrency or config.misskey.download_concurrency,
            proxy_url=network_proxy_for(config, "misskey") or "",
        )
        host = args.host or config.misskey.host
        page_size = normalize_page_size(args.page_size or config.misskey.page_size)
        client = MisskeyClient(token=token, host=host, options=options)
        if args.dry_run:
            user = client.get_user(args.username)
            notes = list(
                client.iter_user_notes(
                    user.user_id,
                    limit=args.limit or 20,
                    include_replies=not args.no_replies,
                    page_size=page_size,
                    max_pages=args.max_pages,
                )
            )
            print(
                json.dumps(
                    {
                        "user": {"id": user.user_id, "handle": user.handle, "notes_count": user.notes_count},
                        "notes": [
                            {"id": n.note_id, "created_at": n.created_at, "files": len(n.files), "cw": n.cw}
                            for n in notes
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        def report(event: dict) -> None:
            if event.get("stage") in {"page_fetched", "user_started", "user_done"}:
                parts = [str(event.get("message") or "")]
                for key in ("page", "sync_count", "remaining", "notes_count", "progress"):
                    if event.get(key) is not None:
                        parts.append(f"{key}={event[key]}")
                print("  " + " ".join(parts))

        service = MisskeySyncService(
            storage,
            client=client,
            downloader=MisskeyDownloader(host=host, options=options),
            storage_strategy_name=args.storage_strategy,
            download_media=not args.no_media,
            download_concurrency=options.download_concurrency,
            progress=report,
        )
        results = service.sync_user(
            args.username,
            limit=args.limit,
            backfill=not args.no_backfill,
            include_replies=not args.no_replies,
            page_size=page_size,
            max_pages=args.max_pages,
        )
        assets = [asset for result in results for asset in result.assets]
        catalog = _load_catalog(storage)
        engine = create_engine_for_url(database_url)
        init_database(engine)
        session_factory = make_session_factory(engine)
        media_results = []
        if args.generate_cache:
            media_results = [
                item.__dict__
                for item in MediaGenerator(storage, limits=media_limits_from_config(config.media)).generate_all()
            ]
        with session_factory() as session:
            rebuild = rebuild_database(session, storage, catalog)
        catalog.save(storage.tags_dir / "catalog.json")
        print(
            json.dumps(
                {
                    "posts": len(results),
                    "assets": len(assets),
                    "downloaded": len([a for a in assets if a.status == "downloaded"]),
                    "skipped": len([a for a in assets if a.status == "skipped"]),
                    "duplicates": len([a for a in assets if a.status == "duplicate"]),
                    "rebuild": rebuild.__dict__,
                    "media": media_results,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        engine.dispose()
        return 0

    if args.command in {"x-sync-user", "x-sync-posts"}:
        options = XRequestOptions(
            request_delay_seconds=(
                args.request_delay if args.request_delay is not None else config.x.default_request_delay_seconds
            ),
            download_concurrency=args.download_concurrency or config.x.download_concurrency,
            proxy_url=network_proxy_for(config, "x") or "",
        )
        credentials = XCredentials(
            auth_token=(args.auth_token or config.x.auth_token or "").strip(),
            ct0=(args.ct0 or config.x.ct0 or "").strip(),
        )
        if args.command == "x-sync-user" and not credentials.is_complete:
            print("error: walking a timeline needs a session; pass --auth-token/--ct0, set X_AUTH_TOKEN/X_CT0, or configure [x]")
            return 2
        client = XClient(
            credentials=credentials,
            options=options,
            operations=XGraphqlOperations(
                tweet_detail=config.x.tweet_detail_query_id,
                user_by_screen_name=config.x.user_by_screen_name_query_id,
                user_tweets=config.x.user_tweets_query_id,
                user_media=config.x.user_media_query_id,
            ),
        )
        targets = (
            [item for target in args.targets for item in split_batch_input(target)]
            if args.command == "x-sync-posts"
            else []
        )
        if args.dry_run:
            if args.command == "x-sync-posts":
                preview = [
                    {"id": t.tweet_id, "author": t.user.screen_name, "created_at": t.created_at,
                     "media": len(t.media), "metrics": t.metrics, "tags": list(t.tags)}
                    for t in (client.get_tweet(target) for target in targets)
                ]
                print(json.dumps({"posts": preview}, ensure_ascii=False, indent=2))
                return 0
            user = client.get_user(args.username)
            tweets = list(
                client.iter_user_tweets(
                    user.user_id,
                    limit=args.limit or 20,
                    media_only=args.media_only,
                    include_replies=not args.no_replies,
                    page_size=normalize_x_page_size(args.page_size or config.x.page_size),
                    max_pages=args.max_pages,
                )
            )
            print(
                json.dumps(
                    {
                        "user": {"id": user.user_id, "handle": user.handle, "tweets_count": user.statuses_count},
                        "posts": [
                            {"id": t.tweet_id, "created_at": t.created_at, "media": len(t.media), "metrics": t.metrics}
                            for t in tweets
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        def report(event: dict) -> None:
            if event.get("stage") in {"page_fetched", "user_started", "user_done", "batch_started", "batch_done", "tweet_failed"}:
                parts = [str(event.get("message") or "")]
                for key in ("page", "sync_count", "remaining", "tweets_count", "failure_count", "progress"):
                    if event.get(key) is not None:
                        parts.append(f"{key}={event[key]}")
                print("  " + " ".join(parts))

        catalog = _load_catalog(storage)
        generator = MediaGenerator(storage, limits=media_limits_from_config(config.media))
        service = XSyncService(
            storage,
            client=client,
            downloader=XDownloader(options=options),
            storage_strategy_name=args.storage_strategy,
            download_media=not args.no_media,
            download_concurrency=options.download_concurrency,
            cover_writer=generator.generate_from_cover,
            progress=report,
        )
        failures: list = []
        if args.command == "x-sync-posts":
            batch = service.sync_posts(targets)
            results, failures = list(batch.results), list(batch.failures)
        else:
            results = service.sync_user(
                normalize_screen_name(args.username),
                limit=args.limit,
                backfill=not args.no_backfill,
                include_replies=not args.no_replies,
                media_only=args.media_only,
                page_size=normalize_x_page_size(args.page_size or config.x.page_size),
                max_pages=args.max_pages,
            )
        assets = [asset for result in results for asset in result.assets]
        engine = create_engine_for_url(database_url)
        init_database(engine)
        session_factory = make_session_factory(engine)
        media_results = []
        if args.generate_cache:
            media_results = [item.__dict__ for item in generator.generate_all()]
        with session_factory() as session:
            rebuild = rebuild_database(session, storage, catalog)
        catalog.save(storage.tags_dir / "catalog.json")
        print(
            json.dumps(
                {
                    "posts": len(results),
                    "assets": len(assets),
                    "downloaded": len([a for a in assets if a.status == "downloaded"]),
                    "skipped": len([a for a in assets if a.status == "skipped"]),
                    "duplicates": len([a for a in assets if a.status == "duplicate"]),
                    "videos": len([a for a in assets if not a.needs_transcode]),
                    "failures": [failure.to_dict() for failure in failures],
                    "rebuild": rebuild.__dict__,
                    "media": media_results,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        engine.dispose()
        return 0

    if args.command == "fanbox-login":
        cookie = (args.cookie or config.pixiv.cookie or "").strip()
        if not cookie:
            print("error: provide --cookie or configure [pixiv].cookie; Fanbox has no credential of its own to reuse")
            return 2
        session_id = exchange_pixiv_cookie_for_fanbox_session(
            cookie,
            headless=not args.show_browser,
            timeout_seconds=args.timeout,
            proxy_url=network_proxy_for(config, "fanbox") or network_proxy_for(config, "pixiv"),
        )
        print(json.dumps({"session_id": session_id, "cookie": f"FANBOXSESSID={session_id}"}, indent=2))
        return 0

    if args.command in {"fanbox-sync-creator", "fanbox-sync-posts"}:
        options = FanboxRequestOptions(
            request_delay_seconds=(
                args.request_delay if args.request_delay is not None else config.fanbox.default_request_delay_seconds
            ),
            download_concurrency=args.download_concurrency or config.fanbox.download_concurrency,
            proxy_url=network_proxy_for(config, "fanbox") or "",
        )
        credentials = FanboxCredentials(session_id=(args.session or config.fanbox.session_id or "").strip())
        if not credentials.is_complete:
            print("warning: no FANBOXSESSID configured; only public summaries are readable and no media will archive")
        client = FanboxClient(credentials=credentials, options=options)
        if args.dry_run:
            if args.command == "fanbox-sync-posts":
                targets = [i for t in args.targets for i in fanbox_split_batch_input(t)]
                preview = [
                    {"id": p.post_id, "title": p.title, "type": p.post_type, "fee": p.fee_required,
                     "locked": p.is_locked, "files": len(p.files)}
                    for p in (client.get_post(t) for t in targets)
                ]
            else:
                creator = client.get_creator(args.creator)
                preview = {
                    "creator": {"id": creator.creator_id, "user_id": creator.user_id, "name": creator.display_name},
                    "posts": [
                        {"id": p.post_id, "title": p.title, "fee": p.fee_required, "at": p.published_at}
                        for p in client.iter_creator_posts(
                            creator.creator_id,
                            limit=args.limit or 20,
                            page_size=normalize_fanbox_page_size(args.page_size or config.fanbox.page_size),
                            max_pages=args.max_pages,
                        )
                    ],
                }
            print(json.dumps(preview, ensure_ascii=False, indent=2))
            return 0

        def report(event: dict) -> None:
            if event.get("stage") in {"page_fetched", "creator_started", "creator_done", "batch_started", "batch_done", "post_failed"}:
                parts = [str(event.get("message") or "")]
                for key in ("page", "sync_count", "remaining", "failure_count", "locked_posts", "progress"):
                    if event.get(key) is not None:
                        parts.append(f"{key}={event[key]}")
                print("  " + " ".join(parts))

        catalog = _load_catalog(storage)
        service = FanboxSyncService(
            storage,
            client=client,
            downloader=FanboxDownloader(credentials=credentials, options=options),
            storage_strategy_name=args.storage_strategy,
            download_media=not args.no_media,
            download_files=not args.no_files,
            download_concurrency=options.download_concurrency,
            progress=report,
        )
        failures: list = []
        if args.command == "fanbox-sync-posts":
            batch = service.sync_posts(args.targets)
            results, failures = list(batch.results), list(batch.failures)
        else:
            results = service.sync_creator(
                normalize_creator_id(args.creator),
                limit=args.limit,
                backfill=not args.no_backfill,
                page_size=normalize_fanbox_page_size(args.page_size or config.fanbox.page_size),
                max_pages=args.max_pages,
            )
        assets = [asset for result in results for asset in result.assets]
        engine = create_engine_for_url(database_url)
        init_database(engine)
        session_factory = make_session_factory(engine)
        media_results = []
        if args.generate_cache:
            media_results = [
                item.__dict__
                for item in MediaGenerator(storage, limits=media_limits_from_config(config.media)).generate_all()
            ]
        with session_factory() as session:
            rebuild = rebuild_database(session, storage, catalog)
        catalog.save(storage.tags_dir / "catalog.json")
        print(
            json.dumps(
                {
                    "posts": len(results),
                    "locked": len([r for r in results if r.locked]),
                    "assets": len(assets),
                    "downloaded": len([a for a in assets if a.status == "downloaded"]),
                    "skipped": len([a for a in assets if a.status == "skipped"]),
                    "duplicates": len([a for a in assets if a.status == "duplicate"]),
                    "files": len([a for a in assets if a.kind != "image"]),
                    "failures": [f.to_dict() for f in failures],
                    "rebuild": rebuild.__dict__,
                    "media": media_results,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        engine.dispose()
        return 0

    if args.command == "posts-seed":
        post_store = PostStore(storage.root)
        post_store.ensure()
        engine = create_engine_for_url(database_url)
        init_database(engine)
        session_factory = make_session_factory(engine)
        with session_factory() as session:
            asset_keys = list(
                session.scalars(
                    select(AssetModel.asset_key)
                    .where(AssetModel.deletion_status.is_(None))
                    .order_by(AssetModel.asset_key)
                    .limit(3)
                ).all()
            )
            if args.force:
                for post in sample_posts(asset_keys):
                    post_store.write_post(post)
                seeded = 2
            else:
                seeded = ensure_sample_posts(post_store, asset_keys=asset_keys)
                seeded += link_sample_post_media(post_store, asset_keys=asset_keys)
            result = rebuild_posts(session, post_store, replace=True)
            session.commit()
        print(
            json.dumps(
                {"seeded": seeded, "posts": result.posts, "attachments": result.attachments},
                ensure_ascii=False,
            )
        )
        engine.dispose()
        return 0

    if args.command in {"rebuild-db", "create-user", "issue-token", "set-password", "security-config"}:
        catalog = _load_catalog(storage)
        engine = create_engine_for_url(database_url)
        init_database(engine)
        session_factory = make_session_factory(engine)
        with session_factory() as session:
            if args.command == "rebuild-db":
                media_results = []
                if args.generate_cache:
                    media_results = [
                        item.__dict__
                        for item in MediaGenerator(storage, limits=media_limits_from_config(config.media)).generate_all()
                    ]
                result = rebuild_database(session, storage, catalog, replace=not args.merge)
                catalog.save(storage.tags_dir / "catalog.json")
                print(
                    json.dumps(
                        {
                            "assets": result.assets,
                            "tags": result.tags,
                            "duplicates": result.duplicates,
                            "posts": result.posts,
                            "post_attachments": result.post_attachments,
                            "media": media_results,
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                )
                engine.dispose()
                return 0
            if args.command == "create-user":
                password = args.password or getpass.getpass("Password: ")
                user = create_user(session, args.username, password, args.role)
                print(json.dumps({"id": user.id, "username": user.username, "role": user.role}, ensure_ascii=False))
                engine.dispose()
                return 0
            if args.command == "issue-token":
                print(issue_api_token(session, args.username, label=args.label))
                engine.dispose()
                return 0
            if args.command == "set-password":
                password = args.password or getpass.getpass("Password: ")
                user = set_user_password(session, args.username, password)
                print(
                    json.dumps(
                        {
                            "id": user.id,
                            "username": user.username,
                            "role": user.role,
                            "password": "updated",
                            "storage": str(storage.root),
                            "database_url": database_url,
                        },
                        ensure_ascii=False,
                    )
                )
                engine.dispose()
                return 0
            if args.command == "security-config":
                updates: dict[str, object] = {}
                if args.csrf_origin_check is not None:
                    updates["csrf_origin_check_enabled"] = args.csrf_origin_check == "on"
                if args.trust_proxy_headers is not None:
                    updates["trust_proxy_headers"] = args.trust_proxy_headers == "on"
                if args.viewer_api_whitelist_enabled is not None:
                    updates["viewer_api_whitelist_enabled"] = args.viewer_api_whitelist_enabled == "on"
                if args.clear_trusted_origins:
                    updates["trusted_origins"] = []
                elif args.trusted_origin is not None:
                    updates["trusted_origins"] = args.trusted_origin
                if args.clear_viewer_api_whitelist:
                    updates["viewer_api_whitelist"] = []
                elif args.viewer_api_whitelist is not None:
                    updates["viewer_api_whitelist"] = args.viewer_api_whitelist
                result = (
                    update_security_settings(session, updates, updated_by_username="cli")
                    if updates
                    else get_security_settings(session)
                )
                print(json.dumps(result, ensure_ascii=False, indent=2))
                engine.dispose()
                return 0

    if args.command == "generate-cache":
        generator = MediaGenerator(storage, limits=media_limits_from_config(config.media))
        if args.asset_key:
            results = [generator.generate_for_asset_key(args.asset_key).__dict__]
        else:
            results = [item.__dict__ for item in generator.generate_all()]
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return 0

    if args.command == "serve":
        import uvicorn

        if args.config:
            os.environ["NYAGALLERY_CONFIG"] = str(Path(args.config).expanduser())
        os.environ["NYAGALLERY_STORAGE"] = str(storage.root)
        os.environ["NYAGALLERY_DATABASE_URL"] = database_url
        uvicorn.run(
            "nyagallery.app:create_app",
            factory=True,
            host=args.host or config.server.host,
            port=args.port or config.server.port,
            reload=False,
            access_log=args.access_log or config.server.access_log,
        )
        return 0

    client, downloader = _pixiv_cli_sync_components(args, config)
    storage_strategy = storage.validate_storage_strategy(args.storage_strategy)
    service = PixivSyncService(storage, client=client, downloader=downloader, storage_strategy_name=storage_strategy)
    if args.command == "pixiv-sync-pid":
        results = service.sync_pid(args.pid)
    elif args.command == "pixiv-sync-user":
        results = service.sync_user(args.uid, limit=args.limit)
    else:
        parser.error(f"unknown command: {args.command}")
        return 2

    media_results = []
    rebuild_result = None
    if args.generate_cache:
        generator = MediaGenerator(storage, limits=media_limits_from_config(config.media))
        for result in results:
            if result.status != "skipped":
                media_results.append(generator.generate_for_asset_key(result.asset_key).__dict__)
    if args.rebuild_db or args.generate_cache:
        catalog = _load_catalog(storage)
        engine = create_engine_for_url(database_url)
        init_database(engine)
        session_factory = make_session_factory(engine)
        with session_factory() as session:
            rebuild_result = rebuild_database(session, storage, catalog)
        catalog.save(storage.tags_dir / "catalog.json")
        engine.dispose()
    print(
        json.dumps(
            {
                "sync": [result.__dict__ for result in results],
                "media": media_results,
                "rebuild": rebuild_result.__dict__ if rebuild_result else None,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _load_catalog(storage: GalleryStorage) -> TagCatalog:
    path = storage.tags_dir / "catalog.json"
    return TagCatalog.load(path) if path.exists() else TagCatalog.default()


def _pixiv_cli_sync_components(args, config: NyaGalleryConfig) -> tuple[object, object]:
    mode = str(args.auth_mode or "auto").strip().casefold().replace("-", "_")
    refresh_token = args.refresh_token or config.pixiv.refresh_token
    cookie = args.cookie or config.pixiv.cookie
    options = PixivRequestOptions(proxy_url=network_proxy_for(config, "pixiv") or "")
    if mode == "auto":
        if cookie:
            mode = "cookie"
        elif refresh_token or os.environ.get("PIXIV_REFRESH_TOKEN"):
            mode = "refresh_token"
        else:
            mode = "public"
    if mode == "public":
        return PixivCookieClient("", options=options), HTTPPixivDownloader(options=options)
    if mode == "cookie":
        if not cookie:
            raise SystemExit("--auth-mode cookie requires --cookie")
        return PixivCookieClient(cookie, options=options), HTTPPixivDownloader(cookie=cookie, options=options)
    if mode == "refresh_token":
        return PixivPyClient.from_refresh_token(refresh_token, options=options), HTTPPixivDownloader(options=options)
    raise SystemExit(f"unsupported Pixiv auth mode: {mode}")


def _ensure_setup_config(args, config: NyaGalleryConfig, _storage: GalleryStorage) -> NyaGalleryConfig:
    config_path = Path(args.config).expanduser() if args.config else config.path or Path("nyagallery.toml")
    data = config_to_dict(config, redact_secrets=False)
    core = data.setdefault("core", {})
    if isinstance(core, dict):
        core["storage"] = args.storage or config.core.storage
        core["database_url"] = args.database_url or config.core.database_url or ""
    saved = save_config_file(data, config_path)
    return saved


def _setup(args, storage: GalleryStorage, database_url: str) -> dict[str, object]:
    tag_catalog_path = storage.tags_dir / "catalog.json"
    if args.replace_tags or not tag_catalog_path.exists():
        TagCatalog.default().save(tag_catalog_path)
        tag_action = "created"
    else:
        tag_action = "kept"

    metadata_migration = {"skipped": True}
    if not args.skip_metadata_migration:
        metadata_migration = storage.migrate_metadata_to_groups()

    catalog = _load_catalog(storage)
    engine = create_engine_for_url(database_url)
    init_database(engine)
    session_factory = make_session_factory(engine)
    media_results = []
    if args.generate_cache:
        media_results = [item.__dict__ for item in MediaGenerator(storage, limits=media_limits_from_config(config.media)).generate_all()]

    with session_factory() as session:
        encrypted_credentials = encrypt_stored_pixiv_credentials(session)
        rebuild_result = rebuild_database(session, storage, catalog)
        catalog.save(storage.tags_dir / "catalog.json")
        user = session.scalar(select(UserModel).where(UserModel.username == args.username))
        user_action = "kept"
        if user is None:
            password = args.password or _prompt_new_password()
            user = create_user(session, args.username, password, args.role)
            user_action = "created"
        else:
            changed = False
            if args.password:
                user.password_hash = hash_password(args.password)
                changed = True
            if user.role != args.role:
                user.role = args.role
                changed = True
            if changed:
                user.updated_at = now_utc()
                session.commit()
                user_action = "updated"
        token = issue_api_token(session, user.username)

    engine.dispose()
    return {
        "storage": str(storage.root),
        "tag_catalog": tag_action,
        "metadata_migration": metadata_migration,
        "database": {
            "url": database_url,
            "assets": rebuild_result.assets,
            "tags": rebuild_result.tags,
            "duplicates": rebuild_result.duplicates,
        },
        "media": media_results,
        "secret_encryption": {
            "enabled": secret_encryption_enabled(),
            "pixiv_tokens_encrypted": encrypted_credentials["pixiv_tokens"],
            "pixiv_cookies_encrypted": encrypted_credentials["pixiv_cookies"],
        },
        "user": {
            "id": user.id,
            "username": user.username,
            "role": user.role,
            "action": user_action,
        },
        "token": token,
    }


def _prompt_new_password() -> str:
    while True:
        password = getpass.getpass("Admin password: ")
        confirm = getpass.getpass("Confirm password: ")
        if password == confirm:
            if password:
                return password
            print("Password cannot be empty.")
        else:
            print("Passwords do not match.")


if __name__ == "__main__":
    raise SystemExit(main())
