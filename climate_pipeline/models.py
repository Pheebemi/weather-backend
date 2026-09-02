from django.db import models

from boundaries.models import Ward


class WardClimate(models.Model):
    """
    Step 4 output of the Supervisor's formal data-prep pipeline (see
    CLAUDE.md): an area-weighted temperature/rainfall average for one ward,
    computed offline by resampling a downscaled CMIP6 climate grid onto
    ward boundaries that survived the Step 3 LULC filter (agricultural or
    forested wards only).

    One row per ward *per scenario and period*, so a ward can hold both a
    near-term and a later projection and the app can show how its climate
    changes between them.

    These are projections, not observations. weather_data/views.py returns
    them alongside live NASA POWER under their own key, never as today's
    weather.
    """

    ward = models.ForeignKey(Ward, on_delete=models.CASCADE, related_name="climates")
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

    class Meta:
        unique_together = ("ward", "scenario", "period")
        ordering = ["period"]

    def __str__(self):
        return f"{self.ward.name}: {self.temperature_avg_c}°C / {self.precipitation_avg_mm}mm"
