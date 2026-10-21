"""Local account recovery without passwords in arguments or output.

Run from the backend directory: python -m app.admin reset-password [email]
"""
import argparse
import getpass
import hmac
import re
import sys
import warnings

from sqlalchemy.exc import SQLAlchemyError

from .account_security import locked_user, revoke_sessions
from .database import SessionLocal
from .security import decrypt, digest, encrypt, password_hash
from .services import event


class SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse normally repeats unrecognized arguments, which could include
        # an accidentally supplied password. Do not echo any argument values.
        self.print_usage(sys.stderr)
        self.exit(2,"Invalid command arguments. Use --help for usage.\n")


def main(argv=None):
    parser = SafeArgumentParser(description="Local account recovery. Passwords are requested with hidden prompts.")
    commands = parser.add_subparsers(dest="command",required=True)
    reset = commands.add_parser("reset-password",help="Revoke sessions, reset a password and activate emergency stop")
    reset.add_argument("email",nargs="?",help="Account email; requested interactively if omitted")
    args = parser.parse_args(argv)
    try:
        email = (args.email if args.email is not None else input("Account email: ")).strip().lower()
        if len(email)>254 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+",email):
            print("A valid account email is required.",file=sys.stderr)
            return 1
        with warnings.catch_warnings():
            # getpass otherwise falls back to echoed input when no hidden
            # terminal is available. Refuse recovery in that situation.
            warnings.simplefilter("error",getpass.GetPassWarning)
            password = getpass.getpass("New password: ")
            confirmation = getpass.getpass("Confirm new password: ")
        if not 12<=len(password)<=256:
            print("Password must contain between 12 and 256 characters.",file=sys.stderr)
            return 1
        if not hmac.compare_digest(password.encode(),confirmation.encode()):
            print("Passwords do not match. No account changes made.",file=sys.stderr)
            return 1
        new_hash = password_hash(password)
        with SessionLocal() as db:
            user = locked_user(db,email_hash=digest(email))
            if user is None:
                print("Account not found. No account changes made.",file=sys.stderr)
                return 1
            user.password_hash = new_hash
            policy = decrypt(user.policy_encrypted)
            policy["emergency_stop"] = True
            user.policy_encrypted = encrypt(policy)
            revoke_sessions(db,user.id)
            event(db,user.id,"password_reset","Password reset by local operator; all sessions signed out and emergency stop activated",notify=True)
            db.commit()
    except (EOFError,KeyboardInterrupt,getpass.GetPassWarning):
        print("Hidden password entry is unavailable or recovery was cancelled. No account changes made.",file=sys.stderr)
        return 1
    except SQLAlchemyError:
        print("Account recovery could not be completed. Check the local database configuration.",file=sys.stderr)
        return 1
    print("Password reset. All sessions signed out; emergency stop is active.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
