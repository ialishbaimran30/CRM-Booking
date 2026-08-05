from django.contrib import admin
from .models import Staff, Resource, BookingAssignment

admin.site.register(Staff)
admin.site.register(Resource)
admin.site.register(BookingAssignment)