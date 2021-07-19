FROM registry.access.redhat.com/ubi8/ubi-minimal:8.3

# Make Ansible happy with arbitrary UID/GID in OpenShift.
RUN chmod g=u /etc/passwd /etc/group

WORKDIR /opt/cloudigrade
RUN microdnf install shadow-utils \
	&& useradd -r cloudigrade \
	&& microdnf clean all

RUN microdnf install libicu \
    && curl -O https://download.postgresql.org/pub/repos/yum/11/redhat/rhel-8.3-x86_64/postgresql11-libs-11.9-4PGDG.rhel8.x86_64.rpm \
    && curl -O https://download.postgresql.org/pub/repos/yum/11/redhat/rhel-8.3-x86_64/postgresql11-11.9-4PGDG.rhel8.x86_64.rpm \
    && rpm -iv postgresql11-libs-11.9-4PGDG.rhel8.x86_64.rpm \
    && rpm --nodeps -iv postgresql11-11.9-4PGDG.rhel8.x86_64.rpm \
    && rm -f postgresql11-libs-11.9-4PGDG.rhel8.x86_64.rpm postgresql11-11.9-4PGDG.rhel8.x86_64.rpm \
    && microdnf clean all

COPY pyproject.toml poetry.lock ./
RUN microdnf update \
    && microdnf install git which procps-ng nmap-ncat libcurl-devel gcc openssl-devel python38-devel python38-pip redhat-rpm-config -y \
    && if [ ! -e /usr/bin/pip ]; then ln -s /usr/bin/pip3.8 /usr/bin/pip ; fi \
    && if [[ ! -e /usr/bin/python ]]; then ln -sf /usr/bin/python3.8 /usr/bin/python; fi \
    && pip install -U pip \
    && pip install poetry \
    && poetry config virtualenvs.create false \
    && PYCURL_SSL_LIBRARY=openssl poetry install -n --no-dev \
    && microdnf remove libcurl-devel gcc python3-devel openssl-devel annobin -y \
    && microdnf clean all

# Need jq for parsing the clowder configuration json in shell scripts
RUN microdnf install jq -y \
    && microdnf clean all

COPY deployment/playbooks/ ./playbooks
COPY deployment/scripts/mid_hook.sh ./scripts/mid_hook.sh
COPY deployment/scripts/cloudigrade_init.sh ./scripts/cloudigrade_init.sh
COPY cloudigrade .
USER cloudigrade

# Default is 8080, For clowder it is 8000
EXPOSE 8080 8000

ENTRYPOINT ["gunicorn"]
CMD ["-c","config/gunicorn.py","config.wsgi"]
