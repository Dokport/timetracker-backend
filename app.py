from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import base64
from io import BytesIO

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///timelogs.db'
db = SQLAlchemy(app)

class TimeLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    task_name = db.Column(db.String(80))
    start_time = db.Column(db.DateTime)
    end_time = db.Column(db.DateTime)
    duration = db.Column(db.String(20))

def parse_datetime(datetime_str):
    try:
        return datetime.strptime(datetime_str, "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        datetime_str = datetime_str.replace('.', ':')
        return datetime.strptime(datetime_str, "%Y-%m-%dT%H:%M:%S")

@app.route('/api/timelogs', methods=['POST'])
def create_timelog():
    data = request.json
    print(f"Received data: {data}")
    try:
        start_time = parse_datetime(data['StartTime'])
        end_time = parse_datetime(data['EndTime'])

        new_log = TimeLog(
            task_name=data['TaskName'],
            start_time=start_time,
            end_time=end_time,
            duration=str(data['Duration'])
        )
        db.session.add(new_log)
        db.session.commit()
        return jsonify({'message': 'Time log created'}), 201
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({'error': str(e)}), 400

@app.route('/api/sync_timelogs', methods=['POST'])
def sync_timelogs():
    data = request.json
    print(f"Received sync data: {data}")
    try:
        task_name = data['TaskName']
        start_time = parse_datetime(data['StartTime'])
        elapsed_time = data['ElapsedTime']

        existing_log = TimeLog.query.filter_by(task_name=task_name, start_time=start_time).first()

        if existing_log:
            existing_log.duration = elapsed_time
        else:
            new_log = TimeLog(
                task_name=task_name,
                start_time=start_time,
                duration=elapsed_time
            )
            db.session.add(new_log)

        db.session.commit()
        return jsonify({'message': 'Time log synced'}), 200
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({'error': str(e)}), 400

@app.route('/api/start_timelog', methods=['POST'])
def start_timelog():
    data = request.json
    print(f"Start timelog request: {data}")
    try:
        task_name = data['TaskName']
        start_time = parse_datetime(data['StartTime'])

        new_log = TimeLog(
            task_name=task_name,
            start_time=start_time
        )
        db.session.add(new_log)
        db.session.commit()
        return jsonify({'message': 'Time log started'}), 200
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({'error': str(e)}), 400

@app.route('/status')
def status():
    logs = TimeLog.query.all()
    return jsonify([
        {
            'TaskName': log.task_name,
            'StartTime': log.start_time,
            'EndTime': log.end_time,
            'Duration': log.duration
        } for log in logs
    ])

@app.route('/retainer_status')
def retainer_status():
    hourly_rate = 700
    initial_retainer_pool = 12000

    logs = TimeLog.query.filter(TimeLog.task_name.contains('Retainer')).all()
    
    monthly_summary = {}

    for log in logs:
        log_duration = log.duration.split(':')
        hours, minutes = int(log_duration[0]), int(log_duration[1])
        seconds = float(log_duration[2])
        log_time = timedelta(hours=hours, minutes=minutes, seconds=seconds)
        
        log_month = log.start_time.strftime("%Y-%m")

        if log_month not in monthly_summary:
            monthly_summary[log_month] = timedelta()

        monthly_summary[log_month] += log_time

    monthly_data = []

    for month, total_duration in monthly_summary.items():
        total_hours, total_minutes = divmod(total_duration.total_seconds() // 60, 60)
        amount_used = int(total_hours * hourly_rate + (total_minutes / 60) * hourly_rate)
        remaining_pool = initial_retainer_pool - amount_used
        remaining_hours = int(remaining_pool // hourly_rate)
        remaining_minutes = int((remaining_pool % hourly_rate) / hourly_rate * 60)

        month_summary = {
            'Month': month,
            'TotalRetainerTime': f"{int(total_hours)} hours {int(total_minutes)} minutes",
            'AmountUsed': f"{amount_used} kr",
            'RemainingPool': f"{remaining_pool} kr",
            'RemainingTime': f"{remaining_hours} hours {remaining_minutes} minutes"
        }

        monthly_data.append(month_summary)

    return jsonify(monthly_data)

def autopct_format(pct, allvals):
    total = sum(allvals)
    val = pct * total / 100.0
    return f'{val:.1f} hrs'

@app.route('/retainer_charts')
def retainer_charts():
    hourly_rate = 700
    initial_retainer_pool = 12000
    months_data = {}

    logs = TimeLog.query.filter(TimeLog.task_name.contains('Retainer')).all()
    
    for log in logs:
        log_duration = log.duration.split(':')
        hours, minutes = int(log_duration[0]), int(log_duration[1])
        seconds = float(log_duration[2])
        log_time = timedelta(hours=hours, minutes=minutes, seconds=seconds)
        
        log_month = log.start_time.strftime("%B %Y")

        if log_month not in months_data:
            months_data[log_month] = timedelta()

        months_data[log_month] += log_time

    charts = []

    for month, total_duration in months_data.items():
        total_hours = total_duration.total_seconds() / 3600
        amount_used = total_hours * hourly_rate
        remaining_pool = initial_retainer_pool - amount_used
        remaining_hours = remaining_pool / hourly_rate

        labels = 'Hours Used', 'Hours Remaining'
        sizes = [total_hours, remaining_hours]
        colors = ['#ffc09f', '#a0ced9']

        fig, ax = plt.subplots()
        wedges, texts, autotexts = ax.pie(sizes, labels=labels, colors=colors, autopct=lambda pct: autopct_format(pct, sizes), startangle=140, counterclock=False)
        
        for text, color in zip(texts, colors):
            text.set_color(color)
        
        for autotext in autotexts:
            autotext.set_color('black')

        ax.axis('equal')
        plt.title(f'Retainer Hours Usage for {month}', fontsize=16, fontweight='bold')

        buf = BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        img_base64 = base64.b64encode(buf.read()).decode('utf-8')
        buf.close()
        
        charts.append(f'<img src="data:image/png;base64,{img_base64}" />')

    return '<br>'.join(charts)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
