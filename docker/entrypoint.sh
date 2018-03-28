#!/bin/sh

while ! nc -w 1 --send-only < /dev/null db 5432;
do
    sleep 0.1;
    echo "entrypoint.sh: Waiting on postgres."
done;

echo "entrypoint.sh: Postgres is alive, proceeding with migrations."
scl enable rh-postgresql96 rh-python36 './manage.py migrate;'
echo "entrypoint.sh: Migrations are done, starting gunicorn."
scl enable rh-postgresql96 rh-python36 'gunicorn -c config/gunicorn.py --reload config.wsgi'
