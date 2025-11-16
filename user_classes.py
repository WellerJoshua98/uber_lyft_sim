"""
Core domain models for the Uber/Lyft simulation system.
Implements Observer pattern for trip state changes and base user classes.
"""
from abc import ABC, abstractmethod
from enum import Enum
from typing import List, Optional
from datetime import datetime


class TripState(Enum):
    """Enum for trip states"""
    REQUESTED = "requested"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class Observer(ABC):
    """Observer interface for the Observer pattern"""
    @abstractmethod
    def update(self, trip: 'Trip', old_state: TripState, new_state: TripState) -> None:
        """Called when trip state changes"""
        pass


class Subject:
    """Subject class that manages observers"""
    def __init__(self):
        self._observers: List[Observer] = []
    
    def attach(self, observer: Observer) -> None:
        """Attach an observer"""
        if observer not in self._observers:
            self._observers.append(observer)
    
    def detach(self, observer: Observer) -> None:
        """Detach an observer"""
        if observer in self._observers:
            self._observers.remove(observer)
    
    def notify(self, trip: 'Trip', old_state: TripState, new_state: TripState) -> None:
        """Notify all observers of state change"""
        for observer in self._observers:
            observer.update(trip, old_state, new_state)


class User(ABC):
    """Abstract base class for all users in the system"""
    def __init__(self, user_id: str, name: str, email: str, phone: str):
        self.user_id = user_id
        self.name = name
        self.email = email
        self.phone = phone
        self.created_at = datetime.now()
    
    @abstractmethod
    def get_role(self) -> str:
        """Return the role of the user"""
        pass
    
    def __str__(self) -> str:
        return f"{self.get_role()}: {self.name} ({self.user_id})"


class Rider(User, Observer):
    """Rider class - can request trips and observe their status"""
    def __init__(self, user_id: str, name: str, email: str, phone: str):
        super().__init__(user_id, name, email, phone)
        self.trip_history: List[int] = []  # List of trip IDs
        self.current_trip: Optional['Trip'] = None
        self.payment_methods: List[str] = []
    
    def get_role(self) -> str:
        return "Rider"
    
    def request_trip(self, pickup: str, destination: str, strategy_name: str) -> 'Trip':
        """Request a new trip"""
        from trip_management import Trip
        trip = Trip(
            pickup=pickup,
            destination=destination,
            rider=self,
            strategy_name=strategy_name
        )
        trip.attach(self)  # Rider observes their own trip
        self.current_trip = trip
        return trip
    
    def update(self, trip: 'Trip', old_state: TripState, new_state: TripState) -> None:
        """Observer method - called when trip state changes"""
        print(f"[Rider {self.name}] Trip {trip.trip_id} changed: {old_state.value} → {new_state.value}")
        
        if new_state in [TripState.COMPLETED, TripState.CANCELLED]:
            if trip.trip_id:
                self.trip_history.append(trip.trip_id)
            self.current_trip = None
    
    def add_payment_method(self, payment_method: str) -> None:
        """Add a payment method"""
        self.payment_methods.append(payment_method)


class Driver(User, Observer):
    """Driver class - can accept trips and observe their status"""
    def __init__(self, user_id: str, name: str, email: str, phone: str, 
                 vehicle_type: str, license_plate: str):
        super().__init__(user_id, name, email, phone)
        self.vehicle_type = vehicle_type
        self.license_plate = license_plate
        self.is_available = True
        self.current_location: Optional[tuple] = None  # (lat, lon)
        self.trip_history: List[int] = []
        self.current_trip: Optional['Trip'] = None
        self.rating = 5.0
        self.total_trips = 0
    
    def get_role(self) -> str:
        return "Driver"
    
    def accept_trip(self, trip: 'Trip') -> bool:
        """Accept a trip request"""
        if not self.is_available:
            return False
        
        trip.attach(self)  # Driver observes the trip
        self.current_trip = trip
        self.is_available = False
        trip.accept(self)
        return True
    
    def decline_trip(self, trip: 'Trip') -> None:
        """Decline a trip request"""
        trip.decline()
    
    def complete_trip(self) -> None:
        """Mark current trip as completed"""
        if self.current_trip:
            self.current_trip.complete()
    
    def update(self, trip: 'Trip', old_state: TripState, new_state: TripState) -> None:
        """Observer method - called when trip state changes"""
        print(f"[Driver {self.name}] Trip {trip.trip_id} changed: {old_state.value} → {new_state.value}")
        
        if new_state in [TripState.COMPLETED, TripState.CANCELLED]:
            if trip.trip_id:
                self.trip_history.append(trip.trip_id)
                self.total_trips += 1
            self.current_trip = None
            self.is_available = True
    
    def set_location(self, lat: float, lon: float) -> None:
        """Update driver's current location"""
        self.current_location = (lat, lon)