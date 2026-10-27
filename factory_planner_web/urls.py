"""URL configuration for the factory planner."""

from django.urls import include, path


urlpatterns = [path("", include("planner.urls"))]
