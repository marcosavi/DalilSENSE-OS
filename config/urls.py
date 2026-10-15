from django.contrib import admin
from django.urls import include, path

from dalilsense.dashboard import views, workspace

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", workspace.home, name="home"),
    path("experiments/", include("dalilsense.dashboard.experiment_urls")),
    path("exp1", views.index),
    path("exp1/", include("dalilsense.dashboard.urls")),
]
