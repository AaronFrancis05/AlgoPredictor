"""Operator commands that must work before any admin exists.

  python -m app.admin_tools set-role <email> admin|user

The account must already exist (registered or signed in with Google once). The change is audited.
"""
import argparse
import asyncio
import sys

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import get_sessionmaker
from app.models import ROLES
from app.services import access_tokens
from app.services.audit import audit


async def set_role(email: str, role: str) -> int:
    async with get_sessionmaker()() as db:
        try:
            user = await access_tokens.set_role(db, email, role)
        except LookupError as e:
            print(e, file=sys.stderr)
            return 1
        await audit(db, "role_changed", None, None, target=str(user.id), role=role, via="admin_tools")
        await db.commit()
    try:
        await access_tokens.after_change()
    except Exception as e:  # Redis unreachable from here: the cached plan expires within a minute anyway
        print(f"note: could not clear the plan cache ({e.__class__.__name__}); takes effect within 60 s")
    print(f"{email} is now {role}")
    return 0


def main() -> None:
    configure_logging(get_settings().log_level)
    ap = argparse.ArgumentParser(prog="python -m app.admin_tools")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sr = sub.add_parser("set-role", help="make an account admin or user")
    sr.add_argument("email")
    sr.add_argument("role", choices=ROLES)
    args = ap.parse_args()
    raise SystemExit(asyncio.run(set_role(args.email, args.role)))


if __name__ == "__main__":
    main()
