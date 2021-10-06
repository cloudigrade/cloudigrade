"""Functions for managing PSKs."""
import binascii
import os
import re

from django.conf import settings


def normalize_service_name(svc_name):
    """Given a service name, normalize the service name for use in our PSK list."""
    return re.sub("-{2,}", "-", re.sub(r"[\s:,]", "-", svc_name.lower()))


def service_entry(svc_name, svc_psk):
    """
    Given a service name and PSK, return the service entry in the PSKs.

    Service entries in the cloudigrade PSKs are as follows:
            service-name:302df7dd-7e9d9b2c-3d0ac1cd-92414092
    """
    return normalize_service_name(svc_name) + ":" + svc_psk


def psk_service_name(psk):
    """Given a PSK, this function returns the related service name."""
    for service_psk in settings.CLOUDIGRADE_PSKS.split(","):
        svc_name, svc_psk = service_psk.split(":")
        if svc_psk == psk:
            return normalize_service_name(svc_name)

    return None


def generate_psk():
    """
    Create a random 32 hex digit PSK for a micro-service.

    PSKs are dash seperated as in the following example:
            302df7dd-7e9d9b2c-3d0ac1cd-92414092
    """
    return binascii.b2a_hex(os.urandom(16), "-", 4).decode()


def add_service_psk(psks, new_svc_name, new_svc_psk):
    """
    Add a service name and psk to the list of service PSKs.

    Given the list of service PSKs, insert the svc_name:svc_psk
    to that list in service name sorted order.
    """
    service_psks = [service_entry(new_svc_name, new_svc_psk)]
    if psks:
        for service_psk in psks.split(","):
            svc_name, svc_psk = service_psk.split(":")
            service_psks += [service_entry(svc_name, svc_psk)]
    return ",".join(sorted(service_psks))
