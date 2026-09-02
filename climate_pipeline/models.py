from django.db import models

from boundaries.models import Ward


class WardClimate(models.Model):
    """
    Step 4 output of the Supervisor's formal data-prep pipeline (see
    CLAUDE.md): an area-weighted temperature/rainfall average for one ward,
    computed offline by resampling a downscaled CMIP6 climate grid onto
    ward boundaries that survived the Step 3 LULC filter (agricultural or
    forested wards only).

    A ward only gets a row here once it has been through the full pipeline.
    weather_data/views.py prefers this precomputed value over a live NASA
    POWER call when a row exists; live NASA POWER remains the fallback for
    wards the pipeline hasn't covered.
    """

    ward = models.OneToOneField(Ward, on_delete=models.CASCADE, related_name="climate")
    temperature_avg_c = models.FloatField(
        help_text="Area-weighted annual mean temperature from the downscaled CMIP6 grid."
    )
    precipitation_avg_mm = models.FloatField(
        help_text="Area-weighted annual total rainfall (mm/year) from the downscaled CMIP6 grid."
    )
    temperature_max_avg_c = models.FloatField(
        null=True,
        blank=True,
        help_text="Annual mean daily maximum temperature — heat stress matters more to crops than the mean.",
    )
    humidity_avg_pct = models.FloatField(
        null=True, blank=True, help_text="Annual mean relative humidity (%)."
    )
    climate_source = models.CharField(
        max_length=200,
        default="Downscaled/bias-corrected CMIP6 (offline pipeline, Step 4 output)",
    )
    scenario = models.CharField(
        max_length=20, blank=True, help_text="Emissions scenario, e.g. ssp245."
    )
    period = models.CharField(
        max_length=20, blank=True, help_text="Projection period, e.g. 2026-2035."
    )
    pipeline_run_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.ward.name}: {self.temperature_avg_c}°C / {self.precipitation_avg_mm}mm"
