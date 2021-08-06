"""Gunicorn configuration file."""

from app_common_python import LoadedConfig as clowder_cfg
from app_common_python import isClowderEnabled

timeout = 30

if isClowderEnabled():
    bind = "0.0.0.0:" + str(clowder_cfg.webPort)
else:
    bind = "0.0.0.0:8080"

forwarded_allow_ips = "*"
workers = 2
