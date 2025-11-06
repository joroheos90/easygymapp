def gym_context(request):
    gp = getattr(request.user, "gym_profile", None) if request.user.is_authenticated else None
    role = getattr(gp, "role", None)
    return {
        "gym_profile": gp,              # objeto GymUser o None
        "gym_role": role,               # "admin" | "member" | None
        "is_admin": role == "admin",
        "is_member": role == "member",
    }
