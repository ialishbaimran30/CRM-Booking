#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys


def main():
    """Run administrative tasks."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "bookings.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Django import nahi ho saka. Virtual environment activate karke "
            "requirements.txt ki dependencies install karein."
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
