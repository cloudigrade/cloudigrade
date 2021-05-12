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

RUN curl -L -o /usr/bin/haberdasher \
    https://github.com/RedHatInsights/haberdasher/releases/download/v0.1.5/haberdasher_linux_amd64 && \
    chmod 755 /usr/bin/haberdasher

COPY deployment/playbooks/ ./playbooks
COPY deployment/scripts/mid_hook.sh ./scripts/mid_hook.sh
COPY cloudigrade .
USER cloudigrade

EXPOSE 8080

ENTRYPOINT ["/usr/bin/haberdasher"]
CMD ["gunicorn","-c","config/gunicorn.py","config.wsgi"]
