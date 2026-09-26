-- Academic targeting for student opportunities.
CREATE TABLE IF NOT EXISTS saved_opportunity (
 id BIGSERIAL PRIMARY KEY,
 user_id INTEGER NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
 opportunity_id INTEGER NOT NULL REFERENCES opportunity(id) ON DELETE CASCADE,
 created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
 CONSTRAINT uq_saved_opportunity_user_opp UNIQUE(user_id,opportunity_id)
);
CREATE TABLE IF NOT EXISTS opportunity_university_target (
 id BIGSERIAL PRIMARY KEY,
 opportunity_id INTEGER NOT NULL REFERENCES opportunity(id) ON DELETE CASCADE,
 university_id INTEGER NOT NULL REFERENCES university(id) ON DELETE CASCADE,
 CONSTRAINT uq_opp_university_target UNIQUE(opportunity_id,university_id)
);
CREATE INDEX IF NOT EXISTS ix_opp_university_target_university ON opportunity_university_target(university_id);
CREATE TABLE IF NOT EXISTS opportunity_program_target (
 id BIGSERIAL PRIMARY KEY,
 opportunity_id INTEGER NOT NULL REFERENCES opportunity(id) ON DELETE CASCADE,
 program_id INTEGER NOT NULL REFERENCES program(id) ON DELETE CASCADE,
 CONSTRAINT uq_opp_program_target UNIQUE(opportunity_id,program_id)
);
CREATE INDEX IF NOT EXISTS ix_opp_program_target_program ON opportunity_program_target(program_id);
CREATE TABLE IF NOT EXISTS opportunity_year_target (
 id BIGSERIAL PRIMARY KEY,
 opportunity_id INTEGER NOT NULL REFERENCES opportunity(id) ON DELETE CASCADE,
 year INTEGER NOT NULL,
 CONSTRAINT uq_opp_year_target UNIQUE(opportunity_id,year)
);
CREATE INDEX IF NOT EXISTS ix_opp_year_target_year ON opportunity_year_target(year);
CREATE TABLE IF NOT EXISTS opportunity_semester_target (
 id BIGSERIAL PRIMARY KEY,
 opportunity_id INTEGER NOT NULL REFERENCES opportunity(id) ON DELETE CASCADE,
 semester INTEGER NOT NULL,
 CONSTRAINT uq_opp_semester_target UNIQUE(opportunity_id,semester)
);
CREATE INDEX IF NOT EXISTS ix_opp_semester_target_semester ON opportunity_semester_target(semester);
