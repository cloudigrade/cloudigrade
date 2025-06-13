### Base Image
FROM registry.access.redhat.com/ubi8-minimal:8.10-1295 as base

WORKDIR /opt/cloudigrade

RUN microdnf update \
    && microdnf install -y \
        git \
        jq \
        libicu \
        nmap-ncat \
        libpq \
        libpq-devel \
        procps-ng \
        python39 \
        redhat-rpm-config \
        shadow-utils \
        which \
    && if [[ ! -e /usr/bin/python ]]; then ln -sf /usr/bin/python3.9 /usr/bin/python; fi


### Build virtualenv
FROM base as build

COPY pyproject.toml poetry.lock ./
RUN microdnf install -y \
        gcc \
        libpq \
        libpq-devel \
        python39-devel \
        python39-pip \
    && if [ ! -e /usr/bin/pip ]; then ln -s /usr/bin/pip3.9 /usr/bin/pip ; fi \
    && pip install -U pip \
    && pip install poetry==1.8.5 \
    && poetry config virtualenvs.in-project true \
    && poetry config installer.max-workers 10 \
    && PATH="$PATH:/usr/pgsql-14/bin" poetry install -n --no-dev


### Create a release image
FROM base as release

ENV VIRTUAL_ENV=/opt/cloudigrade/.venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Grab our built virtualenv
COPY --from=build /opt/cloudigrade/.venv/ .venv/

# Copy in cloudigrade
COPY deployment/playbooks/ ./playbooks
COPY deployment/scripts/cloudigrade_init.sh ./scripts/cloudigrade_init.sh
COPY deployment/scripts/wait_for_migrations.sh ./scripts/wait_for_migrations.sh
COPY cloudigrade .

EXPOSE 8000

ENTRYPOINT ["gunicorn"]
CMD ["-c","config/gunicorn.py","config.wsgi"]
