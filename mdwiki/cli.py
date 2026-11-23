from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .build import BuildError, build
from .config import ConfigError, SiteConfig
from .ordering import OrderError, append, insert_after, insert_before, remove
from .server import serve
from .validate import validate_report


def _cmd_serve(args: argparse.Namespace) -> int:
    serve(dir=args.dir, port=args.port, config=args.config, widgets=args.widgets, host=args.host, watch=args.watch)
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    config = SiteConfig.load(Path(args.config) if args.config else None)
    widgets_dir = Path(args.widgets).resolve() if args.widgets else config.widgets_dir
    errors, warnings = validate_report(Path(args.dir), config, widgets_dir)
    if not errors and not warnings:
        print("mdwiki validate: clean, no issues found.")
        return 0
    if errors:
        print(f"mdwiki validate: {len(errors)} error(s):")
        for issue in errors:
            print(f"  - {issue}")
    if warnings:
        print(f"mdwiki validate: {len(warnings)} warning(s){' (failing: --strict)' if args.strict else ''}:")
        for issue in warnings:
            print(f"  - {issue}")
    return 1 if errors or (warnings and args.strict) else 0


def _cmd_build(args: argparse.Namespace) -> int:
    try:
        pages = build(
            Path(args.dir),
            Path(args.out),
            config_path=Path(args.config) if args.config else None,
            widgets_dir=Path(args.widgets) if args.widgets else None,
        )
    except BuildError as exc:
        print(f"mdwiki build: {exc}", file=sys.stderr)
        return 1
    print(f"mdwiki build: wrote {pages} page(s) to {args.out}")
    return 0


def _cmd_order(args: argparse.Namespace) -> int:
    dir_path = Path(args.order_dir)
    try:
        if args.order_action == "insert-after":
            insert_after(dir_path, args.existing_name, args.new_name)
        elif args.order_action == "insert-before":
            insert_before(dir_path, args.existing_name, args.new_name)
        elif args.order_action == "append":
            append(dir_path, args.new_name)
        elif args.order_action == "remove":
            remove(dir_path, args.name)
    except OrderError as exc:
        print(f"mdwiki order: {exc}", file=sys.stderr)
        return 2
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mdwiki")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_serve = sub.add_parser("serve", help="Serve a directory of markdown files as a wiki.")
    p_serve.add_argument("--dir", required=True, help="Content root directory.")
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--config", default=None, help="Path to mdwiki.yml (site config).")
    p_serve.add_argument("--widgets", default=None, help="Host-supplied widgets directory.")
    p_serve.add_argument(
        "--watch",
        action="store_true",
        help="Reload open pages in the browser when a content or theme file changes (for authoring).",
    )
    p_serve.set_defaults(func=_cmd_serve)

    p_validate = sub.add_parser("validate", help="Pre-flight check: _order.yml entries, widget references.")
    p_validate.add_argument("--dir", required=True)
    p_validate.add_argument("--config", default=None)
    p_validate.add_argument("--widgets", default=None)
    p_validate.add_argument(
        "--strict",
        action="store_true",
        help="Also fail on warnings (pages not positioned in _order.yml, unknown mdwiki.yml keys).",
    )
    p_validate.set_defaults(func=_cmd_validate)

    p_build = sub.add_parser("build", help="Export the wiki as static HTML files (for GitHub Pages etc).")
    p_build.add_argument("--dir", required=True, help="Content root directory.")
    p_build.add_argument("--out", required=True, help="Output directory (created; must be empty or a previous build).")
    p_build.add_argument("--config", default=None)
    p_build.add_argument("--widgets", default=None)
    p_build.set_defaults(func=_cmd_build)

    p_order = sub.add_parser("order", help="Edit a directory's _order.yml without hand-editing YAML.")
    order_sub = p_order.add_subparsers(dest="order_action", required=True)

    p_ia = order_sub.add_parser("insert-after")
    p_ia.add_argument("order_dir")
    p_ia.add_argument("existing_name")
    p_ia.add_argument("new_name")

    p_ib = order_sub.add_parser("insert-before")
    p_ib.add_argument("order_dir")
    p_ib.add_argument("existing_name")
    p_ib.add_argument("new_name")

    p_ap = order_sub.add_parser("append")
    p_ap.add_argument("order_dir")
    p_ap.add_argument("new_name")

    p_rm = order_sub.add_parser("remove")
    p_rm.add_argument("order_dir")
    p_rm.add_argument("name")

    p_order.set_defaults(func=_cmd_order)

    return parser


def _check_paths(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    """Fail fast on a mistyped path instead of serving an empty site or
    reporting a nonexistent one as "clean"."""
    if getattr(args, "dir", None) is not None and not Path(args.dir).is_dir():
        parser.error(f"--dir {args.dir}: not a directory")
    if getattr(args, "config", None) and not Path(args.config).is_file():
        parser.error(f"--config {args.config}: no such file")
    if getattr(args, "widgets", None) and not Path(args.widgets).is_dir():
        parser.error(f"--widgets {args.widgets}: not a directory")


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    _check_paths(parser, args)
    try:
        sys.exit(args.func(args))
    except ConfigError as exc:
        print(f"mdwiki: {exc}", file=sys.stderr)
        sys.exit(2)
