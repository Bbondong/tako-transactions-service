from src.data import db
from datetime import datetime

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
