import boto3
from botocore.exceptions import ClientError

def assume_role(role_arn: str, external_id: str | None = None):
    sts = boto3.client("sts")

    params = {
        "RoleArn": role_arn,
        "RoleSessionName": "monitoring-hub-session"
    }

    if external_id:
        params["ExternalId"] = external_id

    response = sts.assume_role(**params)

    credentials = response["Credentials"]

    return boto3.Session(
        aws_access_key_id=credentials["AccessKeyId"],
        aws_secret_access_key=credentials["SecretAccessKey"],
        aws_session_token=credentials["SessionToken"],
    )