"""Functions for parsing, managing, and interacting with sources-api data."""

import http
import json
import logging

import requests
from cache_memoize import cache_memoize
from confluent_kafka import KafkaException, Producer as KafkaProducer
from django.conf import settings
from django.utils.translation import gettext as _

from util.exceptions import (
    KafkaProducerException,
    SourcesAPINotJsonContent,
    SourcesAPINotOkStatus,
)
from util.redhatcloud import identity

logger = logging.getLogger(__name__)


def get_authentication(account_number, org_id, authentication_id):
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
    url = (
        f"{settings.SOURCES_API_INTERNAL_BASE_URL}"
        f"/authentications/{authentication_id}"
    )
    headers = generate_sources_headers(account_number, org_id)
    params = {"expose_encrypted_attribute[]": "password"}
    return make_sources_call(account_number, org_id, url, headers, params)


def get_application(account_number, org_id, application_id):
    """
    Get an Application object from the Sources API.

    If the `requests.get` itself fails unexpectedly, let the exception bubble
    up to be handled by a higher level in the stack.

    Args:
        account_number (str): account number identifier for Insights auth
        application_id (int): the requested application's id

    Returns:
        dict response payload from the sources api.
    """
    url = f"{settings.SOURCES_API_EXTERNAL_BASE_URL}/applications/{application_id}"
    headers = generate_sources_headers(account_number, org_id)
    return make_sources_call(account_number, org_id, url, headers)


def list_application_authentications(account_number, org_id, authentication_id):
    """
    List filtered Application-Authentication objects from the Sources API.

    If the `requests.get` itself fails unexpectedly, let the exception bubble
    up to be handled by a higher level in the stack.

    Args:
        account_number (str): account number identifier for Insights auth
        authentication_id (int): filter by this authentication id.

    Returns:
        dict response payload from the sources api.
    """
    url = (
        f"{settings.SOURCES_API_EXTERNAL_BASE_URL}/application_authentications"
        f"?filter[authentication_id]={authentication_id}"
    )
    headers = generate_sources_headers(account_number, org_id)
    return make_sources_call(account_number, org_id, url, headers)


def get_source(account_number, org_id, source_id):
    """
    Get a Source object from the Sources API.

    If the `requests.get` itself fails unexpectedly, let the exception bubble
    up to be handled by a higher level in the stack.

    Args:
        account_number (str): account number identifier for Insights auth
        org_id (str): org_id identifier for Insights auth
        source_id (int): the requested source's id

    Returns:
        dict response payload from the sources api.
    """
    url = f"{settings.SOURCES_API_EXTERNAL_BASE_URL}/sources/{source_id}"
    headers = generate_sources_headers(account_number, org_id)
    return make_sources_call(account_number, org_id, url, headers)


def make_sources_call(account_number, org_id, url, headers, params=None):
    """
    Make an API call to the Sources API.

    If the `requests.get` itself fails unexpectedly, let the exception bubble
    up to be handled by a higher level in the stack.

    Args:
        account_number (str): account number identifier for Insights auth
        org_id (str): Org Id identifier for Insights auth
        url (str): the requested url
        headers (dict): a dict of headers for the request.
        params (dict): a dict of params for the request

    Returns:
        dict response payload from the sources api or None if not found.
    """
    response = requests.get(url, headers=headers, params=params)

    if response.status_code == http.HTTPStatus.NOT_FOUND:
        return None
    elif response.status_code != http.HTTPStatus.OK:
        message = _(
            "unexpected status {status} using"
            " account_number '{account_number}'"
            " and org_id '{org_id}'"
            " at {url}"
        ).format(
            status=response.status_code,
            account_number=account_number,
            org_id=org_id,
            url=url,
        )
        logger.info(message)
        logger.info(
            _("sources-api response content: %(response_text)s"),
            {"response_text": response.text},
        )
        raise SourcesAPINotOkStatus(message)

    try:
        response_json = response.json()
    except json.decoder.JSONDecodeError:
        message = _(
            "unexpected non-json response using"
            " account_number '{account_number}'"
            " and org_id '{org_id}'"
            " at {url}"
        ).format(account_number=account_number, org_id=org_id, url=url)
        logger.info(message)
        logger.info(
            _("sources-api response content: %(response_text)s"),
            {"response_text": response.text},
        )
        raise SourcesAPINotJsonContent(message)

    return response_json


def extract_ids_from_kafka_message(message, headers):
    """
    Get the account_number and platform_id from the Kafka topic message and headers.

    Args:
        message (dict): the "value" attribute of a message from a Kafka
            topic generated by the Sources service
        headers (list[tuple]): the headers of a message from a Kafka topic
            generated by the Sources service

    Returns:
        (account_number, org_id, platform_id) (str, str, str):
            the extracted account number, org_id and platform id.
    """
    account_number = get_sources_account_number_from_headers(headers)
    org_id = get_sources_org_id_from_headers(headers)
    if not account_number:
        if not org_id:
            auth_header = identity.get_x_rh_identity_header(headers)
            if not auth_header:
                logger.error(
                    _(
                        "Missing expected auth header from message "
                        "%(message)s, headers %(headers)s"
                    ),
                    {"message": message, "headers": headers},
                )
                # Early exit if auth_header does not exist
                return None, None, None

            account_number = auth_header.get("identity", {}).get("account_number")
            org_id = auth_header.get("identity", {}).get("org_id")
            if not account_number and not org_id:
                logger.error(
                    _(
                        "Missing expected account number or org_id from message "
                        "%(message)s, headers %(headers)s"
                    ),
                    {"message": message, "headers": headers},
                )

    platform_id = message.get("id")
    if not platform_id:
        logger.error(
            _("Missing expected id from message %s, headers %s"), message, headers
        )

    return account_number, org_id, platform_id


def get_sources_org_id_from_headers(headers):
    """Get the x-rh-sources-org-id from the headers."""
    for header in headers:
        if header[0] == "x-rh-sources-org-id":
            return header[1]
    return None


def get_sources_account_number_from_headers(headers):
    """Get the x-rh-sources-account-number from the headers."""
    for header in headers:
        if header[0] == "x-rh-sources-account-number":
            return header[1]
    return None


@cache_memoize(settings.CACHE_TTL_SOURCES_APPLICATION_TYPE_ID, cache_alias="locmem")
def get_cloudigrade_application_type_id(account_number, org_id):
    """Get the cloudigrade application type id from sources."""
    url = (
        f"{settings.SOURCES_API_EXTERNAL_BASE_URL}/application_types"
        f"?filter[name]=/insights/platform/cloud-meter"
    )

    headers = generate_sources_headers(account_number, org_id)
    cloudigrade_application_type = make_sources_call(
        account_number, org_id, url, headers
    )
    if cloudigrade_application_type:
        return cloudigrade_application_type.get("data")[0].get("id")
    return None


def notify_application_availability(
    account_number,
    org_id,
    application_id,
    availability_status,
    availability_status_error="",
):
    """
    Update Sources application's availability status.

    The application's availability status is updated by Sources upon
    receiving the availability_status update request Kafka message.

    Args:
        account_number (str): Account number identifier
        org_id (str): Org Id identifier
        application_id (int): Platform insights application id
        availability_status (string): Availability status to set
        availability_status_error (string): Optional status error
    """
    logger.info(
        _(
            "Notifying sources application availability for "
            "account_number '%(account_number)s' "
            "org_id '%(org_id)s' "
            "application_id '%(application_id)s' "
            "availability_status '%(availability_status)s' "
            "availability_status_error '%(availability_status_error)s' "
        ),
        {
            "account_number": account_number,
            "org_id": org_id,
            "application_id": application_id,
            "availability_status": availability_status,
            "availability_status_error": availability_status_error,
        },
    )
    if (
        not settings.SOURCES_ENABLE_DATA_MANAGEMENT
        or not settings.SOURCES_ENABLE_DATA_MANAGEMENT_FROM_KAFKA
    ):
        logger.info(
            "Skipping notify_application_availability because "
            "settings.SOURCES_ENABLE_DATA_MANAGEMENT or "
            "settings.SOURCES_ENABLE_DATA_MANAGEMENT_FROM_KAFKA is not enabled."
        )
        return

    if hasattr(settings, "KAFKA_BROKERS"):
        bootstrap_servers = ",".join(
            [f"{b.hostname}:{b.port}" for b in settings.KAFKA_BROKERS]
        )
    else:
        bootstrap_server_host = settings.KAFKA_SERVER_HOST
        bootstrap_server_port = settings.KAFKA_SERVER_PORT
        bootstrap_servers = f"{bootstrap_server_host}:{bootstrap_server_port}"

    sources_kafka_config = {
        "bootstrap.servers": bootstrap_servers
    }

    payload = {
        "resource_type": settings.SOURCES_RESOURCE_TYPE,
        "resource_id": application_id,
        "status": availability_status,
        "error": availability_status_error,
    }

    try:
        if settings.VERBOSE_SOURCES_NOTIFICATION_LOGGING:
            logger.info(
                _("Instantiating KafkaProducer with %(sources_kafka_config)s"),
                {"sources_kafka_config": sources_kafka_config},
            )
        kafka_producer = KafkaProducer(update_kafka_sasl_config(sources_kafka_config))

        message_headers = generate_sources_headers(
            account_number, org_id, include_psk=False
        )
        message_topic = settings.SOURCES_STATUS_TOPIC
        message_value = json.dumps(payload)
        message_headers["event_type"] = settings.SOURCES_AVAILABILITY_EVENT_TYPE

        if settings.VERBOSE_SOURCES_NOTIFICATION_LOGGING:
            logger.info(
                _(
                    "KafkaProducer will produce with "
                    "topic='%(topic)s' value='%(value)s' headers='%(headers)s'"
                ),
                {
                    "topic": message_topic,
                    "value": message_value,
                    "headers": message_headers,
                },
            )
        kafka_producer.produce(
            topic=message_topic,
            value=message_value,
            headers=message_headers,
            callback=_check_response,
        )
        if settings.VERBOSE_SOURCES_NOTIFICATION_LOGGING:
            logger.info(_("KafkaProducer produced!"))

        kafka_producer.flush()
        if settings.VERBOSE_SOURCES_NOTIFICATION_LOGGING:
            logger.info(_("KafkaProducer flushed!"))

    except BufferError as error:
        message = f"BufferError: {str(error)}"
        logger.exception(error)
        raise KafkaProducerException(message)
    except KafkaException as exception:
        message = f"KafkaException: {exception.args[0].str()}"
        logger.exception(exception)
        raise KafkaProducerException(message)

    logger.info(
        _(
            "Successfully notified sources application availability for "
            "account_number '%(account_number)s' "
            "org_id '%(org_id)s' "
            "application_id '%(application_id)s' "
        ),
        {
            "account_number": account_number,
            "org_id": org_id,
            "application_id": application_id,
        },
    )


def _check_response(error, message):
    """Verify that the message was delivered without an error."""
    if error is not None:
        logger.error(
            _("Failed to deliver message: %(message)s due to: %(error)s"),
            {"message": message, "error": error},
        )
    else:
        log_msg = _("Successfully delivered message: %(message)s"), {"message": message}

        if settings.VERBOSE_SOURCES_NOTIFICATION_LOGGING:
            logger.info(*log_msg)
        else:
            logger.debug(*log_msg)


def generate_sources_headers(account_number, org_id, include_psk=True):
    """
    Return the headers needed for accessing Sources.

    The Sources API requires the x-rh-sources-account-number
    and/or the x-rh-sources-org-id header as well as the
    x-rh-sources-psk for service to service communication instead
    of the earlier x-rh-identity.

    By default we include the PSK, but for Kafka messages,
    the PSK is not required, so we can optionally exclude it.

    Args:
        account_number (str): Account number identifier
        org_id (str): Org Id identifier
        include_psk (boolean): Whether or not to include the PSK
    """
    headers = {}
    if account_number:
        headers["x-rh-sources-account-number"] = account_number
    if org_id:
        headers["x-rh-sources-org-id"] = org_id

    if include_psk:
        if settings.SOURCES_PSK == "":
            raise SourcesAPINotOkStatus(
                "Failed to generate headers for Sources, SOURCES_PSK is not defined"
            )
        else:
            headers["x-rh-sources-psk"] = settings.SOURCES_PSK

    return headers


def update_kafka_sasl_config(kafka_config):
    """Update a kafka consumer or producer configure with the sasl information."""
    if settings.KAFKA_SERVER_CA_LOCATION:
        kafka_config["ssl.ca.location"] = settings.KAFKA_SERVER_CA_LOCATION

    if settings.KAFKA_SERVER_SASL_USERNAME:
        kafka_config.update(
            {
                "security.protocol": settings.KAFKA_SERVER_SECURITY_PROTOCOL,
                "sasl.mechanism": settings.KAFKA_SERVER_SASL_MECHANISM,
                "sasl.username": settings.KAFKA_SERVER_SASL_USERNAME,
                "sasl.password": settings.KAFKA_SERVER_SASL_PASSWORD,
            }
        )

    return kafka_config
