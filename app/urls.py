from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="app.home"),
    path("selector", views.selector, name="app.selector"),
    path("hours", views.hours, name="app.hours"),
    path("profile", views.profile, name="app.profile"),
    path("edit", views.edit, name="app.edit"),
    path("payment", views.payment, name="app.payment"),
    path("users", views.users, name="app.users"),
    path("payments", views.payments, name="app.payments"),
]