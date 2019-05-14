FROM fedora:29

WORKDIR /opt/cloudigrade
RUN useradd -r cloudigrade

COPY requirements requirements
RUN dnf update -y \
    && dnf install procps-ng nmap-ncat libcurl-devel gcc openssl-devel python3-devel redhat-rpm-config -y \
    && /usr/bin/pip3.7 install --upgrade "urllib3<1.25" \
    && PYCURL_SSL_LIBRARY=openssl /usr/bin/pip3.7 install -r requirements/prod.txt \
    && dnf erase libcurl-devel gcc python3-devel openssl-devel -y \
    && dnf clean all \
    && rm -rf /var/cache/dnf

COPY cloudigrade .
USER cloudigrade

ENTRYPOINT ["gunicorn"]
CMD ["-c","config/gunicorn.py","config.wsgi"]
