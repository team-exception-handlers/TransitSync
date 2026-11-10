"""Time conversions shared by simulation orchestration and API serialization."""

from simulator.scenario import Scenario


def scenario_start_clock_s(scenario: Scenario) -> float:
    """Return local scenario start time as seconds after midnight.

    Run events use relative seconds, so this absolute clock value is kept
    separately for the response and for shifting timetable visits.
    """
    start = scenario.start_time
    return float(start.hour * 3600 + start.minute * 60 + start.second)
