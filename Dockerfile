FROM centos:7

RUN useradd -r cloudigrade

RUN yum install centos-release-scl -y \
    && yum-config-manager --enable centos-sclo-rh-testing \
    && yum install \
        libcurl-devel \
        nmap-ncat \
        rh-postgresql96 \
        rh-postgresql96-postgresql-devel \
        rh-python36 \
        rh-python36-python-pip \
        libffi-devel gcc -y

WORKDIR /opt/cloudigrade

COPY requirements requirements
RUN PYCURL_SSL_LIBRARY=nss scl enable rh-postgresql96 rh-python36 \
    'pip install -r requirements/prod.txt' \
    && rm -rf requirements

COPY cloudigrade .
USER cloudigrade
ENTRYPOINT ["scl", "enable", "rh-postgresql96", "rh-python36", "--", "gunicorn"]
CMD ["-c","config/gunicorn.py","config.wsgi"]
