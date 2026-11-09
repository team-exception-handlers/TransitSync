# AI contribution: 50% or more AI-generated
"""Check connection service headways for saved settings and strategies (#51)."""

from collections.abc import Mapping

from simulator.control.validation import finite_number


def validate_connection_headways(value: object) -> dict[str, float]:
    """Copy connection service headways after checking IDs and seconds (#51).

    Each platform needs a nonblank ID and a finite positive headway.
    Raise ``ValueError`` naming the bad field. Used by saved settings and
    direct strategy construction so both accept the same values.
    """
    if not isinstance(value, Mapping):
        raise ValueError("headways_s must be a mapping")
    headways: dict[str, float] = {}
    for platform_id, seconds in value.items():
        if not isinstance(platform_id, str) or not platform_id.strip():
            raise ValueError("headways_s platform ID must be a non-empty string")
        label = f"headways_s[{platform_id!r}]"
        try:
            seconds = finite_number(label, seconds)
        except OverflowError as error:
            raise ValueError(f"{label} must be finite seconds") from error
        if seconds <= 0:
            raise ValueError(f"{label} must be > 0 seconds")
        headways[platform_id] = seconds
    return headways
