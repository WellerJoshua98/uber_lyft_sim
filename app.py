from flask import Flask
from sim_ui.rider_home import rider_home

app = Flask(__name__)
app.register_blueprint(rider_home)

if __name__ == "__main__":
    app.run(debug=True)