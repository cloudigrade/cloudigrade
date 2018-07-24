FROM centos:7

WORKDIR /opt/cloudigrade
RUN useradd -r cloudigrade

RUN yum install centos-release-scl -y \
    && yum-config-manager --enable centos-sclo-rh-testing \
    && yum install rh-python36 rh-python36-python-pip -y \
    && yum clean all \
    && rm -rf /var/cache/yum

COPY requirements requirements
RUN yum install libcurl-devel gcc -y \
    && PYCURL_SSL_LIBRARY=nss scl enable rh-python36 \
        'pip install -r requirements/prod.txt' \
    && yum erase libcurl-devel gcc -y \
    && yum autoremove -y \
    && yum clean all \
    && rm -rf /var/cache/yum

COPY cloudigrade .
USER cloudigrade

ENTRYPOINT ["scl", "enable", "rh-python36", "--", "gunicorn"]
CMD ["-c","config/gunicorn.py","config.wsgi"]
