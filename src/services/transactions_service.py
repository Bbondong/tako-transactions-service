from src.models.ride_model import db, Ride
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
