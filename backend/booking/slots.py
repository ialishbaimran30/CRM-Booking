"""Fixed business-hours slot grid used by the Available Slots feature."""
from datetime import time

# Hourly slots from 9 AM through 11 PM inclusive (start hour of each slot).
BUSINESS_START_HOUR = 9
BUSINESS_END_HOUR = 23  # last slot starts at 11 PM


def generate_daily_slots():
    """Return the fixed list of (start_time, end_time) slot boundaries for a business day.

    Each slot is one hour, except the last (11 PM), which runs to 23:59:59 —
    this avoids wrapping start/end across midnight, which plain `time` values
    (with no date component) can't represent correctly.
    """
    slots = []
    for hour in range(BUSINESS_START_HOUR, BUSINESS_END_HOUR + 1):
        start = time(hour, 0)
        end = time(23, 59, 59) if hour == BUSINESS_END_HOUR else time(hour + 1, 0)
        slots.append((start, end))
    return slots
