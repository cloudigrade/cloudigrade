"""Various utility functions for the account app."""
import collections

from django.utils import timezone

from account.models import Instance, InstanceEvent


def create_initial_instance_events(account, instances_data):
    """
    Create Instance and InstanceEvent for the first time we see each instance.

    This function is useful for recording InstanceEvents for the first time we
    discover a running instance and we have to assume that "now" is the
    earliest known time that the instance was running.

    Args:
        account (Account): The Account that owns the Instance that spawned
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
            instance, __ = Instance.objects.get_or_create(
                account=account,
                ec2_instance_id=instance_data['InstanceId'],
                region=region,
            )
            event = InstanceEvent(
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
