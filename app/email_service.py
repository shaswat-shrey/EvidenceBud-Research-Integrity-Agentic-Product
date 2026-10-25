import os
import resend
from dotenv import load_dotenv
from html import escape
load_dotenv()

resend.api_key = os.getenv("RESEND_API")

EMAIL_FROM = os.getenv(
    "EMAIL_FROM",
    "Blue API <onboarding@resend.dev>",
)

BACKEND_URL = os.getenv(
    "BACKEND_URL",
    "http://localhost:8000",
)

def send_verification_email(email: str, token: str) -> None:
    verification_url = (
        f"{BACKEND_URL}/api/v1/auth/verify-email?token={token}"
    )
    params = {
        "from": EMAIL_FROM,
        "to": [email],
        "subject": "Verify your Blue API email",
        "html": f"""
            <h2>Welcome to Blue API!</h2>
            <p>Click the link below to verify your email address.</p>
            <p>
                <a href="{escape(verification_url, quote=True)}">
                    Verify Email
                </a>
            </p>
            <p>This link expires in 30 minutes.</p>
        """,
    }

    resend.Emails.send(params)