"""Functions for interacting with and handling platform identity headers."""

import base64
import json
import logging

from django.utils.translation import gettext as _


logger = logging.getLogger(__name__)


def generate_http_identity_headers(account_number, is_org_admin=False):
    """
    Generate an Insights-specific identity HTTP header.

    For calls to the Authentication API, the account_number must match the
    customer's account number, and is_org_admin should be set to True.

    Args:
        account_number (str): account number identifier for Insights auth
        is_org_admin (bool): boolean for creating an org admin header

    Returns:
        dict with encoded Insights identity header

    """
    raw_header = {"identity": {"account_number": account_number}}
    if is_org_admin:
        raw_header["identity"]["user"] = {"is_org_admin": True}
    identity_encoded = base64.b64encode(json.dumps(raw_header).encode("utf-8")).decode(
        "utf-8"
    )
    headers = {"X-RH-IDENTITY": identity_encoded}
    return headers


def get_x_rh_identity_header(headers):
    """
    Get the x-rh-identity contents from the Kafka topic message headers.

    Args:
        headers (list[tuple]): the headers of a message from a Kafka topic
            generated by the Sources service

    Returns:
        dict contents of the x-rh-identity header.
    """
    auth_header = {}
    # The headers are a list of... tuples.
    for header in headers:
        if header[0] == "x-rh-identity":
            try:
                auth_header = json.loads(base64.b64decode(header[1]).decode("utf-8"))
                break
            except (UnicodeDecodeError, json.JSONDecodeError) as e:
                logger.info(_("x-rh-identity header parsing error %s"), e)
                logger.info(_("Raw headers are: %s"), headers)
                return
    return auth_header
