from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "mysql+mysqlconnector://user:password@db/transactions_db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

class Ride(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    passenger_id = db.Column(db.Integer, nullable=False)
    driver_id = db.Column(db.Integer, nullable=True)
    start_location_lat = db.Column(db.Float, nullable=False)
    start_location_lon = db.Column(db.Float, nullable=False)
    end_location_lat = db.Column(db.Float, nullable=True)
    end_location_lon = db.Column(db.Float, nullable=True)
    status = db.Column(db.String(50), default="pending") # pending, accepted, in_progress, completed, cancelled
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<Ride {self.id} - {self.status}>"

class DriverLocation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    driver_id = db.Column(db.Integer, nullable=False, unique=True)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<DriverLocation Driver:{self.driver_id} Lat:{self.latitude} Lon:{self.longitude}>"

@app.route("/", methods=["GET"])
def health_check():
    return jsonify({"status": "Transactions service is up and running!"}), 200

@app.route("/rides", methods=["POST"])
def create_ride():
    data = request.get_json()
    passenger_id = data.get("passenger_id")
    start_lat = data.get("start_location_lat")
    start_lon = data.get("start_location_lon")

    if not all([passenger_id, start_lat, start_lon]):
        return jsonify({"message": "Missing ride details"}), 400

    new_ride = Ride(passenger_id=passenger_id, start_location_lat=start_lat, start_location_lon=start_lon)
    db.session.add(new_ride)
    db.session.commit()

    return jsonify({"message": "Ride created successfully", "ride_id": new_ride.id}), 201

@app.route("/rides/<int:ride_id>", methods=["GET"])
def get_ride(ride_id):
    ride = Ride.query.get(ride_id)
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

@app.route("/driver_location", methods=["POST"])
def update_driver_location():
    data = request.get_json()
    driver_id = data.get("driver_id")
    latitude = data.get("latitude")
    longitude = data.get("longitude")

    if not all([driver_id, latitude, longitude]):
        return jsonify({"message": "Missing driver location details"}), 400

    driver_loc = DriverLocation.query.filter_by(driver_id=driver_id).first()
    if driver_loc:
        driver_loc.latitude = latitude
        driver_loc.longitude = longitude
    else:
        driver_loc = DriverLocation(driver_id=driver_id, latitude=latitude, longitude=longitude)
        db.session.add(driver_loc)
    db.session.commit()

    return jsonify({"message": "Driver location updated successfully"}), 200

@app.route("/driver_location/<int:driver_id>", methods=["GET"])
def get_driver_location(driver_id):
    driver_loc = DriverLocation.query.filter_by(driver_id=driver_id).first()
    if not driver_loc:
        return jsonify({"message": "Driver location not found"}), 404
    return jsonify({
        "driver_id": driver_loc.driver_id,
        "latitude": driver_loc.latitude,
        "longitude": driver_loc.longitude,
        "timestamp": driver_loc.timestamp.isoformat()
    }), 200


if __name__ == "__main__":
    with app.app_context():
        db.create_all() # Crée les tables si elles n'existent pas
    app.run(host="0.0.0.0", port=5002)
