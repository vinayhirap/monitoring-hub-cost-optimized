# app/aws/federation.py
"""
Builds account-specific AWS Console deep links via the federation endpoint.

Why this exists
----------------
Just linking to https://<region>.console.aws.amazon.com/... does NOT select
an AWS account — it opens whatever account is already active in the user's
browser session (via existing sign-in cookies). If the operator is signed
into a different account than the one the alert belongs to, the console
opens the WRONG account.

The fix is to mint a short-lived sign-in token for the alert's specific
account/role via STS + the AWS sign-in federation endpoint, then wrap the
target deep-link in a `Destination=` federation login URL. That login URL
forces the correct account context before landing on the resource page,
regardless of any existing browser session.

Docs: https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_providers_enable-console-custom-url.html
"""
import json
import logging
import urllib.parse

import requests

from app.aws.sts import assume_role

logger = logging.getLogger(__name__)

FEDERATION_ENDPOINT = "https://signin.aws.amazon.com/federation"
ISSUER = "monitoring-hub"
SESSION_DURATION_SECONDS = 3600  # must be <= the assumed role's max session duration


def resource_console_destination(resource: str, region: str) -> str:
    """
    Resource-type-specific AWS Console deep link.

    Mirrors the mapping in frontend/src/pages/Alerts.jsx (awsConsoleUrl) —
    keep both in sync if a new resource type is added.
    """
    region = region or "us-east-1"
    if not resource:
        return f"https://{region}.console.aws.amazon.com/console/home?region={region}"

    if resource.startswith("i-"):
        return (f"https://{region}.console.aws.amazon.com/ec2/home"
                f"?region={region}#Instances:instanceId={resource}")
    if resource.startswith("vol-"):
        return (f"https://{region}.console.aws.amazon.com/ec2/home"
                f"?region={region}#Volumes:volumeId={resource}")
    if "lambda" in resource or resource.startswith("arn:aws:lambda"):
        fn = resource.split(":")[-1]
        return (f"https://{region}.console.aws.amazon.com/lambda/home"
                f"?region={region}#/functions/{fn}")
    if resource.startswith("db-") or "rds" in resource:
        return f"https://{region}.console.aws.amazon.com/rds/home?region={region}#database:"

    return f"https://{region}.console.aws.amazon.com/console/home?region={region}"


def build_federated_console_url(role_arn: str, external_id: str | None,
                                 destination: str) -> str:
    """
    Assumes `role_arn` (the alert's own AWS account), exchanges the temporary
    credentials for a sign-in token, and returns a login URL that drops the
    user directly onto `destination` inside the CORRECT account — no
    dependence on whatever account the browser is currently signed into.
    """
    session = assume_role(role_arn, external_id)
    creds = session.get_credentials().get_frozen_credentials()

    session_json = json.dumps({
        "sessionId": creds.access_key,
        "sessionKey": creds.secret_key,
        "sessionToken": creds.token,
    })

    resp = requests.get(
        FEDERATION_ENDPOINT,
        params={
            "Action": "getSigninToken",
            "SessionDuration": SESSION_DURATION_SECONDS,
            "Session": session_json,
        },
        timeout=10,
    )
    resp.raise_for_status()
    signin_token = resp.json()["SigninToken"]

    return (
        f"{FEDERATION_ENDPOINT}?Action=login"
        f"&Issuer={urllib.parse.quote(ISSUER, safe='')}"
        f"&Destination={urllib.parse.quote(destination, safe='')}"
        f"&SigninToken={urllib.parse.quote(signin_token, safe='')}"
    )
