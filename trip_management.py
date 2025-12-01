"""
Minimal Trip class to demonstrate core OOP patterns.
This integrates User classes (Observer), Fare strategies, and Map service.
"""
from typing import Optional
from datetime import datetime
from user_classes import Subject, TripState, Rider, Driver
from fare_calc import FareStrategy, FareStrategyFactory


class Trip(Subject):
    """
    Basic Trip class integrating Observer and Strategy patterns.
    """
    
    _id_counter = 1000
    
    def __init__(self, pickup: str, destination: str, rider: Rider, 
                 strategy_name: str = "Standard"):
        super().__init__()
        self.trip_id = Trip._id_counter
        Trip._id_counter += 1
        
        self.pickup = pickup
        self.destination = destination
        self.rider = rider
        self.driver: Optional[Driver] = None
        
        # State management
        self._state = TripState.REQUESTED
        self.created_at = datetime.now()
        
        # Route and fare information
        self.distance_km: float = 0.0
        self.duration_min: float = 0.0
        
        # Strategy pattern - fare calculation
        # Normalize strategy name to proper case (handle mixed case from database)
        normalized_strategy = strategy_name.capitalize() if strategy_name else "Standard"
        self.fare_strategy: FareStrategy = FareStrategyFactory.create_strategy(normalized_strategy)
        self.base_fare: float = 0.0
    
    @property
    def state(self) -> TripState:
        return self._state
    
    def _change_state(self, new_state: TripState) -> None:
        """Change state and notify observers"""
        old_state = self._state
        self._state = new_state
        self.notify(self, old_state, new_state)
    
    def set_route_info(self, distance_km: float, duration_min: float) -> None:
        """Set route info and calculate fare using strategy"""
        self.distance_km = distance_km
        self.duration_min = duration_min
        self.base_fare = self.fare_strategy.calculate_fare(distance_km, duration_min)
    
    def accept(self, driver: Driver) -> None:
        """Driver accepts trip"""
        self.driver = driver
        self._change_state(TripState.ACCEPTED)
    
    def decline(self) -> None:
        """Driver declines trip"""
        self._change_state(TripState.DECLINED)
    
    def start(self) -> None:
        """Start trip"""
        self._change_state(TripState.IN_PROGRESS)
    
    def complete(self) -> None:
        """Complete trip"""
        self._change_state(TripState.COMPLETED)
    
    def __str__(self) -> str:
        return (f"Trip {self.trip_id}: {self.pickup} → {self.destination} "
                f"[{self._state.value}] ${self.base_fare:.2f}")