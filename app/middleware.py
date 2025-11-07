from django.shortcuts import redirect
from django.utils.deprecation import MiddlewareMixin
from django.contrib import messages
from app.models import Gym

class GymContextMiddleware(MiddlewareMixin):
    """
    Adjunta request.gym si existe en sesión o cookie.
    No obliga; solo adjunta. Usa el decorador @gym_required para exigirlo.
    """
    def process_request(self, request):
        request.gym = None
        gym_id = request.session.get("gym_id") or request.COOKIES.get("gym_id")
        if gym_id:
            try:
                request.gym = Gym.objects.get(pk=gym_id, is_active=True)
            except Gym.DoesNotExist:
                # limpiamos basura
                request.session.pop("gym_id", None)
        return None
