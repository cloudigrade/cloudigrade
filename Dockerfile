FROM python:3.6-alpine

RUN addgroup -S cloudigrade
RUN adduser -S cloudigrade -G cloudigrade

WORKDIR /opt/cloudigrade

COPY requirements requirements
RUN apk --no-cache --update add postgresql-libs
RUN apk --no-cache --update add --virtual build-deps python3-dev gcc postgresql-dev musl-dev libffi-dev \
  && pip install -r requirements/prod.txt \
  && apk del build-deps \
  && rm -rf requirements

USER cloudigrade
COPY cloudigrade .

ENTRYPOINT ["python","manage.py"]
CMD ["runserver","0.0.0.0:8000"]
