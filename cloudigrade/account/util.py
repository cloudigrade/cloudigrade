"""Various utility functions for the account app."""
import collections

from django.utils import timezone

from account.models import AwsInstance, AwsInstanceEvent, InstanceEvent


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
            event = AwsInstanceEvent(
                instance=instance,
                event_type=InstanceEvent.TYPE.power_on,
                occurred_at=timezone.now(),
                subnet=instance_data['SubnetId'],
                ec2_ami_id=instance_data['ImageId'],
                instance_type=instance_data['InstanceType'],
            )
            event.save()
            saved_instances[region].append(instance)
    return dict(saved_instances)


def create_new_machine_images(instances_data):
    platforms = {instance['ImageId']: instance['Platform']
                 for instance in instance_data
                 if instance['Platform'] == 'Windows'}
    seen_amis = set([instance['ImageId'] for instance in instance_data])
    known_amis = MachineImage.objects.filter(ami_id__in=list(amis))
    new_amis = list(seen_amis.difference(known_amis))

    for new_ami in new_amis:
        ami = MachineImage(
            ami_id = new_ami,
            platform = MachineImage.TYPE.Windows if platforms.get(new_ami) \
                else MachineImage.TYPE.Linux
        )
        ami.save()

    return new_amis
