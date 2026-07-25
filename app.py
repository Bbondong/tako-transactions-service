from flask import Flask
from src.models.ride_model import db as ride_db
from src.models.driver_location_model import db as driver_location_db
from src.routes.transactions_routes import transactions_bp

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "mysql+mysqlconnector://user:password@db/transactions_db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

ride_db.init_app(app)
driver_location_db.init_app(app)

app.register_blueprint(transactions_bp)

if __name__ == "__main__":
    with app.app_context():
        ride_db.create_all()
        driver_location_db.create_all()
    app.run(host="0.0.0.0", port=5002)
