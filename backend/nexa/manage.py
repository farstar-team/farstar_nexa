import argparse
import getpass

from sqlalchemy import select

from nexa.db import SessionLocal
from nexa.models import User
from nexa.routes.auth import Register, create_user
from nexa.security import audit, issue_token


def main():
    parser = argparse.ArgumentParser(prog="nexa-manage")
    parser.add_argument("command", choices=["create-admin", "reset-password", "telegram-webhook"])
    args = parser.parse_args()
    if args.command == "telegram-webhook":
        from nexa.telegram import configure_webhook

        configure_webhook()
        print("Telegram webhook configured.")
        return
    with SessionLocal() as db:
        if args.command == "create-admin":
            if db.scalar(select(User).where(User.role == "SUPER_ADMIN")):
                print("An owner already exists. Use reset-password for recovery.")
                return
            username, email = input("Admin username: "), input("Admin email: ")
            password = getpass.getpass("Password (12+ characters): ")
            if password != getpass.getpass("Confirm password: "):
                raise SystemExit("Passwords do not match.")
            try:
                data = Register(username=username, email=email, password=password)
            except ValueError:
                raise SystemExit("Invalid username, email, or weak password.") from None
            user = create_user(db, data, "SUPER_ADMIN")
            audit(db, user.id, "admin.bootstrapped")
            db.commit()
            print("Administrator created. Sign in using your chosen credentials.")
        else:
            username = input("Username to recover: ").lower()
            user = db.scalar(select(User).where(User.username == username))
            if not user:
                raise SystemExit("User not found.")
            token = issue_token(db, user.id, "password_reset", minutes=15)
            audit(db, user.id, "auth.recovery_issued_cli")
            db.commit()
            print("One-time recovery token (15 minutes; keep private): " + token)


if __name__ == "__main__":
    main()
