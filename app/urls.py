from django.urls import path

from . import views

urlpatterns = [
    #admin
    path("base_hours", views.base_hours, name="app.base_hours"),
    path("hours", views.hours, name="app.hours"),
    path("payment", views.payment, name="app.payment"),
    path("users", views.users, name="app.users"),
    path("staff", views.staff, name="app.staff"),
    path("panel", views.admin, name="app.admin"),
    path("staff-profile", views.staff_profile, name="app.staff_profile"),
    path("edit-staff-profile", views.edit_staff_profile, name="app.edit_staff_profile"),
    path("activity", views.activity, name="app.activity"),

    #members
    path("selector", views.selector, name="app.selector"),

    #shared
    path("", views.home, name="app.home"),
    path("profile", views.profile, name="app.profile"),
    path("user", views.user, name="app.edit"),
    path("payments", views.payments, name="app.payments"),
    
    #auth
    path("login/", views.AppLoginView.as_view(), name="app.login"),
    path("logout/", views.logout_view, name="app.logout"),
    path("profile/password/", views.MemberPasswordChangeView.as_view(), name="app.password_change"),

    #join
    path("join/<int:gym_id>", views.public_join_by_gym, name="app.join"),
]