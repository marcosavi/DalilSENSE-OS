"""Backfill the SQLite Run index from existing on-disk run directories."""
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from dalilsense.dashboard import runs


class Command(BaseCommand):
    help = "Index every run under DALILSENSE_RUNS_DIR into the SQLite table."

    def handle(self, *args, **options):
        root = Path(settings.DALILSENSE_RUNS_DIR)
        if not root.exists():
            self.stdout.write("No runs directory yet; nothing to sync.")
            return
        indexed = skipped = 0
        for config_path in sorted(root.glob("*/config.json")):
            run_id = config_path.parent.name
            try:
                runs.sync_run(run_id)
            except (FileNotFoundError, ValueError, KeyError, OSError) as exc:
                skipped += 1
                self.stderr.write(f"Skipped {run_id}: {exc}")
                continue
            indexed += 1
            self.stdout.write(f"Indexed {run_id}")
        self.stdout.write(self.style.SUCCESS(f"Done. {indexed} indexed, {skipped} skipped."))
