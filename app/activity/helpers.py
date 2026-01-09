from ..models import ActivityLog
from .message_builder import build_message

def log_activity(*, gym=None, actor, event_type, metadata=None):
    metadata = metadata or {}

    message = build_message(
        event_type=event_type,
        actor_name=actor.get_full_name(),
        metadata=metadata
    )

    ActivityLog.objects.create(
        gym=gym,
        actor_id=actor.id,
        actor_name=actor.get_full_name(),
        event_type=event_type,
        message=message,
        metadata=metadata,
    )
