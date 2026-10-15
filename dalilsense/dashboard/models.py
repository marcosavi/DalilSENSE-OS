"""SQLite index over the on-disk run directories.

The JSONL/config.json files remain the source of truth for reproducibility.
Each Run row is a derived snapshot refreshed when a run completes or is reviewed,
plus the rendered markdown summary for cheap listing and preview.
"""
import uuid

from django.db import models

STATUS_LABELS = {
    "running": "Generating",
    "completed": "Ready for review",
    "completed_with_errors": "Finished with errors",
    "failed": "Failed",
    "interrupted": "Interrupted",
}


class Run(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    model = models.CharField(max_length=255)
    model_digest = models.CharField(max_length=128, blank=True)
    status = models.CharField(max_length=32)
    created_at = models.CharField(max_length=32)
    finished_at = models.CharField(max_length=32, blank=True)
    prompt_sha = models.CharField(max_length=64)
    dataset_sha = models.CharField(max_length=64)
    selection = models.CharField(max_length=16)
    sample_seed = models.IntegerField(null=True, blank=True)
    total = models.IntegerField(default=0)
    n_out = models.IntegerField(default=0)
    n_lbl = models.IntegerField(default=0)
    n_h = models.IntegerField(default=0)
    rate = models.CharField(max_length=16, default="—")
    mean_latency_ms = models.IntegerField(null=True, blank=True)
    summary_md = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)

    @property
    def status_label(self):
        return STATUS_LABELS.get(self.status, self.status)

    def __str__(self):
        return f"{self.name} ({self.model})"
