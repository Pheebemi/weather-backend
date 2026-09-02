from django.contrib import admin

from .models import WardClimate


@admin.register(WardClimate)
class WardClimateAdmin(admin.ModelAdmin):
    list_display = ("ward", "temperature_avg_c", "precipitation_avg_mm", "pipeline_run_at")
    list_filter = ("ward__lga__state",)
    search_fields = ("ward__name", "ward__code")
