from flask import Flask, render_template, request, redirect, url_for, flash, Response
from flask_sqlalchemy import SQLAlchemy
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
import os
import click
from flask.cli import with_appcontext
from collections import defaultdict
import csv
import io
from sqlalchemy.orm import joinedload
import json

# --- App Setup ---
basedir = os.path.abspath(os.path.dirname(__file__))
app = Flask(__name__)
app.config['SECRET_KEY'] = 'a-very-secret-key' # Needed for flash messages
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'app.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# --- Database Models ---

class Beneficiary(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    gender = db.Column(db.String(50))
    relationship_to_grantee = db.Column(db.String(100))
    province = db.Column(db.String(100))
    municipality = db.Column(db.String(100))
    barangay = db.Column(db.String(100))
    household_id = db.Column(db.String(100), unique=True, nullable=False)
    parent_group_name = db.Column(db.String(100))
    contact_number = db.Column(db.String(50))
    assessments = db.relationship('Assessment', backref='beneficiary', lazy=True, cascade="all, delete-orphan")

class Assessment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    beneficiary_id = db.Column(db.Integer, db.ForeignKey('beneficiary.id'), nullable=False)
    date_taken = db.Column(db.DateTime, server_default=db.func.now())
    answers = db.relationship('Answer', backref='assessment', lazy=True, cascade="all, delete-orphan")

class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    section = db.Column(db.String(100), nullable=False)
    question_type = db.Column(db.String(50), nullable=False) # 'rating' or 'narrative'
    text = db.Column(db.String(500), nullable=False)
    order = db.Column(db.Integer, nullable=False)

class Answer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    assessment_id = db.Column(db.Integer, db.ForeignKey('assessment.id'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('question.id'), nullable=False)
    value = db.Column(db.String(1000))
    question = db.relationship('Question')

# --- Routes ---
@app.route('/')
def index():
    questions_from_db = Question.query.order_by(Question.order).all()
    grouped_questions = defaultdict(list)
    for q in questions_from_db:
        grouped_questions[q.section].append(q)

    # Load and process address data
    address_data = defaultdict(lambda: defaultdict(list))
    with open('address.csv', mode='r', encoding='utf-8') as csv_file:
        csv_reader = csv.DictReader(csv_file)
        for row in csv_reader:
            province = row['Province Name']
            municipality = row['City/Municipality Name']
            barangay = row['Barangay Name']

            if province and municipality and barangay:
                address_data[province][municipality].append(barangay)

    # Get unique sorted list of provinces
    provinces = sorted(address_data.keys())

    # Sort municipalities and barangays
    for province in address_data:
        for municipality in address_data[province]:
            address_data[province][municipality] = sorted(list(set(address_data[province][municipality])))
        address_data[province] = dict(sorted(address_data[province].items()))

    return render_template('index.html',
                           questions=grouped_questions,
                           provinces=provinces,
                           address_data=json.dumps(address_data))

@app.route('/submit', methods=['POST'])
def submit():
    household_id = request.form.get('household_id')
    if not household_id:
        flash('Household ID is required.', 'danger')
        return redirect(url_for('index'))

    beneficiary = Beneficiary.query.filter_by(household_id=household_id).first()
    if not beneficiary:
        beneficiary = Beneficiary(
            household_id=household_id,
            name=request.form.get('name'),
            gender=request.form.get('gender'),
            relationship_to_grantee=request.form.get('relationship_to_grantee'),
            province=request.form.get('province'),
            municipality=request.form.get('municipality'),
            barangay=request.form.get('barangay'),
            parent_group_name=request.form.get('parent_group_name'),
            contact_number=request.form.get('contact_number')
        )
        db.session.add(beneficiary)

    assessment = Assessment(beneficiary=beneficiary)
    db.session.add(assessment)

    for key, value in request.form.items():
        if key.startswith('q-'):
            question_id = int(key.split('-')[1])
            if value:
                answer = Answer(
                    assessment=assessment,
                    question_id=question_id,
                    value=value
                )
                db.session.add(answer)

    try:
        db.session.commit()
        flash('Assessment submitted successfully!', 'success')
        return redirect(url_for('success'))
    except Exception as e:
        db.session.rollback()
        flash(f'An error occurred: {e}', 'danger')
        return redirect(url_for('index'))

@app.route('/success')
def success():
    return render_template('success.html')

@app.route('/results')
def results():
    assessments = Assessment.query.options(
        joinedload(Assessment.beneficiary)
    ).order_by(Assessment.date_taken.desc()).all()
    return render_template('results.html', assessments=assessments)

@app.route('/dashboard')
def dashboard():
    # Chart 1: Average score per section
    avg_scores_data = db.session.query(
        Question.section,
        func.avg(func.cast(Answer.value, db.Float))
    ).join(Answer, Answer.question_id == Question.id)\
    .filter(Question.question_type == 'rating')\
    .group_by(Question.section)\
    .order_by(Question.section)\
    .all()

    avg_scores_labels = [row[0] for row in avg_scores_data]
    avg_scores_values = [round(row[1], 2) if row[1] is not None else 0 for row in avg_scores_data]

    # Chart 2: Assessments over time
    assessments_over_time_data = db.session.query(
        func.date(Assessment.date_taken),
        func.count(Assessment.id)
    ).group_by(func.date(Assessment.date_taken))\
    .order_by(func.date(Assessment.date_taken))\
    .all()

    assessments_over_time_labels = [row[0] for row in assessments_over_time_data]
    assessments_over_time_values = [row[1] for row in assessments_over_time_data]

    # Chart 3: Average score by province and section
    avg_scores_by_province_section = db.session.query(
        Beneficiary.province,
        Question.section,
        func.avg(func.cast(Answer.value, db.Float))
    ).join(Assessment, Beneficiary.id == Assessment.beneficiary_id)\
     .join(Answer, Assessment.id == Answer.assessment_id)\
     .join(Question, Answer.question_id == Question.id)\
     .filter(Question.question_type == 'rating')\
     .group_by(Beneficiary.province, Question.section)\
     .order_by(Beneficiary.province, Question.section)\
     .all()

    provinces = sorted(list(set([row[0] for row in avg_scores_by_province_section if row[0] is not None])))
    sections = sorted(list(set([row[1] for row in avg_scores_by_province_section if row[1] is not None])))

    data_dict = {}
    for province, section, avg_score in avg_scores_by_province_section:
        if province and section:
            if province not in data_dict:
                data_dict[province] = {}
            data_dict[province][section] = round(avg_score, 2) if avg_score is not None else 0

    datasets = []
    # Generate a color palette for the sections
    # Using a simple hash function to generate a color for each section
    colors = {}
    for i, section in enumerate(sections):
        # Create a unique color for each section based on its name
        # This is a simple way to generate different colors, but for a large number of sections,
        # you might want a more sophisticated color generation scheme.
        hash_code = hash(section)
        r = (hash_code & 0xFF0000) >> 16
        g = (hash_code & 0x00FF00) >> 8
        b = hash_code & 0x0000FF
        colors[section] = f'rgba({r}, {g}, {b}, 0.5)'


    for section in sections:
        dataset = {
            'label': section,
            'data': [data_dict.get(province, {}).get(section, 0) for province in provinces],
            'backgroundColor': colors.get(section, 'rgba(54, 162, 235, 0.5)'), # Default color
            'borderColor': colors.get(section, 'rgba(54, 162, 235, 1)').replace('0.5', '1'), # Default border color
            'borderWidth': 1
        }
        datasets.append(dataset)

    province_chart_data = {
        'labels': provinces,
        'datasets': datasets
    }

    return render_template(
        'dashboard.html',
        avg_scores_labels=avg_scores_labels,
        avg_scores_values=avg_scores_values,
        assessments_over_time_labels=assessments_over_time_labels,
        assessments_over_time_values=assessments_over_time_values,
        province_chart_data=json.dumps(province_chart_data)
    )

@app.route('/dashboard/province/<province_name>')
def province_dashboard(province_name):
    # Query for municipality-level data for the given province
    avg_scores_by_municipality = db.session.query(
        Beneficiary.municipality,
        Question.section,
        func.avg(func.cast(Answer.value, db.Float))
    ).join(Assessment, Beneficiary.id == Assessment.beneficiary_id)\
     .join(Answer, Assessment.id == Answer.assessment_id)\
     .join(Question, Answer.question_id == Question.id)\
     .filter(Beneficiary.province == province_name, Question.question_type == 'rating')\
     .group_by(Beneficiary.municipality, Question.section)\
     .order_by(Beneficiary.municipality, Question.section)\
     .all()

    municipalities = sorted(list(set([row[0] for row in avg_scores_by_municipality if row[0] is not None])))
    sections = sorted(list(set([row[1] for row in avg_scores_by_municipality if row[1] is not None])))

    data_dict = {}
    for municipality, section, avg_score in avg_scores_by_municipality:
        if municipality and section:
            if municipality not in data_dict:
                data_dict[municipality] = {}
            data_dict[municipality][section] = round(avg_score, 2) if avg_score is not None else 0

    datasets = []
    colors = {}
    for i, section in enumerate(sections):
        hash_code = hash(section)
        r = (hash_code & 0xFF0000) >> 16
        g = (hash_code & 0x00FF00) >> 8
        b = hash_code & 0x0000FF
        colors[section] = f'rgba({r}, {g}, {b}, 0.5)'

    for section in sections:
        dataset = {
            'label': section,
            'data': [data_dict.get(municipality, {}).get(section, 0) for municipality in municipalities],
            'backgroundColor': colors.get(section, 'rgba(54, 162, 235, 0.5)'),
            'borderColor': colors.get(section, 'rgba(54, 162, 235, 1)').replace('0.5', '1'),
            'borderWidth': 1
        }
        datasets.append(dataset)

    municipality_chart_data = {
        'labels': municipalities,
        'datasets': datasets
    }

    return render_template(
        'province_dashboard.html',
        province_name=province_name,
        municipality_chart_data=json.dumps(municipality_chart_data)
    )

@app.route('/download_csv')
def download_csv():
    questions = Question.query.order_by(Question.order).all()
    question_headers = [q.text for q in questions]
    headers = [
        'Assessment ID', 'Beneficiary Name', 'Household ID', 'Date Taken'
    ] + question_headers

    assessments = Assessment.query.options(
        joinedload(Assessment.beneficiary),
        joinedload(Assessment.answers).joinedload(Answer.question)
    ).all()

    rows = []
    for assessment in assessments:
        answer_map = {ans.question_id: ans.value for ans in assessment.answers}
        row = {
            'Assessment ID': assessment.id,
            'Beneficiary Name': assessment.beneficiary.name,
            'Household ID': assessment.beneficiary.household_id,
            'Date Taken': assessment.date_taken.strftime('%Y-%m-%d %H:%M:%S'),
        }
        for q in questions:
            row[q.text] = answer_map.get(q.id, '')
        rows.append(row)

    si = io.StringIO()
    writer = csv.DictWriter(si, fieldnames=headers)
    writer.writeheader()
    writer.writerows(rows)
    output = si.getvalue()

    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=4ps_assessments_report.csv"}
    )

# --- DB Initialization Command ---
def get_all_questions():
    return [
        # KATATASAN SA PROGRAMA
        {'section': 'KATATASAN SA PROGRAMA', 'type': 'rating', 'text': 'Natutukoy ang mga layunin ng Pantawid Pamilyang Pilipino Program (4Ps)'},
        {'section': 'KATATASAN SA PROGRAMA', 'type': 'rating', 'text': 'Naipapaliwanag ang mga pamantayan sa pagpili ng mga pamilyang magiging miyembro ng Programa.'},
        {'section': 'KATATASAN SA PROGRAMA', 'type': 'rating', 'text': 'Naipapaliwanag ang mga kondisyon ng mga Programa.'},
        {'section': 'KATATASAN SA PROGRAMA', 'type': 'rating', 'text': 'Natutukoy ang mga nilalaman ng Panunumpa (Oath of Commitment)'},
        {'section': 'KATATASAN SA PROGRAMA', 'type': 'rating', 'text': 'Naipapaliwanag ang Listahanan Assessment'},
        {'section': 'KATATASAN SA PROGRAMA', 'type': 'rating', 'text': 'Naipapaliwanag ang Social Welfare Development Indicator (SWDI) bilang isa sa sukatan sa pag-graduate sa Programa'},
        {'section': 'KATATASAN SA PROGRAMA', 'type': 'rating', 'text': 'May nakasulat na Family Vision na nauunawaan ng lahat ng miyembro.'},
        {'section': 'KATATASAN SA PROGRAMA', 'type': 'rating', 'text': 'Kabahagi ang pamilya sa pagbuo ng plano o Household Intervention Plan'},
        {'section': 'KATATASAN SA PROGRAMA', 'type': 'rating', 'text': 'Natutukoy ang mga hakbang ng Case Management na pagdadaanan ng aming Pamilya.'},
        {'section': 'KATATASAN SA PROGRAMA', 'type': 'rating', 'text': 'Nauunawaaan ang mga batayan ng aming pagtatapos sa Programa.'},
        {'section': 'KATATASAN SA PROGRAMA', 'type': 'rating', 'text': 'Nagagawa ang wastong proseso ng pag-update ng mga datos ng aming pamilya.'},
        {'section': 'KATATASAN SA PROGRAMA', 'type': 'rating', 'text': 'Nagagawa ang tamang proseso sa paghain ng katanungan o reklamo sa programa.'},
        {'section': 'KATATASAN SA PROGRAMA', 'type': 'rating', 'text': 'Nauunawan ang prohibisyon o hindi naangkop sa programa'},

        # EDUKASYON
        {'section': 'EDUKASYON', 'type': 'rating', 'text': 'Nagpapatupad ng hakbangin para pahalagahan ang edukasyon para sa kinabukasan ng anak.'},
        {'section': 'EDUKASYON', 'type': 'rating', 'text': 'Ang mga batang minomonitor ng programa sa pamilya ay pumapasok sa paaralan alinsunod sa tinakdang kondisyon.'},
        {'section': 'EDUKASYON', 'type': 'rating', 'text': 'Naglalaan ng sapat na oras para kumustahin ang anak sa kanyang pag-aaral.'},
        {'section': 'EDUKASYON', 'type': 'rating', 'text': 'Naglalaan ng sapat na oras para matulungan ang mga anak sa kanilang mga gawain sa paaralan.'},
        {'section': 'EDUKASYON', 'type': 'rating', 'text': 'Naibibigay ang mga pangangailangan ng mga anak sa kanilang pag-aaral.'},
        {'section': 'EDUKASYON', 'type': 'rating', 'text': 'Dumadalo sa mga Parent-Teacher Association (PTA) meeting.'},

        # KALUSUGAN
        {'section': 'KALUSUGAN', 'type': 'rating', 'text': 'Regular na nagpapacheck-up ang buntis na miyembro ng pamilya sa health center or health facility/clinic o hospital.'},
        {'section': 'KALUSUGAN', 'type': 'rating', 'text': 'Kasunod nito ay ang pagpapost-natal Check-up matapos manganak.'},
        {'section': 'KALUSUGAN', 'type': 'rating', 'text': 'Ang buntis ay nanganganak sa isang Accredited Birthing Facility.'},
        {'section': 'KALUSUGAN', 'type': 'rating', 'text': 'Nagpapapurga ang mga batang edad 1-14 sa aming sambahayan dalawang beses sa isang taon.'},
        {'section': 'KALUSUGAN', 'type': 'rating', 'text': 'Pinababakunahan ang mga batang edad 0 hanggang 23 buwan gulang.'},
        {'section': 'KALUSUGAN', 'type': 'rating', 'text': 'Naipapatupad ang mga kaalaman sa unang isang libong (1000) araw ng buhay o F1KD pagkatapos magsilang ng anak.'},
        {'section': 'KALUSUGAN', 'type': 'rating', 'text': 'Nag a-update ng datos tungkol sa kalusugan ng pamilya (halimbawa: nabuntis, nanganak at etc.).'},
        {'section': 'KALUSUGAN', 'type': 'rating', 'text': 'Pinapainom ang mga anak ng bitaminang angkop sa kanilang edad.'},
        {'section': 'KALUSUGAN', 'type': 'rating', 'text': 'Ang mga miyembro ng sambahayan ay nagpapakonsulta at tumatangkilik ng mga serbisyong pangkalusugan.'},
        {'section': 'KALUSUGAN', 'type': 'rating', 'text': 'Ang bawat miyembro ng pamilya ay binibigyan ng suporta sa pagpapanatili ng kanilang kalusugan habang sila ay nagdadalang-tao, at para sa kalusugan ng mga batang may edad 0-5.'},
        {'section': 'KALUSUGAN', 'type': 'rating', 'text': 'Gumagamit ng mga pamamaraan sa pagpaplano ng pamilya (Family Planning Method).'},
        {'section': 'KALUSUGAN', 'type': 'rating', 'text': 'Ang pamilya ay may ligtas na pinagkukunan ng tubig sa pangkalahatang gamit (General Use) tulad ng pampaligo, panglaba, panghugas ng pinagkainan, panlinis ng bahay, atbp.'},
        {'section': 'KALUSUGAN', 'type': 'rating', 'text': 'Ang mga miyembro ng pamilya ay naghuhugas ng kamay bago at pagkatapos kumain at pagkatapos gumamit ng palikuran gamit ang malinis na tubig at sabon.'},
        {'section': 'KALUSUGAN', 'type': 'rating', 'text': 'Binibigyan ng karampatang lunas ang miyembro ng pamilya na may sakit.'},

        # NUTRISYON
        {'section': 'NUTRISYON', 'type': 'rating', 'text': 'Ang mga batang edad 0-6 buwan ay eksklusibong pinapasuso ng gatas ng ina.'},
        {'section': 'NUTRISYON', 'type': 'rating', 'text': 'Ang mga batang edad na anim na buwan ay binibigyan na ng pagkain at patuloy na pinapasuso ng gatas ng ina hanggang dalawang taon.'},
        {'section': 'NUTRISYON', 'type': 'rating', 'text': 'Kumakain ng masusustansyang pagkain batay sa panuntunan ng Pinggang Pinoy.'},
        {'section': 'NUTRISYON', 'type': 'rating', 'text': 'Kumakain ang sambahayan ng mga pinatibay na pagkain (Fortified Foods)'},
        {'section': 'NUTRISYON', 'type': 'rating', 'text': 'Ang mga batang nasa edad 0-5 taon ay nasa normal na timbang.'},
        {'section': 'NUTRISYON', 'type': 'rating', 'text': 'Ang mga batang nasa edad 0-5 taon ay nasa normal na tangkad.'},
        {'section': 'NUTRISYON', 'type': 'rating', 'text': 'Nagtatanim ng prutas o/at gulay sa bakuran.'},
        {'section': 'NUTRISYON', 'type': 'rating', 'text': 'Kumakain ng gulay o/at prutas na galing sa gulayan sa sariling bakuran o barangay.'},

        # PAMAMAHALA SA BUHAY PAMILYA
        {'section': 'PAMAMAHALA SA BUHAY PAMILYA', 'type': 'rating', 'text': 'Ako at ang aking asawa o partner ay may pantay na responsibilidad sa pagpapatakbo ng pamilya.'},
        {'section': 'PAMAMAHALA SA BUHAY PAMILYA', 'type': 'rating', 'text': 'Ako at ang aking asawa o partner ay pantay sa responsibilidad sa pagpapalaki sa aming mga anak.'},
        {'section': 'PAMAMAHALA SA BUHAY PAMILYA', 'type': 'rating', 'text': "Ako at ang aking asawa o partner ay nagpapatupad ng hakbangin para mapanatili ang maayos na ugnayan ng pamilya."},
        {'section': 'PAMAMAHALA SA BUHAY PAMILYA', 'type': 'rating', 'text': "Naglalaan ng oras para sa one-on-one time para sa isa't isa (Family Bonding)."},
        {'section': 'PAMAMAHALA SA BUHAY PAMILYA', 'type': 'rating', 'text': 'Bukas ang komunikasyon ng pamilya.'},
        {'section': 'PAMAMAHALA SA BUHAY PAMILYA', 'type': 'rating', 'text': 'Nagtutulungan ang bawat miyembro ng pamilya sa gawaing bahay.'},
        {'section': 'PAMAMAHALA SA BUHAY PAMILYA', 'type': 'rating', 'text': 'Bahagi ang bawat miyembro ng aking pamilya sa mga desisyong pangsambahayan.'},
        {'section': 'PAMAMAHALA SA BUHAY PAMILYA', 'type': 'rating', 'text': 'Nagtutulungan ang bawat miyembro ng pamilya sa paghahanap ng solusyon o pagresolba sa mga problema.'},
        {'section': 'PAMAMAHALA SA BUHAY PAMILYA', 'type': 'rating', 'text': 'Pinapatupad ang wastong pagdidisiplina sa mga bata sa sambahayan.'},
        {'section': 'PAMAMAHALA SA BUHAY PAMILYA', 'type': 'rating', 'text': 'Nagpapakita ako ng pagmamahal at positibong damdamin sa aking mga anak'},
        {'section': 'PAMAMAHALA SA BUHAY PAMILYA', 'type': 'rating', 'text': 'Sumusunod at tumutugon ako sa mga hakbangin o initisyatibo ng aking mga anak'},
        {'section': 'PAMAMAHALA SA BUHAY PAMILYA', 'type': 'rating', 'text': 'Nakikipag-usap ako ng malapit sa aking anak (mayroon man o walang salita)'},
        {'section': 'PAMAMAHALA SA BUHAY PAMILYA', 'type': 'rating', 'text': 'Napupuri ang bawat miyembro ng sambahayan sa kanilang mabuting gawi at tagumpay.'},
        {'section': 'PAMAMAHALA SA BUHAY PAMILYA', 'type': 'rating', 'text': 'Nakatuon ako sa mga interes at karanasan ng aking mga anak'},
        {'section': 'PAMAMAHALA SA BUHAY PAMILYA', 'type': 'rating', 'text': 'Inilalarawan ko, binibigyang kahulugan at nagpapakita ako na may sigla sa mga karanasan at interes ng aking mga anak'},
        {'section': 'PAMAMAHALA SA BUHAY PAMILYA', 'type': 'rating', 'text': 'Pinapalawak at pinapayaman ko ang mga karanasan ng aking mga anak sa pamamagitan ng pagkonekta sa kanilang mga imahinasyon at lohika'},
        {'section': 'PAMAMAHALA SA BUHAY PAMILYA', 'type': 'rating', 'text': 'Sinusuportahan ko ang aking mga anak sa pamamagitan ng pagtatakda ng mga limitasyon sa positibong paraan, sa pamamagitan ng pagturo ng mga kahihinatnan at pag-aalok ng mga alternatibo'},
        {'section': 'PAMAMAHALA SA BUHAY PAMILYA', 'type': 'rating', 'text': 'Natutukoy ang mga palatandaan na maaaring may pinagdadaanang problema, isyu o suliranin ang miyembro ng pamilya.'},
        {'section': 'PAMAMAHALA SA BUHAY PAMILYA', 'type': 'rating', 'text': 'May kaalaman ang bawat miyembro ng sambahayan sa karapatang may kinalaman sa mga bata at kababaihan'},
        {'section': 'PAMAMAHALA SA BUHAY PAMILYA', 'type': 'rating', 'text': 'Ang batang nasa edad na 14 na taong gulang pababa sa aming sambahayan ay hindi naghahanap-buhay.'},
        {'section': 'PAMAMAHALA SA BUHAY PAMILYA', 'type': 'rating', 'text': 'Nagpapatupad ng patakarang pangkaligtasan ang pamilya laban sa anumang panganib, sakuna o disaster.'},
        {'section': 'PAMAMAHALA SA BUHAY PAMILYA', 'type': 'rating', 'text': 'Nakahanda ang emergency balde o bag na magagamit sa panahon ng sakuna.'},
        {'section': 'PAMAMAHALA SA BUHAY PAMILYA', 'type': 'rating', 'text': 'May nakasulat na Family Disaster Action Plan.'},
        {'section': 'PAMAMAHALA SA BUHAY PAMILYA', 'type': 'rating', 'text': 'May updated na Family Emergency Directory.'},
        {'section': 'PAMAMAHALA SA BUHAY PAMILYA', 'type': 'rating', 'text': 'Nauunawaan ang mga isyu at suliranin sa komunidad.'},
        {'section': 'PAMAMAHALA SA BUHAY PAMILYA', 'type': 'rating', 'text': 'Natutukoy ang tamang solusyon sa isyu at suliranin ng komunidad.'},
        {'section': 'PAMAMAHALA SA BUHAY PAMILYA', 'type': 'rating', 'text': 'Ako at ang aking pamilya ay aktibong nakikibahagi sa mga proyekto o aktibidad ng aming komunidad gaya ng Clean-Up drive at iba pang gawain.'},
        {'section': 'PAMAMAHALA SA BUHAY PAMILYA', 'type': 'rating', 'text': 'Nakakapag access ng iba’t-ibang programa ng pamahalaan o pribadong organisasyon batay sa aming pangangailangan.'},
        {'section': 'PAMAMAHALA SA BUHAY PAMILYA', 'type': 'rating', 'text': 'Anumang diskriminasyon at anyo ng karahasan sa kasarian ay hindi umiiral sa sambahayan.'},
        {'section': 'PAMAMAHALA SA BUHAY PAMILYA', 'type': 'rating', 'text': 'Natutukoy ang pagkakaiba ng Sex at Gender.'},

        # KABUHAYAN AT KAALAMAN SA PANANALAPI
        {'section': 'KABUHAYAN AT KAALAMAN SA PANANALAPI', 'type': 'rating', 'text': 'Nagagamit ang aming Cash Card sa iba pang pampinansyal na transaksyon (transaction account).'},
        {'section': 'KABUHAYAN AT KAALAMAN SA PANANALAPI', 'type': 'rating', 'text': 'May isang miyembro ng pamilya ang may regular na hanapbuhay at kita (6 na buwan pataas nang kumikita).'},
        {'section': 'KABUHAYAN AT KAALAMAN SA PANANALAPI', 'type': 'rating', 'text': 'Lumalahok sa mga aktibidad na nakakatulong upang mapalawak ang kaalaman ng pamilya sa tamang paghawak ng pera.'},
        {'section': 'KABUHAYAN AT KAALAMAN SA PANANALAPI', 'type': 'rating', 'text': 'May nasusulat na planong pinansyal ang sambahayan.'},
        {'section': 'KABUHAYAN AT KAALAMAN SA PANANALAPI', 'type': 'rating', 'text': 'Pinapatupad ng pamilya ang praktikal na hakbang sa pagbabadyet/ laang-gugulin.'},
        {'section': 'KABUHAYAN AT KAALAMAN SA PANANALAPI', 'type': 'rating', 'text': 'Regular na pinag-uusapan ng pamilya ang kalagayang pinansyal.'},
        {'section': 'KABUHAYAN AT KAALAMAN SA PANANALAPI', 'type': 'rating', 'text': 'Regular na sinusubaybayan ang mga gastos at badyet ng pamilya.'},
        {'section': 'KABUHAYAN AT KAALAMAN SA PANANALAPI', 'type': 'rating', 'text': 'Marunong sa mga pangunahing mathematical operations gaya ng addition, subtraction, multiplication, at division.'},
        {'section': 'KABUHAYAN AT KAALAMAN SA PANANALAPI', 'type': 'rating', 'text': 'Nakakapag-ipon gamit ang nakasanayang pamamaraan at hindi sa bangko (Conventional Method).'},
        {'section': 'KABUHAYAN AT KAALAMAN SA PANANALAPI', 'type': 'rating', 'text': 'Nakakapag-ipon sa bangko.'},
        {'section': 'KABUHAYAN AT KAALAMAN SA PANANALAPI', 'type': 'rating', 'text': 'Nakakapag-ipon para sa mga emergency na gastos.'},
        {'section': 'KABUHAYAN AT KAALAMAN SA PANANALAPI', 'type': 'rating', 'text': "Ginagamit ang iba't ibang Digital Financial Services."},
        {'section': 'KABUHAYAN AT KAALAMAN SA PANANALAPI', 'type': 'rating', 'text': 'Aktibong miyembro ng Insurance.'},
        {'section': 'KABUHAYAN AT KAALAMAN SA PANANALAPI', 'type': 'rating', 'text': 'May mga napundar na ari-arian.'},
        {'section': 'KABUHAYAN AT KAALAMAN SA PANANALAPI', 'type': 'rating', 'text': 'Nag-aacess ng tulong sa “Micro credit” institution.'},
        {'section': 'KABUHAYAN AT KAALAMAN SA PANANALAPI', 'type': 'rating', 'text': 'May karanasan na gumawa ng plano para sa negosyo.'},
        {'section': 'KABUHAYAN AT KAALAMAN SA PANANALAPI', 'type': 'rating', 'text': 'May karanasan sa pagbebenta ng mga produkto at paghihikayat ng mga mamimili.'},
        {'section': 'KABUHAYAN AT KAALAMAN SA PANANALAPI', 'type': 'rating', 'text': 'Kumikita ang sambahayan mula sa bakuran/communal garden.'},
        {'section': 'KABUHAYAN AT KAALAMAN SA PANANALAPI', 'type': 'rating', 'text': 'Mayroon ng kalayaang pang-pinansyal (financial freedom) ang sambahayan.'},

        # MGA TANONG SA PAGSISIYASAT
        {'section': 'PAGSISIYASAT - KATATASAN SA PROGRAMA', 'type': 'narrative', 'text': 'Ano ang layunin ng 4Ps?'},
        {'section': 'PAGSISIYASAT - KATATASAN SA PROGRAMA', 'type': 'narrative', 'text': 'Anu-ano ang mga kondisyon ng programa?'},
        {'section': 'PAGSISIYASAT - KATATASAN SA PROGRAMA', 'type': 'narrative', 'text': 'Ano ang batayan ng pagtatapos sa programa?'},
        {'section': 'PAGSISIYASAT - KATATASAN SA PROGRAMA', 'type': 'narrative', 'text': 'Ano ang prohibisyon o hindi naangkop sa programa?'},
        {'section': 'PAGSISIYASAT - EDUKASYON', 'type': 'narrative', 'text': 'Ano ang kahalagahan ng edukasyon sa bata?'},
        {'section': 'PAGSISIYASAT - EDUKASYON', 'type': 'narrative', 'text': 'Ano ang kondisyon ng edukasyon sa programa?'},
        {'section': 'PAGSISIYASAT - EDUKASYON', 'type': 'narrative', 'text': 'Paano natutulungan at nasusuportahan ang anak sa kanilang pag-aaral?'},
        {'section': 'PAGSISIYASAT - PAMAMAHALA SA SAMBAHAYAN', 'type': 'narrative', 'text': 'Paano dinidisiplina ang mga bata sa sambahayan?'},
        {'section': 'PAGSISIYASAT - PAMAMAHALA SA SAMBAHAYAN', 'type': 'narrative', 'text': 'Anu-ano ang mga karapatang may kinalaman sa mga bata at kababaihan?'},
        {'section': 'PAGSISIYASAT - PAMAMAHALA SA SAMBAHAYAN', 'type': 'narrative', 'text': 'Ano ang iba’t-ibang programa ng pamahalaan o pribadong organisasyon na na-access ng pamilya sa loob ng isang taon?'},
        {'section': 'PAGSISIYASAT - KABUHAYAN AT KAALAMAN SA PANANALAPI', 'type': 'narrative', 'text': 'Ano ang mga karanasan sa pagbebenta ng mga produkto'},
        {'section': 'PAGSISIYASAT - KABUHAYAN AT KAALAMAN SA PANANALAPI', 'type': 'narrative', 'text': 'Ano ang kakayahan sa kabuhayan (livelihood skills) na nais matutunan?'},
        {'section': 'PAGSISIYASAT - PANINILAY', 'type': 'narrative', 'text': 'Base sa naging resulta ng inyong pagtatasa, alin sa mga pahayag sa taas ang mas tumatak sa inyo at bakit?'},
    ]

@click.command('init-db')
@with_appcontext
def init_db_command():
    """Clears the existing data and creates new tables and questions."""
    db.drop_all()
    db.create_all()

    questions_data = get_all_questions()
    for i, q_data in enumerate(questions_data):
        question = Question(
            section=q_data['section'],
            question_type=q_data['type'],
            text=q_data['text'],
            order=i
        )
        db.session.add(question)

    db.session.commit()
    click.echo(f'Initialized the database and populated {len(questions_data)} questions.')

app.cli.add_command(init_db_command)

if __name__ == '__main__':
    # app.run(debug=True)
    app.run(host="0.0.0.0", port=5000, debug=True)

