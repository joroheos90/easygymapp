from django.db.models import TextChoices


class ActivityEventType(TextChoices):
    LOGIN = "login", "Inicio de sesión"
    LOGOUT = "logout", "Cierre de sesión"

    PROFILE_UPDATE = "profile_update", "Actualización de perfil"
    PASSWORD_CHANGE = "password_change", "Cambio de contraseña"

    GROUP_JOIN = "group_join", "Entrada a grupo"
    GROUP_LEAVE = "group_leave", "Salida de grupo"

    MEMBER_ADD = "member_add", "Alta de miembro"
    MEMBER_REMOVE = "member_remove", "Baja de miembro"

    COUCH_ADD = "couch_add", "Alta de entrenador"
    COUCH_REMOVE = "couch_remove", "Baja de entrenador"

    BASE_SCHEDULE_ACTIVATE = "base_schedule_activate", "Activar horario base"
    BASE_SCHEDULE_DEACTIVATE = "base_schedule_deactivate", "Desactivar horario base"

    PAYMENT_ADD = "payment_add", "Registro de pago"

    PAYMENT_REMOVE = "payment_remove", "Eliminacion de pago"


    ERROR = "error", "Error"
