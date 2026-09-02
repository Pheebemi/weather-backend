from django.urls import path

from . import views

urlpatterns = [
    path("states/", views.StateListView.as_view(), name="state-list"),
    path("states/<int:state_id>/lgas/", views.LGAListView.as_view(), name="lga-list"),
    path("lgas/<int:lga_id>/wards/", views.WardListView.as_view(), name="ward-list"),
    path("wards/<int:ward_id>/farmland/", views.WardFarmlandView.as_view(), name="ward-farmland"),
]
