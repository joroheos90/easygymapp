from django.contrib import admin
from app.models import GymUser, Payment, BaseTimeslot, DailyTimeslot, TimeslotSignup, UserWeight

@admin.register(GymUser)
class GymUserAdmin(admin.ModelAdmin):
    list_display = ("id","full_name","role","phone","join_date","is_active")
    search_fields = ("full_name","phone")
    list_filter = ("role","is_active")

admin.site.register(Payment)
admin.site.register(BaseTimeslot)
admin.site.register(DailyTimeslot)
admin.site.register(TimeslotSignup)
admin.site.register(UserWeight)
