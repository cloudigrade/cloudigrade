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


def get_authentication(account_number, authentication_id):
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

    headers = identity.generate_http_identity_headers(account_number, is_org_admin=True)
    params = {"expose_encrypted_attribute[]": "password"}

    return make_sources_call(account_number, url, headers, params)


def get_application(account_number, application_id):
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
    sources_api_base_url = settings.SOURCES_API_BASE_URL
    sources_api_external_uri = settings.SOURCES_API_EXTERNAL_URI

    url = (
        f"{sources_api_base_url}/{sources_api_external_uri}"
        f"applications/{application_id}/"
    )

    headers = identity.generate_http_identity_headers(account_number, is_org_admin=True)
    return make_sources_call(account_number, url, headers)


def list_application_authentications(account_number, authentication_id):
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
    sources_api_base_url = settings.SOURCES_API_BASE_URL
    sources_api_external_uri = settings.SOURCES_API_EXTERNAL_URI

    url = (
        f"{sources_api_base_url}/{sources_api_external_uri}"
        f"application_authentications/?filter[authentication_id]={authentication_id}"
    )

    headers = identity.generate_http_identity_headers(account_number, is_org_admin=True)
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
        dict response payload from the sources api or None if not found.
    """
    response = requests.get(url, headers=headers, params=params)

    if response.status_code == http.HTTPStatus.NOT_FOUND:
        return None
    elif response.status_code != http.HTTPStatus.OK:
        message = _(
            "unexpected status {status} using account {account_number} at {url}"
        ).format(status=response.status_code, account_number=account_number, url=url)
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
            "unexpected non-json response using account {account_number} at {url}"
        ).format(account_number=account_number, url=url)
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
        (account_number, platform_id) (str, str):
            the extracted account number and platform id.
    """
    auth_header = identity.get_x_rh_identity_header(headers)
    if not auth_header:
        logger.error(
            _("Missing expected auth header from message %s, headers %s"),
            message,
            headers,
        )
        # Early exit if auth_header does not exist
        return None, None

    account_number = auth_header.get("identity", {}).get("account_number")
    if not account_number:
        logger.error(
            _("Missing expected account number from message %s, headers %s"),
            message,
            headers,
        )

    platform_id = message.get("id")
    if not platform_id:
        logger.error(
            _("Missing expected id from message %s, headers %s"), message, headers
        )

    return account_number, platform_id


@cache_memoize(settings.CACHE_TTL_SOURCES_APPLICATION_TYPE_ID)
def get_cloudigrade_application_type_id(account_number):
    """Get the cloudigrade application type id from sources."""
    sources_api_base_url = settings.SOURCES_API_BASE_URL
    sources_api_external_uri = settings.SOURCES_API_EXTERNAL_URI
    url = (
        f"{sources_api_base_url}/{sources_api_external_uri}"
        f"application_types?filter[name]=/insights/platform/cloud-meter"
    )

    headers = identity.generate_http_identity_headers(account_number)
    cloudigrade_application_type = make_sources_call(account_number, url, headers)
    if cloudigrade_application_type:
        return cloudigrade_application_type.get("data")[0].get("id")
    return None


def notify_application_availability(
    application_id, availability_status, availability_status_error=""
):
    """
    Update Sources application's availability status.

    The application's availability status is updated by Sources upon
    receiving the availability_status update request Kafka message.

    Args:
        application_id (int): Platform insights application id
        availability_status (string): Availability status to set
        availability_status_error (string): Optional status error
    """
    if not settings.SOURCES_ENABLE_DATA_MANAGEMENT_FROM_KAFKA:
        logger.info(
            "Skipping notify_application_availability because "
            "settings.SOURCES_ENABLE_DATA_MANAGEMENT_FROM_KAFKA is not enabled."
        )
        return

    sources_kafka_config = {
        "bootstrap.servers": f"{settings.LISTENER_SERVER}:{settings.LISTENER_PORT}"
    }

    payload = {
        "resource_type": settings.SOURCES_RESOURCE_TYPE,
        "resource_id": application_id,
        "status": availability_status,
        "error": availability_status_error,
    }

    logger.info(
        _(
            "Requesting the update of the availability status for application "
            "%(application_id)s as %(status)s"
        ),
        {"application_id": application_id, "status": availability_status},
    )

    try:
        if settings.VERBOSE_SOURCES_NOTIFICATION_LOGGING:
            logger.info(
                _("Instantiating KafkaProducer with %(sources_kafka_config)s"),
                {"sources_kafka_config": sources_kafka_config},
            )
        kafka_producer = KafkaProducer(sources_kafka_config)

        message_topic = settings.SOURCES_STATUS_TOPIC
        message_value = json.dumps(payload)
        message_headers = {"event_type": settings.SOURCES_AVAILABILITY_EVENT_TYPE}

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
