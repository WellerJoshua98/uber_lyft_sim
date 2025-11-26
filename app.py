from flask import Flask
from db import init_db
from sim_ui.rider_home import rider_home
from sim_ui.driver_home import driver_home



def create_app():
    app = Flask(__name__)
    
    # Set a secret key for session management and flash messages
    app.secret_key = 'uber_lyft_sim_secret_key_2025'  # In production, use a more secure random key
    
    app.register_blueprint(rider_home)
    app.register_blueprint(driver_home, url_prefix="/driver")
    return app

if __name__ == "__main__":
    init_db()
    app = create_app()
    app.run(debug=True)