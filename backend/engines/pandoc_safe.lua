-- Neutralise everything that would make a Pandoc writer read local files or fetch URLs:
-- images that are neither inline data nor already embedded in the input document
-- (e.g. DOCX media) become their alt text; raw passthrough blocks are dropped.
local function is_embedded(src)
  return src:match("^data:") ~= nil or pandoc.mediabag.lookup(src) ~= nil
end

function Image(el)
  if not is_embedded(el.src) then
    return el.caption
  end
end

function RawBlock(_)
  return {}
end

function RawInline(_)
  return {}
end
