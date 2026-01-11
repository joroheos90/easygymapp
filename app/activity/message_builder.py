from django.utils.formats import date_format
from .event_types import ActivityEventType


def _actor(name):
    return f"<b class='capitalize'>{name}</b>"

def _payment_amount(amount):
    formatted = f"${amount:,.2f}"
    return f"<b>{formatted}</b>"


def _payment_method(method):
    return f"<b class='capitalize'>{method}</b>"

def _group_label(meta):
    return f"{meta['group_title']} el día {meta['group_date']}"


def _schedule_label(meta):
    return f"{meta['title']}"


def build_message(event_type, actor_name, metadata):
    match event_type:
        case ActivityEventType.LOGIN:
            return f"{_actor(actor_name)} inició sesión"

        case ActivityEventType.LOGOUT:
            return f"{_actor(actor_name)} cerró su sesión"

        case ActivityEventType.PASSWORD_CHANGE:
            return f"{_actor(actor_name)} cambió su <b>contraseña</b>"
        
        case ActivityEventType.PROFILE_UPDATE:
            fields = ", ".join(metadata.get("fields", []))
            member_name = metadata.get("member_name", "")
            if member_name == actor_name:
                return (
                    f"{_actor(actor_name)} actualizó su "
                    f"<b class='capitalize'>{fields}</b>"
                )
            else:
                return (
                    f"{_actor(actor_name)} actualizó el "
                    f"<b class='capitalize'>{fields}</b> de <b class='capitalize'>{member_name}</b>"
                )
            
        case ActivityEventType.GROUP_JOIN:
            return (
                f"{_actor(actor_name)} se metió al grupo de "
                f"<b>{_group_label(metadata)}</b>"
            )
        
        case ActivityEventType.GROUP_LEAVE:
            return (
                f"{_actor(actor_name)} se salió del grupo de "
                f"<b>{_group_label(metadata)}</b>"
            )
        
        case ActivityEventType.MEMBER_ADD:
            return (
                f"{_actor(actor_name)} agregó al miembro "
                f"<b>{metadata['member_name']}</b>"
            )

        case ActivityEventType.MEMBER_REMOVE:
            return (
                f"{_actor(actor_name)} eliminó al miembro "
                f"<b>{metadata['member_name']}</b>"
            )
        
        case ActivityEventType.COUCH_REMOVE:
            return (
                f"{_actor(actor_name)} eliminó al entrenador "
                f"<b>{metadata['couch_name']}</b>"
            )
        
        case ActivityEventType.COUCH_ADD:
            return (
                f"{_actor(actor_name)} agregó al entrenador "
                f"<b>{metadata['couch_name']}</b>"
            )

        case ActivityEventType.BASE_SCHEDULE_ACTIVATE:
            return (
                f"{_actor(actor_name)} activó el horario base de "
                f"<b>{_schedule_label(metadata)}</b>"
            )

        case ActivityEventType.BASE_SCHEDULE_DEACTIVATE:
            return (
                f"{_actor(actor_name)} desactivó el horario base de "
                f"<b>{_schedule_label(metadata)}</b>"
            )

        case ActivityEventType.PAYMENT_ADD:
            return (
                f"{_actor(actor_name)} registró {_payment_amount(metadata['amount'])} "
                f"vía  {_payment_method(metadata['method'])} de "
                f"<b>{metadata['member_name']}</b> para el periodo "
                f"<b>{metadata['period']}</b>"
            )
        
        case ActivityEventType.PAYMENT_REMOVE:
            return (
                f"{_actor(actor_name)} eliminó {_payment_amount(metadata['amount'])} "
                f"vía  {_payment_method(metadata['method'])} de "
                f"<b>{metadata['member_name']}</b> para el periodo "
                f"<b>{metadata['period']}</b>"
            )

        case ActivityEventType.ERROR:
            return (
                f"{_actor(actor_name)} tuvo un error al intentar "
                f"<b>{metadata['action']}</b>"
            )

        case _:
            return f"{_actor(actor_name)} realizó una acción"
