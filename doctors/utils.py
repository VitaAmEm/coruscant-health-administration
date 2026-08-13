def compute_trends(readings):
    """
    Groups a patient's readings by type and compares the two most recent
    of each type, to support the "monitor if the patient's condition is
    improving or not" requirement without needing a full charting library
    for this MVP.

    Only readings whose value parses as a plain number are compared
    numerically (heart rate, temperature, glucose, O2 saturation).
    Blood pressure readings ("120/80") aren't single numbers, so they're
    shown without a trend arrow rather than guessing at a comparison.

    `readings` must already be ordered most-recent-first (the model's
    default ordering does this).
    """
    grouped = {}
    for reading in readings:
        grouped.setdefault(reading.reading_type, []).append(reading)

    trends = {}
    for reading_type, items in grouped.items():
        latest = items[0]
        previous = items[1] if len(items) > 1 else None

        trend = None
        if previous is not None:
            try:
                latest_value = float(latest.value)
                previous_value = float(previous.value)
            except ValueError:
                trend = None
            else:
                if latest_value > previous_value:
                    trend = "up"
                elif latest_value < previous_value:
                    trend = "down"
                else:
                    trend = "same"

        trends[reading_type] = {
            "label": latest.get_reading_type_display(),
            "latest": latest,
            "previous": previous,
            "trend": trend,
        }
    return trends
