### Base Image
FROM registry.access.redhat.com/ubi9/ubi-minimal:9.0.0 as base

WORKDIR /opt/cloudigrade

RUN rpm -iv https://download.postgresql.org/pub/repos/yum/reporpms/EL-9-x86_64/pgdg-redhat-repo-latest.noarch.rpm \
    && microdnf update -y \
    && microdnf install -y \
        git \
        jq \
        libicu \
        nmap-ncat \
        postgresql14-libs \
        procps-ng \
        python3 \
        redhat-rpm-config \
        shadow-utils \
        which \
    && if [[ ! -e /usr/bin/python ]]; then ln -sf /usr/bin/python3 /usr/bin/python; fi


### Build virtualenv
FROM base as build

COPY pyproject.toml poetry.lock ./
RUN microdnf install -y \
        gcc \
        postgresql14-devel \
        python3-devel \
        python3-pip \
    && if [ ! -e /usr/bin/pip ]; then ln -s /usr/bin/pip3 /usr/bin/pip ; fi \
    && pip install -U pip \
    && pip install poetry \
    && poetry config virtualenvs.in-project true \
    && PATH="$PATH:/usr/pgsql-14/bin" poetry install -n --no-dev


### Create a release image
FROM base as release

ENV VIRTUAL_ENV=/opt/cloudigrade/.venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Make Ansible happy with arbitrary UID/GID in OpenShift.
RUN chmod g=u /etc/passwd /etc/group

# Grab our built virtualenv
COPY --from=build /opt/cloudigrade/.venv/ .venv/

# Copy in cloudigrade
COPY deployment/playbooks/ ./playbooks
COPY deployment/scripts/cloudigrade_init.sh ./scripts/cloudigrade_init.sh
COPY cloudigrade .

EXPOSE 8000

ENTRYPOINT ["gunicorn"]
CMD ["-c","config/gunicorn.py","config.wsgi"]
