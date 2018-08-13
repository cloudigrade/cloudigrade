# How to register an account @ \*.cloudigra.de
## Superuser account
Make a superuser account if you don't already have one
```
$ oc rsh -c cloudigrade-api $(oc get pods -o jsonpath='{.items[*].metadata.name}' -l name=cloudigrade-api | awk '{print $1}') scl enable rh-python36 -- python manage.py createsuperuser
Username: ilya.white@redhat.com
Email address: ilya.white@redhat.com
Password:
Password (again):
Superuser created successfully.
```
## Register the user
Forward port on 8080
```
$ oc port-forward $(oc get pods -o jsonpath='{.items[*].metadata.name}' -l name=cloudigrade-api) 8080
```
Login @ `127.0.0.1:8080/admin/` with your superuser account
You'll see a lot of css missing, that's ok!

Navigate to: `http://localhost:8080/admin/auth/user/add/`

Come up with a username & password and hit add!

Dunzo!
