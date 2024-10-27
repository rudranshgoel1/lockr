from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, abort
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import IntegrityError
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user, login_required
from werkzeug.utils import secure_filename
import os

app = Flask(__name__, template_folder="templates")

UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///newdb1.sqlite"
app.config["SECRET_KEY"] = "super_secret_key"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class Users(db.Model, UserMixin):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(250), nullable=False)
    email = db.Column(db.String(250), unique=True, nullable=False)
    password = db.Column(db.String(250), nullable=False)



def get_user_name(id):
    user = Users.query.get(id)
    if user:
        return user.name
    return None

def get_email(id):
    user = Users.query.get(id)
    if user:
        return user.email
    return None

@login_manager.user_loader
def load_user(user_id):
    return Users.query.get(int(user_id))

# Routes -----------------------------------------------------------------------
@app.route('/', methods=['GET', 'POST'])
def home():
    if request.method == 'POST':
        if 'file' not in request.files:
            return redirect(request.url)
        file = request.files['file']
        if file.filename == '':
            return redirect(request.url)
        if file:
            filename = secure_filename(file.filename)
            file.save(os.path.join(f'static/uploads/{current_user.id}', filename))
            return redirect(url_for('uploads'))
    else:
        if current_user.is_authenticated:
            user_name = get_user_name(current_user.id)
            return render_template('index1.html', user_name=user_name)
        else:
            return redirect(url_for("login"))


@app.route('/uploads')
def uploads():
    user_id = current_user.id
    files = os.listdir(f'static/uploads/{current_user.id}')
    file_urls = [url_for('static', filename=f'uploads/{current_user.id}/{file}') for file in files]
    return render_template('uploads.html', files=file_urls, file_names=files, zip=zip, os=os, user_id=user_id)

@app.route("/logout")
def logout():
    logout_user()
    return redirect(url_for("login"))


@app.route('/register', methods=["GET", "POST"])
def register():
    error = None
    if request.method == "POST":
        email = Users.query.filter_by(email=request.form.get("email")).first()
        if email is None:
            user = Users(name=request.form.get("name"), email=request.form.get(
                "email"), password=request.form.get("password"))
            db.session.add(user)
            db.session.commit()
            return redirect("/login")
        else:
            error = "Email Already Exists"
    return render_template("register.html", error=error)

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        email = Users.query.filter_by(email=request.form.get("email")).first()
        if email is None:
            error = "Invalid Email"
        elif email.password == request.form.get("password"):
            login_user(email)
            error = "Successfully Logged In"
            if os.path.exists(os.path.join(os.getcwd(), 'static', 'uploads', f'{current_user.id}')) == False:
                os.makedirs(f'static/uploads/{current_user.id}')
            return redirect(url_for('home'))
        else:
            error = "Wrong Password. <a href='/forgot'>Forgot Password?</a>"
    return render_template("login.html", error=error)
