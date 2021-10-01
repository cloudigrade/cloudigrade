"""Functions for managing PSKs."""
import environ


def psk_service_name(psk):
    """Given a PSK, this function returns the related service name."""
    env = environ.Env()
    cloudigrade_psks = env("CLOUDIGRADE_PSKS", default="")

    for service_psk in cloudigrade_psks.split(","):
        svc_name, svc_psk = service_psk.split(":")
        if svc_psk == psk:
            return svc_name

    return None
