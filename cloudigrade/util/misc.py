"""Miscellaneous utility functions."""


def generate_device_name(index, prefix='/dev/xvd'):
    """
    Generate a linux device name based on provided index and prefix.

    Args:
        index (int): Index of the device to generate the name for.
        prefix (str): Prefix for the device name.

    Returns (str): Generated device name.

    """
    return f'{prefix}' \
           f'{chr(ord("b") + int(index / 26)) + chr(ord("a") + index % 26)}'
