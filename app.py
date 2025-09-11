from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
import psycopg2
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

# Temporary admin credentials (username: admin, password: 1234)
ADMIN_CREDENTIALS = {
    'admin': {
        'password': generate_password_hash('1234'),
        'name': 'Ma. Fe M. Cantutay'
    },
    'admin2': {
        'password': generate_password_hash('4321'),
        'name': 'Lie Jenica L. Egam'
    }
}


def init_db():
    conn = None
    try:
        conn = psycopg2.connect(
            dbname="MEDISYNC_DB",
            user="postgres",
            password="Chryscelle1!",
            host="localhost",
            port=1234
        )
        c = conn.cursor()
        
        c.execute('''CREATE TABLE IF NOT EXISTS Category (
            id SERIAL PRIMARY KEY,
            category_name TEXT NOT NULL,
            created_at DATE DEFAULT CURRENT_DATE
        )''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS Unit (
            unit_id SERIAL PRIMARY KEY,
            unit_name TEXT NOT NULL
        )''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS Product (
            id SERIAL PRIMARY KEY,
            product_name TEXT NOT NULL,
            product_type TEXT NOT NULL,
            category_id INTEGER REFERENCES Category(id),
            stock_quantity INTEGER NOT NULL DEFAULT 0,
            unit_id INTEGER REFERENCES Unit(unit_id),
            stock_status TEXT DEFAULT 'in stock',
            status TEXT DEFAULT 'active',
            created_at DATE DEFAULT CURRENT_DATE
        )''')
        
        conn.commit()
        print("Database initialization schema check complete.")
    except Exception as e:
        print(f"Error initializing database: {str(e)}")
        if conn:
            conn.rollback()
    finally:
        if conn is not None:
            conn.close()

# Login required decorator
def login_required(f):
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            flash('Please log in to access this page', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

# Routes
@app.route('/')
def login():
    session.clear()
    return render_template('index.html')

@app.route('/auth', methods=['POST'])
def auth():
    username = request.form['username']
    password = request.form['password']

    user = ADMIN_CREDENTIALS.get(username)
    if user and check_password_hash(user['password'], password):
        session['logged_in'] = True
        session['username'] = username
        session['name'] = user['name']
        return redirect(url_for('dashboard'))
    else:
        flash('Invalid credentials', 'error')
        return redirect(url_for('login'))


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    conn = None
    try:
        conn = psycopg2.connect(
            dbname="MEDISYNC_DB",
            user="postgres",
            password="Chryscelle1!",
            host="localhost",
            port=1234
        )
        c = conn.cursor()
        
        # Get total stocks (sum of quantity of active products)
        c.execute("""
            SELECT SUM(stock_quantity) 
            FROM Product 
            WHERE status = 'active'
        """)
        total_stocks_quantity = c.fetchone()[0] or 0

        # Get total medicines and supplies (count of active products by type)
        c.execute("""
            SELECT 
                SUM(CASE WHEN product_type = 'medicine' THEN 1 ELSE 0 END) as medicines,
                SUM(CASE WHEN product_type = 'supply' THEN 1 ELSE 0 END) as supplies
            FROM Product 
            WHERE status = 'active'
        """)
        result = c.fetchone()
        total_medicines_count = result[0] or 0
        total_supplies_count = result[1] or 0

        # Get stock-ins for this week (medicines and supplies)
        c.execute("""
            SELECT 
                SUM(CASE WHEN pr.product_type = 'medicine' THEN p.purchase_quantity ELSE 0 END) as medicines,
                SUM(CASE WHEN pr.product_type = 'supply' THEN p.purchase_quantity ELSE 0 END) as supplies
            FROM Purchase p
            JOIN Product pr ON p.product_id = pr.id
            WHERE p.purchase_date >= CURRENT_DATE - INTERVAL '7 days'
        """)
        result_stockins = c.fetchone()
        stockins_medicines = result_stockins[0] or 0
        stockins_supplies = result_stockins[1] or 0

        # Get stock-outs for this week (medicines and supplies)
        c.execute("""
            SELECT 
                SUM(CASE WHEN pr.product_type = 'medicine' THEN o.order_quantity ELSE 0 END) as medicines,
                SUM(CASE WHEN pr.product_type = 'supply' THEN o.order_quantity ELSE 0 END) as supplies
            FROM "Order" o
            JOIN Product pr ON o.product_id = pr.id
            WHERE o.order_date >= CURRENT_DATE - INTERVAL '7 days'
        """)
        result_stockouts = c.fetchone()
        stockouts_medicines = result_stockouts[0] or 0
        stockouts_supplies = result_stockouts[1] or 0

        # Get total out of stock items
        c.execute("""
            SELECT COUNT(*) 
            FROM Product 
            WHERE stock_status = 'out of stock' AND status = 'active'
        """)
        total_out_of_stock = c.fetchone()[0] or 0

        # Get total orders
        c.execute("""
            SELECT COUNT(*) 
            FROM "Order"
        """)
        total_orders = c.fetchone()[0] or 0

        # Get total purchases with near-expiry status
        c.execute("""
            SELECT COUNT(*) 
            FROM Purchase 
            WHERE status = 'near expiry'
        """)
        total_expiring_soon = c.fetchone()[0] or 0

        # Get expiring soon items with details
        c.execute("""
            SELECT p.id as code, pr.product_name as name, p.expiration_date as expiration
            FROM Purchase p
            JOIN Product pr ON p.product_id = pr.id
            WHERE p.status = 'near expiry'
            ORDER BY p.expiration_date ASC
        """)
        expiring_soon = [{'code': row[0], 'name': row[1], 'expiration': row[2]} for row in c.fetchall()]

        return render_template('admin.html', 
                             total_stocks=total_stocks_quantity,
                             out_of_stocks=total_out_of_stock,
                             total_orders=total_orders,
                             expiring_soon=expiring_soon,
                             medicines=total_medicines_count,
                             supplies=total_supplies_count,
                             stockins_medicines=stockins_medicines,
                             stockins_supplies=stockins_supplies,
                             stockouts_medicines=stockouts_medicines,
                             stockouts_supplies=stockouts_supplies)
    except Exception as e:
        print(f"Error in dashboard route: {str(e)}")
        flash(f'Error loading dashboard: {str(e)}', 'error')
        return render_template('admin.html', 
                             total_stocks=0,
                             out_of_stocks=0,
                             total_orders=0,
                             expiring_soon=[],
                             medicines=0,
                             supplies=0,
                             stockins_medicines=0,
                             stockins_supplies=0,
                             stockouts_medicines=0,
                             stockouts_supplies=0)
    finally:
        if conn is not None:
            conn.close()

@app.route('/products')
@login_required
def products():
    conn = None
    try:
        conn = psycopg2.connect(
            dbname="MEDISYNC_DB",
            user="postgres",
            password="Chryscelle1!",
            host="localhost",
            port=1234
        )
        c = conn.cursor()
        c.execute("""
            SELECT p.id, p.product_name, p.product_type, p.stock_quantity, 
                   c.category_name, u.unit_name, p.stock_status
            FROM Product p
            LEFT JOIN Category c ON p.category_id = c.id
            LEFT JOIN Unit u ON p.unit_id = u.unit_id
            ORDER BY p.id DESC
        """)
        products = c.fetchall()
        c.execute("SELECT id, category_name FROM Category")
        categories = c.fetchall()
        c.execute("SELECT unit_id, unit_name FROM Unit")
        units = c.fetchall()
        c.execute("SELECT DISTINCT product_type FROM Product")
        product_types = [row[0] for row in c.fetchall()]
        return render_template('products.html', 
                             products=products,
                             categories=categories,
                             units=units,
                             product_types=product_types)
    except Exception as e:
        print(f"Error in products route: {str(e)}")
        flash(f'Error loading products: {str(e)}', 'error')
        return render_template('products.html', products=[], categories=[], units=[], product_types=[])
    finally:
        if conn is not None:
            conn.close()

@app.route('/purchases')
@login_required
def purchases():
    conn = None
    try:
        conn = psycopg2.connect(
            dbname="MEDISYNC_DB",
            user="postgres",
            password="Chryscelle1!",
            host="localhost",
            port=1234
        )
        c = conn.cursor()
        c.execute("""
            SELECT pu.id, pr.product_name, pu.batch_number, pu.purchase_quantity, 
                   pu.remaining_quantity, pu.expiration_date, pu.status, pu.purchase_date
            FROM Purchase pu
            LEFT JOIN Product pr ON pu.product_id = pr.id
            ORDER BY pu.purchase_date DESC
        """)
        purchases = c.fetchall()
        c.execute("SELECT id, product_name FROM Product ORDER BY product_name ASC")
        products = c.fetchall()
        print("Purchases fetched:", purchases)
        return render_template('purchase.html', purchases=purchases, products=products)
    except Exception as e:
        print(f"Error in purchases route: {str(e)}")
        flash(f'Error loading purchases: {str(e)}', 'error')
        return render_template('purchase.html', purchases=[], products=[])
    finally:
        if conn is not None:
            conn.close()

@app.route('/orders')
@login_required
def orders():
    conn = None
    try:
        conn = psycopg2.connect(
            dbname="MEDISYNC_DB",
            user="postgres",
            password="Chryscelle1!",
            host="localhost",
            port=1234
        )
        c = conn.cursor()
        c.execute("""
            SELECT o.order_id, p.product_name, o.order_quantity, o.batch_number, o.order_date
            FROM "Order" o
            LEFT JOIN Product p ON o.product_id = p.id
            ORDER BY o.order_date DESC
        """)
        orders = c.fetchall()
        c.execute("SELECT id, product_name FROM Product ORDER BY product_name ASC")
        products = c.fetchall()
        print("Orders fetched:", orders)
        return render_template('orders.html', orders=orders, products=products)
    except Exception as e:
        print(f"Error in orders route: {str(e)}")
        flash(f'Error loading orders: {str(e)}', 'error')
        return render_template('orders.html', orders=[], products=[])
    finally:
        if conn is not None:
            conn.close()

@app.route('/notification')
@login_required
def notification():
    conn = None
    try:
        conn = psycopg2.connect(
            dbname="MEDISYNC_DB",
            user="postgres",
            password="Chryscelle1!",
            host="localhost",
            port=1234
        )
        c = conn.cursor()
        c.execute("""
            SELECT id, message, created_at, is_read, type
            FROM public.notification
            ORDER BY created_at DESC
        """)
        notifications = c.fetchall()
        print("Fetched notifications:", notifications)  # Debug print
        return render_template('notification.html', notifications=notifications)
    except Exception as e:
        print(f"Error in notification route: {str(e)}")
        flash(f'Error loading notifications: {str(e)}', 'error')
        return render_template('notification.html', notifications=[])
    finally:
        if conn is not None:
            conn.close()

@app.route('/add-product', methods=['POST'])
@login_required
def add_product():
    conn = None
    try:
        conn = psycopg2.connect(
            dbname="MEDISYNC_DB",
            user="postgres",
            password="Chryscelle1!",
            host="localhost",
            port=1234
        )
        c = conn.cursor()
        
        # Get form data
        product_name = request.form['product_name']
        product_type = request.form['product_type']
        category_id = request.form['category_id']
        unit_id = request.form['unit_id']
        
        # Insert new product
        c.execute("""
            INSERT INTO Product (product_name, product_type, category_id, 
                               stock_quantity, unit_id)
            VALUES (%s, %s, %s, 0, %s)
            RETURNING id
        """, (product_name, product_type, category_id, unit_id))
        
        conn.commit()
        flash('Product added successfully!', 'success')
        return redirect(url_for('products'))
        
    except Exception as e:
        if conn:
            conn.rollback()
        flash(f'Error adding product: {str(e)}', 'error')
        return redirect(url_for('products'))
    finally:
        if conn is not None:
            conn.close()

@app.route('/test-db')
def test_db():
    conn = None
    try:
        conn = psycopg2.connect(
            dbname="MEDISYNC_DB",
            user="postgres",
            password="Chryscelle1!",
            host="localhost",
            port=1234
        )
        c = conn.cursor()
        
        # Test Category table
        c.execute("SELECT * FROM Category")
        categories = c.fetchall()
        print("\n=== Categories ===")
        for cat in categories:
            print(cat)
        
        # Test Unit table
        c.execute("SELECT * FROM Unit")
        units = c.fetchall()
        print("\n=== Units ===")
        for unit in units:
            print(unit)
        
        # Test Product table with joins
        c.execute("""
            SELECT p.*, c.category_name, u.unit_name 
            FROM Product p
            LEFT JOIN Category c ON p.category_id = c.id
            LEFT JOIN Unit u ON p.unit_id = u.unit_id
        """)
        products = c.fetchall()
        print("\n=== Products ===")
        for prod in products:
            print(prod)
        
        return jsonify({
            'categories': categories,
            'units': units,
            'products': products
        })
    except Exception as e:
        print(f"Database test error: {str(e)}")
        return jsonify({'error': str(e)})
    finally:
        if conn is not None:
            conn.close()

@app.route('/init-sample-data')
def init_sample_data():
    conn = None
    try:
        conn = psycopg2.connect(
            dbname="MEDISYNC_DB",
            user="postgres",
            password="Chryscelle1!",
            host="localhost",
            port=1234
        )
        c = conn.cursor()
        
        # Insert sample categories
        categories = [
            ('Analgesics',),
            ('Antibiotics',),
            ('Antihistamines',),
            ('First Aid',)
        ]
        c.executemany("INSERT INTO Category (category_name) VALUES (%s)", categories)
        
        # Insert sample units
        units = [
            ('Tablet',),
            ('Capsule',),
            ('Bottle',),
            ('Box',)
        ]
        c.executemany("INSERT INTO Unit (unit_name) VALUES (%s)", units)
        
        # Insert sample products
        products = [
            ('Paracetamol 500mg', 'medicine', 1, 100, 100, 1, 'in stock'),
            ('Amoxicillin 500mg', 'medicine', 2, 50, 50, 2, 'in stock'),
            ('Band-aid', 'supply', 4, 200, 50, 4, 'low stock'),
            ('Antihistamine Syrup', 'medicine', 3, 30, 5, 3, 'out of stock')
        ]
        c.executemany("""
            INSERT INTO Product 
            (product_name, product_type, category_id, starting_inventory, 
            stock_quantity, unit_id, stock_status) 
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, products)
        
        conn.commit()
        return jsonify({'message': 'Sample data initialized successfully'})
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)})
    finally:
        if conn is not None:
            conn.close()

@app.route('/add-purchase', methods=['POST'])
@login_required
def add_purchase():
    conn = None
    try:
        conn = psycopg2.connect(
            dbname="MEDISYNC_DB",
            user="postgres",
            password="Chryscelle1!",
            host="localhost",
            port=1234
        )
        c = conn.cursor()
        product_id = request.form['product_id']
        purchase_quantity = int(request.form['purchase_quantity'])
        expiration_date = request.form['expiration_date']
        c.execute("""
            INSERT INTO Purchase (product_id, purchase_quantity, remaining_quantity, expiration_date)
            VALUES (%s, %s, %s, %s)
        """, (product_id, purchase_quantity, purchase_quantity, expiration_date))
        conn.commit()
        flash('Purchase added successfully!', 'success')
        return redirect(url_for('purchases'))
    except Exception as e:
        if conn:
            conn.rollback()
        flash(f'Error adding purchase: {str(e)}', 'error')
        return redirect(url_for('purchases'))
    finally:
        if conn is not None:
            conn.close()

@app.route('/add-order', methods=['POST'])
@login_required
def add_order():
    conn = None
    try:
        conn = psycopg2.connect(
            dbname="MEDISYNC_DB",
            user="postgres",
            password="Chryscelle1!",
            host="localhost",
            port=1234
        )
        c = conn.cursor()
        product_id = request.form['product_id']
        batch_number = request.form['batch_number']
        order_quantity = int(request.form['order_quantity'])
        c.execute("""
            INSERT INTO "Order" (product_id, order_quantity, batch_number)
            VALUES (%s, %s, %s)
        """, (product_id, order_quantity, batch_number))
        conn.commit()
        flash('Order added successfully!', 'success')
        return redirect(url_for('orders'))
    except Exception as e:
        if conn:
            conn.rollback()
        flash(f'Error adding order: {str(e)}', 'error')
        return redirect(url_for('orders'))
    finally:
        if conn is not None:
            conn.close()

def get_notifications(limit=10):
    conn = psycopg2.connect(
        dbname="MEDISYNC_DB",
            user="postgres",
            password="Chryscelle1!",
            host="localhost",
            port=1234
    )
    c = conn.cursor()
    c.execute("SELECT id, message, created_at, is_read FROM Notification ORDER BY created_at DESC LIMIT %s", (limit,))
    notifications = c.fetchall()
    conn.close()
    return notifications

if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=8080)