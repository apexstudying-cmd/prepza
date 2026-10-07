"""
University + Program seed migration
=====================================

Seeds ~103 universities (Kenya + major East Africa) and pairs each one
with the same shared 146-course catalog, per the agreed tradeoff:
per-university-accurate course catalogs aren't realistically maintainable,
so every university gets the same course list, and the frontend's
type-to-filter + "not found = blocked" signup flow is what keeps this
honest rather than a false promise of exact per-institution accuracy.

Source of truth: frontend/src/data/institutions.ts (this script's data
was generated FROM that file, not hand-retyped, to avoid drift between
the two - see chat history for the extraction method).

SAFE TO RE-RUN: idempotent. Existing universities are matched by exact
name (not re-created, not re-coded) and existing programs are matched
by (university_id, name) - re-running this after new courses/unis are
added to institutions.ts will only insert what's missing, never
duplicate what's already there. Kenyatta University's 3 real,
already-live programs are matched exactly (note the "&" not "and" in
their names) so this will NOT create duplicates for KU.

Usage:
    cd ~/Desktop/prepza
    python seed_universities_and_programs.py --dry-run   # preview counts only, writes nothing
    python seed_universities_and_programs.py             # actually seed the DB
"""

import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from app import app, db, University, Program

DRY_RUN = "--dry-run" in sys.argv

UNIVERSITIES = [
    dict(name='University of Nairobi', short_code='UoN', country='Kenya'),
    dict(name='Moi University', short_code='MOI', country='Kenya'),
    dict(name='Kenyatta University', short_code='KU', country='Kenya'),
    dict(name='Egerton University', short_code='EGERTON', country='Kenya'),
    dict(name='Jomo Kenyatta University of Agriculture and Technology', short_code='JKUAT', country='Kenya'),
    dict(name='Maseno University', short_code='MASENO', country='Kenya'),
    dict(name='Masinde Muliro University of Science and Technology', short_code='MMUST', country='Kenya'),
    dict(name='Dedan Kimathi University of Technology', short_code='DEKUT', country='Kenya'),
    dict(name='Chuka University', short_code='CHUKA', country='Kenya'),
    dict(name='Technical University of Kenya', short_code='TUK', country='Kenya'),
    dict(name='Technical University of Mombasa', short_code='TUM', country='Kenya'),
    dict(name='Pwani University', short_code='PWANI', country='Kenya'),
    dict(name='Kisii University', short_code='KISII', country='Kenya'),
    dict(name='University of Eldoret', short_code='UOELDORET', country='Kenya'),
    dict(name='Maasai Mara University', short_code='MMARARA', country='Kenya'),
    dict(name='Jaramogi Oginga Odinga University of Science and Technology', short_code='JOOUST', country='Kenya'),
    dict(name='Laikipia University', short_code='LAIKIPIA', country='Kenya'),
    dict(name='South Eastern Kenya University', short_code='SEKU', country='Kenya'),
    dict(name='Meru University of Science and Technology', short_code='MUST-KE', country='Kenya'),
    dict(name='Multimedia University of Kenya', short_code='MMUK', country='Kenya'),
    dict(name='University of Kabianga', short_code='KABIANGA', country='Kenya'),
    dict(name='Karatina University', short_code='KARATINA', country='Kenya'),
    dict(name='Kibabii University', short_code='KIBU', country='Kenya'),
    dict(name='Rongo University', short_code='RONGO', country='Kenya'),
    dict(name='The Co-operative University of Kenya', short_code='COOPU', country='Kenya'),
    dict(name='Taita Taveta University', short_code='TTU', country='Kenya'),
    dict(name="Murang'a University of Technology", short_code='MURANGA', country='Kenya'),
    dict(name='University of Embu', short_code='UOEMBU', country='Kenya'),
    dict(name='Machakos University', short_code='MKSU', country='Kenya'),
    dict(name='Kirinyaga University', short_code='KYU-KE', country='Kenya'),
    dict(name='Garissa University', short_code='GARISSA', country='Kenya'),
    dict(name='Alupe University', short_code='ALUPE', country='Kenya'),
    dict(name='Kaimosi Friends University', short_code='KAFU', country='Kenya'),
    dict(name='Tom Mboya University', short_code='TMBOYA', country='Kenya'),
    dict(name='Tharaka University', short_code='THARAKA', country='Kenya'),
    dict(name='Bomet University', short_code='BOMET-KE', country='Kenya'),
    dict(name='University of Eastern Africa, Baraton', short_code='UEAB', country='Kenya'),
    dict(name='Catholic University of Eastern Africa', short_code='CUEA', country='Kenya'),
    dict(name='Daystar University', short_code='DAYSTAR', country='Kenya'),
    dict(name='Scott Christian University', short_code='SCOTT', country='Kenya'),
    dict(name='United States International University Africa', short_code='USIU', country='Kenya'),
    dict(name='Africa Nazarene University', short_code='ANU', country='Kenya'),
    dict(name='Kenya Methodist University', short_code='KEMU', country='Kenya'),
    dict(name="St. Paul's University", short_code='SPU-KE', country='Kenya'),
    dict(name='Pan Africa Christian University', short_code='PACU', country='Kenya'),
    dict(name='Strathmore University', short_code='STRATH', country='Kenya'),
    dict(name='Kabarak University', short_code='KABARAK', country='Kenya'),
    dict(name='Mount Kenya University', short_code='MKU', country='Kenya'),
    dict(name='Africa International University', short_code='AIU', country='Kenya'),
    dict(name='Kenya Highlands Evangelical University', short_code='KHEU', country='Kenya'),
    dict(name='Great Lakes University of Kisumu', short_code='GLUK', country='Kenya'),
    dict(name='KCA University', short_code='KCAU', country='Kenya'),
    dict(name='Adventist University of Africa', short_code='ADVUA', country='Kenya'),
    dict(name='KAG EAST University', short_code='KAGEAST', country='Kenya'),
    dict(name='Umma University', short_code='UMMA', country='Kenya'),
    dict(name='Presbyterian University of East Africa', short_code='PUEA', country='Kenya'),
    dict(name='Aga Khan University', short_code='AKU', country='Kenya'),
    dict(name="Kiriri Women's University of Science and Technology", short_code='KWUST', country='Kenya'),
    dict(name='The East African University', short_code='TEAU', country='Kenya'),
    dict(name='Zetech University', short_code='ZETECH', country='Kenya'),
    dict(name='Lukenya University', short_code='LUKENYA', country='Kenya'),
    dict(name='Management University of Africa', short_code='MUA', country='Kenya'),
    dict(name='Tangaza University', short_code='TANGAZA', country='Kenya'),
    dict(name='Islamic University of Kenya', short_code='IUK-KE', country='Kenya'),
    dict(name='Riara University', short_code='RIARA', country='Kenya'),
    dict(name='Uzima University', short_code='UZIMA', country='Kenya'),
    dict(name='Gretsa University', short_code='GRETSA', country='Kenya'),
    dict(name='Amref International University', short_code='AMREF', country='Kenya'),
    dict(name='National Defence University - Kenya', short_code='NDUK', country='Kenya'),
    dict(name='Open University of Kenya', short_code='OUK-KE', country='Kenya'),
    dict(name='National Intelligence Research University', short_code='NIRU', country='Kenya'),
    dict(name='Makerere University', short_code='MAK', country='Uganda'),
    dict(name='Kyambogo University', short_code='KYAMBOGO', country='Uganda'),
    dict(name='Mbarara University of Science and Technology', short_code='MUST-UG', country='Uganda'),
    dict(name='Busitema University', short_code='BUSITEMA', country='Uganda'),
    dict(name='Gulu University', short_code='GULU', country='Uganda'),
    dict(name='Muni University', short_code='MUNI', country='Uganda'),
    dict(name='Soroti University', short_code='SOROTI', country='Uganda'),
    dict(name='Uganda Christian University', short_code='UCU', country='Uganda'),
    dict(name='Uganda Martyrs University', short_code='UMU-UG', country='Uganda'),
    dict(name='Uganda Technology and Management University', short_code='UTAMU', country='Uganda'),
    dict(name='Kampala International University', short_code='KIU', country='Uganda'),
    dict(name='Islamic University in Uganda', short_code='IUIU', country='Uganda'),
    dict(name='Ndejje University', short_code='NDEJJE', country='Uganda'),
    dict(name='Bugema University', short_code='BUGEMA', country='Uganda'),
    dict(name='Kabale University', short_code='KABALE', country='Uganda'),
    dict(name='Lira University', short_code='LIRA', country='Uganda'),
    dict(name='University of Dar es Salaam', short_code='UDSM', country='Tanzania'),
    dict(name='Sokoine University of Agriculture', short_code='SUA', country='Tanzania'),
    dict(name='Ardhi University', short_code='ARU', country='Tanzania'),
    dict(name='Muhimbili University of Health and Allied Sciences', short_code='MUHAS', country='Tanzania'),
    dict(name='Mzumbe University', short_code='MZUMBE', country='Tanzania'),
    dict(name='Open University of Tanzania', short_code='OUT-TZ', country='Tanzania'),
    dict(name='St. Augustine University of Tanzania', short_code='SAUT', country='Tanzania'),
    dict(name='Tumaini University Makumira', short_code='TUMA', country='Tanzania'),
    dict(name='State University of Zanzibar', short_code='SUZA', country='Tanzania'),
    dict(name='University of Dodoma', short_code='UDOM', country='Tanzania'),
    dict(name='Nelson Mandela African Institution of Science and Technology', short_code='NMAIST', country='Tanzania'),
    dict(name='University of Rwanda', short_code='UR', country='Rwanda'),
    dict(name='Kigali Independent University (ULK)', short_code='ULK', country='Rwanda'),
    dict(name='Adventist University of Central Africa', short_code='AUCA', country='Rwanda'),
    dict(name='Mount Kenya University Rwanda', short_code='MKU-RW', country='Rwanda'),
    dict(name='Carnegie Mellon University Africa', short_code='CMU-AFRICA', country='Rwanda'),
]

# (course name, discipline_category) - paired with EVERY university above.
COURSES = [
    ('BSc Actuarial Science', 'Business, Actuarial Science & Statistics'),
    ('Bachelor of Commerce (Accounting)', 'Business, Actuarial Science & Statistics'),
    ('Bachelor of Commerce (Finance)', 'Business, Actuarial Science & Statistics'),
    ('Bachelor of Commerce (Marketing)', 'Business, Actuarial Science & Statistics'),
    ('Bachelor of Commerce (Management)', 'Business, Actuarial Science & Statistics'),
    ('Bachelor of Commerce (Human Resource Management)', 'Business, Actuarial Science & Statistics'),
    ('Bachelor of Commerce (Procurement & Supply Chain Management)', 'Business, Actuarial Science & Statistics'),
    ('Bachelor of Commerce (Insurance)', 'Business, Actuarial Science & Statistics'),
    ('Bachelor of Economics', 'Business, Actuarial Science & Statistics'),
    ('Bachelor of Economics and Statistics', 'Business, Actuarial Science & Statistics'),
    ('Bachelor of Economics and Finance', 'Business, Actuarial Science & Statistics'),
    ('BSc Mathematics', 'Business, Actuarial Science & Statistics'),
    ('BSc Mathematics & Computer Science', 'Business, Actuarial Science & Statistics'),
    ('BSc Applied Statistics', 'Business, Actuarial Science & Statistics'),
    ('BSc Statistics', 'Business, Actuarial Science & Statistics'),
    ('BSc Statistics & Programming', 'Business, Actuarial Science & Statistics'),
    ('Bachelor of Business Administration', 'Business, Actuarial Science & Statistics'),
    ('Bachelor of Business Information Technology', 'Business, Actuarial Science & Statistics'),
    ('Bachelor of Procurement and Logistics Management', 'Business, Actuarial Science & Statistics'),
    ('BSc Financial Engineering', 'Business, Actuarial Science & Statistics'),
    ('Bachelor of Cooperative Management', 'Business, Actuarial Science & Statistics'),
    ('Bachelor of Laws (LLB)', 'Law'),
    ('Bachelor of Hospitality Management', 'Business & Hospitality'),
    ('Bachelor of Tourism Management', 'Business & Hospitality'),
    ('Bachelor of Hotel and Institution Management', 'Business & Hospitality'),
    ('Bachelor of Travel and Tourism Management', 'Business & Hospitality'),
    ('Bachelor of Events Management', 'Business & Hospitality'),
    ('Bachelor of Arts', 'Social Sciences & Arts'),
    ('Bachelor of Arts (Sociology)', 'Social Sciences & Arts'),
    ('Bachelor of Arts (Psychology)', 'Social Sciences & Arts'),
    ('Bachelor of Arts (Political Science)', 'Social Sciences & Arts'),
    ('Bachelor of Arts (Public Administration)', 'Social Sciences & Arts'),
    ('Bachelor of Arts in Communication and Media', 'Social Sciences & Arts'),
    ('Bachelor of Journalism and Mass Communication', 'Social Sciences & Arts'),
    ('Bachelor of Fine Art', 'Social Sciences & Arts'),
    ('Bachelor of Arts (Film and Animation)', 'Social Sciences & Arts'),
    ('Bachelor of Arts (Theatre and Film Technology)', 'Social Sciences & Arts'),
    ('Bachelor of Social Work', 'Social Sciences & Arts'),
    ('Bachelor of Arts in Linguistics', 'Social Sciences & Arts'),
    ('Bachelor of Arts (Literature)', 'Social Sciences & Arts'),
    ('Bachelor of Arts (Criminology and Security Studies)', 'Social Sciences & Arts'),
    ('Bachelor of Arts (International Relations and Diplomacy)', 'Social Sciences & Arts'),
    ('Bachelor of Arts (Development Studies)', 'Social Sciences & Arts'),
    ('Bachelor of Arts (Anthropology)', 'Social Sciences & Arts'),
    ('Bachelor of Arts (Gender and Development Studies)', 'Social Sciences & Arts'),
    ('Bachelor of Arts (Religious Studies)', 'Social Sciences & Arts'),
    ('Bachelor of Arts (History)', 'Social Sciences & Arts'),
    ('Bachelor of Arts (Geography)', 'Social Sciences & Arts'),
    ('Bachelor of Music', 'Social Sciences & Arts'),
    ('BSc Geology', 'Geosciences'),
    ('BSc Mining Engineering', 'Geosciences'),
    ('BSc Geospatial Engineering', 'Geosciences'),
    ('BSc Meteorology', 'Geosciences'),
    ('Bachelor of Engineering (Civil Engineering)', 'Engineering'),
    ('Bachelor of Engineering (Mechanical Engineering)', 'Engineering'),
    ('Bachelor of Engineering (Electrical and Electronic Engineering)', 'Engineering'),
    ('Bachelor of Engineering (Electrical and Computer Engineering)', 'Engineering'),
    ('Bachelor of Engineering (Chemical Engineering)', 'Engineering'),
    ('Bachelor of Engineering (Mechatronic Engineering)', 'Engineering'),
    ('Bachelor of Engineering (Biomedical Engineering)', 'Engineering'),
    ('Bachelor of Engineering (Telecommunication Engineering)', 'Engineering'),
    ('Bachelor of Engineering (Agricultural Engineering)', 'Engineering'),
    ('BSc Electrical and Electronic Engineering', 'Engineering'),
    ('BSc Mechanical Engineering', 'Engineering'),
    ('BSc Civil Engineering', 'Engineering'),
    ('BSc Industrial Engineering', 'Engineering'),
    ('BSc Petroleum Engineering', 'Engineering'),
    ('BSc Textile Engineering', 'Engineering'),
    ('Bachelor of Architecture', 'Architecture & Built Environment'),
    ('Bachelor of Architectural Studies', 'Architecture & Built Environment'),
    ('Bachelor of Quantity Surveying', 'Architecture & Built Environment'),
    ('Bachelor of Land Economics', 'Architecture & Built Environment'),
    ('Bachelor of Real Estate', 'Architecture & Built Environment'),
    ('Bachelor of Construction Management', 'Architecture & Built Environment'),
    ('Bachelor of Urban and Regional Planning', 'Architecture & Built Environment'),
    ('BSc Computer Science', 'Computing & IT'),
    ('BSc Information Technology', 'Computing & IT'),
    ('BSc Software Engineering', 'Computing & IT'),
    ('BSc Computer Technology', 'Computing & IT'),
    ('BSc Data Science', 'Computing & IT'),
    ('BSc Cyber Security and Digital Forensics', 'Computing & IT'),
    ('BSc Information Systems', 'Computing & IT'),
    ('BSc Artificial Intelligence', 'Computing & IT'),
    ('BSc Agribusiness Management', 'Agribusiness'),
    ('BSc Agricultural Economics', 'Agribusiness'),
    ('Bachelor of Agribusiness and Trade', 'Agribusiness'),
    ('BSc Biology', 'Sciences'),
    ('BSc Zoology', 'Sciences'),
    ('BSc Botany', 'Sciences'),
    ('BSc Microbiology', 'Sciences'),
    ('BSc Microbiology and Biotechnology', 'Sciences'),
    ('BSc Molecular and Cellular Biology', 'Sciences'),
    ('BSc Biochemistry', 'Sciences'),
    ('BSc Chemistry', 'Sciences'),
    ('BSc Physics', 'Sciences'),
    ('BSc Applied Physics', 'Sciences'),
    ('BSc Biotechnology', 'Sciences'),
    ('BSc Conservation Biology', 'Sciences'),
    ('BSc Genomic Sciences', 'Sciences'),
    ('BSc Applied Biology', 'Sciences'),
    ('BSc Entomology and Parasitology', 'Sciences'),
    ('BSc Forensic Biology', 'Sciences'),
    ('BSc Medical Biochemistry', 'Sciences'),
    ('BSc Environmental Chemistry', 'Sciences'),
    ('BSc Industrial Chemistry', 'Sciences'),
    ('Bachelor of Interior Design', 'Design & Textiles'),
    ('Bachelor of Fashion Design and Marketing', 'Design & Textiles'),
    ('Bachelor of Textile Technology', 'Design & Textiles'),
    ('Bachelor of Medicine and Bachelor of Surgery (MBChB)', 'Medicine & Health Sciences'),
    ('Bachelor of Pharmacy', 'Medicine & Health Sciences'),
    ('Bachelor of Dental Surgery', 'Medicine & Health Sciences'),
    ('Bachelor of Science in Nursing', 'Medicine & Health Sciences'),
    ('Bachelor of Science in Clinical Medicine', 'Medicine & Health Sciences'),
    ('Bachelor of Science in Public Health', 'Medicine & Health Sciences'),
    ('Bachelor of Science in Nutrition and Dietetics', 'Medicine & Health Sciences'),
    ('Bachelor of Science in Medical Laboratory Sciences', 'Medicine & Health Sciences'),
    ('Bachelor of Science in Physiotherapy', 'Medicine & Health Sciences'),
    ('Bachelor of Science in Environmental Health', 'Medicine & Health Sciences'),
    ('Bachelor of Veterinary Medicine', 'Medicine & Health Sciences'),
    ('Bachelor of Science in Radiography', 'Medicine & Health Sciences'),
    ('Bachelor of Science in Health Records and Information Management', 'Medicine & Health Sciences'),
    ('Bachelor of Science in Occupational Therapy', 'Medicine & Health Sciences'),
    ('Bachelor of Science in Community Health and Development', 'Medicine & Health Sciences'),
    ('BSc Agriculture', 'Agriculture & Environment'),
    ('BSc Animal Health and Production', 'Agriculture & Environment'),
    ('BSc Animal Science', 'Agriculture & Environment'),
    ('BSc Food Science and Technology', 'Agriculture & Environment'),
    ('BSc Horticulture', 'Agriculture & Environment'),
    ('BSc Agricultural Extension', 'Agriculture & Environment'),
    ('BSc Range Management', 'Agriculture & Environment'),
    ('BSc Agroforestry and Rural Development', 'Agriculture & Environment'),
    ('BSc Land Resource Management', 'Agriculture & Environment'),
    ('BSc Wildlife Management', 'Agriculture & Environment'),
    ('BSc Fisheries and Aquaculture Sciences', 'Agriculture & Environment'),
    ('BSc Dairy Science and Technology', 'Agriculture & Environment'),
    ('BSc Environmental Science', 'Agriculture & Environment'),
    ('BSc Natural Resource Management', 'Agriculture & Environment'),
    ('BSc Water and Environmental Management', 'Agriculture & Environment'),
    ('BSc Soil, Water and Environmental Engineering', 'Agriculture & Environment'),
    ('BSc Forestry', 'Agriculture & Environment'),
    ('Bachelor of Education (Arts)', 'Education'),
    ('Bachelor of Education (Science)', 'Education'),
    ('Bachelor of Education (Early Childhood Development)', 'Education'),
    ('Bachelor of Education (Special Needs Education)', 'Education'),
    ('Bachelor of Education (Technology)', 'Education'),
    ('Bachelor of Education (Primary Option)', 'Education'),
]


def main():
    with app.app_context():
        existing_unis = {u.name: u for u in University.query.all()}
        new_uni_count = 0
        for u in UNIVERSITIES:
            if u["name"] not in existing_unis:
                new_uni_count += 1
                if not DRY_RUN:
                    row = University(name=u["name"], short_code=u["short_code"], country=u["country"])
                    db.session.add(row)
        if not DRY_RUN:
            db.session.flush()  # assigns ids to newly-added universities without a full commit yet

        # Re-read the full name->row map now that new ones have ids (or,
        # in dry-run mode, just use what already existed in the DB).
        all_unis = {u.name: u for u in University.query.all()} if not DRY_RUN else existing_unis

        existing_programs = set(
            (p.university_id, p.name)
            for p in Program.query.with_entities(Program.university_id, Program.name).all()
        )

        new_program_count = 0
        skipped_no_uni_id = 0
        for u in UNIVERSITIES:
            uni_row = all_unis.get(u["name"])
            if uni_row is None or uni_row.id is None:
                # Only happens in --dry-run for universities that don't exist yet -
                # we can't know their future id, so just count them as "would add".
                if DRY_RUN and u["name"] not in existing_unis:
                    new_program_count += len(COURSES)
                    continue
                skipped_no_uni_id += 1
                continue
            for course_name, category in COURSES:
                key = (uni_row.id, course_name)
                if key in existing_programs:
                    continue
                new_program_count += 1
                if not DRY_RUN:
                    db.session.add(Program(
                        university_id=uni_row.id,
                        name=course_name,
                        degree_level="Bachelors",
                        discipline_category=category,
                    ))
                    existing_programs.add(key)  # guard against dupes within this same run

        if DRY_RUN:
            print(f"[DRY RUN] Would create {new_uni_count} new universities.")
            print(f"[DRY RUN] Would create {new_program_count} new programs.")
            print("[DRY RUN] Nothing written. Re-run without --dry-run to actually seed.")
            db.session.rollback()
        else:
            db.session.commit()
            print(f"Created {new_uni_count} new universities.")
            print(f"Created {new_program_count} new programs.")
            print("Done.")


if __name__ == "__main__":
    main()
