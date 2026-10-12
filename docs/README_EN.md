# Inspection Workbench 0.1.5 — English edition

Windows 10/11, 64-bit. Extract the complete ZIP into a folder, then double-click
InspectionWorkbenchEnglish.exe. The program opens your browser and runs locally.
You do not need Python, an account or internet access to edit drafts and generate
DOCX reports. Actual paginated preview requires installed and activated Microsoft Word.

This edition always uses English. The separate InspectionWorkbench download
retains the Chinese interface and its English language menu.

1. Enter report details. Manage authors and reviewers through Personnel in the header.
   Replace the example people with your own names, qualifications and titles.
2. Add photographs to the current subitem. Captions are optional. The photo editor supports cropping,
   rotation, circles, rectangles, arrows and drawing, with undo and redo.
   Save the photograph, then save its inspection item. Original images are retained.
3. Select Element and ratings for the inspection item. All its subitems share these
   values. Custom descriptions are supported. Standard choices are:
   Likelihood: Unlikely, Possible, Likely.
   Severity: Negligible, Minor, Moderate, Severe.
   Priority: Low, Moderate, High, Urgent.
4. Use Add subitem to create independently described groups of photographs.
   Each subitem needs at least one photograph and an Observation; Recommendation
   may be left empty. Choose common wording and adapt it to the site. Select a
   subitem to edit it, or drag its handle to reorder the groups. Earlier/later
   buttons are also available. Save the entire inspection item when ready.
   Drag a saved item's handle to change report order.
5. Complete report sections and cost estimates. Preview or generate the Word report.
   An item still open in the editor must be saved to appear in the report.
   Word numbers photos continuously within each item (1.1, 1.2, 1.3, etc.).
   Photos from the same subitem share a vertically merged description cell;
   the next subitem starts a separate description. Shared rating headers repeat
   when a table continues onto another page.

The common wording library contains 90 observations and 44 recommendations.
Download its Excel file to edit entries and import it again through Wording library.
Names, captions and report text remain exactly as entered, including other languages.

Data is stored beside the EXE in WorkbenchDataEnglish. If the program folder is
read-only, the fallback is %LOCALAPPDATA%/WMLInspectionWorkbenchEnglish.
The interface displays the actual data location. This is separate from the
bilingual edition's WorkbenchData folder.

Use Export draft / Import draft to transfer a report and its photographs between
computers or editions. Copy personnel.json separately to transfer your personnel library.
Before upgrading, click Exit in the header. Extract the new program and retain
your WorkbenchDataEnglish folder. Closing the browser alone does not stop the service.
Back up drafts before upgrading. Older drafts open as a single subitem per item;
the original file changes only when saved. Drafts with subitems require version
0.1.5 or newer and cannot be edited in 0.1.4 or earlier.
Wait for the saved status before closing or refreshing a page. If another page
changes the same report, keep a copy or recovery backup before loading the latest draft.

Preserve LICENSES/ and source/ when redistributing this package. The ZIP contains
the program, documentation, application sources and required third-party sources;
it does not include personal drafts or site photographs. See THIRD_PARTY_NOTICES.txt.
