from django.urls import path

from . import views

urlpatterns = [
    #admin
    path("base_hours", views.base_hours, name="app.base_hours"),
    path("hours", views.hours, name="app.hours"),
    path("payment", views.payment, name="app.payment"),
    path("users", views.users, name="app.users"),
    path("panel", views.admin, name="app.admin"),

    #members
    path("selector", views.selector, name="app.selector"),

    #shared
    path("", views.index, name="app.home"),
    path("profile", views.profile, name="app.profile"),
    path("edit", views.edit, name="app.edit"),
    path("payments", views.payments, name="app.payments"),
    
    #auth
    path("login/", views.AppLoginView.as_view(), name="app.login"),
    path("logout/", views.logout_view, name="app.logout"),
    path("profile/password/", views.MemberPasswordChangeView.as_view(), name="app.password_change"),
    
]