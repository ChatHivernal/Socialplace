import os
import html
from functools import wraps
from flask_login import UserMixin
import re
import base64
import hashlib
import secrets
import requests
from mutagen.mp3 import MP3
from flask import Response, Flask, render_template, request, redirect, url_for, flash, jsonify, abort, session, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
from PIL import Image, ImageDraw
import bcrypt
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo
from cryptography.fernet import Fernet
from flask import g
from datetime import timedelta
from sqlalchemy import func

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
STATIC_DIR = os.path.join(BASE_DIR, 'static')
INSTANCE_DIR = os.path.join(BASE_DIR, 'instance')
USB_MOUNT = '/media/usb'
UPLOADS_BASE = os.path.join(USB_MOUNT, 'uploads')
PROFILE_UPLOAD_FOLDER = os.path.join(UPLOADS_BASE, 'profiles')
POST_UPLOAD_FOLDER = os.path.join(UPLOADS_BASE, 'posts')

if not os.path.exists(USB_MOUNT):
    PROFILE_UPLOAD_FOLDER = os.path.join(STATIC_DIR, 'uploads', 'profiles')
    POST_UPLOAD_FOLDER = os.path.join(STATIC_DIR, 'uploads', 'posts')

os.makedirs(PROFILE_UPLOAD_FOLDER, exist_ok=True)
os.makedirs(POST_UPLOAD_FOLDER, exist_ok=True)
os.makedirs(INSTANCE_DIR, exist_ok=True)

def create_default_avatar():
    default_path = os.path.join(STATIC_DIR, 'images', 'default', 'default_avatar.png')
    uploads_path = os.path.join(PROFILE_UPLOAD_FOLDER, 'default.png')
    if not os.path.exists(default_path):
        os.makedirs(os.path.dirname(default_path), exist_ok=True)
        img = Image.new('RGB', (200, 200), color=(255, 107, 53))
        draw = ImageDraw.Draw(img)
        draw.ellipse([50, 50, 150, 150], fill=(255, 209, 102))
        draw.ellipse([80, 80, 95, 95], fill=(0, 0, 0))
        draw.ellipse([105, 80, 120, 95], fill=(0, 0, 0))
        draw.arc([75, 100, 125, 130], 0, 180, fill=(0, 0, 0), width=3)
        img.save(default_path)
        img.save(uploads_path)

create_default_avatar()

def get_valid_profile_pic(user):
    if not user.profile_pic:
        return 'default.png'
    filepath = os.path.join(app.config['PROFILE_UPLOAD_FOLDER'], user.profile_pic)
    if not os.path.exists(filepath):
        return 'default.png'
    return user.profile_pic

def get_audio_duration(filename):
    try:
        file_path = os.path.join(app.config['POST_UPLOAD_FOLDER'], filename)
        audio_info = MP3(file_path)
        return audio_info.info.length
    except Exception:
        return 0

def is_scratch_url(url):
    if not url:
        return False
    patterns = [
        r'scratch\.mit\.edu/projects/\d+',
        r'scratch\.mit\.edu/projects/\d+/embed',
    ]
    for p in patterns:
        if re.search(p, url):
            return True
    return False

def extract_scratch_id(url):
    if not url:
        return None
    match = re.search(r'projects/(\d+)', url)
    return match.group(1) if match else None


app = Flask(__name__)
app.config['SECRET_KEY'] = 'votre-clee'
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{os.path.join(INSTANCE_DIR, "socialplace.db")}'
app.config['PROFILE_UPLOAD_FOLDER'] = PROFILE_UPLOAD_FOLDER
app.config['POST_UPLOAD_FOLDER'] = POST_UPLOAD_FOLDER
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'mp4', 'webm', 'mov', 'mp3', 'zip'}
app.config['TURNSTILE_SITE_KEY'] = 'votre-clee'
app.config['TURNSTILE_SECRET_KEY'] = 'votre-clee'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

def get_fernet():
    key = hashlib.sha256(app.config['SECRET_KEY'].encode()).digest()
    fernet_key = base64.urlsafe_b64encode(key)
    return Fernet(fernet_key)

def encrypt_content(plain_text):
    return get_fernet().encrypt(plain_text.encode()).decode()

def decrypt_content(encrypted_text):
    return get_fernet().decrypt(encrypted_text.encode()).decode()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.Text, nullable=False)
    email_hash = db.Column(db.String(64), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    is_verified = db.Column(db.Boolean, default=False)
    profile_pic = db.Column(db.String(200), default='default.png')
    bio = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    scratch_username = db.Column(db.String(100), nullable=True)
    scratch_profile_url = db.Column(db.String(300), nullable=True)

    posts = db.relationship('Post', backref='author', cascade='all, delete-orphan')
    comments = db.relationship('Comment', backref='author', cascade='all, delete-orphan')
    likes = db.relationship('Like', backref='user', cascade='all, delete-orphan')
    dislikes = db.relationship('Dislike', backref='user', cascade='all, delete-orphan')
    sent_messages = db.relationship('Message', foreign_keys='Message.sender_id', cascade='all, delete-orphan')
    received_messages = db.relationship('Message', foreign_keys='Message.receiver_id', cascade='all, delete-orphan')

    def set_email(self, plain_email):
        if not plain_email:
            return
        normalized = plain_email.lower().strip()
        self.email = encrypt_content(normalized)
        self.email_hash = hashlib.sha256(normalized.encode()).hexdigest()

    def get_email(self):
        try:
            return decrypt_content(self.email)
        except Exception:
            return self.email

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    media_file = db.Column(db.String(200))
    media_type = db.Column(db.String(20))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    scratch_url = db.Column(db.String(500))
    scratch_project_id = db.Column(db.String(100))

    comments = db.relationship('Comment', backref='post', cascade='all, delete-orphan')
    likes = db.relationship('Like', backref='post', cascade='all, delete-orphan')
    dislikes = db.relationship('Dislike', backref='post', cascade='all, delete-orphan')

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('comment.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    replies = db.relationship('Comment', backref=db.backref('parent', remote_side=[id]), cascade='all, delete-orphan')

class Like(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint('user_id', 'post_id', name='unique_like'),)

class Dislike(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint('user_id', 'post_id', name='unique_dislike'),)

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    read = db.Column(db.Boolean, default=False)
    encrypted = db.Column(db.Boolean, default=False)

class Block(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    blocker_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    blocked_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint('blocker_id', 'blocked_id', name='unique_block'),)
    blocker = db.relationship('User', foreign_keys=[blocker_id], backref='blocking')
    blocked = db.relationship('User', foreign_keys=[blocked_id], backref='blocked_by')

class ActionLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    ip_address = db.Column(db.String(45), nullable=False)
    endpoint = db.Column(db.String(200), nullable=True)
    method = db.Column(db.String(10), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='action_logs')

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def save_profile_picture(file):
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        unique_filename = f"{secrets.token_hex(8)}_{filename}"
        filepath = os.path.join(app.config['PROFILE_UPLOAD_FOLDER'], unique_filename)
        img = Image.open(file)
        img.thumbnail((200, 200))
        img.save(filepath)
        return unique_filename
    return None

def save_post_media(file):
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        unique_filename = f"{secrets.token_hex(8)}_{filename}"
        filepath = os.path.join(app.config['POST_UPLOAD_FOLDER'], unique_filename)
        file.save(filepath)
        ext = filename.rsplit('.', 1)[1].lower()
        if ext in ['png', 'jpg', 'jpeg', 'gif', 'webp']:
            media_type = 'image'
        elif ext in ['mp4', 'webm', 'mov']:
            media_type = 'video'
        elif ext == 'mp3':
            media_type = 'audio'
        elif ext == 'zip':
            media_type = 'zip'
        else:
            media_type = None
        return unique_filename, media_type
    return None, None

def verify_turnstile(token):
    return True

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))







@app.template_filter('decrypt')
def decrypt_filter(content, encrypted):
    if encrypted:
        try:
            return decrypt_content(content)
        except Exception:
            return content
    return content

@app.context_processor
def inject_unread_count():
    if current_user.is_authenticated:
        total_unread = Message.query.filter_by(receiver_id=current_user.id, read=False).count()
        return {'total_unread': total_unread}
    return {'total_unread': 0}

@app.context_processor
def inject_admin_status():
    return {
        'is_impersonating': 'admin_id' in session if session else False,
        'original_admin': User.query.get(session.get('admin_id')) if session and 'admin_id' in session else None
    }

@app.context_processor
def inject_profile_pic():
    return dict(get_profile_pic=get_valid_profile_pic)

@app.template_filter('datetime_fr')
def datetime_fr(dt):
    if not dt:
        return ""
    return dt.replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo("Europe/Paris")).strftime('%d/%m/%Y %H:%M')

@app.before_request
def log_action():
    if current_user.is_authenticated:
        g.log_entry = ActionLog(
            user_id=current_user.id,
            ip_address=request.remote_addr,
            endpoint=request.endpoint,
            method=request.method,
            timestamp=datetime.utcnow()
        )

@app.after_request
def commit_log(response):
    if hasattr(g, 'log_entry'):
        try:
            db.session.add(g.log_entry)
            db.session.commit()
        except Exception:
            db.session.rollback()
    return response

@app.route('/')
def index():
    if not current_user.is_authenticated:
        return redirect(url_for('login'))
    page = request.args.get('page', 1, type=int)
    posts_paginate = Post.query.order_by(Post.created_at.desc()).paginate(page=page, per_page=10)
    posts_items = [p for p in posts_paginate.items if p.author is not None]
    active_users = User.query.order_by(User.created_at.desc()).limit(10).all()
    liked_posts = [like.post_id for like in current_user.likes]
    disliked_posts = [dislike.post_id for dislike in current_user.dislikes]
    for post in posts_items:
        if post.media_type == 'audio' and post.media_file:
            post.audio_duration = get_audio_duration(post.media_file)
        else:
            post.audio_duration = 0
    posts_paginate.items = posts_items
    return render_template('index.html', posts=posts_paginate, active_users=active_users, liked_posts=liked_posts, disliked_posts=disliked_posts)


@app.route('/uwucom')
@login_required
@admin_required
def uwucom():
    comments = Comment.query.order_by(Comment.created_at.desc()).all()
    return render_template('uwucom.html', comments=comments)

@app.route('/uwuplace')
@login_required
@admin_required
def admin_panel():
    user_q = request.args.get('user_q', '').strip()
    searched_user = None
    if user_q:
        if user_q.isdigit():
            searched_user = User.query.get(int(user_q))
        else:
            searched_user = User.query.filter_by(username=user_q).first()
        if not searched_user:
            flash(f"Aucun utilisateur trouvé pour '{user_q}'", "warning")
    post_q = request.args.get('post_q', '').strip()
    searched_post = None
    if post_q:
        if post_q.isdigit():
            searched_post = Post.query.get(int(post_q))
        if not searched_post:
            flash(f"Aucun post trouvé avec l'ID '{post_q}'", "warning")
    comments = Comment.query.order_by(Comment.created_at.desc()).all()
    return render_template('admin_panel.html', searched_user=searched_user, searched_post=searched_post, comments=comments, user_q=user_q, post_q=post_q)


@app.route('/uwuplace/ip_activity')
@login_required
@admin_required
def admin_ip_activity():
    page = request.args.get('page', 1, type=int)
    per_page = 50
    logs_query = ActionLog.query.order_by(ActionLog.timestamp.desc())
    logs = logs_query.paginate(page=page, per_page=per_page)

    # Utilisateurs actifs dans les 15 dernières minutes
    active_cutoff = datetime.utcnow() - timedelta(minutes=15)
    active_subq = db.session.query(
        ActionLog.user_id,
        func.max(ActionLog.ip_address).label('ip'),
        func.max(ActionLog.timestamp).label('last_seen')
    ).filter(
        ActionLog.timestamp >= active_cutoff,
        ActionLog.user_id.isnot(None)
    ).group_by(ActionLog.user_id).subquery()

    active_users = db.session.query(User, active_subq.c.ip, active_subq.c.last_seen)\
        .join(active_subq, User.id == active_subq.c.user_id).all()

    return render_template('admin_ip_activity.html',
                           logs=logs,
                           active_users=active_users)

@app.route('/uwuplace/impersonate/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def admin_impersonate(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash("Déjà connecté sur ce compte.", "info")
        return redirect(url_for('admin_panel'))
    session['admin_id'] = current_user.id
    session['admin_username'] = current_user.username
    login_user(user)
    flash(f"Connecté en tant que {user.username}", "success")
    return redirect(url_for('index'))

@app.route('/uwuplace/stop-impersonate')
@login_required
def stop_impersonate():
    if 'admin_id' not in session:
        flash("Aucune impersonation active.", "error")
        return redirect(url_for('index'))
    admin = User.query.get(session['admin_id'])
    session.pop('admin_id', None)
    session.pop('admin_username', None)
    login_user(admin)
    flash("Retour au compte admin.", "success")
    return redirect(url_for('admin_panel'))
"""
@app.route('/admin/delete_user/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def admin_delete_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash("Impossible de supprimer son propre compte.", "error")
        return redirect(url_for('admin_panel'))
    db.session.delete(user)
    db.session.commit()
    flash("Utilisateur supprimé (admin)", "success")
    return redirect(url_for('admin_panel'))
"""
@app.route('/music')
@login_required
def music():
    all_audio = Post.query.filter_by(media_type='audio').order_by(Post.created_at.desc()).all()
    audio_posts = [p for p in all_audio if p.media_file and get_audio_duration(p.media_file) >= 30]
    return render_template('musique.html', audio_posts=audio_posts, get_audio_duration=get_audio_duration)

@app.route('/scratch_login')
@login_required
def scratch_login():
    redirect_url = url_for('scratch_handle', _external=True)
    redirect_location = base64.b64encode(redirect_url.encode()).decode()
    auth_url = f"https://auth.itinerary.eu.org/auth/?redirect={redirect_location}&name=Nyapi"
    return redirect(auth_url)

@app.route('/scratch_handle')
@login_required
def scratch_handle():
    private_code = request.args.get('privateCode')
    if not private_code:
        flash("Private code missing", "error")
        return redirect(url_for('edit_profile'))
    verify_url = f"https://auth.itinerary.eu.org/api/auth/verifyToken?privateCode={private_code}"
    try:
        resp = requests.get(verify_url)
        data = resp.json()
        if data.get('valid') is True and data.get('redirect'):
            current_user.scratch_username = data.get('username')
            current_user.scratch_profile_url = f"https://scratch.mit.edu/users/{data.get('username')}/"
            db.session.commit()
            flash("Profil Scratch lié avec succès !", "success")
        else:
            flash("Échec de la vérification Scratch.", "error")
    except Exception:
        flash("Erreur serveur lors de la vérification.", "error")
    return redirect(url_for('profile', username=current_user.username))

@app.route('/download_zip/<int:post_id>')
@login_required
def download_zip(post_id):
    post = Post.query.get_or_404(post_id)
    if post.media_type != 'zip' or not post.media_file:
        flash('Pas de fichier ZIP', 'error')
        return redirect(url_for('post_detail', post_id=post_id))
    zip_path = os.path.join(app.config['POST_UPLOAD_FOLDER'], post.media_file)
    if not os.path.exists(zip_path):
        flash('Fichier introuvable', 'error')
        return redirect(url_for('post_detail', post_id=post_id))
    original_name = '_'.join(post.media_file.split('_')[1:]) if '_' in post.media_file else post.media_file
    return send_file(zip_path, as_attachment=True, download_name=original_name, mimetype='application/zip')

@app.route('/create_post', methods=['GET', 'POST'])
@login_required
def create_post():
    if request.method == 'POST':
        
        title = request.form.get('title', '').strip()
        content = request.form.get('content', '').strip()
        scratch_url = request.form.get('scratch_url', '').strip()
        media_file = request.files.get('media')
        if not title or not content:
            flash('Titre et contenu obligatoires', 'error')
            return redirect(url_for('create_post'))
        media_filename, media_type = None, None
        if media_file and media_file.filename:
            media_filename, media_type = save_post_media(media_file)
        scratch_project_id = extract_scratch_id(scratch_url) if is_scratch_url(scratch_url) else None
        post = Post(title=title, content=content, media_file=media_filename, media_type=media_type,
                    user_id=current_user.id, scratch_url=scratch_url if scratch_url else None,
                    scratch_project_id=scratch_project_id)
        db.session.add(post)
        db.session.commit()
        flash('Posted !', 'success')
        return redirect(url_for('post_detail', post_id=post.id))
    return render_template('create_post.html')

@app.route('/post/<int:post_id>')
@login_required
def post_detail(post_id):
    post = Post.query.get_or_404(post_id)
    root_comments = Comment.query.filter_by(post_id=post.id, parent_id=None).order_by(Comment.created_at.desc()).all()
    liked_posts, disliked_posts = [], []
    if current_user.is_authenticated:
        liked_posts = [like.post_id for like in current_user.likes]
        disliked_posts = [dislike.post_id for dislike in current_user.dislikes]
    return render_template('post_detail.html', post=post, root_comments=root_comments,
                           liked_posts=liked_posts, disliked_posts=disliked_posts, get_audio_duration=get_audio_duration)

@app.route('/add_comment/<int:post_id>', methods=['POST'])
@login_required
def add_comment(post_id):
    post = Post.query.get_or_404(post_id)
    content = html.escape(request.form.get('content', '').strip())
    parent_id = request.form.get('parent_id')
    if not content:
        flash('Le commentaire ne peut être vide', 'error')
        return redirect(url_for('post_detail', post_id=post_id))
    parent_comment = None
    if parent_id:
        parent_comment = Comment.query.get(int(parent_id))
        if not parent_comment:
            flash('Commentaire parent introuvable', 'error')
            return redirect(url_for('post_detail', post_id=post_id))
        depth = 1
        cur = parent_comment
        while cur.parent is not None:
            depth += 1
            cur = cur.parent
        if depth >= 7:
            flash('Profondeur maximale atteinte (7 niveaux).', 'error')
            return redirect(url_for('post_detail', post_id=post_id))
    comment = Comment(content=content, user_id=current_user.id, post_id=post_id,
                      parent_id=int(parent_id) if parent_id else None)
    db.session.add(comment)
    db.session.commit()
    flash('Commentaire ajouté !', 'success')
    return redirect(url_for('post_detail', post_id=post_id))

@app.route('/add_comment_ajax/<int:post_id>', methods=['POST'])
@login_required
def add_comment_ajax(post_id):
    post = Post.query.get_or_404(post_id)
    content = html.escape(request.form.get('content', '').strip())
    parent_id = request.form.get('parent_id')
    if not content:
        return jsonify({'success': False, 'error': 'Commentaire vide'})
    parent_comment = None
    if parent_id:
        parent_comment = Comment.query.get(int(parent_id))
        if not parent_comment:
            return jsonify({'success': False, 'error': 'Commentaire parent introuvable'})
        depth = 1
        cur = parent_comment
        while cur.parent is not None:
            depth += 1
            cur = cur.parent
        if depth >= 7:
            return jsonify({'success': False, 'error': 'Profondeur maximale atteinte'})
    comment = Comment(content=content, user_id=current_user.id, post_id=post_id,
                      parent_id=int(parent_id) if parent_id else None)
    db.session.add(comment)
    db.session.commit()
    comment_data = {
        'id': comment.id,
        'content': comment.content,
        'author': {'id': comment.author.id, 'username': comment.author.username, 'profile_pic': comment.author.profile_pic},
        'created_at': comment.created_at.strftime('%b %d, %Y %H:%M'),
        'parent_id': comment.parent_id
    }
    return jsonify({'success': True, 'comment': comment_data})

@app.route('/like_post/<int:post_id>', methods=['POST'])
@login_required
def like_post(post_id):
    post = Post.query.get_or_404(post_id)
    existing_like = Like.query.filter_by(user_id=current_user.id, post_id=post_id).first()
    existing_dislike = Dislike.query.filter_by(user_id=current_user.id, post_id=post_id).first()
    
    if existing_like:
        db.session.delete(existing_like)
        liked = False
    else:
        db.session.add(Like(user_id=current_user.id, post_id=post_id))
        liked = True
        if existing_dislike:
            db.session.delete(existing_dislike)
    
    db.session.commit()
    # Re-query to get updated counts
    post = Post.query.get(post_id)
    return jsonify({'likes': len(post.likes), 'dislikes': len(post.dislikes), 'liked': liked, 'disliked': False})

@app.route('/dislike_post/<int:post_id>', methods=['POST'])
@login_required
def dislike_post(post_id):
    post = Post.query.get_or_404(post_id)
    existing_dislike = Dislike.query.filter_by(user_id=current_user.id, post_id=post_id).first()
    existing_like = Like.query.filter_by(user_id=current_user.id, post_id=post_id).first()
    if existing_dislike:
        db.session.delete(existing_dislike)
        disliked = False
    else:
        db.session.add(Dislike(user_id=current_user.id, post_id=post_id))
        disliked = True
        if existing_like:
            db.session.delete(existing_like)
    db.session.commit()
    post = Post.query.get(post_id)
    return jsonify({'likes': len(post.likes), 'dislikes': len(post.dislikes), 'liked': False, 'disliked': disliked})

@app.route('/toggle_block/<int:user_id>', methods=['POST'])
@login_required
def toggle_block(user_id):
    if user_id == current_user.id:
        return jsonify({'error': 'Cannot block yourself'}), 400
    block = Block.query.filter_by(blocker_id=current_user.id, blocked_id=user_id).first()
    if block:
        db.session.delete(block)
        db.session.commit()
        return jsonify({'status': 'unblocked'})
    else:
        db.session.add(Block(blocker_id=current_user.id, blocked_id=user_id))
        db.session.commit()
        return jsonify({'status': 'blocked'})

@app.route('/check_block_status/<int:user_id>')
@login_required
def check_block_status(user_id):
    is_blocked = Block.query.filter_by(blocker_id=current_user.id, blocked_id=user_id).first() is not None
    is_blocked_by = Block.query.filter_by(blocker_id=user_id, blocked_id=current_user.id).first() is not None
    return jsonify({'blocked': is_blocked, 'blocked_by': is_blocked_by})

@app.route('/get_blocked_users')
@login_required
def get_blocked_users():
    blocks = Block.query.filter_by(blocker_id=current_user.id).all()
    users = []
    for block in blocks:
        user = User.query.get(block.blocked_id)
        users.append({'id': user.id, 'username': user.username, 'profile_pic': user.profile_pic, 'blocked_at': block.created_at.strftime('%d/%m/%Y')})
    return jsonify({'blocked_users': users})

@app.route('/messages')
@login_required
def messages():
    user_msgs = Message.query.filter(
        (Message.sender_id == current_user.id) | (Message.receiver_id == current_user.id)
    ).order_by(Message.created_at.desc()).all()
    threads = {}
    for msg in user_msgs:
        other_id = msg.receiver_id if msg.sender_id == current_user.id else msg.sender_id
        if other_id not in threads:
            other_user = User.query.get(other_id)
            if not other_user:
                continue
            threads[other_id] = {
                'user': other_user,
                'last_message': msg,
                'unread': False,
                'unread_count': 0
            }
        if not msg.read and msg.receiver_id == current_user.id:
            threads[other_id]['unread'] = True
            threads[other_id]['unread_count'] += 1
        # ✅ Comparaison via timestamp
        if msg.created_at.timestamp() > threads[other_id]['last_message'].created_at.timestamp():
            threads[other_id]['last_message'] = msg

    # ✅ Tri via timestamp
    sorted_threads = sorted(
        threads.values(),
        key=lambda x: x['last_message'].created_at.timestamp(),
        reverse=True
    )

    # Déchiffrer si nécessaire
    for t in sorted_threads:
        if t['last_message'].encrypted:
            try:
                t['last_message'].content = decrypt_content(t['last_message'].content)
            except Exception:
                pass

    total_unread = Message.query.filter_by(receiver_id=current_user.id, read=False).count()
    return render_template('messages.html', threads=sorted_threads, total_unread=total_unread)

@app.route('/messages/<int:user_id>', methods=['GET', 'POST'])
@login_required
def message_thread(user_id):
    other_user = User.query.get_or_404(user_id)
    if other_user.id == current_user.id:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'error': 'Impossible de s\'envoyer un message à soi-même'})
        flash("Impossible", "error")
        return redirect(url_for('messages'))
    is_blocked = Block.query.filter_by(blocker_id=current_user.id, blocked_id=user_id).first() is not None
    is_blocked_by = Block.query.filter_by(blocker_id=user_id, blocked_id=current_user.id).first() is not None
    if request.method == 'POST':
        content = request.form.get('content', '').strip()
        if is_blocked:
            err = "Utilisateur bloqué"
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'error': err})
            flash(err, 'error')
            return redirect(url_for('message_thread', user_id=user_id))
        if is_blocked_by:
            err = "Vous êtes bloqué"
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'error': err})
            flash(err, 'error')
            return redirect(url_for('message_thread', user_id=user_id))
        if not content:
            err = "Message vide"
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'error': err})
            flash(err, 'error')
            return redirect(url_for('message_thread', user_id=user_id))
        if re.search(r'[<>\\{\\}]', content):
            err = "Caractère interdit"
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'error': err})
            flash(err, 'error')
            return redirect(url_for('message_thread', user_id=user_id))
        enc = encrypt_content(content)
        msg = Message(content=enc, sender_id=current_user.id, receiver_id=user_id, encrypted=True)
        db.session.add(msg)
        db.session.commit()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': True, 'message_id': msg.id, 'content': content,
                            'created_at': msg.created_at.strftime('%d/%m/%Y %H:%M'), 'sent_by_current_user': True})
        return redirect(url_for('message_thread', user_id=user_id))
    per_page = 30
    before_id = request.args.get('before_id', type=int)
    base_q = Message.query.filter(
        ((Message.sender_id == current_user.id) & (Message.receiver_id == user_id)) |
        ((Message.sender_id == user_id) & (Message.receiver_id == current_user.id))
    )
    if before_id:
        msgs = base_q.filter(Message.id < before_id).order_by(Message.id.desc()).limit(per_page).all()
        msgs.reverse()
    else:
        msgs = base_q.order_by(Message.id.desc()).limit(per_page).all()
        msgs.reverse()
    has_more = False
    if msgs:
        oldest_id = msgs[0].id
        has_more = base_q.filter(Message.id < oldest_id).first() is not None
    for m in msgs:
        if m.receiver_id == current_user.id and not m.read:
            m.read = True
        if m.encrypted:
            try:
                m.content = decrypt_content(m.content)
            except Exception:
                pass
    db.session.commit()
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        data = [{'id': m.id, 'content': m.content.replace('\n', '<br>'), 'sender_id': m.sender_id,
                 'created_at': m.created_at.strftime('%d/%m/%Y %H:%M'), 'sent_by_current_user': m.sender_id == current_user.id} for m in msgs]
        return jsonify({'messages': data, 'has_more': has_more})
    return render_template('message_thread.html', other_user=other_user, messages=msgs,
                           is_blocked=is_blocked, is_blocked_by=is_blocked_by, has_more=has_more)

@app.route('/get_new_messages')
@login_required
def get_new_messages():
    last_id = request.args.get('last_id', 0, type=int)
    other_user_id = request.args.get('user_id', 0, type=int)
    if not other_user_id or other_user_id == current_user.id:
        return jsonify({'messages': []})
    messages = Message.query.filter(
        Message.id > last_id,
        ((Message.sender_id == current_user.id) & (Message.receiver_id == other_user_id)) |
        ((Message.sender_id == other_user_id) & (Message.receiver_id == current_user.id))
    ).order_by(Message.created_at.asc()).all()
    for msg in messages:
        if msg.receiver_id == current_user.id and not msg.read:
            msg.read = True
    db.session.commit()
    messages_data = []
    for msg in messages:
        content = msg.content
        if msg.encrypted:
            try:
                content = decrypt_content(msg.content)
            except Exception:
                pass
        messages_data.append({
            'id': msg.id,
            'content': content,
            'sender_id': msg.sender_id,
            'receiver_id': msg.receiver_id,
            'created_at': msg.created_at.isoformat() if msg.created_at else datetime.utcnow().isoformat(),
            'sent_by_current_user': msg.sender_id == current_user.id
        })
    return jsonify({'messages': messages_data})

@app.route('/check_unread_messages')
@login_required
def check_unread_messages():
    total = Message.query.filter_by(receiver_id=current_user.id, read=False).count()
    return jsonify({'total_unread': total, 'has_unread': total > 0})

@app.route('/profile/<username>')
@login_required
def profile(username):
    user = User.query.filter_by(username=username).first_or_404()
    if not user.profile_pic:
        user.profile_pic = 'default.png'
    else:
        profile_path = os.path.join(app.config['PROFILE_UPLOAD_FOLDER'], user.profile_pic)
        if not os.path.exists(profile_path):
            user.profile_pic = 'default.png'
    page = request.args.get('page', 1, type=int)
    posts = Post.query.filter_by(user_id=user.id).order_by(Post.created_at.desc()).paginate(page=page, per_page=10)
    return render_template('profile.html', user=user, posts=posts)

@app.route('/edit_profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    if request.method == 'POST':
        bio = request.form.get('bio')
        profile_pic = request.files.get('profile_pic')
        remove_pic = request.form.get('remove_pic')
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        if current_password or new_password or confirm_password:
            if not current_password:
                flash('Mot de passe actuel requis.', 'error')
                return redirect(url_for('edit_profile'))
            if not new_password or not confirm_password:
                flash('Nouveau mot de passe et confirmation requis.', 'error')
                return redirect(url_for('edit_profile'))
            if new_password != confirm_password:
                flash('Les mots de passe ne correspondent pas.', 'error')
                return redirect(url_for('edit_profile'))
            if len(new_password) < 6:
                flash('6 caractères minimum.', 'error')
                return redirect(url_for('edit_profile'))
            if not bcrypt.checkpw(current_password.encode('utf-8'), current_user.password_hash.encode('utf-8')):
                flash('Mot de passe actuel incorrect.', 'error')
                return redirect(url_for('edit_profile'))
            current_user.password_hash = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            flash('Mot de passe changé.', 'success')
        current_user.bio = bio
        if remove_pic:
            current_user.profile_pic = 'default.png'
        elif profile_pic:
            filename = save_profile_picture(profile_pic)
            if filename:
                current_user.profile_pic = filename
        db.session.commit()
        flash('Profil mis à jour.', 'success')
        return redirect(url_for('profile', username=current_user.username))
    return render_template('edit_profile.html')



@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and bcrypt.checkpw(password.encode('utf-8'), user.password_hash.encode('utf-8')):
            login_user(user)
            
            return redirect(url_for('index'))
        else:
            flash('Identifiants invalides', 'error')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/delete_account', methods=['POST'])
@login_required
def delete_account():
    password = request.form.get('password')
    if not password:
        flash('Veuillez entrer votre mot de passe pour confirmer.', 'error')
        return redirect(url_for('profile', username=current_user.username))
    if not bcrypt.checkpw(password.encode('utf-8'), current_user.password_hash.encode('utf-8')):
        flash('Mot de passe incorrect.', 'error')
        return redirect(url_for('profile', username=current_user.username))
    try:
        user_id = current_user.id
        Message.query.filter((Message.sender_id == user_id) | (Message.receiver_id == user_id)).delete(synchronize_session=False)
        Like.query.filter_by(user_id=user_id).delete(synchronize_session=False)
        Dislike.query.filter_by(user_id=user_id).delete(synchronize_session=False)
        Comment.query.filter_by(user_id=user_id).delete(synchronize_session=False)
        Post.query.filter_by(user_id=user_id).delete(synchronize_session=False)
        Block.query.filter((Block.blocker_id ==user_id) | (Block.blocked_id == user_id)).delete(synchronize_session=False)
        user = User.query.get(user_id)
        db.session.delete(user)
        db.session.commit()
        logout_user()
        flash('Compte supprimé avec succès.', 'success')
        return redirect(url_for('login'))
    except Exception:
        db.session.rollback()
        flash('Erreur lors de la suppression.', 'error')
        return redirect(url_for('profile', username=current_user.username))

@app.route('/delete_post/<int:post_id>', methods=['POST'])
@login_required
def delete_post(post_id):
    post = Post.query.get_or_404(post_id)
    if post.user_id != current_user.id and not current_user.is_admin:
        abort(403)
    db.session.delete(post)
    db.session.commit()
    flash('Post supprimé', 'success')
    return redirect(url_for('index'))

@app.route('/delete_comment/<int:comment_id>', methods=['POST'])
@login_required
def delete_comment(comment_id):
    comment = Comment.query.get_or_404(comment_id)
    if comment.user_id != current_user.id and not current_user.is_admin:
        abort(403)
    post_id = comment.post_id
    db.session.delete(comment)
    db.session.commit()
    flash('Commentaire supprimé', 'success')
    return redirect(url_for('post_detail', post_id=post_id))

@app.route('/find_users')
@login_required
def find_users():
    q = request.args.get('q', '')
    page = request.args.get('page', 1, type=int)
    if q:
        users = User.query.filter(User.username.contains(q) | User.bio.contains(q)).filter(User.id != current_user.id).paginate(page=page, per_page=12)
    else:
        users = User.query.filter(User.id != current_user.id).order_by(User.created_at.desc()).paginate(page=page, per_page=12)
    return render_template('find_users.html', users=users, query=q)

@app.route('/search')
@login_required
def search():
    q = request.args.get('q', '')
    page = request.args.get('page', 1, type=int)
    posts = Post.query.filter(Post.title.contains(q) | Post.content.contains(q)).order_by(Post.created_at.desc()).paginate(page=page, per_page=10)
    users = User.query.filter(User.username.contains(q)).limit(10).all()
    return render_template('search.html', query=q, posts=posts, users=users)

@app.route('/search_ajax')
@login_required
def search_ajax():
    q = request.args.get('q', '')
    if len(q) < 2:
        return jsonify({'results': []})
    users = User.query.filter(User.username.contains(q) | User.bio.contains(q)).limit(5).all()
    posts = Post.query.filter(Post.title.contains(q) | Post.content.contains(q)).limit(5).all()
    results = {
        'users': [{'id': u.id, 'username': u.username, 'profile_pic': u.profile_pic, 'bio': u.bio[:100]} for u in users],
        'posts': [{'id': p.id, 'title': p.title, 'content': p.content[:150], 'author': p.author.username, 'created_at': p.created_at.strftime('%b %d, %Y')} for p in posts]
    }
    return jsonify(results)

@app.route('/following')
@login_required
def following():
    page = request.args.get('page', 1, type=int)
    msgs = Message.query.filter((Message.sender_id == current_user.id) | (Message.receiver_id == current_user.id)).all()
    interacted = set()
    for m in msgs:
        if m.sender_id != current_user.id:
            interacted.add(m.sender_id)
        if m.receiver_id != current_user.id:
            interacted.add(m.receiver_id)
    posts = Post.query.filter(Post.user_id.in_(interacted)).order_by(Post.created_at.desc()).paginate(page=page, per_page=10)
    liked_posts = [like.post_id for like in current_user.likes]
    disliked_posts = [dislike.post_id for dislike in current_user.dislikes]
    active_users = User.query.order_by(User.created_at.desc()).limit(10).all()
    for post in posts.items:
        if post.media_type == 'audio' and post.media_file:
            post.audio_duration = get_audio_duration(post.media_file)
        else:
            post.audio_duration = 0
    return render_template('index.html', posts=posts, active_users=active_users, liked_posts=liked_posts, disliked_posts=disliked_posts, following=True)





@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        if not username or not email or not password or not confirm_password:
            flash("Tous les champs sont requis", "error")
            return redirect(url_for('register'))
        if not re.fullmatch(r'[A-Za-z0-9_-]+', username):
            flash("Caractères autorisés : lettres, chiffres, -, _", "error")
            return redirect(url_for('register'))
        if len(username) < 3 or len(username) > 20:
            flash("Le pseudo doit faire entre 3 et 20 caractères.", "error")
            return redirect(url_for('register'))
        if password != confirm_password:
            flash("Les mots de passe ne correspondent pas", "error")
            return redirect(url_for('register'))
        if len(password) < 6:
            flash("Minimum 6 caractères", "error")
            return redirect(url_for('register'))
        if User.query.filter_by(username=username).first():
            flash("Pseudo déjà pris", "error")
            return redirect(url_for('register'))
        normalized = email.lower().strip()
        email_hash = hashlib.sha256(normalized.encode()).hexdigest()
        if User.query.filter_by(email_hash=email_hash).first():
            flash("Email déjà utilisé", "error")
            return redirect(url_for('register'))
        password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        user = User(username=username, password_hash=password_hash)
        user.set_email(email)
        db.session.add(user)
        db.session.commit()
        flash("Inscription réussie. Vous pouvez vous connecter.", "success")
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/tos')
def tos():
    return render_template('tos.html')

@app.route('/conf')
def conf():
    return render_template('conf.html')

@app.route('/816c1c8b-c4cb-465f-b4b1-5335d6e10f53.html')
def special_page():
    return render_template('816c1c8b-c4cb-465f-b4b1-5335d6e10f53.html')

@app.route('/update')
def update():
    return render_template('update.html')

@app.route('/thanks')
def thanks():
    return render_template('thanks.html')

@app.route('/politique')
def politique():
    return render_template('politique.html')

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        conn = sqlite3.connect(os.path.join(INSTANCE_DIR, 'socialplace.db'))
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(post)")
        columns = [col[1] for col in cursor.fetchall()]
        if 'scratch_url' not in columns:
            cursor.execute("ALTER TABLE post ADD COLUMN scratch_url VARCHAR(500)")
        if 'scratch_project_id' not in columns:
            cursor.execute("ALTER TABLE post ADD COLUMN scratch_project_id VARCHAR(100)")
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='block'")
        if not cursor.fetchone():
            cursor.execute('CREATE TABLE block (id INTEGER PRIMARY KEY AUTOINCREMENT, blocker_id INTEGER NOT NULL, blocked_id INTEGER NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (blocker_id) REFERENCES user (id), FOREIGN KEY (blocked_id) REFERENCES user (id), UNIQUE(blocker_id, blocked_id))')
        cursor.execute("PRAGMA table_info(user)")
        user_cols = [col[1] for col in cursor.fetchall()]
        if 'is_verified' not in user_cols:
            cursor.execute("ALTER TABLE user ADD COLUMN is_verified BOOLEAN DEFAULT 0")
            cursor.execute("UPDATE user SET is_verified = 1 WHERE username = 'LTchat'")
        cursor.execute("PRAGMA table_info(message)")
        msg_cols = [col[1] for col in cursor.fetchall()]
        if 'encrypted' not in msg_cols:
            cursor.execute("ALTER TABLE message ADD COLUMN encrypted BOOLEAN DEFAULT 0")
        if 'email_hash' not in user_cols:
            cursor.execute("ALTER TABLE user ADD COLUMN email_hash VARCHAR(64)")
            cursor.execute("SELECT id, email FROM user")
            for uid, plain in cursor.fetchall():
                if plain and not plain.startswith('gAAAAA'):
                    normalized = plain.lower().strip()
                    enc = encrypt_content(normalized)
                    h = hashlib.sha256(normalized.encode()).hexdigest()
                    cursor.execute("UPDATE user SET email = ?, email_hash = ? WHERE id = ?", (enc, h, uid))
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_user_email_hash ON user (email_hash)")
        conn.commit()
        conn.close()
        admins = [""]
        for a in admins:
            u = User.query.filter_by(username=a).first()
            if u and not u.is_admin:
                u.is_admin = True
        db.session.commit()
    app.run(port=5015, debug=False, host='0.0.0.0')
