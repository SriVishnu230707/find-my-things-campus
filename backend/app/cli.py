"""Local administration: never expose these commands as public API routes."""
import argparse
from datetime import datetime, timezone
from getpass import getpass
import os
import secrets
from sqlalchemy import select
from sqlalchemy.orm import Session
from pydantic import ValidationError
from app.database import engine, verify_database
from app.models.users import User
from app.models.items import Item
from app.schemas.users import UserRegister, normalize_email
from app.security import SECRET_FILE, hash_password


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init-secret")
    create = commands.add_parser("create-staff")
    create.add_argument("--email", required=True)
    create.add_argument("--name", required=True)
    role = commands.add_parser("set-role")
    role.add_argument("--email", required=True)
    role.add_argument("--role", choices=["student", "staff"], required=True)
    owner = commands.add_parser("assign-owner")
    owner.add_argument("--item-id", type=int, required=True)
    owner.add_argument("--email", required=True)
    args = parser.parse_args()
    try:
        if args.command == "init-secret":
            SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
            try:
                descriptor = os.open(SECRET_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                print("Signing secret already exists; kept unchanged.")
                return
            with os.fdopen(descriptor, "w", encoding="utf-8") as output:
                output.write(secrets.token_urlsafe(48))
            print("Created local signing secret; keep backend/data/auth.secret private.")
            return
        verify_database(engine)
        with Session(engine) as session:
            email = normalize_email(args.email)
            user = session.scalar(select(User).where(User.email == email))
            if args.command == "create-staff":
                if user is not None:
                    parser.error("Email already exists; use set-role for an existing account")
                password = getpass("Password (12–128 characters): ")
                if password != getpass("Confirm password: "):
                    parser.error("Passwords do not match")
                data = UserRegister(email=email, display_name=args.name, password=password)
                now = datetime.now(timezone.utc)
                session.add(User(email=data.email, display_name=data.display_name,
                                 password_hash=hash_password(data.password.get_secret_value()),
                                 role="staff", created_at=now, updated_at=now))
            elif user is None:
                parser.error("Account not found")
            elif args.command == "set-role":
                user.role = args.role
                user.updated_at = datetime.now(timezone.utc)
            else:
                item = session.get(Item, args.item_id)
                if item is None:
                    parser.error("Report not found")
                item.reporter_id = user.id
                item.reported_by = user.display_name
                item.updated_at = datetime.now(timezone.utc)
            session.commit()
            print("Account/report administration completed.")
    except ValidationError as error:
        parser.error("Invalid account details: " + "; ".join(issue["msg"] for issue in error.errors()))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
