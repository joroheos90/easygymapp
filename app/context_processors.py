def gym_context(request):
    gp = request.user.gym_profile if (request.user.is_authenticated and hasattr(request.user, "gym_profile")) else None
    role = getattr(gp, "role", None)
    return {"gym_profile": gp, "gym_role": role, "is_admin": role=="admin", "is_member": role=="member"}
