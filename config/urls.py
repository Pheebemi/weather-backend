from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("boundaries.urls")),
    path("api/", include("weather_data.urls")),
]
