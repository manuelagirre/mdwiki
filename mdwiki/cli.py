from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import SiteConfig
from .ordering import append, insert_after, insert_before, remove
from .server import serve
from .validate import validate


def _cmd_serve(args: argparse.Namespace) -> int:
    serve(dir=args.dir, port=args.port, config=args.config, widgets=args.widgets, host=args.host)
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    config = SiteConfig.load(Path(args.config) if args.config else None)
    widgets_dir = Path(args.widgets).resolve() if args.widgets else None
    issues = validate(Path(args.dir), config, widgets_dir)
    if not issues:
        print("mdwiki validate: clean, no issues found.")
        return 0
    print(f"mdwiki validate: {len(issues)} issue(s):")
    for issue in issues:
        print(f"  - {issue}")
    return 1


def _cmd_order(args: argparse.Namespace) -> int:
    dir_path = Path(args.order_dir)
    if args.order_action == "insert-after":
        insert_after(dir_path, args.existing_name, args.new_name)
    elif args.order_action == "insert-before":
        insert_before(dir_path, args.existing_name, args.new_name)
    elif args.order_action == "append":
        append(dir_path, args.new_name)
    elif args.order_action == "remove":
        remove(dir_path, args.name)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mdwiki")
    sub = parser.add_subparsers(dest="command", required=True)

    p_serve = sub.add_parser("serve", help="Serve a directory of markdown files as a wiki.")
    p_serve.add_argument("--dir", required=True, help="Content root directory.")
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--config", default=None, help="Path to mdwiki.yml (site config).")
    p_serve.add_argument("--widgets", default=None, help="Host-supplied widgets directory.")
    p_serve.set_defaults(func=_cmd_serve)

    p_validate = sub.add_parser("validate", help="Pre-flight check: _order.yml entries, widget references.")
    p_validate.add_argument("--dir", required=True)
    p_validate.add_argument("--config", default=None)
    p_validate.add_argument("--widgets", default=None)
    p_validate.set_defaults(func=_cmd_validate)

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


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    sys.exit(args.func(args))
