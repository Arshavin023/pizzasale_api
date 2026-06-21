import os
import boto3
from botocore.exceptions import ClientError

AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
SES_SENDER_EMAIL = os.getenv("SES_SENDER_EMAIL")

if not SES_SENDER_EMAIL:
    raise RuntimeError("SES_SENDER_EMAIL is not set")

_ses_client = boto3.client("ses", region_name=AWS_REGION)


def send_verification_email(to_email: str, verification_link: str) -> None:
    """
    Sends a verification email via AWS SES.

    Raises ClientError if SES rejects the send (e.g. recipient not
    verified while in sandbox mode, sender not verified, rate limit).
    Caller decides how to handle that — see auth_routes.py.
    """
    subject = "Verify your Pizzasale account"
    body_text = (
        f"Welcome to Pizzasale!\n\n"
        f"Please verify your email by visiting the link below:\n"
        f"{verification_link}\n\n"
        f"If you didn't create this account, you can ignore this email."
    )
    body_html = f"""
    <html>
      <body>
        <h2>Welcome to Pizzasale!</h2>
        <p>Please verify your email by clicking the link below:</p>
        <p><a href="{verification_link}">Verify my email</a></p>
        <p>If you didn't create this account, you can ignore this email.</p>
      </body>
    </html>
    """

    try:
        _ses_client.send_email(
            Source=SES_SENDER_EMAIL,
            Destination={"ToAddresses": [to_email]},
            Message={
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {
                    "Text": {"Data": body_text, "Charset": "UTF-8"},
                    "Html": {"Data": body_html, "Charset": "UTF-8"},
                },
            },
        )
    except ClientError as e:
        # Common cause in SES sandbox mode: recipient email isn't
        # verified yet. Re-raise with the original SES error message
        # intact so the caller/logs show the real reason.
        raise RuntimeError(f"Failed to send verification email: {e.response['Error']['Message']}") from e
