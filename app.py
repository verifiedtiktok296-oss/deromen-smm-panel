import os, sqlite3
from pathlib import Path
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

BASE = Path(__file__).resolve().parent
DB = BASE / 'deromen.db'
app = Flask(__name__, template_folder=str(BASE/'templates'), static_folder=str(BASE/'static'))
app.secret_key = os.getenv('SECRET_KEY', 'change-this-secret-key')

def db():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c

def init_db():
    c=db(); c.executescript('''
    CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, balance REAL NOT NULL DEFAULT 0, is_admin INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS services(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, category TEXT NOT NULL, rate REAL NOT NULL DEFAULT 0, min_qty INTEGER NOT NULL DEFAULT 1, max_qty INTEGER NOT NULL DEFAULT 100000, description TEXT DEFAULT '', active INTEGER NOT NULL DEFAULT 1);
    CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, service_id INTEGER, link TEXT NOT NULL, quantity INTEGER NOT NULL, charge REAL NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'Pending', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS tickets(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, subject TEXT NOT NULL, message TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'Open', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS transactions(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, amount REAL NOT NULL, type TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'Pending', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
    ''')
    if not c.execute("SELECT id FROM users WHERE username='admin'").fetchone():
        c.execute("INSERT INTO users(username,email,password_hash,is_admin) VALUES(?,?,?,1)",('admin','admin@deromen.local',generate_password_hash('admin12345')))
    if c.execute('SELECT COUNT(*) FROM services').fetchone()[0]==0:
        c.executemany('INSERT INTO services(name,category,rate,min_qty,max_qty,description) VALUES(?,?,?,?,?,?)',[
        ('Instagram Followers','Instagram',120,100,100000,'Starter service'),('Instagram Likes','Instagram',80,100,100000,'Starter service'),('TikTok Likes','TikTok',80,100,50000,'Starter service'),('TikTok Views','TikTok',50,100,100000,'Starter service'),('YouTube Views','YouTube',150,100,100000,'Starter service')])
    c.commit(); c.close()

def current_user():
    if 'user_id' not in session:return None
    c=db(); u=c.execute('SELECT * FROM users WHERE id=?',(session['user_id'],)).fetchone(); c.close(); return u

def login_required(f):
    @wraps(f)
    def w(*a,**k): return f(*a,**k) if current_user() else redirect(url_for('login'))
    return w

def admin_required(f):
    @wraps(f)
    def w(*a,**k):
        u=current_user()
        if not u or not u['is_admin']: flash('Admin access required.','error'); return redirect(url_for('dashboard'))
        return f(*a,**k)
    return w

@app.context_processor
def inject(): return {'me':current_user()}

@app.route('/')
def home(): return redirect(url_for('dashboard') if current_user() else url_for('login'))

@app.route('/login',methods=['GET','POST'])
def login():
    if request.method=='POST':
        identity=request.form.get('identity','').strip(); pw=request.form.get('password','')
        c=db(); u=c.execute('SELECT * FROM users WHERE username=? OR email=?',(identity,identity.lower())).fetchone(); c.close()
        if u and check_password_hash(u['password_hash'],pw): session.clear(); session['user_id']=u['id']; return redirect(url_for('dashboard'))
        flash('Invalid username/email or password.','error')
    return render_template('login.html')

@app.route('/register',methods=['GET','POST'])
def register():
    if request.method=='POST':
        username=request.form.get('username','').strip(); email=request.form.get('email','').strip().lower(); pw=request.form.get('password',''); cp=request.form.get('confirm_password','')
        if not username or not email or len(pw)<8: flash('Password must be at least 8 characters.','error')
        elif pw!=cp: flash('Passwords do not match.','error')
        else:
            c=db()
            try:
                c.execute('INSERT INTO users(username,email,password_hash) VALUES(?,?,?)',(username,email,generate_password_hash(pw))); c.commit(); c.close(); flash('Account created successfully.','success'); return redirect(url_for('login'))
            except sqlite3.IntegrityError: c.close(); flash('Username or email already exists.','error')
    return render_template('register.html')

@app.route('/dashboard')
@login_required
def dashboard():
    c=db(); u=current_user(); orders=c.execute('SELECT COUNT(*) FROM orders WHERE user_id=?',(u['id'],)).fetchone()[0]; pending=c.execute("SELECT COUNT(*) FROM orders WHERE user_id=? AND status='Pending'",(u['id'],)).fetchone()[0]; spent=c.execute('SELECT COALESCE(SUM(charge),0) FROM orders WHERE user_id=?',(u['id'],)).fetchone()[0]; c.close(); return render_template('dashboard.html',user=u,orders=orders,pending=pending,spent=spent)

@app.route('/services')
@login_required
def services():
    c=db(); rows=c.execute('SELECT * FROM services WHERE active=1 ORDER BY category,name').fetchall(); c.close(); return render_template('services.html',services=rows)

@app.route('/new-order',methods=['GET','POST'])
@login_required
def new_order():
    c=db(); services=c.execute('SELECT * FROM services WHERE active=1 ORDER BY category,name').fetchall()
    if request.method=='POST':
        try: sid=int(request.form.get('service_id')); qty=int(request.form.get('quantity'))
        except: sid=0; qty=0
        link=request.form.get('link','').strip(); s=c.execute('SELECT * FROM services WHERE id=? AND active=1',(sid,)).fetchone(); u=current_user()
        if not s or not link or qty<s['min_qty'] or qty>s['max_qty']: flash('Check service, link and quantity.','error')
        else:
            charge=qty*s['rate']/1000
            if u['balance']<charge: flash('Insufficient balance. Please add funds.','error')
            else:
                c.execute('UPDATE users SET balance=balance-? WHERE id=?',(charge,u['id'])); c.execute('INSERT INTO orders(user_id,service_id,link,quantity,charge) VALUES(?,?,?,?,?)',(u['id'],sid,link,qty,charge)); c.execute("INSERT INTO transactions(user_id,amount,type,status) VALUES(?,?,?,?)",(u['id'],charge,'Order','Completed')); c.commit(); flash('Order placed successfully.','success'); c.close(); return redirect(url_for('orders'))
    c.close(); return render_template('new_order.html',services=services)

@app.route('/orders')
@login_required
def orders():
    c=db(); rows=c.execute('SELECT o.*,s.name service_name FROM orders o LEFT JOIN services s ON s.id=o.service_id WHERE o.user_id=? ORDER BY o.id DESC',(current_user()['id'],)).fetchall(); c.close(); return render_template('orders.html',orders=rows)

@app.route('/tickets',methods=['GET','POST'])
@login_required
def tickets():
    c=db(); uid=current_user()['id']
    if request.method=='POST':
        c.execute('INSERT INTO tickets(user_id,subject,message) VALUES(?,?,?)',(uid,request.form.get('subject',''),request.form.get('message',''))); c.commit(); flash('Ticket created.','success')
    rows=c.execute('SELECT * FROM tickets WHERE user_id=? ORDER BY id DESC',(uid,)).fetchall(); c.close(); return render_template('tickets.html',tickets=rows)

@app.route('/add-funds',methods=['GET','POST'])
@login_required
def add_funds():
    if request.method=='POST':
        try: amount=float(request.form.get('amount',0))
        except: amount=0
        if amount<=0: flash('Enter a valid amount.','error')
        else:
            c=db(); c.execute("INSERT INTO transactions(user_id,amount,type) VALUES(?,?,?)",(current_user()['id'],amount,'Add Funds')); c.commit(); c.close(); flash('Funds request submitted for admin approval.','success')
    return render_template('add_funds.html')

@app.route('/transactions')
@login_required
def transactions():
    c=db(); rows=c.execute('SELECT * FROM transactions WHERE user_id=? ORDER BY id DESC',(current_user()['id'],)).fetchall(); c.close(); return render_template('transactions.html',transactions=rows)

@app.route('/settings')
@login_required
def settings(): return render_template('settings.html')
@app.route('/api')
@login_required
def api_page(): return render_template('api.html')
@app.route('/logout')
def logout(): session.clear(); return redirect(url_for('login'))

@app.route('/admin')
@admin_required
def admin():
    c=db(); data=[c.execute('SELECT COUNT(*) FROM users WHERE is_admin=0').fetchone()[0],c.execute('SELECT COUNT(*) FROM orders').fetchone()[0],c.execute('SELECT COUNT(*) FROM services').fetchone()[0],c.execute("SELECT COUNT(*) FROM tickets WHERE status='Open'").fetchone()[0]]; c.close(); return render_template('admin.html',users=data[0],orders=data[1],services=data[2],tickets=data[3])
@app.route('/admin/users')
@admin_required
def admin_users():
    c=db(); rows=c.execute('SELECT * FROM users ORDER BY id DESC').fetchall(); c.close(); return render_template('admin_users.html',users=rows)
@app.route('/admin/add-balance/<int:uid>',methods=['POST'])
@admin_required
def admin_add_balance(uid):
    try: amount=float(request.form.get('amount',0))
    except: amount=0
    if amount>0:
        c=db(); c.execute('UPDATE users SET balance=balance+? WHERE id=?',(amount,uid)); c.execute("UPDATE transactions SET status='Completed' WHERE user_id=? AND type='Add Funds' AND status='Pending'",(uid,)); c.commit(); c.close()
    return redirect(url_for('admin_users'))
@app.route('/admin/services',methods=['GET','POST'])
@admin_required
def admin_services():
    c=db()
    if request.method=='POST': c.execute('INSERT INTO services(name,category,rate,min_qty,max_qty,description) VALUES(?,?,?,?,?,?)',(request.form.get('name',''),request.form.get('category',''),float(request.form.get('rate',0)),int(request.form.get('min_qty',1)),int(request.form.get('max_qty',100000)),request.form.get('description',''))); c.commit()
    rows=c.execute('SELECT * FROM services ORDER BY id DESC').fetchall(); c.close(); return render_template('admin_services.html',services=rows)
@app.route('/api/services')
def api_services():
    c=db(); rows=c.execute('SELECT id,name,category,rate,min_qty,max_qty,description FROM services WHERE active=1').fetchall(); c.close(); return jsonify([dict(r) for r in rows])

init_db()
if __name__=='__main__': app.run(host='0.0.0.0',port=int(os.getenv('PORT',5000)))
