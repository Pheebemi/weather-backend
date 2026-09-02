from django.urls import path

from . import views

urlpatterns = [
    path("weather/", views.WeatherByPointView.as_view(), name="weather-by-point"),
    path("weather/ward/<int:ward_id>/", views.WeatherByWardView.as_view(), name="weather-by-ward"),
]
