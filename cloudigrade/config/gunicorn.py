"""Gunicorn configuration file."""
timeout = 120
bind = "unix:/var/run/cloudigrade/gunicorn.sock"
workers = 2
