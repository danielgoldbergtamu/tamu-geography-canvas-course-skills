# Rules

Each rule names the WCAG 2.1 success criterion it serves. "Auto" fixes have one right
answer; "proposed" fixes are prefilled for review; "needs value" fixes need a person.

## Contents

- Rule table
- How the color fix works
- How a fix finds its element
- What is not checked

## Rule table

| Rule | WCAG | Finds | Fix |
|---|---|---|---|
| contrast | 1.4.3 | Inline text color below 4.5:1 against its background (3:1 for large text: 18pt, or 14pt bold, or inside h1 and h2) | Auto: the nearest color with the same hue and saturation that passes |
| fake-list | 1.3.1 | Two or more paragraphs in a row that start with a bullet or number | Report only |
| heading-empty | 1.3.1 | A heading with no text | Auto: remove it |
| heading-h1 | 1.3.1 | An h1 in a page body; Canvas uses h1 for the page title | Auto: make it h2 |
| heading-long | 2.4.6 | A heading over 120 characters | Report only |
| heading-skip | 1.3.1 | A heading more than one level below the one before it | Auto: one level below the one before |
| iframe-no-title | 4.1.2 | Embedded content with no title | Proposed: "Embedded content from <site>" |
| img-alt-long | 1.1.1 | Alt text over 150 characters | Needs value |
| img-alt-missing | 1.1.1 | An image with no alt attribute | Needs value, or `""` if decorative |
| img-alt-useless | 1.1.1 | Alt text that is a file name or the word "image" | Needs value |
| link-bare-url | 2.4.4 | Link text that is the web address itself (warning) | Needs value |
| link-empty | 2.4.4 | A link with no text, image alt or label | Needs value |
| link-vague | 2.4.4 | Link text such as "click here", "here", "read more", "details" | Needs value |
| table-no-caption | 1.3.1 | A table with no caption (warning) | Proposed: the nearest heading above |
| table-no-header | 1.3.1 | A table with cells but no header cells | Proposed: make the first row the header, or "skip" for a layout table |
| th-no-scope | 1.3.1 | A header cell without scope | Auto: `col` in the first row, `row` elsewhere |
| underline | 1.3.3 | Underlined text that is not a link (warning) | Report only |

## How the color fix works

The text color is converted to hue, lightness and saturation. Lightness is moved, one
percent at a time, toward whichever end passes first against the background, and the first
color that meets the required ratio is used. A light grey on white becomes the lightest
grey that passes (#bbbbbb becomes #767676), so the page keeps its look as closely as the
standard allows. The background is the nearest one set inline on the element or an
ancestor, or white, as in Canvas.

## How a fix finds its element

Each finding records its file, the element's tag, which occurrence of that tag it is in
the file, and the exact start tag. The fixer re-parses the file, finds that occurrence,
and refuses unless the start tag still matches character for character. Several fixes on
one element (a heading renamed and recolored) are combined into one edit. Nothing outside
the named elements changes.

## What is not checked

- PDFs, Word, PowerPoint and other uploaded files, and video or audio captions.
- Discussion and quiz text, which the export stores inside XML.
- Contrast set by stylesheets or the Canvas theme rather than inline styles.
- Whether alt text is accurate and whether headings describe their sections.
