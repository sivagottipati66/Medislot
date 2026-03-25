from flask import Flask, render_template, request, redirect
import sqlite3

app = Flask(__name__)

# ---------------- DATABASE ----------------
def get_db():
    conn = sqlite3.connect('database.db')
    conn.row_factory = lambda cursor, row: {
        col[0]: row[idx] for idx, col in enumerate(cursor.description)
    }
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute('''CREATE TABLE IF NOT EXISTS hospitals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        location TEXT)''')

    cur.execute('''CREATE TABLE IF NOT EXISTS doctors (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        specialization TEXT,
        hospital_id INTEGER)''')

    cur.execute('''CREATE TABLE IF NOT EXISTS slots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        doctor_id INTEGER,
        time TEXT,
        is_booked INTEGER DEFAULT 0)''')

    cur.execute('''CREATE TABLE IF NOT EXISTS cart (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        doctor_id INTEGER,
        slot_id INTEGER,
        patient_name TEXT,
        age INTEGER,
        gender TEXT)''')

    cur.execute('''CREATE TABLE IF NOT EXISTS appointments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        doctor_id INTEGER,
        slot_id INTEGER,
        patient_name TEXT,
        payment_status TEXT,
        reference_id TEXT)''')

    conn.commit()
    conn.close()

# ---------------- UTIL ----------------
def get_cart_count():
    conn = get_db()
    result = conn.execute("SELECT COUNT(*) as total FROM cart").fetchone()
    conn.close()
    return result['total']

# ---------------- SAMPLE DATA ----------------
def add_sample_data():
    conn = get_db()
    cur = conn.cursor()

    # Clear old data
    cur.execute("DELETE FROM hospitals")
    cur.execute("DELETE FROM doctors")
    cur.execute("DELETE FROM slots")

    # Hospitals
    hospitals = [
        ("Apollo Hospital", "Chennai"),
        ("AIIMS", "Delhi"),
        ("Fortis", "Bangalore"),
        ("KIMS", "Hyderabad"),
        ("Global", "Mumbai")
    ]

    for h in hospitals:
        cur.execute("INSERT INTO hospitals (name, location) VALUES (?, ?)", h)

    hospital_ids = cur.execute("SELECT id FROM hospitals").fetchall()

    # Doctors (5 per specialization across hospitals)
    specializations = ["Cardiologist", "Dentist", "Neurologist", "Dermatologist", "Orthopedic"]

    doctor_names = [
        ["Dr. Ravi", "Dr. Arun", "Dr. Meena", "Dr. Kiran", "Dr. Raj"],
        ["Dr. Priya", "Dr. Ajay", "Dr. Neha", "Dr. Ramesh", "Dr. Kavya"],
        ["Dr. Arjun", "Dr. Vivek", "Dr. Suresh", "Dr. Deepak", "Dr. Rahul"],
        ["Dr. Sneha", "Dr. Pooja", "Dr. Anjali", "Dr. Divya", "Dr. Nisha"],
        ["Dr. Kumar", "Dr. Manoj", "Dr. Rakesh", "Dr. Vikas", "Dr. Sanjay"]
    ]

    for i, spec in enumerate(specializations):
        for j, name in enumerate(doctor_names[i]):
            cur.execute(
                "INSERT INTO doctors (name, specialization, hospital_id) VALUES (?, ?, ?)",
                (name, spec, hospital_ids[j]['id'])
            )

    # Slots
    doctor_ids = cur.execute("SELECT id FROM doctors").fetchall()

    def generate_slots(start, end):
        slots = []
        for h in range(start, end):
            for m in [0, 20, 40]:
                slots.append(f"{h:02d}:{m:02d}")
        return slots

    all_slots = generate_slots(9, 12) + generate_slots(14, 17)

    for doc in doctor_ids:
        for t in all_slots:
            cur.execute("INSERT INTO slots (doctor_id, time) VALUES (?, ?)", (doc['id'], t))

    conn.commit()
    conn.close()

# ---------------- INIT ----------------
init_db()
add_sample_data()

# ---------------- ROUTES ----------------

@app.route('/')
def index():
    return redirect('/hospitals')

@app.route('/hospitals')
def hospitals():
    conn = get_db()
    hospitals = conn.execute("SELECT * FROM hospitals").fetchall()
    conn.close()
    return render_template('hospitals.html', hospitals=hospitals, cart_count=get_cart_count())

@app.route('/doctors/<int:hospital_id>')
def doctors(hospital_id):
    conn = get_db()
    doctors = conn.execute("SELECT * FROM doctors WHERE hospital_id=?", (hospital_id,)).fetchall()
    conn.close()
    return render_template('doctors.html', doctors=doctors, cart_count=get_cart_count())

@app.route('/slots/<int:doctor_id>')
def slots(doctor_id):
    conn = get_db()
    slots = conn.execute(
        "SELECT * FROM slots WHERE doctor_id=? AND is_booked=0",
        (doctor_id,)
    ).fetchall()
    conn.close()
    return render_template('slots.html', slots=slots, cart_count=get_cart_count())

@app.route('/patient_form/<int:slot_id>', methods=['GET','POST'])
def patient_form(slot_id):
    if request.method == 'POST':
        name = request.form['name']
        age = request.form['age']
        gender = request.form['gender']

        conn = get_db()

        slot = conn.execute("SELECT doctor_id FROM slots WHERE id=?", (slot_id,)).fetchone()

        conn.execute("""
            INSERT INTO cart (doctor_id, slot_id, patient_name, age, gender)
            VALUES (?, ?, ?, ?, ?)
        """, (slot['doctor_id'], slot_id, name, age, gender))

        conn.commit()
        conn.close()

        return redirect('/hospitals')

    return render_template('patient_form.html', cart_count=get_cart_count())

@app.route('/checkout')
def checkout():
    conn = get_db()

    items = conn.execute("""
        SELECT cart.*, doctors.name AS doctor_name, slots.time
        FROM cart
        JOIN doctors ON cart.doctor_id = doctors.id
        JOIN slots ON cart.slot_id = slots.id
    """).fetchall()

    total = len(items) * 200

    conn.close()
    return render_template('checkout.html', items=items, total=total, cart_count=get_cart_count())

# ---------------- PAYMENT ----------------
@app.route('/payment', methods=['GET','POST'])
def payment():
    if request.method == 'POST':
        status = request.form['payment_status']
        ref = request.form.get('reference_id')

        conn = get_db()
        cart = conn.execute("SELECT * FROM cart").fetchall()

        for item in cart:

            # ✅ PAYMENT DONE
            if status == "Payment Done":
                conn.execute("""
                    INSERT INTO appointments
                    (doctor_id, slot_id, patient_name, payment_status, reference_id)
                    VALUES (?, ?, ?, ?, ?)
                """, (item['doctor_id'], item['slot_id'], item['patient_name'], "Confirmed", None))

                conn.execute("UPDATE slots SET is_booked=1 WHERE id=?", (item['slot_id'],))

            # ❌ PAYMENT FAILED
            elif status == "Payment Failed":
                return "Payment Failed ❌. Try again."

            # ⏳ UNDER PROCESS
            elif status == "Payment Under Process":

                if not ref:
                    return "Reference ID is required!"

                conn.execute("""
                    INSERT INTO appointments
                    (doctor_id, slot_id, patient_name, payment_status, reference_id)
                    VALUES (?, ?, ?, ?, ?)
                """, (item['doctor_id'], item['slot_id'], item['patient_name'], "Waiting", ref))

                conn.execute("UPDATE slots SET is_booked=1 WHERE id=?", (item['slot_id'],))

        conn.execute("DELETE FROM cart")

        conn.commit()
        conn.close()

        return "Appointment Processed Successfully!"

    return render_template('payment.html', cart_count=get_cart_count())

# ---------------- RUN ----------------
if __name__ == '__main__':
    app.run(debug=True)
