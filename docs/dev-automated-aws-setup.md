# Cloudigrade AWS setup with Ansible

This is an alternative, automated workflow to the manual workflows described in [dev-houndigrade-cluster-setup.md](https://github.com/cloudigrade/cloudigrade/blob/master/docs/dev-houndigrade-cluster-setup.md) and [dev-cloudtrail-initial-setup.rst](https://github.com/cloudigrade/cloudigrade/blob/master/docs/dev-cloudtrail-initial-setup.rst). They are mutually exclusive.

## Assumptions + Dependencies

* Python executable in path must have boto3 importable
* Must have AWS key and id in env for acct acting as cloudigrade
  * `AWS_ACCESS_KEY_ID`
  * `AWS_SECRET_ACCESS_KEY`
* Must have ssh key created on aws account and know the name
* Must have recorded what vpc, subnet, and security group you want to use are (details below)
* Must have ansible, ansible-galaxy, and ansible-playbook in your path. Preferebly version 2.5.1+
* Must have aws cli in path
* Host running the playbook must have `/etc/ansible/` directory and permission to write to it. This probably won't be an issue if you are using your system's `ansible`, probably will be an issue if using a virutal env install of `ansible`.

## Install roles and create playbook

```
ansible-galaxy install kdelee.aws_ecs_autoscale_role
ansible-galaxy install kdelee.aws_cloudtrail_bucket
cat > cloudigrade-aws-resources.yaml << 'EOL'
- hosts: localhost
  connection: local
  roles:
    - kdelee.aws_ecs_autoscale_role
    - kdelee.aws_cloudtrail_bucket
EOL
```

### Keeping roles up to date
If at a later time you want to ensure your ansible roles are up to date, you can force the update with the `--force` flag to `ansible-galaxy install`.

```
ansible-galaxy install --force kdelee.aws_ecs_autoscale_role
ansible-galaxy install --force kdelee.aws_cloudtrail_bucket
```

## Set up variables

### Specific Names To Identify Your Resources
_You should change these to uniquely identify your environment._
_Locally, you might want to just use your user name._
_In a CI context, a git branch may be appropriate._

```
export AWS_NAME_PREFIX="${USER}-awesome-feature-"
export HOUNDIGRADE_ECS_CLUSTER_NAME="${AWS_NAME_PREFIX}-houndigrade"
export HOUNDIGRADE_AWS_AUTOSCALING_GROUP_NAME="${HOUNDIGRADE_ECS_CLUSTER_NAME}-asg"
export HOUNDIGRADE_LAUNCH_CONFIG_NAME="${HOUNDIGRADE_ECS_CLUSTER_NAME}-lc"
export EC2_HOST_NAME="${HOUNDIGRADE_ECS_CLUSTER_NAME}-host"
```
### Sane defaults
```
export RECOMMENDED_AMI="ami-5253c32d" # recommended by AWS for ECS
export INSTANCE_TYPE="t2.micro" # recommended by cloudigrade devs
```

### Variables that are dependent on your account
The following items should be collected from the AWS account in question. You can find all these values by looking at the EC2 cluster wizard: https://console.aws.amazon.com/ecs/home?region=us-east-1#/clusters/create/new 
Select `"EC2 Linux + networking" > next`, scroll down to `Networking`, you can select the first vpc that is in drop down, then the first subnet in drop down,  then select a the security group labeled "default". Observe the region that is displayed along side the subnet (in my case, `us-east-1c`. This will be your `HOUNDIGRADE_AWS_AVAILABILITY_ZONE`.)

Additionally you need to have a named ssh key available on AWS. You can create one by going to `EC2 > NETWORK & SECURITY > KEY PAIRS`. Either pick one there that works for you, or create a new one and record the name.

_These values are valid for dev09_
```
# grab this from list of pre-configured vpc's on aws
export VPC_NAME="vpc-0049bdb38cae50d7c"

# grab this from list of pre-configured vpc's on aws
export SUBNET_NAME="subnet-023bec14370c7bab1"

# should be ONE zone that matches where subnet is
export HOUNDIGRADE_AWS_AVAILABILITY_ZONE="us-east-1c"

# grab this from list of pre-configured security groups
export SECURITY_GROUP_NAME="sg-0954d400d462ac63c"

# this needs to match the name of an ssh key that exists on the account
export SSH_KEY_NAME="cloudigrade-key"
```

## Run playbook
_To be done in the same directory where you created the playbook._
```
ansible-playbook -e ecs_cluster_name=$HOUNDIGRADE_ECS_CLUSTER_NAME -e ec2_asg_name=$HOUNDIGRADE_AWS_AUTOSCALING_GROUP_NAME -e ec2_launch_configuration_name=$HOUNDIGRADE_LAUNCH_CONFIG_NAME -e ec2_instance_type=$INSTANCE_TYPE -e ec2_ami_id=$RECOMMENDED_AMI -e ec2_instance_name=$EC2_HOST_NAME -e ec2_asg_min_size=0 -e ec2_asg_max_size=0 -e ec2_asg_desired_capacity=0 -e ec2_asg_availability_zones=$HOUNDIGRADE_AWS_AVAILABILITY_ZONE -e vpc_name=$VPC_NAME -e ec2_asg_vpc_subnets=$SUBNET_NAME -e ec2_security_groups=$SECURITY_GROUP_NAME -e key_name=$SSH_KEY_NAME -e application_name=houndigrade -e aws_prefix=$AWS_NAME_PREFIX cloudigrade-aws-resources.yaml
```

## Observe Results
_The first time you do this, you should verify everything looks as it should._

```
# show autoscaling group
# note there is only one availability zone and 0 for min max and default instances
aws autoscaling describe-auto-scaling-groups --auto-scaling-group-names $HOUNDIGRADE_AWS_AUTOSCALING_GROUP_NAME

# show cluster
aws ecs list-clusters | grep $HOUNDIGRADE_ECS_CLUSTER_NAME

# show s3 bucket
aws s3 ls | grep $AWS_NAME_PREFIX
# go to web UI to show policy and notifications ... would be good to find CLI way to confirm

# show queue 
aws sqs list-queues | grep "${AWS_NAME_PREFIX}-cloudigrade-cloudtrail-sqs"
# go to web UI to show policy ... would be good to find CLI way to confirm
```



## Push templates to the OpenShift cluster you are using
### (This happens your copy of the shiftigrade repo.)
_To use these resources, you must create the OpenShift deployment configs and config maps with these environment variables still set._

**must have `oc` logged into the OpenShift cluster you desire to use**

```
make oc-create-cloudigrade-all
oc start-build cloudigrade-api
```

## Clean up
_We can also tear down everything we made with the same roles._
_This does not remove the ecsInstanceRole because that is a default role that Amazon provides and would interfere with other clusters that may also be using it._
```
# Remove resources created
ansible-playbook -e ecs_cluster_name=$HOUNDIGRADE_ECS_CLUSTER_NAME -e ec2_asg_name=$HOUNDIGRADE_AWS_AUTOSCALING_GROUP_NAME -e ec2_launch_configuration_name=$HOUNDIGRADE_LAUNCH_CONFIG_NAME -e ecs_state=absent -e ec2_lc_state=absent -e ec2_asg_state=absent -e bucket_state=absent -e sqs_state=absent -e aws_prefix=$AWS_NAME_PREFIX cloudigrade-aws-resources.yaml

# Show clean up
# show no cluster
aws ecs list-clusters | grep $HOUNDIGRADE_ECS_CLUSTER_NAME

# show no s3 bucket
aws s3 ls | grep $AWS_NAME_PREFIX

# show no queue 
aws sqs list-queues | grep "${AWS_NAME_PREFIX}-cloudigrade-cloudtrail-sqs"
```
