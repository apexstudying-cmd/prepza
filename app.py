import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv

load_dotenv()  # reads variables from .env file

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    year = db.Column(db.Integer, nullable=True)      # e.g. 1, 2, 3, 4
    semester = db.Column(db.Integer, nullable=True)  # e.g. 1 or 2

    def __repr__(self):
        return f"<User {self.email}>"


@app.route("/")
def home():
    return "Prepza is alive!"


@app.route("/db-check")
def db_check():
    try:
        count = User.query.count()
        return f"Database connected! Current user count: {count}"
    except Exception as e:
        return f"Database connection failed: {str(e)}"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
