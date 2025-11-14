from flask import Flask
from db import init_db
from sim_ui.rider_home import rider_home
from sim_ui.driver_home import driver_home



def create_app():
    app = Flask(__name__)
    app.register_blueprint(rider_home)
    app.register_blueprint(driver_home, url_prefix="/driver")
    return app

if __name__ == "__main__":
    init_db()
    app = create_app()
    app.run(debug=True)