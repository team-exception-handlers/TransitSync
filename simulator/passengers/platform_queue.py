# AI contribution: 50% or more AI-generated
"""FIFO platform waiting and capacity-limited recovery from suspension (#27).

Uses the queueing principle Q = A - D (Mathematical Foundations §5).
Passenger generation and destination selection remain upstream components.
"""

from collections import defaultdict, deque

from simulator.engine.events import PassengerArrival
from simulator.trains.train import Train


class PlatformQueue:
    """Optional owner of waiting passengers for explicitly selected platforms."""

    def __init__(self, platform_ids: tuple[str, ...]) -> None:
        if any(not isinstance(item, str) or not item.strip() for item in platform_ids):
            raise ValueError("Platform IDs cannot be empty")
        self.platform_ids = frozenset(platform_ids)
        self._waiting: dict[str, deque[str]] = defaultdict(deque)
        self._seen: set[str] = set()

    def arrive(self, event: PassengerArrival) -> bool:
        """Enqueue a passenger once; return whether this queue owns the platform."""
        if event.platform_id not in self.platform_ids:
            return False
        if event.passenger_id in self._seen:
            raise ValueError(f"Duplicate passenger arrival: {event.passenger_id}")
        self._seen.add(event.passenger_id)
        self._waiting[event.platform_id].append(event.passenger_id)
        return True

    def waiting_count(self, platform_id: str) -> int:
        """Number still waiting at this platform."""
        return len(self._waiting[platform_id])

    def board(self, platform_id: str, train: Train) -> list[str]:
        """Board in arrival order up to remaining capacity; return passenger IDs."""
        waiting = self._waiting[platform_id]
        count = min(len(waiting), train.available_capacity)
        train.board(count)
        return [waiting.popleft() for _ in range(count)]
