import os, sqlite3
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash

BASE = Path(__file__).resolve().parent
ROOT = BASE.parent
DB = BASE / 'deromen.db'
app = Flask(__name__, template_folder=str(BASE/'templates'), static_folder=str(BASE/'static'), static_url_path='/static')
app.secret_key = os.getenv('SECRET_KEY', 'dev-only-change-me')

def db():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c

def init_db():
    c=db(); c.executescript('''
    CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, balance REAL NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS services(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, category TEXT NOT NULL, rate REAL NOT NULL DEFAULT 0, min_qty INTEGER NOT NULL DEFAULT 1, max_qty INTEGER NOT NULL DEFAULT 1000, description TEXT DEFAULT '', active INTEGER NOT NULL DEFAULT 1);
    CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, service_id INTEGER, link TEXT NOT NULL, quantity INTEGER NOT NULL, charge REAL NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'Pending', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(user_id) REFERENCES users(id), FOREIGN KEY(service_id) REFERENCES services(id));
    CREATE TABLE IF NOT EXISTS tickets(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, subject TEXT NOT NULL, message TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'Open', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS transactions(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, amount REAL NOT NULL, type TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'Pending', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
    ''')
    if c.execute('SELECT COUNT(*) FROM services').fetchone()[0]==0:
        c.executemany('INSERT INTO services(name,category,rate,min_qty,max_qty,description) VALUES (?,?,?,?,?,?)',[
            ('Instagram Followers','Instagram',120,100,100000,'Provider service placeholder'),('TikTok Likes','TikTok',80,100,50000,'Provider service placeholder'),('YouTube Views','YouTube',150,100,100000,'Provider service placeholder')])
    c.commit(); c.close()

def logged(): return 'user_id' in session

@app.route('/static/js/<path:filename>')
def static_js(filename): return send_from_directory(str(ROOT/'frontend/js'), filename)

@app.route('/')
def home(): return redirect(url_for('dashboard') if logged() else url_for('login'))

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method=='POST':
        identity=request.form.get('identity','').strip(); password=request.form.get('password','')
        c=db(); u=c.execute('SELECT * FROM users WHERE username=? OR email=?',(identity,identity)).fetchone(); c.close()
        if u and check_password_hash(u['password_hash'],password):
            session['user_id']=u['id']; session['username']=u['username']; return redirect(url_for('dashboard'))
        flash('Invalid username/email or password.','error')
    return render_template('login.html')

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method=='POST':
        username=request.form.get('username','').strip(); email=request.form.get('email','').strip().lower(); password=request.form.get('password',''); confirm=request.form.get('confirm_password','')
        if not username or not email or len(password)<8: flash('Enter valid details. Password must be at least 8 characters.','error')
        elif password!=confirm: flash('Passwords do not match.','error')
        else:
            c=db()
            try:
                c.execute('INSERT INTO users(username,email,password_hash) VALUES (?,?,?)',(username,email,generate_password_hash(password))); c.commit(); c.close(); flash('Account created. Please log in.','success'); return redirect(url_for('login'))
            except sqlite3.IntegrityError: c.close(); flash('Username or email already exists.','error')
    return render_template('register.html')

@app.route('/dashboard')
def dashboard():
    if not logged(): return redirect(url_for('login'))
    c=db(); u=c.execute('SELECT * FROM users WHERE id=?',(session['user_id'],)).fetchone(); n=c.execute('SELECT COUNT(*) FROM orders WHERE user_id=?',(session['user_id'],)).fetchone()[0]; c.close()
    return render_template('dashboard.html',user=u,order_count=n)

@app.route('/services')
def services():
    if not logged(): return redirect(url_for('login'))
    c=db(); rows=c.execute('SELECT * FROM services WHERE active=1 ORDER BY category,name').fetchall(); c.close(); return render_template('services.html',services=rows)

@app.route('/orders')
def orders():
    if not logged(): return redirect(url_for('login'))
    c=db(); rows=c.execute('SELECT o.*,s.name service_name FROM orders o LEFT JOIN services s ON s.id=o.service_id WHERE o.user_id=? ORDER BY o.id DESC',(session['user_id'],)).fetchall(); c.close(); return render_template('orders.html',orders=rows)

@app.route('/logout')
def logout(): session.clear(); return redirect(url_for('login'))

@app.route('/api/services')
def api_services():
    c=db(); rows=c.execute('SELECT id,name,category,rate,min_qty,max_qty,description FROM services WHERE active=1').fetchall(); c.close(); return jsonify([dict(r) for r in rows])

if __name__=='__main__': init_db(); app.run(host='0.0.0.0',port=int(os.getenv('PORT',5000)),debug=False)
