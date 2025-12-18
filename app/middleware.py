from django.shortcuts import redirect
from django.utils.deprecation import MiddlewareMixin
from django.contrib import messages
from app.models import Gym

class GymUserMiddleware(MiddlewareMixin):
    def process_request(self, request):
        print("antes")
        request.gym_user = None
        request.gym_role = None
        request.user_id = None
        request.is_admin = False
        request.is_staff = False
        request.is_member = False

        if request.user.is_authenticated:
            print("esta authenticado")
            gp = getattr(request.user, "gym_profile", None)
            print(gp)
            if gp is not None:
                request.gym_user = gp
                role = getattr(gp, "role", None)
                request.gym_role = role
                request.is_admin = (role == "admin")
                request.is_staff = (role == "staff")
                request.is_member = (role == "member")
                user_id = getattr(gp, "id", None)
                request.user_id = user_id

        request.gym = None
        gym_id = request.session.get("gym_id") or request.COOKIES.get("gym_id")
        if gym_id:
            try:
                request.gym = Gym.objects.get(pk=gym_id, is_active=True)
            except Gym.DoesNotExist:
                request.session.pop("gym_id", None)

        return None


class NoCacheHTMLMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
    def __call__(self, request):
        resp = self.get_response(request)
        ctype = resp.get("Content-Type", "")
        if request.method == "GET" and "text/html" in ctype:
            resp["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            resp["Pragma"] = "no-cache"
            resp["Expires"] = "0"
        return resp
