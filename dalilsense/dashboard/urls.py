from django.urls import path

from . import views

app_name = "dashboard"
urlpatterns = [
    path("", views.index, name="index"),
    path("run", views.run, name="run"),
    path("label", views.label, name="label"),
    path("stream", views.stream, name="stream"),
    path("summary", views.summary, name="summary"),
]
