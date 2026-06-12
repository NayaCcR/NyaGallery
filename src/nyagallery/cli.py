from __future__ import annotations

import argparse
import getpass
import json
import os
from pathlib import Path

from sqlalchemy import select

from nyagallery.config import NyaGalleryConfig, apply_config_environment, config_to_dict, load_config, save_config_file
from nyagallery.db import (
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
    set_user_password,
    update_security_settings,
)
from nyagallery.auth import hash_password
from nyagallery.media import MediaGenerator
from nyagallery.pixiv import (
    PixivOAuthError,
    HTTPPixivDownloader,
    PixivCookieClient,
    PixivPyClient,
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
    subparsers = parser.add_subparsers(dest="command", required=True)

    secret_key_cmd = subparsers.add_parser("generate-secret-key", help="Generate a deployment secret key for encrypted credentials.")
    secret_key_cmd.add_argument("--json", action="store_true", help="Print as a JSON object.")

    sync_pid = subparsers.add_parser("pixiv-sync-pid", help="Sync one Pixiv artwork by PID.")
    sync_pid.add_argument("pid")
    sync_pid.add_argument("--auth-mode", default="auto", help="auto, public, refresh_token, or cookie.")
    sync_pid.add_argument("--refresh-token", default=None)
    sync_pid.add_argument("--cookie", default=None)
    sync_pid.add_argument("--storage-strategy", default=None, help="Original storage strategy name.")
    sync_pid.add_argument("--generate-cache", action="store_true")
    sync_pid.add_argument("--rebuild-db", action="store_true")

    sync_user = subparsers.add_parser("pixiv-sync-user", help="Sync Pixiv artworks by user UID.")
    sync_user.add_argument("uid")
    sync_user.add_argument("--limit", type=int, default=None)
    sync_user.add_argument("--auth-mode", default="auto", help="auto, public, refresh_token, or cookie.")
    sync_user.add_argument("--refresh-token", default=None)
    sync_user.add_argument("--cookie", default=None)
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

    args = parser.parse_args(argv)
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

    if args.command in {"rebuild-db", "create-user", "issue-token", "set-password", "security-config"}:
        catalog = _load_catalog(storage)
        engine = create_engine_for_url(database_url)
        init_database(engine)
        session_factory = make_session_factory(engine)
        with session_factory() as session:
            if args.command == "rebuild-db":
                media_results = []
                if args.generate_cache:
                    media_results = [item.__dict__ for item in MediaGenerator(storage).generate_all()]
                result = rebuild_database(session, storage, catalog, replace=not args.merge)
                catalog.save(storage.tags_dir / "catalog.json")
                print(
                    json.dumps(
                        {
                            "assets": result.assets,
                            "tags": result.tags,
                            "duplicates": result.duplicates,
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
        generator = MediaGenerator(storage)
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
        generator = MediaGenerator(storage)
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
    if mode == "auto":
        if cookie:
            mode = "cookie"
        elif refresh_token or os.environ.get("PIXIV_REFRESH_TOKEN"):
            mode = "refresh_token"
        else:
            mode = "public"
    if mode == "public":
        return PixivCookieClient(""), HTTPPixivDownloader()
    if mode == "cookie":
        if not cookie:
            raise SystemExit("--auth-mode cookie requires --cookie")
        return PixivCookieClient(cookie), HTTPPixivDownloader(cookie=cookie)
    if mode == "refresh_token":
        return PixivPyClient.from_refresh_token(refresh_token), HTTPPixivDownloader()
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
        media_results = [item.__dict__ for item in MediaGenerator(storage).generate_all()]

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
