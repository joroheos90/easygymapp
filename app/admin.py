from django.contrib import admin
from app.models import GymUser, Payment, BaseTimeslot, DailyTimeslot, TimeslotSignup, UserWeight

admin.site.register(GymUser)
admin.site.register(Payment)
admin.site.register(BaseTimeslot)
admin.site.register(DailyTimeslot)
admin.site.register(TimeslotSignup)
admin.site.register(UserWeight)
