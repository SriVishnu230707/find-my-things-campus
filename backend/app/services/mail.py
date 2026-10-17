"""Local .eml delivery for development, or authenticated TLS SMTP."""

import os
import secrets
import smtplib
import ssl
from email.message import EmailMessage

from app.account_config import mail_directory, mail_mode, public_base_url


def deliver_account_email(email, purpose, token):
    message = EmailMessage()
    message["From"] = os.environ.get("SMTP_FROM", "campus@localhost")
    message["To"] = email
    message["Subject"] = (
        "Verify your campus account"
        if purpose == "verify"
        else "Reset your campus password"
    )
    lifetime = "30 minutes" if purpose == "verify" else "15 minutes"
    link = f"{public_base_url()}/campus/#{purpose}={token}"
    message.set_content(
        f"Use this single-use link within {lifetime}:\n\n{link}\n\nIf you did not request this message, ignore it. This link is private."
    )
    if mail_mode() == "local":
        directory = mail_directory()
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / (secrets.token_hex(16) + ".eml")
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as output:
            output.write(message.as_bytes())
        return path
    security = os.environ.get("SMTP_SECURITY", "starttls")
    connection = smtplib.SMTP_SSL if security == "ssl" else smtplib.SMTP
    kwargs = {
        "host": os.environ["SMTP_HOST"],
        "port": int(os.environ.get("SMTP_PORT", "465" if security == "ssl" else "587")),
        "timeout": 10,
    }
    if security == "ssl":
        kwargs["context"] = ssl.create_default_context()
    with connection(**kwargs) as smtp:
        if security == "starttls":
            smtp.ehlo()
            smtp.starttls(context=ssl.create_default_context())
            smtp.ehlo()
        if os.environ.get("SMTP_USERNAME"):
            smtp.login(os.environ["SMTP_USERNAME"], os.environ["SMTP_PASSWORD"])
        smtp.send_message(message)
    return None
