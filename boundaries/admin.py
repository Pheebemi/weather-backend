from django.contrib import admin

from .models import LGA, FarmlandReport, LGAFarmland, State, Ward, WardFarmland


@admin.register(State)
class StateAdmin(admin.ModelAdmin):
    list_display = ("name", "code")
    search_fields = ("name", "code")


@admin.register(LGA)
class LGAAdmin(admin.ModelAdmin):
    list_display = ("name", "state", "code")
    list_filter = ("state",)
    search_fields = ("name", "code")


@admin.register(Ward)
class WardAdmin(admin.ModelAdmin):
    list_display = ("name", "lga", "latitude", "longitude")
    list_filter = ("lga__state",)
    search_fields = ("name", "code")


@admin.register(WardFarmland)
class WardFarmlandAdmin(admin.ModelAdmin):
    list_display = ("ward", "has_agric_land", "cropland_percent", "manually_corrected")
    list_filter = ("has_agric_land", "manually_corrected")


@admin.register(FarmlandReport)
class FarmlandReportAdmin(admin.ModelAdmin):
    list_display = ("ward", "created_at", "resolved")
    list_filter = ("resolved",)
    search_fields = ("ward__name", "note")


@admin.register(LGAFarmland)
class LGAFarmlandAdmin(admin.ModelAdmin):
    list_display = ("lga", "has_agric_land", "cropland_percent", "manually_corrected")
    list_filter = ("has_agric_land", "manually_corrected", "lga__state")
