-- The longest eligible PDFs, to find the biggest document the AI server will accept.
--
-- For the capacity check of the AI server VM (cloud_azure/ai_vm/README.md in the infra repo,
-- step 6): the peak memory of the server is measured while one of these is analysed. Read-only,
-- like scripts/smoke_candidates.sql, whose filters it repeats (keep the two in step):
-- public documents with a validated PDF, a licence that allows reuse (the text goes to
-- GreenPT), type Book, Issue, Article or Report, and nothing tied to a sensitive massif or
-- entrance (a PDF can contain coordinates).
--
-- It lists the 20 documents with the most pages between 40 and 300 (the server refuses over
-- 300 pages, MAX_PAGES). The database holds the page range but NOT the size of the file, and
-- what loads the server's memory is mostly the size (the bytes are held in memory, and a scan
-- is sent whole to OCR), so check the real sizes before choosing, and keep the server limit
-- of 50 MB in mind:
--
--   for u in <url> <url> ...; do
--     printf '%s MB  %s\n' "$(curl -sI "$u" | awk 'tolower($1)=="content-length:" {printf "%.1f", $2/1048576}')" "$u"
--   done
--
-- Then analyse the biggest one that is under 50 MB, and, to cover the other kind of load, the
-- one with the most pages. A very long text PDF is the expensive one in GreenPT calls.

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
)

SELECT
  id,
  type,
  approx_pages,
  license,
  date_publication,
  left(title, 70) AS title,
  url
FROM candidates
WHERE approx_pages BETWEEN 40 AND 300
ORDER BY approx_pages DESC, id
LIMIT 20;
