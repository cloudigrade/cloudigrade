"""Gunicorn configuration file."""
timeout = 600
bind = "unix:/var/run/cloudigrade/gunicorn.sock"
workers = 2
