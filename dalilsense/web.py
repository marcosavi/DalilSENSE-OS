"""Compatibility launcher for the Django experiment dashboard."""
import os


def main(host: str = "127.0.0.1", port: int = 8000) -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django
    from django.core.management import call_command

    django.setup()
    # Runs live in this process; a code reload would interrupt an experiment.
    call_command("runserver", f"{host}:{port}", use_reloader=False, use_threading=True)


if __name__ == "__main__":
    main()
