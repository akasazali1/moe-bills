from flask import Flask, render_template, request, redirect, url_for, session, send_file
from config import Config
from utils.supabase_client import supabase
import os
import io
import csv
import zipfile
from datetime import datetime

app = Flask(__name__)
app.secret_key = Config.SECRET_KEY

# ---- Debug ----
@app.route('/debug')
def debug():
    return f"SUPABASE_URL: {os.environ.get('SUPABASE_URL')}<br>SUPABASE_KEY (first 20 chars): {os.environ.get('SUPABASE_KEY', '')[:20] if os.environ.get('SUPABASE_KEY') else 'None'}"

# ---- Helpers ----
def is_logged_in():
    return session.get('logged_in', False)

def get_current_user():
    return session.get('username', 'Staff')

def get_current_year():
    return datetime.now().year

def update_budget_used(year):
    try:
        water_sum = supabase.table('water_bills').select('amount_paid').eq('year', year).execute()
        water_total = sum([item['amount_paid'] or 0 for item in water_sum.data])
        elec_sum = supabase.table('electricity_bills').select('amount_paid').eq('year', year).execute()
        elec_total = sum([item['amount_paid'] or 0 for item in elec_sum.data])
        tel_sum = supabase.table('telephone_bills').select('amount_paid').eq('year', year).execute()
        tel_total = sum([item['amount_paid'] or 0 for item in tel_sum.data])
        sut_sum = supabase.table('sut_spending').select('amount').eq('year', year).execute()
        sut_total = sum([item['amount'] or 0 for item in sut_sum.data])
        total_used = water_total + elec_total + tel_total + sut_total
        supabase.table('budget').update({'used_budget': total_used}).eq('year', year).execute()
        return True
    except Exception as e:
        print(f"Budget update error: {e}")
        return False

def get_budget(year):
    try:
        res = supabase.table('budget').select('*').eq('year', year).execute()
        if res.data:
            data = res.data[0]
            total = data.get('total_budget', 0) or 0
            used = data.get('used_budget', 0) or 0
            return total, used, total - used
        return 0, 0, 0
    except Exception as e:
        print(f"Budget fetch error: {e}")
        return 0, 0, 0

# ---- Auth ----
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form.get('password') == os.environ.get('SIMPLE_PASSWORD', 'admin123'):
            session['logged_in'] = True
            session['username'] = 'Staff'
            return redirect(url_for('dashboard'))
        return render_template('login.html', error="Invalid password.")
    return render_template('login.html', error=None)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ---- Dashboard ----
@app.route('/')
def dashboard():
    if not is_logged_in():
        return redirect(url_for('login'))
    year = get_current_year()
    total, used, remaining = get_budget(year)
    water_latest = elec_latest = tel_latest = []
    try:
        water_latest = supabase.table('water_bills').select('*, departments(name)').eq('year', year).order('created_at', desc=True).limit(5).execute().data
    except Exception as e:
        print("Water fetch error:", e)
    try:
        elec_latest = supabase.table('electricity_bills').select('*, departments(name)').eq('year', year).order('created_at', desc=True).limit(5).execute().data
    except Exception as e:
        print("Electricity fetch error:", e)
    try:
        tel_latest = supabase.table('telephone_bills').select('*, departments(name)').eq('year', year).order('created_at', desc=True).limit(5).execute().data
    except Exception as e:
        print("Telephone fetch error:", e)
    return render_template('dashboard.html', user=session.get('username', 'Staff'),
                           total=total, used=used, remaining=remaining,
                           water=water_latest, electricity=elec_latest,
                           telephone=tel_latest, year=year)

# ---- Water ----
@app.route('/water', methods=['GET', 'POST'])
def water():
    if not is_logged_in():
        return redirect(url_for('login'))
    year = get_current_year()
    if request.method == 'POST':
        try:
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
            update_budget_used(year)
        except Exception as e:
            print("Water insert error:", e)
        return redirect(url_for('water'))
    records = []
    departments = []
    try:
        records = supabase.table('water_bills').select('*, departments(name)').eq('year', year).order('month', desc=True).execute().data
        departments = supabase.table('departments').select('*').execute().data
    except Exception as e:
        print("Water fetch error:", e)
    return render_template('water.html', records=records, departments=departments, year=year, user=get_current_user())

@app.route('/water/edit/<int:id>', methods=['POST'])
def water_edit(id):
    if not is_logged_in():
        return redirect(url_for('login'))
    try:
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
    except Exception as e:
        print("Water edit error:", e)
    return redirect(url_for('water'))

@app.route('/water/delete/<int:id>')
def water_delete(id):
    if not is_logged_in():
        return redirect(url_for('login'))
    try:
        supabase.table('water_bills').delete().eq('id', id).execute()
        update_budget_used(get_current_year())
    except Exception as e:
        print("Water delete error:", e)
    return redirect(url_for('water'))

# ---- Electricity ----
@app.route('/electricity', methods=['GET', 'POST'])
def electricity():
    if not is_logged_in():
        return redirect(url_for('login'))
    year = get_current_year()
    if request.method == 'POST':
        try:
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
        except Exception as e:
            print("Electricity insert error:", e)
        return redirect(url_for('electricity'))
    records = []
    departments = []
    try:
        records = supabase.table('electricity_bills').select('*, departments(name)').eq('year', year).order('month', desc=True).execute().data
        departments = supabase.table('departments').select('*').execute().data
    except Exception as e:
        print("Electricity fetch error:", e)
    return render_template('electricity.html', records=records, departments=departments, year=year, user=get_current_user())

@app.route('/electricity/edit/<int:id>', methods=['POST'])
def electricity_edit(id):
    if not is_logged_in():
        return redirect(url_for('login'))
    try:
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
    except Exception as e:
        print("Electricity edit error:", e)
    return redirect(url_for('electricity'))

@app.route('/electricity/delete/<int:id>')
def electricity_delete(id):
    if not is_logged_in():
        return redirect(url_for('login'))
    try:
        supabase.table('electricity_bills').delete().eq('id', id).execute()
        update_budget_used(get_current_year())
    except Exception as e:
        print("Electricity delete error:", e)
    return redirect(url_for('electricity'))

# ---- Telephone ----
@app.route('/telephone', methods=['GET', 'POST'])
def telephone():
    if not is_logged_in():
        return redirect(url_for('login'))
    year = get_current_year()
    if request.method == 'POST':
        try:
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
        except Exception as e:
            print("Telephone insert error:", e)
        return redirect(url_for('telephone'))
    records = []
    departments = []
    try:
        records = supabase.table('telephone_bills').select('*, departments(name)').eq('year', year).order('month', desc=True).execute().data
        departments = supabase.table('departments').select('*').execute().data
    except Exception as e:
        print("Telephone fetch error:", e)
    return render_template('telephone.html', records=records, departments=departments, year=year, user=get_current_user())

@app.route('/telephone/edit/<int:id>', methods=['POST'])
def telephone_edit(id):
    if not is_logged_in():
        return redirect(url_for('login'))
    try:
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
    except Exception as e:
        print("Telephone edit error:", e)
    return redirect(url_for('telephone'))

@app.route('/telephone/delete/<int:id>')
def telephone_delete(id):
    if not is_logged_in():
        return redirect(url_for('login'))
    try:
        supabase.table('telephone_bills').delete().eq('id', id).execute()
        update_budget_used(get_current_year())
    except Exception as e:
        print("Telephone delete error:", e)
    return redirect(url_for('telephone'))

# ---- SUT ----
@app.route('/sut', methods=['GET', 'POST'])
def sut():
    if not is_logged_in():
        return redirect(url_for('login'))
    year = get_current_year()
    if request.method == 'POST':
        try:
            data = {
                'year': year,
                'month': int(request.form['month']),
                'description': request.form['description'],
                'amount': float(request.form['amount']),
                'updated_by': get_current_user()
            }
            supabase.table('sut_spending').insert(data).execute()
            update_budget_used(year)
        except Exception as e:
            print("SUT insert error:", e)
        return redirect(url_for('sut'))
    records = []
    try:
        records = supabase.table('sut_spending').select('*').eq('year', year).order('month', desc=True).execute().data
    except Exception as e:
        print("SUT fetch error:", e)
    return render_template('sut.html', records=records, year=year, user=get_current_user())

@app.route('/sut/delete/<int:id>')
def sut_delete(id):
    if not is_logged_in():
        return redirect(url_for('login'))
    try:
        supabase.table('sut_spending').delete().eq('id', id).execute()
        update_budget_used(get_current_year())
    except Exception as e:
        print("SUT delete error:", e)
    return redirect(url_for('sut'))

# ---- Reports ----
@app.route('/reports', methods=['GET', 'POST'])
def reports():
    if not is_logged_in():
        return redirect(url_for('login'))
    results = {}
    selected_dept = None
    departments = []
    try:
        departments = supabase.table('departments').select('*').execute().data
    except Exception as e:
        print("Departments fetch error:", e)
    if request.method == 'POST':
        dept_id = request.form.get('department_id')
        year = request.form.get('year')
        month = request.form.get('month')
        selected_dept = dept_id
        water_data = elec_data = tel_data = []
        try:
            water_q = supabase.table('water_bills').select('*, departments(name)').eq('year', year)
            if dept_id: water_q = water_q.eq('department_id', dept_id)
            if month: water_q = water_q.eq('month', month)
            water_data = water_q.execute().data
        except Exception as e:
            print("Water report error:", e)
        try:
            elec_q = supabase.table('electricity_bills').select('*, departments(name)').eq('year', year)
            if dept_id: elec_q = elec_q.eq('department_id', dept_id)
            if month: elec_q = elec_q.eq('month', month)
            elec_data = elec_q.execute().data
        except Exception as e:
            print("Electricity report error:", e)
        try:
            tel_q = supabase.table('telephone_bills').select('*, departments(name)').eq('year', year)
            if dept_id: tel_q = tel_q.eq('department_id', dept_id)
            if month: tel_q = tel_q.eq('month', month)
            tel_data = tel_q.execute().data
        except Exception as e:
            print("Telephone report error:", e)
        results = {'water': water_data, 'electricity': elec_data, 'telephone': tel_data, 'year': year, 'month': month}
    return render_template('reports.html', departments=departments, results=results, selected_dept=selected_dept)

# ---- Central Print ----
@app.route('/print', methods=['GET', 'POST'])
def print_select():
    if not is_logged_in():
        return redirect(url_for('login'))
    departments = []
    try:
        departments = supabase.table('departments').select('*').execute().data
    except Exception as e:
        print("Departments fetch error:", e)
    year = get_current_year()
    if request.method == 'POST':
        utility = request.form['utility']
        year = request.form['year']
        month = request.form.get('month')
        dept_id = request.form.get('department_id')
        table_map = {'water': 'water_bills', 'electricity': 'electricity_bills', 'telephone': 'telephone_bills'}
        table = table_map[utility]
        records = []
        try:
            query = supabase.table(table).select('*, departments(name)').eq('year', year)
            if month and month.strip(): query = query.eq('month', month)
            if dept_id and dept_id.strip(): query = query.eq('department_id', dept_id)
            records = query.execute().data
        except Exception as e:
            print("Print fetch error:", e)
        return render_template('print_list.html', utility=utility, records=records,
                               year=year, month=month, now=datetime.now().strftime('%Y-%m-%d %H:%M'))
    return render_template('print_select.html', departments=departments, year=year)

@app.route('/print/single/<utility>/<int:id>')
def print_single(utility, id):
    if not is_logged_in():
        return redirect(url_for('login'))
    table_map = {'water': 'water_bills', 'electricity': 'electricity_bills', 'telephone': 'telephone_bills'}
    if utility not in table_map:
        return "Invalid utility", 404
    table = table_map[utility]
    record = None
    try:
        res = supabase.table(table).select('*, departments(name)').eq('id', id).execute()
        if res.data:
            record = res.data[0]
    except Exception as e:
        print("Single print error:", e)
    if not record:
        return "Record not found", 404
    return render_template('print_single.html', utility=utility, record=record)

# ---- Backup ----
@app.route('/backup')
def backup():
    if not is_logged_in():
        return redirect(url_for('login'))
    tables = ['water_bills', 'electricity_bills', 'telephone_bills', 'sut_spending', 'departments', 'budget']
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w') as zip_file:
        for table in tables:
            try:
                res = supabase.table(table).select('*').execute()
                data = res.data
                if data:
                    csv_buffer = io.StringIO()
                    writer = csv.DictWriter(csv_buffer, fieldnames=data[0].keys())
                    writer.writeheader()
                    writer.writerows(data)
                    zip_file.writestr(f"{table}.csv", csv_buffer.getvalue())
            except Exception as e:
                print(f"Backup error for {table}: {e}")
    zip_buffer.seek(0)
    return send_file(zip_buffer, as_attachment=True, download_name=f"backup_{datetime.now().strftime('%Y%m%d')}.zip", mimetype='application/zip')

# ---- DEPARTMENTS / ENTITIES MANAGEMENT (NEW) ----
@app.route('/departments')
def departments():
    if not is_logged_in():
        return redirect(url_for('login'))
    # Fetch all departments
    try:
        depts = supabase.table('departments').select('*').order('name').execute().data
    except Exception as e:
        print("Departments fetch error:", e)
        depts = []
    return render_template('departments.html', departments=depts, user=get_current_user())

@app.route('/departments/add', methods=['POST'])
def departments_add():
    if not is_logged_in():
        return redirect(url_for('login'))
    try:
        data = {
            'name': request.form['name'],
            'type': request.form['type'],
            'unit_name': request.form.get('unit_name', ''),
            'division_name': request.form.get('division_name', ''),
            'department_name': request.form.get('department_name', ''),
            'hotline_numbers': request.form.get('hotline_numbers', ''),
            'address': request.form.get('address', ''),
            'notes': request.form.get('notes', ''),
            'water_account': request.form.get('water_account', ''),
            'water_meter': request.form.get('water_meter', ''),
            'electricity_account': request.form.get('electricity_account', ''),
            'electricity_meter': request.form.get('electricity_meter', ''),
            'telephone_account': request.form.get('telephone_account', ''),
            'telephone_number': request.form.get('telephone_number', ''),
            'water_accounts': request.form.get('water_accounts', '[]'),
            'water_meters': request.form.get('water_meters', '[]'),
            'electricity_accounts': request.form.get('electricity_accounts', '[]'),
            'electricity_meters': request.form.get('electricity_meters', '[]'),
            'telephone_accounts': request.form.get('telephone_accounts', '[]'),
            'telephone_numbers': request.form.get('telephone_numbers', '[]'),
        }
        supabase.table('departments').insert(data).execute()
    except Exception as e:
        print("Add department error:", e)
    return redirect(url_for('departments'))

@app.route('/departments/edit/<int:id>', methods=['POST'])
def departments_edit(id):
    if not is_logged_in():
        return redirect(url_for('login'))
    try:
        data = {
            'name': request.form['name'],
            'type': request.form['type'],
            'unit_name': request.form.get('unit_name', ''),
            'division_name': request.form.get('division_name', ''),
            'department_name': request.form.get('department_name', ''),
            'hotline_numbers': request.form.get('hotline_numbers', ''),
            'address': request.form.get('address', ''),
            'notes': request.form.get('notes', ''),
            'water_account': request.form.get('water_account', ''),
            'water_meter': request.form.get('water_meter', ''),
            'electricity_account': request.form.get('electricity_account', ''),
            'electricity_meter': request.form.get('electricity_meter', ''),
            'telephone_account': request.form.get('telephone_account', ''),
            'telephone_number': request.form.get('telephone_number', ''),
            'water_accounts': request.form.get('water_accounts', '[]'),
            'water_meters': request.form.get('water_meters', '[]'),
            'electricity_accounts': request.form.get('electricity_accounts', '[]'),
            'electricity_meters': request.form.get('electricity_meters', '[]'),
            'telephone_accounts': request.form.get('telephone_accounts', '[]'),
            'telephone_numbers': request.form.get('telephone_numbers', '[]'),
        }
        supabase.table('departments').update(data).eq('id', id).execute()
    except Exception as e:
        print("Edit department error:", e)
    return redirect(url_for('departments'))

@app.route('/departments/delete/<int:id>')
def departments_delete(id):
    if not is_logged_in():
        return redirect(url_for('login'))
    try:
        supabase.table('departments').delete().eq('id', id).execute()
    except Exception as e:
        print("Delete department error:", e)
    return redirect(url_for('departments'))

if __name__ == '__main__':
    app.run(debug=True)
