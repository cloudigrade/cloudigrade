"""Gunicorn configuration file."""
bind = 'unix:/var/run/cloudigrade/gunicorn.sock'
workers = 2
