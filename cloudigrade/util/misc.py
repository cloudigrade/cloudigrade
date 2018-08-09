"""Miscellaneous utility functions."""
import datetime


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


def truncate_date(original):
    """
    Ensure the date is in the past or present, not the future.

    Args:
        original (datetime): some datetime to optionally truncate

    Returns:
        datetime: original or "now" if base is in the future

    """
    now = datetime.datetime.now(tz=original.tzinfo)
    return min(original, now)
