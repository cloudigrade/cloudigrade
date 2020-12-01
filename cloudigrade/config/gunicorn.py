"""Gunicorn configuration file."""
timeout = 120
bind = "unix:/var/run/cloudigrade/gunicorn.sock"

# https://docs.gunicorn.org/en/stable/design.html#how-many-workers
# "Generally we recommend (2 x $num_cores) + 1 as the number of workers"
try:
    import os

    cpu_count = os.cpu_count()
except:  # noqa: E722
    cpu_count = 1
workers = (cpu_count * 2) + 1
