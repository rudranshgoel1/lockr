from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, abort, session
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import IntegrityError
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user, login_required
from werkzeug.utils import secure_filename
import os
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

app = Flask(__name__, template_folder="templates")

UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///newdb1.sqlite"
app.config["SECRET_KEY"] = "super_secret_key"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Google Drive setup
GOOGLE_DRIVE_FOLDER_ID = "1uc1sUMU12cX6OXp4b4yk6K9oxBR0bovV"  # Replace with your Google Drive folder ID
SCOPES = ["https://www.googleapis.com/auth/drive"]
CREDENTIALS_FILE = "credentials.json"  # Path to your Google service account credentials

def get_google_drive_service():
    creds = service_account.Credentials.from_service_account_file(
        CREDENTIALS_FILE, scopes=SCOPES)
    return build("drive", "v3", credentials=creds)

def create_user_folder_if_not_exists(drive_service, user_id):
    query = f"mimeType='application/vnd.google-apps.folder' and name='{user_id}' and '{GOOGLE_DRIVE_FOLDER_ID}' in parents"

    try:
        # List the folders matching the query
        results = drive_service.files().list(q=query, fields="files(id, name)").execute()
        folders = results.get('files', [])

        if not folders:
            # Folder does not exist, create it
            folder_metadata = {
                'name': user_id,
                'mimeType': 'application/vnd.google-apps.folder',
                'parents': [GOOGLE_DRIVE_FOLDER_ID]  # Create inside the specified parent folder
            }
            folder = drive_service.files().create(body=folder_metadata, fields='id').execute()
            print(f'Folder created: {folder.get("id")}')
            return folder.get('id')
        else:
            # Folder exists
            print(f'Folder already exists: {folders[0]["id"]}')
            return folders[0]["id"]

    except HttpError as error:
        print(f'An error occurred: {error}')
        return None



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
    if not current_user.is_authenticated:
        flash("You need to log in to access this page.", "error")
        return redirect(url_for("login"))

    user_id = str(current_user.id)  # Ensure user ID is a string
    drive_service = get_google_drive_service()

    # Create a folder for the user if it does not exist
    google_folder_id = create_user_folder_if_not_exists(drive_service, user_id)
    if not google_folder_id:
        flash("Error creating or finding your folder. Please try again.", "error")
        return redirect(url_for("login"))

    if request.method == 'POST':
        if 'file' not in request.files:
            return redirect(request.url)

        file = request.files['file']
        if file.filename == '':
            return redirect(request.url)

        if file:
            filename = secure_filename(file.filename)
            local_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(local_path)
            media = MediaFileUpload(local_path, mimetype=file.content_type)

            file_metadata = {
                'name': filename,
                'parents': [google_folder_id]  # Save the file in the user's specific folder
            }

            try:
                uploaded_file = drive_service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields="id, webViewLink"
                ).execute()

                # Get shared link
                shared_link = uploaded_file.get("webViewLink")
                os.remove(local_path)

                flash("File uploaded successfully!", "success")
                return redirect(url_for('uploads'))

            except HttpError as error:
                print(f'An error occurred during file upload: {error}')
                flash("Error uploading file. Please try again.", "error")
                os.remove(local_path)  # Ensure local file is removed
                return redirect(request.url)
    else:
        user_name = get_user_name(current_user.id)
        return render_template('index1.html', user_name=user_name)




# Route for viewing uploads
@app.route('/uploads')
@login_required
def uploads():
    user_id = getattr(current_user, 'id', None)
    if not isinstance(user_id, int):
        flash("User ID is invalid. Please log in again.", "error")
        return redirect(url_for("login"))

    # Initialize Google Drive service and ensure user's folder exists
    drive_service = get_google_drive_service()
    google_folder_id = create_user_folder_if_not_exists(drive_service, str(user_id))

    # Query only files within the user's Google Drive folder
    query = f"'{google_folder_id}' in parents and mimeType contains 'image/'"  # Only fetch image files
    results = drive_service.files().list(
        q=query, fields="files(id, name, webViewLink)").execute()

    files = [(file['name'], file['webViewLink']) for file in results.get('files', [])]

    # Render template with image file data
    return render_template('uploads.html', files=files, user_id=user_id)


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

            # Create a Google Drive service instance
            drive_service = get_google_drive_service()

            # Create a folder for the user in Google Drive if it doesn't exist
            google_folder_id = create_user_folder_if_not_exists(drive_service, str(current_user.id))
            if google_folder_id is None:
                error = "Error creating your Google Drive folder. Please try again."
                # Log out the user if there was an error
                logout_user()
                return redirect(url_for("login"))

            return redirect(url_for('home'))
        else:
            error = "Wrong Password. <a href='/forgot'>Forgot Password?</a>"
    return render_template("login.html", error=error)


if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5000)

with app.app_context():
    db.create_all()
