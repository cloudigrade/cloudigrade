"""Various utility functions for the account app."""
import collections
import json

import pika
from django.conf import settings
from django.utils import timezone

from account.models import (AwsInstance, AwsInstanceEvent, InstanceEvent,
                            MachineImage, AWSMachineImage)


def create_initial_aws_instance_events(account, instances_data):
    """
    Create AwsInstance and AwsInstanceEvent the first time we see an instance.

    This function is a convenience helper for recording the first time we
    discover a running instance wherein we assume that "now" is the earliest
    known time that the instance was running.

    Args:
        account (AwsAccount): The account that owns the instance that spawned
            the data for these InstanceEvents.
        instances_data (dict): Dict whose keys are AWS region IDs and values
            are each a list of dictionaries that represent an instance

    Returns:
        dict: Similar to the incoming instances_data dict, the returned dict
        has keys that are AWS region IDs and values that are each a list of the
        created InstanceEvent objects.

    """
    saved_instances = collections.defaultdict(list)
    for region, instances in instances_data.items():
        for instance_data in instances:
            instance, __ = AwsInstance.objects.get_or_create(
                account=account,
                ec2_instance_id=instance_data['InstanceId'],
                region=region,
            )
            aws_machine_image = AWSMachineImage.objects.get(
                ec2_ami_id=instance_data['ImageId']
            )
            event = AwsInstanceEvent(
                instance=instance,
                event_type=InstanceEvent.TYPE.power_on,
                occurred_at=timezone.now(),
                subnet=instance_data['SubnetId'],
                ec2_ami_id=aws_machine_image,
                instance_type=instance_data['InstanceType'],
            )
            event.save()
            saved_instances[region].append(instance)
    return dict(saved_instances)


def create_new_machine_images(instances_data):
    saved_amis = []
    for __, instances in instances_data.items():
        print(instances)

        platforms = {instance['ImageId']: instance['Platform']
                     for instance in instances
                     if instance.get('Platform') == 'Windows'}
        seen_amis = set([instance['ImageId'] for instance in instances])
        known_amis = AWSMachineImage.objects.filter(
            ec2_ami_id__in=list(seen_amis)
        )
        new_amis = list(seen_amis.difference(known_amis))

        for new_ami in new_amis:
            ami = AWSMachineImage(
                ec2_ami_id=new_ami,
                platform=MachineImage.TYPE.Windows if platforms.get(new_ami) \
                    else MachineImage.TYPE.Linux
            )
            ami.save()

        saved_amis.extend(new_amis)
    return saved_amis


def generate_aws_ami_messages(instances_data, ami_list):
    messages = []
    for region, instances in instances_data.items():
        for instance in instances:
            if instance['ImageId'] in ami_list:
                messages.append(json.dumps({"cloud_provider": 'AWS',
                                            "region": region,
                                            "image_id": instance['ImageId']}))
    return messages


def add_messages_to_queue(queue_name, messages):
    connection = pika.BlockingConnection(
        pika.URLParameters(settings.CELERY_BROKER_URL)
    )

    channel = connection.channel()
    channel.queue_declare(queue=queue_name)

    for message in messages:
        channel.basic_publish(exchange='',
                              routing_key=queue_name,
                              body=message)

    connection.close()
