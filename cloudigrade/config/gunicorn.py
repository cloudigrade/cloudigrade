"""Gunicorn configuration file."""
timeout = 30
bind = "0.0.0.0:8080"
forwarded_allow_ips = "*"
workers = 2
