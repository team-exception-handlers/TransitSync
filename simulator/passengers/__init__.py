# AI contribution: 50% or more AI-generated
"""Passenger movement through the transit network."""

from simulator.passengers.boarding_component import BoardingComponent
from simulator.passengers.corridor import CorridorPassage, CorridorQueue
from simulator.passengers.demand import DemandPeriod, DemandProfile
from simulator.passengers.generation import PassengerGenerator
from simulator.passengers.passenger import Passenger, PassengerState
from simulator.passengers.transfer_component import TransferComponent, TransferRoute

__all__ = [
    "BoardingComponent",
    "CorridorPassage",
    "CorridorQueue",
    "DemandPeriod",
    "DemandProfile",
    "Passenger",
    "PassengerGenerator",
    "PassengerState",
    "TransferComponent",
    "TransferRoute",
]
