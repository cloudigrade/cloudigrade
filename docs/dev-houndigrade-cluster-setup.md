## AWS ECS Cluster Setup

1. log in to the AWS web console for your houndigrade account
1. go to the ECS (Elastic Container Service) page
1. click Clusters
1. click Create Cluster
1. click to select "EC2 Linux + Networking" and click "Next step"
1. enter appropriate settings and click "Create"
    - give the cluster a reasonably unique name ("yourname-houndigrade-cluster")
    - Provisioning Model: On-Demand Instance
    - EC2 instance type: t2.micro
    - Number of instances: 1 (we want 0, but you can't start with 0)
    - EBS storage (GiB): whatever is default
    - Key pair: set to your key pair (you'll have to create one before selecting it)
    - Networking: while not ideal, all defaults are generally OK
1. wait and watch as things spin!
1. when Cluster Resources becomes available, copy the "Auto Scaling group" value for later use
1. click "View Cluster" when the button becomes available
1. click the "ECS Instances" tab
1. click the "Scale ECS Instances" button
1. set "Desired number of instances" to 0 and click "Scale"
1. press the little reload button inside the tab interface. wait. repeat. eventually the one Container Instance listed should disappear.

## Checking via the CLI

1. save the name you used for creating the cluster to an envirionment variable. you may need this for configuring parts of cloudigrade! for example:
    ```
    export HOUNDIGRADE_ECS_CLUSTER_NAME=brasmith-houndigrade-cluster-2
    ```
1. save that "Auto Scaling group" value you copied earlier to an environment variable. you may need this for configuring parts of cloudigrade! for example:
    ```
    export HOUNDIGRADE_AWS_AUTOSCALING_GROUP_NAME=EC2ContainerService-brasmith-houndigrade-cluster-2-EcsInstanceAsg-1QZUM5SE255CP
    ```

1. be sure to `export` your `AWS_DEFAULT_REGION`, `AWS_ACCESS_KEY_ID`, and `AWS_SECRET_ACCESS_KEY` if you don't have the default AWS CLI profile configure appropriately.
1. use some variation of the following to check the current state of the cluster as needed.
    ```
    aws autoscaling describe-auto-scaling-groups \
        --auto-scaling-group-names $HOUNDIGRADE_AWS_AUTOSCALING_GROUP_NAME \
        --query 'AutoScalingGroups[*].[MinSize,MaxSize,DesiredCapacity,Instances[*].InstanceId]'
    ```
1. if you want to scale down the cluster without poking some celery tasks:
    ```
    aws autoscaling update-auto-scaling-group \
        --auto-scaling-group-name $HOUNDIGRADE_AWS_AUTOSCALING_GROUP_NAME \
        --min-size 0 \
        --max-size 0 \
        --desired-capacity 0
    ```
