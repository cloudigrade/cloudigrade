#!/bin/sh

while ! nc -w 1 -z db 5432;
do
    sleep 0.1;
    echo "entrypoint.sh: Waiting on postgres."
done;

echo "entrypoint.sh: Postgres is alive, proceeding with migrations."
./manage.py migrate;
echo "entrypoint.sh: Migrations are done, starting gunicorn."
gunicorn -c config/gunicorn.py --reload config.wsgi
