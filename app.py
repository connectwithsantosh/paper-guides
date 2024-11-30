import os
from dotenv import load_dotenv
from flask import Flask, render_template, redirect, url_for, flash, request, jsonify, send_from_directory, Response
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User
from datetime import datetime
import base64
import subprocess
import random 
import time

# We are importing all the required functions from the following files inorder to make a huge app file?

# Not the best way to put everything in one single file but, whaterver
from paperGuidesDB import *
from config import *
from logHandler import getCustomLogger

# Load environment variables from .env file

load_dotenv('.env')

app = Flask(__name__)


# Replace hardcoded values with environment variables
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('SQLALCHEMY_DATABASE_URI')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = os.getenv('SQLALCHEMY_TRACK_MODIFICATIONS', default=False)

TURNSTILE_SECRET_KEY = os.getenv('TURNSTILE_SECRET_KEY')

db.init_app(app)

# Initialize custom logger
logger = getCustomLogger(__name__)

# path for the config
configPath = './configs/config.json'
config = loadConfig(configPath)


# Initialize Flask-Login
login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)


migrate = Migrate(app, db)

createDatabase()
# Create the database 
with app.app_context():
    db.create_all()

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/')
def index():
    logger.info('Home page accessed' + ' IP: ' + str(getClientIp()))
    return render_template('index.html')


"""
These routes handle the question papers list and link all the questions in a neat way

allows papole that run wget / curl to spider the site easily and get the data

Maybe in the future there will be a API endpoint to get the data or maybe even database dump torrent?

This part may not require rewrites
"""

@app.route('/levels')
def getLevels():
    logger.info('Levels page accessed' + ' IP: ' + str(getClientIp()))
    config = loadConfig(configPath)
    return render_template('levels.html',config=config )

@app.route('/subjects/<level>')
def getLevelSubjects(level):
    logger.info(f'Subjects page accessed for level {level}' + ' IP: ' + str(getClientIp()))
    config = loadConfig(configPath)
    return render_template('subject.html', config = config, level = level)


@app.route('/subjects/<level>/<subject_name>')
def getSubjectYears(level, subject_name):
    logger.info(f'Years page accessed for level {level}, subject {subject_name}' + ' IP: ' + str(getClientIp()))
    years = getYears(level,subject_name)
    return render_template('years.html', subject_name = subject_name, level = level, years = years)


@app.route('/subjects/<level>/<subject_name>/<year>')
def getSubjectQuestions(level ,subject_name, year):
    logger.info(f'Questions page accessed for level {level}, subject {subject_name}, year {year}' + ' IP: ' + str(getClientIp()))
    question_name = getQuestions(level, subject_name, year)
    return render_template('questions.html', questions_name = question_name, year = year, config = config, level = level )


@app.route('/subjects/<level>/<subject_name>/<year>/<path:file_data>')
def renderSubjectQuestion(level, subject_name, year, file_data):
    logger.info(f'Question rendered for level {level}, subject {subject_name}, year {year}, file {file_data}' + ' IP: ' + str(getClientIp()))
    
    # Ensure `file_data` is properly decoded
    component = file_data.split(', ')[1]
    full_year = file_data.split('Year: ')[1].split(' question')[0]
    question = renderQuestion(level, subject_name, full_year, component)
    return render_template('qp.html', question=question[0], solution= question[1], file_data=file_data, id=question[2], config=config)



# Reders the about page. Duh

@app.route('/about')
def about():
    logger.info('About page accessed' + ' IP: ' + str(getClientIp()))
    return render_template('about.html')



# This is the route to the question genreation page where the user selects their desired questions

@app.route('/question-generator')
def questionGenerator():
    logger.info('Question generator page accessed' + ' IP: ' + str(getClientIp()))
    config = loadConfig(configPath)
    return render_template('question-generator.html', config = config)

# This route displays the questions the uppper route genetated a diffrent page and route
@app.route('/question-gen', methods=['POST', 'GET'])
def questionGen():
    logger.info('Question generation initiated' + ' IP: ' + str(getClientIp()))
    if request.method == 'POST':
        try:
            # Extract form data
            board = request.form.get('board')
            subject = request.form.get('subject')
            level = request.form.get('level')
            topics = request.form.getlist('topic')
            difficulties = request.form.getlist('difficulty')
            components = request.form.getlist('component')

            # Handle ALL selections
            if 'ALL' in topics:
                topics = 'ALL'
            else:
                topics = [topic for topic in topics]

            if 'ALL' in difficulties:
                difficulties = 'ALL'
            else:
                difficulties = [difficulty for difficulty in difficulties]

            if 'ALL' in components:
                components = 'ALL'
            else:
                components = [component for component in components]

            # Get questions
            rows = getQuestionsForGen(board, subject, level, topics, components, difficulties)
            return render_template('qpgen.html', rows=rows)
        except Exception as e:
            logger.error(f'Error in question generation: {str(e)}' + ' IP: ' + str(getClientIp()))
            return redirect(url_for('questionGenerator'))
    else:
        return redirect(url_for('questionGenerator'))

        
@app.route('/submit')
def submit():
    logger.info('Submit page accessed' + ' IP: ' + str(getClientIp()))
    config = loadConfig(configPath)
    return render_template('submit.html', config = config, year = int(datetime.now().year))


@app.route('/model-questions')
def modelQuestions():
    logger.info('Model questions page accessed' + ' IP: ' + str(getClientIp()))
    return render_template('model-questions.html')

@app.route('/support')
def support():
    logger.info('Support page accessed' + ' IP: ' + str(getClientIp()))
    return render_template('support.html')

@app.route('/contact')
def contact():
    logger.info('Contact page accessed' + ' IP: ' + str(getClientIp()))
    return render_template('contact.html')



@app.route('/submitQuestion', methods=['POST'])
@login_required
def submitQuestion():

    # Get the Turnstile token from the form submission
    turnstileToken = request.form.get("cf-turnstile-response")
    if not turnstileToken:
        logger.warning('Turnstile token missing' + ' IP: ' + str(getClientIp()))
        return render_template('captcha-error.html', error_title = "Did you forget the captcha!?", error_message = "Please try again by completing the captcha."), 400

    # Verify the token with enhanced verification
    verificationResult = verifyTurnstile(turnstileToken)
    
    # Check verification success
    if not verificationResult.get("success"):
        logger.warning(
            f'Failed Turnstile verification. '
            f'Errors: {verificationResult.get("error-codes", [])} '
            f'Attempts: {verificationResult.get("attempts", 1)}' + 
            ' IP: ' + str(getClientIp())
        )
        return render_template('captcha-error.html', error_title = "Failed to verify captcha.", error_message = f"Please try again. {verificationResult.get('message', 'Unknown error')}"), 403
    
    
    logger.info('Question submission initiated' + ' IP: ' + str(getClientIp()))
    board = request.form.get('board')
    subject = request.form.get('subject')
    topic = request.form.get('topic')
    difficulty = request.form.get('difficulty')
    level = request.form.get('level')
    component = request.form.get('component')
    questionFile = request.files['questionFile'].read()
    solutionFile = request.files['solutionFile'].read()


    if insertQuestion(board, subject, topic, difficulty, level, component, questionFile, solutionFile, current_user.username, getClientIp()):
        logger.info('Question submitted successfully' + ' IP: ' + str(getClientIp()))
        return redirect(url_for('index'))
    else:
        logger.error('Error occurred while submitting question' + ' IP: ' + str(getClientIp()))
        return "Error occurred while submitting question", 500

@app.route('/submitPaper', methods=['POST'])
@login_required
def submitPaper():

    # Get the Turnstile token from the form submission
    turnstileToken = request.form.get("cf-turnstile-response")
    if not turnstileToken:
        logger.warning('Turnstile token missing' + ' IP: ' + str(getClientIp()))
        return render_template('captcha-error.html', error_title = "Did you forget the captcha!?", error_message = "Please try again by completing the captcha."), 400
        
    # Verify the token with enhanced verification
    verificationResult = verifyTurnstile(turnstileToken)
    
    # Check verification success
    if not verificationResult.get("success"):
        logger.warning(
            f'Failed Turnstile verification. '
            f'Errors: {verificationResult.get("error-codes", [])} '
            f'Attempts: {verificationResult.get("attempts", 1)}' + 
            ' IP: ' + str(getClientIp())
        )
        return render_template('captcha-error.html', error_title = "Failed to verify captcha.", error_message = f"Please try again. {verificationResult.get('message', 'Unknown error')}"), 403
        

    logger.info('Paper submission initiated' + ' IP: ' + str(getClientIp()))
    try:
        board = request.form.get('board')
        subject = request.form.get('subject')
        year = request.form.get('year')
        session = request.form.get('session')
        level = request.form.get('level')
        component = request.form.get('component')
        questionFile = request.files['questionFile'].read()
        solutionFile = request.files['solutionFile'].read()
        paper_type = request.form.get('paper_type')

        if not all([board, subject, level, component, questionFile, paper_type]):
            raise ValueError("Missing required fields")

        # Format year with session for A Levels
        if board == "A Levels" and session:
            # Convert session values to display format
            session_display = {
                "specimen": "Specimen",
                "feb-mar": "Feb / Mar",
                "may-june": "May / June",
                "oct-nov": "Oct / Nov"
            }
            formatted_year = f"{year} ({session_display.get(session, session)})"
        else:
            formatted_year = year

        if paper_type == 'yearly':
            if not year:
                raise ValueError("Year is required for yearly papers")
            result , uuid= insertPaper(board, subject, formatted_year, level, component, questionFile, solutionFile, current_user.username, getClientIp())
        elif paper_type == 'topical':
            result = insertTopical(board, subject, questionFile, solutionFile, current_user.username, getClientIp())
        else:
            raise ValueError(f"Invalid paper type: {paper_type}")

        if result:
            logger.info('Paper submitted successfully' + ' IP: ' + str(getClientIp()))
            if current_user.role == 'admin':
                if approvePaper(uuid)[1] == 400:
                    return redirect(f'admin/paper/{uuid}')
            return redirect(url_for('index'))
        else:
            raise Exception("Insert operation failed")
    except Exception as e:
        logger.error(f'Error in paper submission: {str(e)}' + ' IP: ' + str(getClientIp()))
        return f"Error occurred while submitting paper: {str(e)}", 500



"""
This functionality for the user login and authentication will be implemented later so this part of the code has been commented.

This allows for more functionalities for uploading user submitted data and allowing users to post ratings for the questions.

"""


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':

        # Get the Turnstile token from the form submission
        turnstileToken = request.form.get("cf-turnstile-response")
        if not turnstileToken:
            logger.warning('Turnstile token missing' + ' IP: ' + str(getClientIp()))
            return render_template('captcha-error.html', error_title = "Did you forget the captcha!?", error_message = "Please try again by completing the captcha."), 400

        # Verify the token with enhanced verification
        verificationResult = verifyTurnstile(turnstileToken)
        
        # Check verification success
        if not verificationResult.get("success"):
            logger.warning(
                f'Failed Turnstile verification. '
                f'Errors: {verificationResult.get("error-codes", [])} '
                f'Attempts: {verificationResult.get("attempts", 1)}' + 
                ' IP: ' + str(getClientIp())
            )
            return render_template('captcha-error.html', error_title = "Failed to verify captcha.", error_message = f"Please try again. {verificationResult.get('message', 'Unknown error')}"), 403
        
        username_or_email = request.form.get('username')
        password = request.form.get('password')

        # Check if input is an email
        if '@' in username_or_email:
            user = User.query.filter_by(email=username_or_email).first()
        else:
            user = User.query.filter_by(username=username_or_email).first()

        # Check if user exists and the password matches
        if user and check_password_hash(user.password, password):
            login_user(user)
            logger.info(f'User {user.username} logged in' + ' IP: ' + str(getClientIp()))
            next_page = request.args.get('next')
            return redirect(next_page or url_for('index'))
        else:
            logger.warning(f'Failed login attempt for {username_or_email}' + ' IP: ' + str(getClientIp()))
            flash('Login unsuccessful. Please check your credentials.', 'danger')

    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        # Get the Turnstile token from the form submission
        turnstileToken = request.form.get("cf-turnstile-response")
        if not turnstileToken:
            logger.warning('Turnstile token missing' + ' IP: ' + str(getClientIp()))
            return render_template('captcha-error.html', error_title = "Did you forget the captcha!?", error_message = "Please try again by completing the captcha."), 400

        # Verify the token with enhanced verification
        verificationResult = verifyTurnstile(turnstileToken)
        
        # Check verification success
        if not verificationResult.get("success"):
            logger.warning(
                f'Failed Turnstile verification. '
                f'Errors: {verificationResult.get("error-codes", [])} '
                f'Attempts: {verificationResult.get("attempts", 1)}' + 
                ' IP: ' + str(getClientIp())
            )
            return render_template('captcha-error.html', error_title = "Failed to verify captcha.", error_message = f"Please try again. {verificationResult.get('message', 'Unknown error')}"), 403
    
        username = request.form.get('new-username')
        password = request.form.get('new-password')
        email = request.form.get('new-email')

        # Check if username or email already exists
        existing_user = User.query.filter((User.username == username) | (User.email == email)).first()
        if existing_user:
            flash('Username or email already exists. Please choose another.', 'danger')
        else:
            # Hash the password before storing it
            hashed_password = generate_password_hash(password)

            # Create new user with hashed password
            new_user = User(username=username, password=hashed_password, email=email)
            db.session.add(new_user)
            db.session.commit()

            flash('Account created successfully! You can now log in.', 'success')
            return redirect(url_for('login'))

    return render_template('login.html')


# Will profiles even be a thing ? Public IDK but chaning the email password will be implemented

@app.route('/profile')
@login_required
def profile():

    try:
        user = current_user
        logger.info(f'User {user.username} accessed profile' + ' IP: ' + str(getClientIp()))
    except Exception as e:
        logger.error(f'Error in profile: {str(e)}' + ' IP: ' + str(getClientIp()))
    return render_template('profile.html')

@app.route('/change-password', methods=['POST'])
def changePassword():
    try:
        previous_password = request.form.get('current-password')
        new_password = request.form.get('new-password')
        
        if check_password_hash(current_user.password, previous_password):
            # Hash the password before storing it
            hashed_password = generate_password_hash(new_password)
            
            # Update the user's password
            current_user.password = hashed_password
            db.session.commit()
            
            logger.info(f'User {current_user.username} changed password' + ' IP: ' + str(getClientIp()))
            
            return redirect(url_for('logout'))
        else:
            logger.warning(f'Failed to change password for user {current_user.username}' + ' IP: ' + str(getClientIp()))
            flash('Current password is incorrect.', 'error')
        
        return redirect(url_for('profile'))
    
    except Exception as e:
        logger.error(f'Error in changing password: {str(e)}' + ' IP: ' + str(getClientIp()))
        flash('An error occurred while changing password.', 'error')
        return redirect(url_for('profile'))     
    
    
# @app.route('/rate/<question_UUID>/<int:rating>', methods = ['POST'])
# @login_required
# def rate(question_UUID, rating):
#     try:
#         user = current_user.id
#         if giveRating(user, question_UUID, rating):
#             logger.info(f'User {user} rated question {question_UUID} with {rating}' + ' IP: ' + str(getClientIp()))
#             return True
#         else:
#             logger.warning(f'Failed to rate question {question_UUID}' + ' IP: ' + str(getClientIp()))
#             return False
#     except Exception as e:
#         logger.error(f'Error in rating: {str(e)}' + ' IP: ' + str(getClientIp()))
#         return False



# Update /admin route to send only UUIDs and hashes

@app.route('/admin')
@login_required
def admin_dashboard():
    if current_user.role != 'admin':
        logger.warning(f'Unauthorized access attempt by user: {current_user.username}')
        return redirect(url_for('index'))

    try:
        questions = get_unapproved_questions()
        papers = get_unapproved_papers()

        data = {
            "questions": [],
            "papers": []
        }

        for question in questions:
            data["questions"].append({
                "id": question["id"],
                "uuid": question["uuid"],
                "questionFileHash": getHash(question["questionFile"]),
                "solutionFileHash": getHash(question["solutionFile"]),
                "questionBlob": "none",
                "solutionBlob": "none",
            })

        for paper in papers:
            data["papers"].append({
                "id": paper["id"],
                "uuid": paper["uuid"],
                "questionFileHash": getHash(paper["questionFile"]),
                "solutionFileHash": getHash(paper["solutionFile"]),
                "questionBlob": "none",
                "solutionBlob": "none",
            })

        logger.info('Data sent to the admin page successfully')
        return render_template('admin.html', data=data)

    except Exception as e:
        logger.error(f'Error retrieving unapproved questions or papers: {e}')
        return render_template('admin.html', data={"error": "An error occurred while retrieving data."})

@app.route('/admin/question/<uuid>', methods=['GET'])
def adminShowQuestion(uuid):
    if current_user.role != 'admin':
        logger.warning(f'Unauthorized access attempt by user: {current_user.username} from IP: ', getClientIp())
        return redirect(url_for('index'))
    
    try:
        logger.info(f'Question page addessed for paper {uuid} By: {current_user.username} with role: {current_user.role} IP: ' + str(getClientIp()))
        return render_template('admin-question.html', question=get_question(uuid))
    except Exception as e:
        logger.warning("Error retrieving question: " + str(e))

@app.route('/admin/paper/<uuid>', methods=['GET'])
def adminShowPaper(uuid):
    if current_user.role != 'admin':
        logger.warning(f'Unauthorized access attempt by user: {current_user.username} from IP: ', getClientIp())
        return redirect(url_for('index'))
    try:
        logger.info(f'Paper page addessed for paper {uuid} By: {current_user.username} with role: {current_user.role} IP: ' + str(getClientIp()))
        return render_template('admin-paper.html', paper=get_paper(uuid))
    except Exception as e:
        logger.warning("Error retrieving paper: " + str(e))

@app.route('/getNewData', methods=["POST"])
@login_required
def getNewData():
    if current_user.role != 'admin':
        logger.warning('Admin page / endpoint is trying to be accessed by a non-admin' + ' IP: ' + str(getClientIp()))
        logger.warning(f'Unauthorized access attempt by user: {current_user.username}')
        return redirect(url_for('index'))

    try:
            questions = get_unapproved_questions()
            papers = get_unapproved_papers()

            data = {
                "questions": [],
                "papers": []
            }

            for question in questions:
                data["questions"].append({
                    "id": question["id"],
                    "uuid": question["uuid"],
                    "subject": question["subject"],
                    "topic": question["topic"],
                    "difficulty": question["difficulty"],
                    "board": question["board"],
                    "level": question["level"],
                    "component": question["component"],
                    "submittedBy": question["submittedBy"],
                    "submittedOn": question["submitDate"]
                })

            for paper in papers:
                data["papers"].append({
                    "id": paper["id"],
                    "uuid": paper["uuid"],
                    "subject": paper["subject"],
                    "year": paper["year"],
                    "board": paper["board"],
                    "level": paper["level"],
                    "component": paper["component"],
                    "submittedBy": paper["submittedBy"],
                    "submittedOn": paper["submitDate"]
                })

            return jsonify(data)
    except Exception as e:
        logger.error(f'Error processing getNewData: {e}')
        return jsonify({"error": "An error occurred while processing the request."}),

@app.route('/approve_question/<uuid>' , methods=["POST"])
@login_required
def approve(uuid):
    if current_user.role != 'admin':
        logger.warning('Admin page / endpoint is trying to be accessed by a non-admin' + ' IP: ' + str(getClientIp()))
        flash('Access denied. Administrator privileges required.', 'error')
        return redirect(url_for('index'))

    if approve_question(current_user.username, uuid):
        return jsonify({"message": "Your request was processed successfully"})
    else:
        return jsonify({"error": "Your request was not processed successfully"})

@app.route('/approve_paper/<uuid>', methods=["GET", "POST"])
@login_required
def approvePaper(uuid):
    if current_user.role != 'admin':
        logger.warning(
            f"Admin page / endpoint is trying to be accessed by a non-admin user. IP: {getClientIp()}"
        )
        return redirect(url_for('index'))

    if approve_paper(current_user.username, uuid):
        logger.info(f"Paper {uuid} was approved by {current_user.username}")
        # Returning plain text for success with a 200 status
        return f"Paper {uuid} was approved by {current_user.username}", 200
    else:
        logger.error(f"Paper {uuid} was unable to be approved by {current_user.username}")
        return f"Paper {uuid} was unable to be approved", 400



@app.route('/delete_question/<uuid>', methods=["POST"])
@login_required
def deleteQuestion(uuid):
    if current_user.role != 'admin':
        logger.warning('Admin page / endpoint is trying to be accessed by a non-admin' + ' IP: ' + str(getClientIp()))
        flash('Access denied. Administrator privileges required.', 'error')
        return redirect(url_for('index'))

    if delete_question(uuid):
        return jsonify({"success": "Your request was processed successfully"}), 200
    else:
        return jsonify({"error": "Your request was not processed successfully"}), 304
    

@app.route('/delete_paper/<uuid>', methods=["POST"])
@login_required
def deletePaper(uuid):
    if current_user.role != 'admin':
        logger.warning('Admin page / endpoint is trying to be accessed by a non-admin' + ' IP: ' + str(getClientIp()))
        flash('Access denied. Administrator privileges required.', 'error')
        return redirect(url_for('index'))

    if delete_paper(uuid):
        return jsonify({"success": "Your request was processed successfully"}), 200
    else:
        return jsonify({"error": "Your request was not processed successfully"}), 304

# Temporary solution man
# A route to give admin access to user accounts
@app.route('/admin/give_admin/<username>', methods=['POST'])
def give_admin(username):
    if current_user.role != 'admin':
        logger.warning('Admin page / endpoint is trying to be accessed by a non-admin' + ' IP: ' + str(getClientIp()))
        flash('Access denied. Administrator privileges required.', 'error')
        return redirect(url_for('index'))
    
    try:
        user = User.query.filter_by(username=username).first()
        if not user:
            logger.warning('User not found: ' + username)
            return jsonify({"error": "User not found"}), 404
        if user.role == 'admin':
            logger.info('User already has admin privileges: ' + username)
            return jsonify({"error": "User already has admin privileges"}), 400
        
        user.role = 'admin'
        db.session.commit()
        logger.info('Admin privileges given to user: ' + username)
        return jsonify({"message": "Admin privileges given successfully"}), 200
    except Exception as e:
        logger.error(f'Error giving admin privileges: {e}')
        return False

@app.template_filter('b64encode')
def b64encode_filter(s):
    return base64.b64encode(s).decode('utf-8') if s else ''

@app.route('/robots.txt')
def robotsTxt():
    logger.info('robots.txt accessed from' + ' IP: ' + str(getClientIp()))
    return send_from_directory(app.static_folder, 'robots.txt')

@app.route('/stats')
def stats():
    statsData = getStat(config)
    logger.info('Stats page accessed' + ' IP: ' + str(getClientIp()))
    return render_template('stats-page.html', statsData=statsData)

@app.route('/sitemap.xml')
def sitemap():
    logger.info(f'Sitemap accessed' + ' IP: ' + str(getClientIp()))
    return send_from_directory(os.path.expanduser('~/paper-guides/static'), 'sitemap.xml', mimetype='application/xml'), 200

@app.errorhandler(404)
def page_not_found(e):
    logger.warning(f'404 Not Found error' + ' IP: ' + str(getClientIp()))
    return render_template('404.html'), 404

# Define a reusable function to get the client's IP address
def getClientIp():
    # Try to get the IP from the 'X-Forwarded-For' header (Cloudflare/proxy header)
    return request.headers.get('X-Forwarded-For', request.remote_addr)


def verifyTurnstile(token, max_retries=3):
    """
    Verify Cloudflare Turnstile CAPTCHA token with robust retry mechanism.
    
    Args:
        token (str): The Turnstile response token
        max_retries (int): Maximum number of retry attempts
    
    Returns:
        dict: Verification result with 'success' and detailed error information
    """
    # Initial validation of token
    if not token or not isinstance(token, str) or len(token) > 1000:
        logger.warning('Invalid Turnstile token')
        return {
            "success": False, 
            "error-codes": ["invalid-input-token"],
            "message": "Invalid or too long token"
        }
    
    # Payload for verification
    payload = {
        "secret": TURNSTILE_SECRET_KEY,
        "response": token
    }
    
    # Retry loop with exponential backoff
    for attempt in range(max_retries):
        try:
            # Calculate exponential backoff with jitter
            if attempt > 0:
                # Exponential backoff with jitter to prevent thundering herd problem
                wait_time = (2 ** attempt) + random.uniform(0, 1)
                time.sleep(wait_time)
            
            # Make request with timeout
            response = requests.post(
                "https://challenges.cloudflare.com/turnstile/v0/siteverify", 
                data=payload,
                timeout=5  # 5-second timeout
            )
            # Raise an exception for bad HTTP responses
            response.raise_for_status()
            
            # Parse response
            result = response.json()
            
            # Successful verification
            return {
                "success": result.get("success", False),
                "error-codes": result.get("error-codes", []),
                "message": "Verification complete",
                "attempts": attempt + 1
            }
        
        except requests.exceptions.Timeout:
            logger.warning(f"Turnstile verification timed out. Attempt {attempt + 1}/{max_retries}")
            # Continue to next retry
            continue
        
        except requests.exceptions.ConnectionError:
            logger.warning(f"Network connection error. Attempt {attempt + 1}/{max_retries}")
            # Continue to next retry
            continue
        
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error in Turnstile verification: {e}")
            # For some errors, we might want to exit early
            if attempt == max_retries - 1:
                return {
                    "success": False, 
                    "error-codes": ["network-error"],
                    "message": f"Network error after {max_retries} attempts: {str(e)}",
                    "attempts": max_retries
                }
            continue
        
        except ValueError:  # JSON parsing error
            logger.error(f"Failed to parse Turnstile response. Attempt {attempt + 1}/{max_retries}")
            # Continue to next retry
            continue
    
    # If all retries fail
    logger.error("All Turnstile verification attempts failed")
    return {
        "success": False, 
        "error-codes": ["verification-failed"],
        "message": f"Failed to verify token after {max_retries} attempts",
        "attempts": max_retries
    }

if __name__ == '__main__':
    app.run(debug=True)
