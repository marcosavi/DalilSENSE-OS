from django.urls import path

from . import workspace

app_name = "experiments"
urlpatterns = [
    path("", workspace.index, name="index"),
    path("<uuid:run_id>/", workspace.detail, name="detail"),
    path("<uuid:run_id>/status/", workspace.status, name="status"),
    path("<uuid:run_id>/review/", workspace.review, name="review"),
    path("<uuid:run_id>/summary/", workspace.summary, name="summary"),
]
