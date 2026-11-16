-- Candidate PDFs for the AI server smoke test (scripts/smoke_test.sh --pdf FILE).
--
-- Read-only: run it on a read-only connection to the Grottocenter database, for example
--   psql "$READONLY_URL" -f scripts/smoke_candidates.sql
--
-- What it returns: a few documents per type and size class, each with its title, licence,
-- page range and the public URL of its PDF. Pick one small document for the first run, and
-- the largest one to see how long a big analysis takes (a request over 2 minutes has to
-- get through Traefik).
--
-- What it keeps, and why:
--   * Public documents: validated, not deleted, not merged into another document
--     (redirect_to), and with no modification waiting for review.
--   * A validated PDF file. The size of the file is not in the database: check it before
--     downloading with  curl -sI <url> | grep -i content-length  (the server refuses
--     anything over 50 MB, and over 300 pages).
--   * Licences that allow reuse (CC-BY-SA, CC-BY, ODbL, ODC-BY, Licence Ouverte), because
--     the text of the document is sent to GreenPT. `t_license.is_copyrighted` is not used:
--     its values do not follow the licence (CC-BY-SA is true, ODbL is false).
--   * Documents of the types Book, Issue, Article and Report: the shapes the analysis is
--     written for (an Issue is split into its articles).
--   * Nothing tied to a sensitive place: a PDF can contain coordinates. Documents linked to
--     a sensitive entrance or massif are left out, whether the link is a direct one
--     (id_massif, id_cave) or goes through j_document_entrance / j_document_massif.
--
-- What it does not know: whether the PDF has a text layer or is a scan. Try one of each.
--
-- Output: no personal data (no author, no email), only what is already public.

WITH candidates AS (
  SELECT
    d.id,
    t.name AS type,
    l.name AS license,
    d.pages,
    -- "12-20" gives 9; anything else (empty, "p. 12", "xii", "20-10") gives NULL.
    -- The cast sits inside a nested CASE because SQL does not promise that the left side of
    -- an AND is evaluated first, and a cast on a non-number would fail the whole query.
    -- At most 6 digits per side, so that a huge number cannot overflow an int.
    CASE
      WHEN d.pages ~ '^\s*\d{1,6}\s*-\s*\d{1,6}\s*$' THEN
        CASE
          WHEN split_part(d.pages, '-', 2)::int >= split_part(d.pages, '-', 1)::int
          THEN split_part(d.pages, '-', 2)::int - split_part(d.pages, '-', 1)::int + 1
        END
    END AS approx_pages,
    d.date_publication,
    f.filename,
    'https://grottocenter.blob.core.windows.net/documents/' || f.path AS url,
    (
      SELECT de.title
      FROM t_description de
      WHERE de.id_document = d.id AND NOT de.is_deleted
      ORDER BY de.relevance DESC NULLS LAST, de.id
      LIMIT 1
    ) AS title
  FROM t_document d
  JOIN t_type t ON t.id = d.id_type
  JOIN t_license l ON l.id = d.id_license
  JOIN t_file f ON f.id_document = d.id
  JOIN t_file_format ff ON ff.id = f.id_file_format
  WHERE d.is_validated
    AND NOT d.is_deleted
    AND d.redirect_to IS NULL
    AND d.modified_doc_json IS NULL
    AND t.name IN ('Book', 'Issue', 'Article', 'Report')
    AND l.name IN ('CC-BY-SA', 'CC-BY', 'ODBL', 'ODC-BY', 'Licence Ouverte')
    AND f.is_validated
    AND ff.extension = 'pdf'
    AND f.path IS NOT NULL AND f.path <> ''
    -- linked directly to a sensitive massif
    AND NOT EXISTS (
      SELECT 1 FROM t_massif m WHERE m.id = d.id_massif AND m.is_sensitive
    )
    -- linked through the join tables to a sensitive massif or entrance
    AND NOT EXISTS (
      SELECT 1 FROM j_document_massif jm
      JOIN t_massif m ON m.id = jm.id_massif
      WHERE jm.id_document = d.id AND m.is_sensitive
    )
    AND NOT EXISTS (
      SELECT 1 FROM j_document_entrance je
      JOIN t_entrance e ON e.id = je.id_entrance
      WHERE je.id_document = d.id AND e.is_sensitive
    )
    -- linked to a cave that has a sensitive entrance (t_cave has no sensitivity flag)
    AND NOT EXISTS (
      SELECT 1 FROM t_entrance e WHERE e.id_cave = d.id_cave AND e.is_sensitive
    )
),
classified AS (
  SELECT
    c.*,
    CASE
      WHEN approx_pages IS NULL THEN 'unknown size'
      WHEN approx_pages <= 10   THEN 'S: up to 10 pages'
      WHEN approx_pages <= 60   THEN 'M: 11 to 60 pages'
      ELSE                           'L: over 60 pages'
    END AS size_class
  FROM candidates c
),
ranked AS (
  SELECT
    x.*,
    -- md5 gives a stable pseudo-random order, so a second run shows the same documents
    row_number() OVER (PARTITION BY type, size_class ORDER BY md5(id::text)) AS rn
  FROM classified x
)
SELECT
  id,
  type,
  size_class,
  approx_pages,
  license,
  date_publication,
  left(title, 70) AS title,
  url
FROM ranked
WHERE rn <= 3
ORDER BY type, size_class, rn;
