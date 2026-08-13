/**
 * Hardcoded reference data for the signup wizard's university + course
 * dropdowns (type-to-filter, click to select; "not found" = signup blocked).
 *
 * WHY THIS EXISTS (see chat history for full reasoning):
 * - Cataloging an accurate, unique course list per individual university
 *   isn't realistically maintainable - there are 100+ institutions here
 *   and each offers dozens of programs, with pages that go stale constantly.
 * - Instead: one deduplicated SHARED_COURSES list is paired with ANY
 *   university. This intentionally isn't 100% accurate per-institution
 *   (e.g. it won't know a given college doesn't offer Actuarial Science),
 *   but it satisfies the actual product requirement - a narrowing
 *   typeahead where an unlisted course is explicitly rejected rather than
 *   silently accepted as free text.
 *
 * SOURCES: Commission for University Education (CUE) accredited list
 * (as at 12 March 2026) for Kenya; Wikipedia "List of universities in
 * Uganda/Rwanda", uniRank, for the East Africa shortlist. Course names
 * consolidated and deduplicated from KUCCPS's 2026 20-cluster degree
 * programme list (500+ raw entries collapsed to ~155 canonical names).
 *
 * NEXT STEP (flagged, not done here): for /signup's university_id /
 * program_id validation to accept anything beyond Kenyatta University,
 * these need to be seeded as real University + Program rows in Supabase.
 * This file is the frontend source of truth either way.
 */

export interface Institution {
  name: string
  country: 'Kenya' | 'Uganda' | 'Tanzania' | 'Rwanda'
}

// ─── Kenya: public chartered universities (36, per CUE list) ──────────────
const KENYA_PUBLIC: Institution[] = [
  'University of Nairobi', 'Moi University', 'Kenyatta University', 'Egerton University',
  'Jomo Kenyatta University of Agriculture and Technology', 'Maseno University',
  'Masinde Muliro University of Science and Technology', 'Dedan Kimathi University of Technology',
  'Chuka University', 'Technical University of Kenya', 'Technical University of Mombasa',
  'Pwani University', 'Kisii University', 'University of Eldoret', 'Maasai Mara University',
  'Jaramogi Oginga Odinga University of Science and Technology', 'Laikipia University',
  'South Eastern Kenya University', 'Meru University of Science and Technology',
  'Multimedia University of Kenya', 'University of Kabianga', 'Karatina University',
  'Kibabii University', 'Rongo University', 'The Co-operative University of Kenya',
  'Taita Taveta University', "Murang'a University of Technology", 'University of Embu',
  'Machakos University', 'Kirinyaga University', 'Garissa University', 'Alupe University',
  'Kaimosi Friends University', 'Tom Mboya University', 'Tharaka University', 'Bomet University',
].map(name => ({ name, country: 'Kenya' as const }))

// ─── Kenya: private chartered universities (32, per CUE list) ─────────────
const KENYA_PRIVATE: Institution[] = [
  'University of Eastern Africa, Baraton', 'Catholic University of Eastern Africa', 'Daystar University',
  'Scott Christian University', 'United States International University Africa', 'Africa Nazarene University',
  'Kenya Methodist University', "St. Paul's University", 'Pan Africa Christian University',
  'Strathmore University', 'Kabarak University', 'Mount Kenya University', 'Africa International University',
  'Kenya Highlands Evangelical University', 'Great Lakes University of Kisumu', 'KCA University',
  'Adventist University of Africa', 'KAG EAST University', 'Umma University',
  'Presbyterian University of East Africa', 'Aga Khan University',
  "Kiriri Women's University of Science and Technology", 'The East African University', 'Zetech University',
  'Lukenya University', 'Management University of Africa', 'Tangaza University', 'Islamic University of Kenya',
  'Riara University', 'Uzima University', 'Gretsa University', 'Amref International University',
].map(name => ({ name, country: 'Kenya' as const }))

// ─── Kenya: specialized public degree-awarding institutions ───────────────
const KENYA_SPECIALIZED: Institution[] = [
  'National Defence University - Kenya', 'Open University of Kenya', 'National Intelligence Research University',
].map(name => ({ name, country: 'Kenya' as const }))

// ─── East Africa shortlist: major/flagship universities only ──────────────
const UGANDA: Institution[] = [
  'Makerere University', 'Kyambogo University', 'Mbarara University of Science and Technology',
  'Busitema University', 'Gulu University', 'Muni University', 'Soroti University',
  'Uganda Christian University', 'Uganda Martyrs University', 'Uganda Technology and Management University',
  'Kampala International University', 'Islamic University in Uganda', 'Ndejje University',
  'Bugema University', 'Kabale University', 'Lira University',
].map(name => ({ name, country: 'Uganda' as const }))

const TANZANIA: Institution[] = [
  'University of Dar es Salaam', 'Sokoine University of Agriculture', 'Ardhi University',
  'Muhimbili University of Health and Allied Sciences', 'Mzumbe University', 'Open University of Tanzania',
  'St. Augustine University of Tanzania', 'Tumaini University Makumira', 'State University of Zanzibar',
  'University of Dodoma', 'Nelson Mandela African Institution of Science and Technology',
].map(name => ({ name, country: 'Tanzania' as const }))

const RWANDA: Institution[] = [
  'University of Rwanda', 'Kigali Independent University (ULK)', 'Adventist University of Central Africa',
  'Mount Kenya University Rwanda', 'Carnegie Mellon University Africa',
].map(name => ({ name, country: 'Rwanda' as const }))

export const INSTITUTIONS: Institution[] = [
  ...KENYA_PUBLIC, ...KENYA_PRIVATE, ...KENYA_SPECIALIZED, ...UGANDA, ...TANZANIA, ...RWANDA,
].sort((a, b) => a.name.localeCompare(b.name))

// ─── Shared course/programme master list ───────────────────────────────────
// Deduplicated & consolidated from KUCCPS's 2026 20-cluster degree list.
// Paired with ANY university in INSTITUTIONS above (see file header).
export const SHARED_COURSES: string[] = [
  // Actuarial Science, Accountancy, Mathematics, Economics, Statistics & related
  'BSc Actuarial Science', 'Bachelor of Commerce (Accounting)', 'Bachelor of Commerce (Finance)',
  'Bachelor of Commerce (Marketing)', 'Bachelor of Commerce (Management)',
  'Bachelor of Commerce (Human Resource Management)', 'Bachelor of Commerce (Procurement & Supply Chain Management)',
  'Bachelor of Commerce (Insurance)', 'Bachelor of Economics', 'Bachelor of Economics and Statistics',
  'Bachelor of Economics and Finance', 'BSc Mathematics', 'BSc Mathematics and Computer Science',
  'BSc Applied Statistics', 'BSc Statistics', 'BSc Statistics and Programming',
  'Bachelor of Business Administration', 'Bachelor of Business Information Technology',
  'Bachelor of Procurement and Logistics Management', 'BSc Financial Engineering',
  'Bachelor of Cooperative Management',

  // Law
  'Bachelor of Laws (LLB)',

  // Business & Hospitality
  'Bachelor of Hospitality Management', 'Bachelor of Tourism Management',
  'Bachelor of Hotel and Institution Management', 'Bachelor of Travel and Tourism Management',
  'Bachelor of Events Management',

  // Social Sciences, Media, Fine Arts, Film, Animation, Graphics
  'Bachelor of Arts', 'Bachelor of Arts (Sociology)', 'Bachelor of Arts (Psychology)',
  'Bachelor of Arts (Political Science)', 'Bachelor of Arts (Public Administration)',
  'Bachelor of Arts in Communication and Media', 'Bachelor of Journalism and Mass Communication',
  'Bachelor of Fine Art', 'Bachelor of Arts (Film and Animation)', 'Bachelor of Arts (Theatre and Film Technology)',
  'Bachelor of Social Work', 'Bachelor of Arts in Linguistics', 'Bachelor of Arts (Literature)',
  'Bachelor of Arts (Criminology and Security Studies)', 'Bachelor of Arts (International Relations and Diplomacy)',
  'Bachelor of Arts (Development Studies)', 'Bachelor of Arts (Anthropology)',
  'Bachelor of Arts (Gender and Development Studies)', 'Bachelor of Arts (Religious Studies)',
  'Bachelor of Arts (History)', 'Bachelor of Arts (Geography)', 'Bachelor of Music',

  // Geosciences
  'BSc Geology', 'BSc Mining Engineering', 'BSc Geospatial Engineering', 'BSc Meteorology',

  // Engineering
  'Bachelor of Engineering (Civil Engineering)', 'Bachelor of Engineering (Mechanical Engineering)',
  'Bachelor of Engineering (Electrical and Electronic Engineering)',
  'Bachelor of Engineering (Electrical and Computer Engineering)', 'Bachelor of Engineering (Chemical Engineering)',
  'Bachelor of Engineering (Mechatronic Engineering)', 'Bachelor of Engineering (Biomedical Engineering)',
  'Bachelor of Engineering (Telecommunication Engineering)', 'Bachelor of Engineering (Agricultural Engineering)',
  'BSc Electrical and Electronic Engineering', 'BSc Mechanical Engineering', 'BSc Civil Engineering',
  'BSc Industrial Engineering', 'BSc Petroleum Engineering', 'BSc Textile Engineering',

  // Architecture, Building & related
  'Bachelor of Architecture', 'Bachelor of Architectural Studies', 'Bachelor of Quantity Surveying',
  'Bachelor of Land Economics', 'Bachelor of Real Estate', 'Bachelor of Construction Management',
  'Bachelor of Urban and Regional Planning',

  // Computing / IT
  'BSc Computer Science', 'BSc Information Technology', 'BSc Software Engineering', 'BSc Computer Technology',
  'BSc Data Science', 'BSc Cyber Security and Digital Forensics', 'BSc Information Systems',
  'BSc Artificial Intelligence',

  // Agribusiness
  'BSc Agribusiness Management', 'BSc Agricultural Economics', 'Bachelor of Agribusiness and Trade',

  // General Science, Biological Sciences, Physics, Chemistry
  'BSc Biology', 'BSc Zoology', 'BSc Botany', 'BSc Microbiology', 'BSc Microbiology and Biotechnology',
  'BSc Molecular and Cellular Biology', 'BSc Biochemistry', 'BSc Chemistry', 'BSc Physics',
  'BSc Applied Physics', 'BSc Biotechnology', 'BSc Conservation Biology', 'BSc Genomic Sciences',
  'BSc Applied Biology', 'BSc Entomology and Parasitology', 'BSc Forensic Biology',
  'BSc Medical Biochemistry', 'BSc Environmental Chemistry', 'BSc Industrial Chemistry',

  // Interior Design, Fashion Design, Textiles
  'Bachelor of Interior Design', 'Bachelor of Fashion Design and Marketing', 'Bachelor of Textile Technology',

  // Medicine, Health Sciences & Veterinary Medicine
  'Bachelor of Medicine and Bachelor of Surgery (MBChB)', 'Bachelor of Pharmacy', 'Bachelor of Dental Surgery',
  'Bachelor of Science in Nursing', 'Bachelor of Science in Clinical Medicine',
  'Bachelor of Science in Public Health', 'Bachelor of Science in Nutrition and Dietetics',
  'Bachelor of Science in Medical Laboratory Sciences', 'Bachelor of Science in Physiotherapy',
  'Bachelor of Science in Environmental Health', 'Bachelor of Veterinary Medicine',
  'Bachelor of Science in Radiography', 'Bachelor of Science in Health Records and Information Management',
  'Bachelor of Science in Occupational Therapy', 'Bachelor of Science in Community Health and Development',

  // Agriculture, Animal Health, Food Science, Nutrition, Environmental Sciences, Natural Resources
  'BSc Agriculture', 'BSc Animal Health and Production', 'BSc Animal Science',
  'BSc Food Science and Technology', 'BSc Horticulture', 'BSc Agricultural Extension',
  'BSc Range Management', 'BSc Agroforestry and Rural Development', 'BSc Land Resource Management',
  'BSc Wildlife Management', 'BSc Fisheries and Aquaculture Sciences', 'BSc Dairy Science and Technology',
  'BSc Environmental Science', 'BSc Natural Resource Management', 'BSc Water and Environmental Management',
  'BSc Soil, Water and Environmental Engineering', 'BSc Forestry',

  // Education
  'Bachelor of Education (Arts)', 'Bachelor of Education (Science)',
  'Bachelor of Education (Early Childhood Development)', 'Bachelor of Education (Special Needs Education)',
  'Bachelor of Education (Technology)', 'Bachelor of Education (Primary Option)',
].sort((a, b) => a.localeCompare(b))
