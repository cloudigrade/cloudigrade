*********************************************************
AWS RDS setup for Local Development, Test, and Production
*********************************************************

Optional local development setup for RDS
========================================
#. log in to the AWS web console for the account running the ECS houndigrade cluster
#. under services navigate to the rds (Relational Database Service) page
#. select "Instances" in the side bar and click on "Create database" on the right-hand side
#. select "PostgreSQL" as the engine and click "Next"
#. select "Dev/Test" as the use case and click "Next"
#. enter the following instance specifications and click "Next":
    - leave the default License model
    - set the DB engine version to PostgreSQL 9.6.9-R1
    - in the box labeled "Free tier", select the checkbox for "Only enable options eligible for RDS Free Usage Tier"
    - check that the instance class is set to "db.t2.micro -- 1 vCPU, 1 GiB RAM"
    - check that "no" is selected for Multi-AZ deployment
    - check that "General Purpose (SSD)" is selected for Storage type
    - leave the default of 20 GiB for Allocated storage
    - set the DB instance identifier, master username, and master password. record the username and password because we will need to export them as environment variables
#. enter the following for Network & Security:
    - leave the default VPC
    - set the Subnet group to default
    - select "Yes" for Public accessibility
    - leave the default of "No preference" for the Availability Zone
    - Under VPC security groups select Create new VPC security group
#. enter the following for Database options:
    - set the Database name and record it because we will export it as an environment variable
    - set the Database port to `5432` and record it because we will export it as an environment variable
    - leave the default DB parameter group
#. enter the following for Backup:
    - set the Backup retention period to "7 days"
    - leave the Backup window set to "no preference"
#. leave the defaults for both Monitoring and Maintenance and click "Create database"
#. once your DB instance is created, click on "View DB instance details"
#. scroll down to the Details section
#. copy the endpoint
#. export the following as environment variables:
    - export DJANGO_DATABASE_USER=$YOUR-USERNAME
    - export DJANGO_DATABASE_PASSWORD=$YOUR-PASSWORD
    - export DJANGO_DATABASE_NAME=$YOUR-DB-NAME
    - export DJANGO_DATABASE_PORT=$YOUR-DB-PORT
    - export DJANGO_DATABASE_HOST=$YOUR-DB-ENDPOINT
#. to use your PostgreSql instance in rds with local development bring up the cluster as normal but do not deploy the database
#. start your server as normal

Configuring shiftigrade & cloudigrade test env with RDS
=======================================================
.. note:: The PostgreSql instance for the test environment has been set up in AWS.

#. export the following as environment variables:
    - export DJANGO_DATABASE_USER=$YOUR-USERNAME
    - export DJANGO_DATABASE_PASSWORD=$YOUR-PASSWORD
    - export DJANGO_DATABASE_NAME=postgresql
    - export DJANGO_DATABASE_PORT=5432
    - export DJANGO_DATABASE_HOST=postgresql.c7o17pvjckm4.us-east-1.rds.amazonaws.com

Test & Production RDS setup in AWS
==================================
#. log in to the AWS web console for the account running the ECS houndigrade cluster
#. under services navigate to the rds (Relational Database Service) page
#. select "Instances" in the side bar and click on "Create database" on the right-hand side
#. select "PostgreSQL" as the engine and click "Next"
#. select "Production" as the use case and click "Next"
#. enter the following instance specifications and click "Next":
    - leave the default License model
    - set the DB engine version to PostgreSQL 9.6.9-R1
    - set the DB instance class to "db.t2.micro -- 1 vCPU, 1 GiB RAM"
    - select "no" for Multi-AZ deployment
    - select "General Purpose (SSD)" is selected for Storage type
    - leave the default of 20 GiB for Allocated storage
    - set the DB instance identifier, master username, and master password. Record the username and password because we will need to export them as environment variables

.. note:: These values will likely be changed when setting up the production database.

#. enter the following for Network & Security:
    - leave the default VPC
    - set the Subnet group to default
    - select "Yes" for Public accessibility
    - leave the default of "No preference" for the Availability Zone
    - Under VPC security groups select Create new VPC security group
#. enter the following for Database options:
    - set the Database name and record it because we will export it as an environment variable
    - set the Database port to `5432` and record it because we will export it as an environment variable
    - leave the default DB parameter group
#. enter the following for Backup:
    - set the Backup retention period to 7 days.
    - leave the Backup window set to "no preference"
#. leave the defaults for both Monitoring and Maintenance and click "Create database"
#. once your DB instance is created, click on "View DB instance details"
#. scroll down to the Details section
#. copy the endpoint
#. export the following as environment variables:
    - export DJANGO_DATABASE_USER=$YOUR-USERNAME
    - export DJANGO_DATABASE_PASSWORD=$YOUR-PASSWORD
    - export DJANGO_DATABASE_NAME=$YOUR-DB-NAME
    - export DJANGO_DATABASE_PORT=$YOUR-DB-PORT
    - export DJANGO_DATABASE_HOST=$YOUR-DB-ENDPOINT

Teardown for RDS
================
#. log in to the AWS web console for the account running the ECS houndigrade cluster
#. under services navigate to the rds (Relational Database Service) page
#. select "Instances" in the side bar and click on "Create database" on the right-hand side
#. select the DB Instance that you would like to delete
#. in the Instances top, right-hand side navigation bar, select "Instance actions" and "Delete" in the drop down menu