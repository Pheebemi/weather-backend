from django.urls import path

from . import views

urlpatterns = [
    path("weather/", views.WeatherByPointView.as_view(), name="weather-by-point"),
    path("weather/ward/<int:ward_id>/", views.WeatherByWardView.as_view(), name="weather-by-ward"),
    path("forecast/ward/<int:ward_id>/", views.ForecastByWardView.as_view(), name="forecast-by-ward"),
    path("climate/ward/<int:ward_id>/", views.ClimateByWardView.as_view(), name="climate-by-ward"),
    path("forecast/lga/<int:lga_id>/", views.ForecastByLGAView.as_view(), name="forecast-by-lga"),
    path("climate/lga/<int:lga_id>/", views.ClimateByLGAView.as_view(), name="climate-by-lga"),
]
