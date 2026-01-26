from django.contrib import admin
from app.models import Gym, GymUser, Payment, BaseTimeslot, DailyTimeslot, TimeslotSignup

admin.site.register(Gym)
admin.site.register(GymUser)
admin.site.register(Payment)
admin.site.register(BaseTimeslot)
admin.site.register(DailyTimeslot)
admin.site.register(TimeslotSignup)
