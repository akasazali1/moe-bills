from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file
from config import Config
from utils.supabase_client import supabase
import os
import io
import csv
import zipfile
from datetime import datetime

app = Flask(__name__)
app.secret_key = Config.SECRET_KEY

# ---------- Helper Functions ----------
def get_current_user():
    """Returns the logged-in user's email from session."""
    return session.get('user_email')

def get_current_year():
    return datetime.now().year

def update_budget_used(year):
    """Recalculates total spent from all utilities + SUT for the given year and updates the budget table."""
    # Sum water payments
    water_sum = supabase.table('water_bills').select('amount_paid').eq('year', year).execute()
    water_total = sum([item['amount_paid'] or 0 for item in water_sum.data])

    # Sum electricity payments
    elec_sum = supabase.table('electricity_bills').select('amount_paid').eq('year', year).execute()
    elec_total = sum([item['amount_paid'] or 0 for item in elec_sum.data])

    # Sum telephone payments
    tel_sum = supabase.table('telephone_bills').select('amount_paid').eq('year', year).execute()
    tel_total = sum([item['amount_paid'] or 0 for item in tel_sum.data])

    # Sum SUT spending
    sut_sum = supabase.table('sut_spending').select('amount').eq('year', year).execute()
    sut_total = sum([item['amount'] or 0 for item in sut_sum.data])

    total_used = water_total + elec_total + tel_total + sut_total

    # Update the budget table for this year
    supabase.table('budget').update({'used_budget': total_used}).eq('year', year).execute()

def get_budget(year):
    """Returns total_budget, used_budget, remaining for a given year."""
    res = supabase.table('budget').select('*').eq('year', year).execute()
    if res.data:
        data = res.data[0]
        total = data['total_budget'] or 0
        used = data['used_budget'] or 0
        return total, used, total - used
    return 0, 0, 0

# ---------- Authentication Routes ----------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        try:
            # Sign in with Supabase Auth
            auth_res = supabase.auth.sign_in_with_password({"email": email, "password": password})
            user = auth_res.user
            session['user_email'] = user.email
            session['user_id'] = user.id
            return redirect(url_for('dashboard'))
        except Exception as e:
            return render_template('login.html', error="Invalid email or password. Please try again.")
    return render_template('login.html', error=None)

@app.route('/logout')
def logout():
    supabase.auth.sign_out()
    session.clear()
    return redirect(url_for('login'))

# ---------- Dashboard ----------
@app.route('/')
def dashboard():
    if not get_current_user():
        return redirect(url_for('login'))
    
    year = get_current_year()
    total, used, remaining = get_budget(year)
    
    # Get latest entries (last 5 for each utility)
    water_latest = supabase.table('water_bills').select('*').eq('year', year).order('created_at', desc=True).limit(5).execute()
    elec_latest = supabase.table('electricity_bills').select('*').eq('year', year).order('created_at', desc=True).limit(5).execute()
    tel_latest = supabase.table('telephone_bills').select('*').eq('year', year).order('created_at', desc=True).limit(5).execute()
    
    return render_template('dashboard.html', 
                           user=session['user_email'],
                           total=total, used=used, remaining=remaining,
                           water=water_latest.data,
                           electricity=elec_latest.data,
                           telephone=tel_latest.data,
                           year=year)

# ---------- Water Bills ----------
@app.route('/water', methods=['GET', 'POST'])
def water():
    if not get_current_user():
        return redirect(url_for('login'))
    
    year = get_current_year()
    
    if request.method == 'POST':
        # Add new water bill
        data = {
            'department_id': int(request.form['department_id']),
            'account_number': request.form['account_number'],
            'meter_number': request.form['meter_number'],
            'consumption': float(request.form['consumption']),
            'bill_amount': float(request.form['bill_amount']),
            'outstanding': float(request.form['outstanding']),
            'amount_paid': float(request.form['amount_paid']),
            'notes': request.form['notes'],
            'month': int(request.form['month']),
            'year': year,
            'updated_by': get_current_user()
        }
        supabase.table('water_bills').insert(data).execute()
        update_budget_used(year)  # Recalculate budget
        return redirect(url_for('water'))
    
    # GET: show list
    records = supabase.table('water_bills').select('*, departments(name)').eq('year', year).order('month', desc=True).execute()
    departments = supabase.table('departments').select('*').execute()
    return render_template('water.html', records=records.data, departments=departments.data, year=year, user=get_current_user())

@app.route('/water/edit/<int:id>', methods=['POST'])
def water_edit(id):
    if not get_current_user():
        return redirect(url_for('login'))
    data = {
        'department_id': int(request.form['department_id']),
        'account_number': request.form['account_number'],
        'meter_number': request.form['meter_number'],
        'consumption': float(request.form['consumption']),
        'bill_amount': float(request.form['bill_amount']),
        'outstanding': float(request.form['outstanding']),
        'amount_paid': float(request.form['amount_paid']),
        'notes': request.form['notes'],
        'month': int(request.form['month']),
        'updated_by': get_current_user()
    }
    supabase.table('water_bills').update(data).eq('id', id).execute()
    update_budget_used(get_current_year())
    return redirect(url_for('water'))

@app.route('/water/delete/<int:id>')
def water_delete(id):
    if not get_current_user():
        return redirect(url_for('login'))
    supabase.table('water_bills').delete().eq('id', id).execute()
    update_budget_used(get_current_year())
    return redirect(url_for('water'))

# ---------- Electricity Bills (similar structure) ----------
@app.route('/electricity', methods=['GET', 'POST'])
def electricity():
    if not get_current_user():
        return redirect(url_for('login'))
    year = get_current_year()
    if request.method == 'POST':
        data = {
            'department_id': int(request.form['department_id']),
            'account_number': request.form['account_number'],
            'meter_number': request.form['meter_number'],
            'consumption': float(request.form['consumption']),
            'bill_amount': float(request.form['bill_amount']),
            'outstanding': float(request.form['outstanding']),
            'amount_paid': float(request.form['amount_paid']),
            'notes': request.form['notes'],
            'month': int(request.form['month']),
            'year': year,
            'updated_by': get_current_user()
        }
        supabase.table('electricity_bills').insert(data).execute()
        update_budget_used(year)
        return redirect(url_for('electricity'))
    records = supabase.table('electricity_bills').select('*, departments(name)').eq('year', year).order('month', desc=True).execute()
    departments = supabase.table('departments').select('*').execute()
    return render_template('electricity.html', records=records.data, departments=departments.data, year=year, user=get_current_user())

@app.route('/electricity/edit/<int:id>', methods=['POST'])
def electricity_edit(id):
    if not get_current_user():
        return redirect(url_for('login'))
    data = {
        'department_id': int(request.form['department_id']),
        'account_number': request.form['account_number'],
        'meter_number': request.form['meter_number'],
        'consumption': float(request.form['consumption']),
        'bill_amount': float(request.form['bill_amount']),
        'outstanding': float(request.form['outstanding']),
        'amount_paid': float(request.form['amount_paid']),
        'notes': request.form['notes'],
        'month': int(request.form['month']),
        'updated_by': get_current_user()
    }
    supabase.table('electricity_bills').update(data).eq('id', id).execute()
    update_budget_used(get_current_year())
    return redirect(url_for('electricity'))

@app.route('/electricity/delete/<int:id>')
def electricity_delete(id):
    if not get_current_user():
        return redirect(url_for('login'))
    supabase.table('electricity_bills').delete().eq('id', id).execute()
    update_budget_used(get_current_year())
    return redirect(url_for('electricity'))

# ---------- Telephone Bills ----------
@app.route('/telephone', methods=['GET', 'POST'])
def telephone():
    if not get_current_user():
        return redirect(url_for('login'))
    year = get_current_year()
    if request.method == 'POST':
        data = {
            'department_id': int(request.form['department_id']),
            'account_number': request.form['account_number'],
            'phone_numbers': request.form['phone_numbers'],
            'bill_no': request.form['bill_no'],
            'total_account_charges': float(request.form['total_account_charges']),
            'outstanding': float(request.form['outstanding']),
            'previous_payment': float(request.form['previous_payment']),
            'total_current': float(request.form['total_current']),
            'amount_paid': float(request.form['amount_paid']),
            'notes': request.form['notes'],
            'month': int(request.form['month']),
            'year': year,
            'updated_by': get_current_user()
        }
        supabase.table('telephone_bills').insert(data).execute()
        update_budget_used(year)
        return redirect(url_for('telephone'))
    records = supabase.table('telephone_bills').select('*, departments(name)').eq('year', year).order('month', desc=True).execute()
    departments = supabase.table('departments').select('*').execute()
    return render_template('telephone.html', records=records.data, departments=departments.data, year=year, user=get_current_user())

@app.route('/telephone/edit/<int:id>', methods=['POST'])
def telephone_edit(id):
    if not get_current_user():
        return redirect(url_for('login'))
    data = {
        'department_id': int(request.form['department_id']),
        'account_number': request.form['account_number'],
        'phone_numbers': request.form['phone_numbers'],
        'bill_no': request.form['bill_no'],
        'total_account_charges': float(request.form['total_account_charges']),
        'outstanding': float(request.form['outstanding']),
        'previous_payment': float(request.form['previous_payment']),
        'total_current': float(request.form['total_current']),
        'amount_paid': float(request.form['amount_paid']),
        'notes': request.form['notes'],
        'month': int(request.form['month']),
        'updated_by': get_current_user()
    }
    supabase.table('telephone_bills').update(data).eq('id', id).execute()
    update_budget_used(get_current_year())
    return redirect(url_for('telephone'))

@app.route('/telephone/delete/<int:id>')
def telephone_delete(id):
    if not get_current_user():
        return redirect(url_for('login'))
    supabase.table('telephone_bills').delete().eq('id', id).execute()
    update_budget_used(get_current_year())
    return redirect(url_for('telephone'))

# ---------- SUT Office Spending ----------
@app.route('/sut', methods=['GET', 'POST'])
def sut():
    if not get_current_user():
        return redirect(url_for('login'))
    year = get_current_year()
    if request.method == 'POST':
        data = {
            'year': year,
            'month': int(request.form['month']),
            'description': request.form['description'],
            'amount': float(request.form['amount']),
            'updated_by': get_current_user()
        }
        supabase.table('sut_spending').insert(data).execute()
        update_budget_used(year)
        return redirect(url_for('sut'))
    records = supabase.table('sut_spending').select('*').eq('year', year).order('month', desc=True).execute()
    return render_template('sut.html', records=records.data, year=year, user=get_current_user())

@app.route('/sut/delete/<int:id>')
def sut_delete(id):
    if not get_current_user():
        return redirect(url_for('login'))
    supabase.table('sut_spending').delete().eq('id', id).execute()
    update_budget_used(get_current_year())
    return redirect(url_for('sut'))

# ---------- Reports ----------
@app.route('/reports', methods=['GET', 'POST'])
def reports():
    if not get_current_user():
        return redirect(url_for('login'))
    results = []
    selected_dept = None
    if request.method == 'POST':
        dept_id = request.form.get('department_id')
        year = request.form.get('year')
        month = request.form.get('month')
        selected_dept = dept_id
        
        # Fetch water
        water_q = supabase.table('water_bills').select('*, departments(name)').eq('year', year)
        if dept_id:
            water_q = water_q.eq('department_id', dept_id)
        if month:
            water_q = water_q.eq('month', month)
        water_data = water_q.execute().data
        
        # Fetch electricity
        elec_q = supabase.table('electricity_bills').select('*, departments(name)').eq('year', year)
        if dept_id:
            elec_q = elec_q.eq('department_id', dept_id)
        if month:
            elec_q = elec_q.eq('month', month)
        elec_data = elec_q.execute().data
        
        # Fetch telephone
        tel_q = supabase.table('telephone_bills').select('*, departments(name)').eq('year', year)
        if dept_id:
            tel_q = tel_q.eq('department_id', dept_id)
        if month:
            tel_q = tel_q.eq('month', month)
        tel_data = tel_q.execute().data
        
        results = {
            'water': water_data,
            'electricity': elec_data,
            'telephone': tel_data,
            'year': year,
            'month': month
        }
    
    departments = supabase.table('departments').select('*').execute()
    return render_template('reports.html', departments=departments.data, results=results, selected_dept=selected_dept)

# ---------- Backup (Download all data as CSV in a ZIP) ----------
@app.route('/backup')
def backup():
    if not get_current_user():
        return redirect(url_for('login'))
    
    # Fetch all tables
    tables = ['water_bills', 'electricity_bills', 'telephone_bills', 'sut_spending', 'departments', 'budget']
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w') as zip_file:
        for table in tables:
            res = supabase.table(table).select('*').execute()
            data = res.data
            if not data:
                continue
            # Write CSV
            csv_buffer = io.StringIO()
            writer = csv.DictWriter(csv_buffer, fieldnames=data[0].keys())
            writer.writeheader()
            writer.writerows(data)
            zip_file.writestr(f"{table}.csv", csv_buffer.getvalue())
    
    zip_buffer.seek(0)
    return send_file(zip_buffer, as_attachment=True, download_name=f"backup_{datetime.now().strftime('%Y%m%d')}.zip", mimetype='application/zip')

# ---------- Print (single record) ----------
@app.route('/print/water/<int:id>')
def print_water(id):
    if not get_current_user():
        return redirect(url_for('login'))
    record = supabase.table('water_bills').select('*, departments(name)').eq('id', id).execute()
    return render_template('print_water.html', record=record.data[0])

@app.route('/print/electricity/<int:id>')
def print_electricity(id):
    if not get_current_user():
        return redirect(url_for('login'))
    record = supabase.table('electricity_bills').select('*, departments(name)').eq('id', id).execute()
    return render_template('print_electricity.html', record=record.data[0])

@app.route('/print/telephone/<int:id>')
def print_telephone(id):
    if not get_current_user():
        return redirect(url_for('login'))
    record = supabase.table('telephone_bills').select('*, departments(name)').eq('id', id).execute()
    return render_template('print_telephone.html', record=record.data[0])

if __name__ == '__main__':
    app.run(debug=True)
