FROM fedora:29

WORKDIR /opt/cloudigrade
RUN useradd -r cloudigrade

COPY Pipfile* ./
RUN dnf update -y \
    && dnf install which procps-ng nmap-ncat libcurl-devel gcc openssl-devel python3-devel redhat-rpm-config -y \
    && if [ ! -e /usr/bin/pip ]; then ln -s /usr/bin/pip3.7 /usr/bin/pip ; fi \
    && if [[ ! -e /usr/bin/python ]]; then ln -sf /usr/bin/python3.7 /usr/bin/python; fi \
    && pip install pipenv \
    && PYCURL_SSL_LIBRARY=openssl pipenv install --ignore-pipfile --system  \
    && dnf erase libcurl-devel gcc python3-devel openssl-devel -y \
    && dnf clean all \
    && rm -rf /var/cache/dnf

COPY cloudigrade .
USER cloudigrade

ENTRYPOINT ["gunicorn"]
CMD ["-c","config/gunicorn.py","config.wsgi"]
