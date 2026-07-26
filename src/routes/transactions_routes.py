from flask import Blueprint, jsonify, request
from src.services.transactions_service import create_new_ride, get_ride_by_id, update_driver_location, get_driver_location_by_id, get_available_offers, get_client_location_for_ride
from src.data import db

transactions_bp = Blueprint("transactions", __name__)

@transactions_bp.route("/", methods=["GET"])
def health_check():
    return jsonify({"status": "Transactions service is up and running!"}), 200

@transactions_bp.route("/rides", methods=["POST"])
def create_ride():
    data = request.get_json()
    passenger_id = data.get("passenger_id")
    start_lat = data.get("start_location_lat")
    start_lon = data.get("start_location_lon")

    if not all([passenger_id, start_lat, start_lon]):
        return jsonify({"message": "Missing ride details"}), 400

    new_ride = create_new_ride(passenger_id, start_lat, start_lon)
    return jsonify({"message": "Ride created successfully", "ride_id": new_ride.id}), 201

@transactions_bp.route("/rides/<int:ride_id>", methods=["GET"])
def get_ride(ride_id):
    ride = get_ride_by_id(ride_id)
    if not ride:
        return jsonify({"message": "Ride not found"}), 404
    return jsonify({
        "id": ride.id,
        "passenger_id": ride.passenger_id,
        "driver_id": ride.driver_id,
        "start_location_lat": ride.start_location_lat,
        "start_location_lon": ride.start_location_lon,
        "end_location_lat": ride.end_location_lat,
        "end_location_lon": ride.end_location_lon,
        "status": ride.status,
        "created_at": ride.created_at.isoformat(),
        "updated_at": ride.updated_at.isoformat()
    }), 200

@transactions_bp.route("/driver_location", methods=["POST"])
def update_driver_location_route():
    data = request.get_json()
    driver_id = data.get("driver_id")
    latitude = data.get("latitude")
    longitude = data.get("longitude")

    if not all([driver_id, latitude, longitude]):
        return jsonify({"message": "Missing driver location details"}), 400

    driver_loc = update_driver_location(driver_id, latitude, longitude)
    return jsonify({"message": "Driver location updated successfully"}), 200

@transactions_bp.route("/driver_location/<int:driver_id>", methods=["GET"])
def get_driver_location(driver_id):
    driver_loc = get_driver_location_by_id(driver_id)
    if not driver_loc:
        return jsonify({"message": "Driver location not found"}), 404
    return jsonify({
        "driver_id": driver_loc.driver_id,
        "latitude": driver_loc.latitude,
        "longitude": driver_loc.longitude,
        "timestamp": driver_loc.timestamp.isoformat()
    }), 200

@transactions_bp.route("/offers", methods=["GET"])
def get_offers():
    offers = get_available_offers()
    return jsonify(offers), 200

@transactions_bp.route("/client_location/<int:ride_id>", methods=["GET"])
def get_client_location(ride_id):
    location = get_client_location_for_ride(ride_id)
    if not location:
        return jsonify({"message": "Client location not found for this ride"}), 404
    return jsonify(location), 200
