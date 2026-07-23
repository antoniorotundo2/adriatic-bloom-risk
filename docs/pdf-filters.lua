-- Pandoc Lua filter for the PDF build only (docs/technical-report.md stays
-- plain markdown for GitHub, this filter never touches the source file).
--
-- 1. The document title is a level-1 heading in the body (not pandoc title
--    metadata), so it would otherwise show up in the table of contents as
--    a section with every other heading nested under it. Marking it
--    unlisted/unnumbered keeps it as a normal in-page heading without that
--    TOC artefact.
-- 2. Long DOI URLs and unbreakable parentheticals in the References section
--    can force LaTeX to over-stretch a justified line; ragged-right avoids
--    this without affecting the rest of the report.
function Pandoc(doc)
  local out = {}
  local found_title = false
  local found_refs = false
  for _, block in ipairs(doc.blocks) do
    if not found_title and block.t == "Header" and block.level == 1 then
      block.classes = pandoc.List({"unlisted", "unnumbered"})
      found_title = true
    end
    table.insert(out, block)
    if not found_refs and block.t == "Header" and pandoc.utils.stringify(block.content) == "References" then
      table.insert(out, pandoc.RawBlock("latex", "\\raggedright"))
      found_refs = true
    end
  end
  doc.blocks = out
  return doc
end
