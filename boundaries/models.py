from django.db import models


class State(models.Model):
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=20, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class LGA(models.Model):
    state = models.ForeignKey(State, on_delete=models.CASCADE, related_name="lgas")
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=30, unique=True)

    class Meta:
        ordering = ["name"]
        unique_together = ("state", "name")

    def __str__(self):
        return f"{self.name}, {self.state.name}"


class Ward(models.Model):
    """
    A ward boundary sourced from GRID3/HDX shapefiles. `latitude`/`longitude`
    is the ward centroid, used to resolve a user's selection to a point for
    the NASA POWER weather lookup (see weather_data app). Geometry itself is
    not stored here — only the attributes the app needs at runtime.
    """

    lga = models.ForeignKey(LGA, on_delete=models.CASCADE, related_name="wards")
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=40, unique=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)

    class Meta:
        ordering = ["name"]
        unique_together = ("lga", "name")

    def __str__(self):
        return f"{self.name}, {self.lga.name}"


class WardFarmland(models.Model):
    """
    Pre-computed agricultural-land flag for a ward, derived from ESA
    WorldCover cropland coverage (see CLAUDE.md, Feature 2). Populated by an
    offline batch job, not computed per-request.
    """

    ward = models.OneToOneField(Ward, on_delete=models.CASCADE, related_name="farmland")
    has_agric_land = models.BooleanField()
    cropland_percent = models.FloatField(
        help_text="Percent of ward area classified as Cropland by ESA WorldCover."
    )
    threshold_used = models.FloatField(
        default=10.0, help_text="Cropland %% threshold applied to derive has_agric_land."
    )
    source = models.CharField(
        max_length=100,
        default="ESA WorldCover (satellite-derived, auto-generated)",
        help_text="Shown to users for transparency — this is not manually verified.",
    )
    manually_corrected = models.BooleanField(
        default=False, help_text="True once a reported error has been manually flipped."
    )
    computed_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.ward.name}: {'agric' if self.has_agric_land else 'no agric'}"
