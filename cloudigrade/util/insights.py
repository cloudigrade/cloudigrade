"""Functions and classes for interacting with Insights platform services."""
import base64
import http
import json
import logging

import requests
from django.conf import settings
from django.utils.translation import gettext as _

from util.exceptions import SourcesAPINotJsonContent, SourcesAPINotOkStatus

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


def get_sources_authentication(account_number, authentication_id):
    """
    Get an Authentication objects from the Sources API.

    If the `requests.get` itself fails unexpectedly, let the exception bubble
    up to be handled by a higher level in the stack.

    Args:
        account_number (str): account number identifier for Insights auth
        authentication_id (int): the requested authentication's id

    Returns:
        dict response payload from the sources api.

    """
    sources_api_base_url = settings.SOURCES_API_BASE_URL
    sources_api_internal_uri = settings.SOURCE_API_INTERNAL_URI

    url = (
        f"{sources_api_base_url}/{sources_api_internal_uri}"
        f"authentications/{authentication_id}/"
    )

    headers = generate_http_identity_headers(account_number, is_org_admin=True)
    params = {"expose_encrypted_attribute[]": "password"}

    return make_sources_call(account_number, url, headers, params)


def get_sources_endpoint(account_number, endpoint_id):
    """
    Get an Endpoint object from the Sources API.

    If the `requests.get` itself fails unexpectedly, let the exception bubble
    up to be handled by a higher level in the stack.

    Args:
        account_number (str): account number identifier for Insights auth
        endpoint_id (int): the requested endpoint's id

    Returns:
        dict response payload from the sources api.
    """
    sources_api_base_url = settings.SOURCES_API_BASE_URL
    sources_api_external_uri = settings.SOURCES_API_EXTERNAL_URI

    url = f"{sources_api_base_url}/{sources_api_external_uri}endpoints/{endpoint_id}/"

    headers = generate_http_identity_headers(account_number, is_org_admin=True)
    return make_sources_call(account_number, url, headers)


def make_sources_call(account_number, url, headers, params=None):
    """
    Make an API call to the Sources API.

    If the `requests.get` itself fails unexpectedly, let the exception bubble
    up to be handled by a higher level in the stack.

    Args:
        account_number (str): account number identifier for Insights auth
        url (str): the requested url
        headers (dict): a dict of headers for the request.
        params (dict): a dict of params for the request

    Returns:
        dict response payload from the sources api.
    """
    response = requests.get(url, headers=headers, params=params)

    if response.status_code != http.HTTPStatus.OK:
        message = _(
            "unexpected status {status} using account {account_number} at {url}"
        ).format(status=response.status_code, account_number=account_number, url=url)
        raise SourcesAPINotOkStatus(message)

    try:
        response_json = response.json()
    except json.decoder.JSONDecodeError:
        message = _(
            "unexpected non-json response using account {account_number} at {url}"
        ).format(account_number=account_number, url=url)
        raise SourcesAPINotJsonContent(message)

    return response_json
