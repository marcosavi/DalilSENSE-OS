from django.contrib import admin
from .models import Run


@admin.register(Run)
class RunAdmin(admin.ModelAdmin):
    list_display = ("name", "model", "status", "created_at", "n_out", "total", "rate")
    list_filter = ("status", "model", "created_at")
    search_fields = ("name", "model")
    readonly_fields = ("id", "created_at", "updated_at")
