from src.data import db
from src.models.ride_model import Ride
from src.models.driver_location_model import DriverLocation
from datetime import datetime

def create_new_ride(passenger_id, start_lat, start_lon):
    new_ride = Ride(passenger_id=passenger_id, start_location_lat=start_lat, start_location_lon=start_lon)
    db.session.add(new_ride)
    db.session.commit()
    return new_ride

def get_ride_by_id(ride_id):
    return Ride.query.get(ride_id)

def update_driver_location(driver_id, latitude, longitude):
    driver_loc = DriverLocation.query.filter_by(driver_id=driver_id).first()
    if driver_loc:
        driver_loc.latitude = latitude
        driver_loc.longitude = longitude
    else:
        driver_loc = DriverLocation(driver_id=driver_id, latitude=latitude, longitude=longitude)
        db.session.add(driver_loc)
    db.session.commit()
    return driver_loc

def get_driver_location_by_id(driver_id):
    return DriverLocation.query.filter_by(driver_id=driver_id).first()

def get_available_offers():
    # Cette fonction simule la récupération d'offres de courses disponibles.
    # En réalité, cela impliquerait une logique plus complexe pour filtrer
    # les courses en attente, les attribuer aux chauffeurs à proximité, etc.
    # Pour l'instant, nous retournons une liste de courses en statut 'pending'.
    pending_rides = Ride.query.filter_by(status='pending').all()
    offers = []
    for ride in pending_rides:
        offers.append({
            "ride_id": ride.id,
            "passenger_id": ride.passenger_id,
            "start_location": {
                "latitude": ride.start_location_lat,
                "longitude": ride.start_location_lon
            },
            "status": ride.status,
            "created_at": ride.created_at.isoformat()
        })
    return offers

def get_client_location_for_ride(ride_id):
    ride = get_ride_by_id(ride_id)
    if ride:
        return {
            "latitude": ride.start_location_lat,
            "longitude": ride.start_location_lon
        }
    return None
