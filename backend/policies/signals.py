from django.db.models.signals import post_save
from django.dispatch import receiver

from .chunking import rebuild_chunks
from .models import Policy


@receiver(post_save, sender=Policy)
def reindex_policy(sender, instance, **kwargs):
    rebuild_chunks(instance)
