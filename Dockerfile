FROM python:3.6-alpine

RUN addgroup -S cloudigrade && \
    adduser -S cloudigrade -G cloudigrade

WORKDIR /opt/cloudigrade

COPY requirements requirements
RUN apk --no-cache --update add postgresql-libs \
  && apk --no-cache --update add --virtual build-deps python3-dev gcc postgresql-dev musl-dev libffi-dev \
  && pip install -r requirements/prod.txt \
  && apk del build-deps \
  && rm -rf requirements

COPY cloudigrade .
RUN PYTHONPATH=. && python manage.py collectstatic --no-input --settings=config.settings.docker

USER cloudigrade
ENTRYPOINT ["gunicorn"]
CMD ["-c","config/gunicorn.py","config.wsgi"]
