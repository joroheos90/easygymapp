from django.contrib import admin
from app.models import (Gym, GymUser, Payment, BaseTimeslot, DailyTimeslot,
                        TimeslotSignup, MeasurementDefinition, MeasurementValue, MeasurementRecord)

admin.site.register(Gym)
admin.site.register(GymUser)
admin.site.register(Payment)
admin.site.register(BaseTimeslot)
admin.site.register(DailyTimeslot)
admin.site.register(TimeslotSignup)
admin.site.register(MeasurementDefinition)
admin.site.register(MeasurementValue)
admin.site.register(MeasurementRecord)



