-- Library publication academic-context snapshot.
-- Safe to rerun. Existing publications are backfilled from their Unit where possible.

ALTER TABLE public.library_publication
  ADD COLUMN IF NOT EXISTS university_id integer REFERENCES public.university(id),
  ADD COLUMN IF NOT EXISTS program_id integer REFERENCES public.program(id),
  ADD COLUMN IF NOT EXISTS year integer,
  ADD COLUMN IF NOT EXISTS semester integer;

CREATE INDEX IF NOT EXISTS ix_library_publication_academic_context
  ON public.library_publication (university_id, program_id, year, semester, status);

UPDATE public.library_publication lp
SET university_id = u.university_id,
    year = u.year,
    semester = u.semester
FROM public.unit u
WHERE lp.unit_id = u.id
  AND (lp.university_id IS NULL OR lp.year IS NULL OR lp.semester IS NULL);
