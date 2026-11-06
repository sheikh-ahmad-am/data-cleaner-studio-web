# Data Cleaner Studio — Test Pack (all the data, nothing to find)

**Files in this pack** — the same messy sales data in 3 formats, so you can
test every upload type. All three must give the SAME result.

- `messy_sales.csv` — the CSV
- `messy_sales.xlsx` — the Excel version
- `messy_sales.json` — the JSON version

**The mess inside (on purpose):** dates in 4 formats, prices as "$1,499.00"
and "Rs. 800" and blanks, customer names with extra spaces, categories in
mixed case (Electronics / electronics / ELECTRONICS), missing quantities,
regions and statuses, 3 exact duplicate rows, and one column (Notes) that
is 100% empty.

---

## Test 1 — Load (do this for CSV, then Excel, then JSON)

Upload the file. Preview tab must show:

- **80 rows, 10 columns**
- **133 missing cells, 3 duplicate rows**

Health check table — every column must match exactly:

| Column | Type | Missing | Unique |
|---|---|---|---|
| Order ID | text | 0 | 77 |
| Order Date | date | 0 | 75 |
| Customer | category | 0 | 16 |
| Product | category | 0 | 8 |
| Category | category | 0 | 12 |
| Region | category | 16 (20.0%) | 4 |
| Quantity | number | 19 (23.8%) | 4 |
| Unit Price | number | 5 (6.2%) | 19 |
| Status | category | 13 (16.2%) | 5 |
| Notes | text | 80 (100.0%) | 0 |

**Pass if:** all three files show these exact numbers.

## Test 2 — Clean

Clean tab, all boxes ticked, click **"Clean my data"**. The cleaning log
must show exactly this:

- Rows: **80 → 77 rows**
- Tidy column names: **10 column(s) renamed**
- Strip extra spaces: **26 cell(s) trimmed**
- Drop empty columns: **1: notes**
- Fix numbers: unit_price — **23 value(s) cleaned** (₹ $ , % removed)
- Parse dates: order_date — **80 value(s) parsed as dates**
- Fix categories: product — **9 value(s)**; category — **46 value(s)**;
  status — **45 value(s)** set to one case
- Drop duplicate rows: **3 row(s) removed**
- Fill missing: region — **16 filled with 'Unknown'**; quantity — **19
  filled with median**; unit_price — **5 filled with median**; status —
  **12 filled with 'Unknown'**

Cleaned preview must show: `order_id` still as text (ORD-1001, NOT a
number), `order_date` as real dates, `unit_price` as numbers, `category`
in one case (Electronics, not ELECTRONICS).

**Pass if:** 77 rows, 9 columns, log matches line by line.

## Test 3 — KPIs

KPIs tab must show exactly:

- Rows: **77** · Columns: **9**
- Top customer: **Ananya Rao (13)**
- Top product: **Desk Lamp (14)**
- Top category: **Electronics (33)**
- Top region: **West (19)**
- Total quantity: **198.5** · Average quantity: **2.6**
- Total unit_price: **78,323.0** · Average unit_price: **1,017.2**
- Top status: **Shipped (28)**
- order_date range: **2026-01-04 to 2026-11-08**

Build your own KPI: column `unit_price` + Sum → **78,323.00**.

**Pass if:** every card matches.

## Test 4 — Dashboard (slicers)

1. Chart type Bar, then Line, then Donut — all three draw.
2. Sidebar slicer: untick one category (e.g. Home) — every chart and KPI
   number changes. Tick it back — everything returns to the Test 3 values.
3. Date slicer: narrow the order_date range — charts and KPIs change
   again. Reset it — values return.

**Pass if:** slicers move every chart and every KPI, and resetting
restores the exact Test 3 numbers.

## Test 5 — Report downloads

Report tab — download all three and open them:

- **Report (.md):** reads in plain English, rows 80 → 77, all KPIs listed.
- **Cleaned CSV:** opens with 77 rows, 9 columns.
- **Cleaned Excel:** opens with **3 sheets** — Cleaned Data (77 rows),
  KPIs, Cleaning Log.

**Pass if:** all three open and match.

## Test 6 — Your own file

Upload a real CSV or Excel of yours. Check: ID columns stay text,
money columns become numbers, dates become dates, and the cleaning log
tells the truth line by line. Download the cleaned Excel and spot-check
a few rows against the original.

---

## If anything fails

Screenshot it and tell me: which test, which file, what you clicked,
what you saw, what you expected. That tells me exactly what to fix.

---

## Test 7 — New in v1.1 (use the extra files in this pack)

**7a. Join two files** — files: `messy_sales.csv` + `cities.csv`
1. Load messy_sales.csv. Open the **Join** tab.
2. Upload `cities.csv` as the second file.
3. Key in this file: **Customer** · Key in second file: **customer** ·
   How: **Left (keep all rows from this file)**.
4. Press **Preview join**. Expect: Left 80 rows · Right 2 rows →
   Joined **80 rows** · Matched keys **2** · Only in this file **14** ·
   Only in second file **0**. The preview shows a new `city` column
   (Delhi for Ananya Rao, Patna for Aarav Sharma).
5. Press **Use joined data**, then clean it in the Clean tab as usual.

**7b. Database file** — file: `test.db`
1. Sidebar: upload `test.db` under "... or a database file".
2. Expect two tables: **customers** and **orders**. Pick **customers**,
   press **Load table**.
3. Expect: 3 rows, columns id / name / city.

**7c. Fuzzy matching** — file: `fuzzy_names.csv`
1. Load fuzzy_names.csv, clean it (one click, all boxes ticked).
2. Clean tab, "Fix similar names": column **name**, threshold 0.85,
   press **Find similar names**.
3. Expect 3 groups: **Aarav** (Aarav ×2, Arav), **Priya** (Priya,
   Priyaa), **Delhi** (Delhi ×2, Dehli).
4. Press **Merge these names**. Expect: the name column now has 3
   values — Aarav, Delhi, Priya — and the cleaning log gains a
   "Fuzzy merge" line.

**7d. PDF report**
1. After cleaning the sample, open the **Report** tab.
2. Press **Download PDF report**. Expect: a real PDF that opens with
   the title, the KPIs, and the cleaning log.

**7e. New charts**
1. Dashboard tab, Chart dropdown now has 6 options: Bar, Line, Donut,
   **Histogram**, **Scatter**, **Box plot**.
2. Histogram → number column unit_price: draws a distribution.
3. Scatter → X quantity, Y unit_price: draws the dots.
4. Box plot → Group by category, Number unit_price: draws the boxes.

**7f. Auto-refresh** (needs a public Google Sheet of yours)
1. Load the sheet, tick **Auto-refresh this sheet** in the sidebar,
   pick 15 minutes.
2. Press **Refresh now** — the data reloads. Change a cell in the
   sheet, wait, and the app picks it up by itself while it stays open.
   (It cannot refresh while the app is closed.)

---

## Test 8 — New in v1.2

**8a. Data quality score** — file: `messy_sales.csv`
1. Load the file. Preview tab shows **Data quality score: 83**,
   with the deductions listed (missing cells, 3 duplicate rows, the
   empty Notes column).
2. Clean it. The score becomes **100**.

**8b. Outlier alerts** — after cleaning the sample
1. Clean tab → "Fix values" → **Outlier alerts**. Pick column
   **quantity**: expect **10 outlier(s)**, all value 5. Pick
   **unit_price**: expect **0 outlier(s)**.

**8c. Validation rules** — after cleaning the sample
1. "Fix values" → **Validation rules**. Column **quantity**, rule
   **greater than**, value **4** → **Add rule**.
2. Expect **10 violating rows** (the ten quantity-5 rows).

**8d. Near-duplicates** — file: `fuzzy_names.csv`
1. Load it, clean it. "Fix values" → **Near-duplicates**: text
   column **name** → **Find near-duplicates**.
2. Expect **3 groups**: Aarav, Priya, Delhi. Press **Merge these
   groups** → the file now has **3 rows**.

**8e. Undo**
1. Clean the sample, then press **Undo last snapshot** (top of the
   Clean tab).
2. Expect: the cleaned data is gone — KPIs and Dashboard show
   "Clean the data first". Press "Clean my data" again to redo it.

**8f. Recipes**
1. Clean the sample with all boxes ticked. "Recipes & templates" →
   **Cleaning recipes** → name it `My cleaning` → **Save recipe**.
2. Load `messy_sales.json`. Apply the recipe → expect **77 rows,
   9 columns**, same as Test 2.

**8g. Templates**
1. "Recipes & templates" → **Templates** → pick **attendance** →
   **Load attendance sample** → **Apply template**.
2. Expect: **24 → 22 rows**, 7 columns. Do the same for
   **inventory**: also **24 → 22 rows**.

**8h. Find and replace** — after cleaning the sample
1. "Fix values" → **Find and replace**: column **category**, find
   `Electronics`, replace with `Electronic` → **Replace**.
2. Expect: **33 cell(s) changed**.

**8i. Calculated column** — after cleaning the sample
1. "Fix values" → **Calculated column**: new column `line_total` =
   `quantity` × `unit_price` → **Add calculated column**.
2. KPIs tab → build your own KPI: column `line_total` + Sum →
   **198,301.50**.

**8j. Bulk clean**
1. "Clean many files at once" → upload `messy_sales.csv` and
   `fuzzy_names.csv` → **Clean all files**.
2. Expect: **2 files, both OK**, with a download button per file.

**8k. Compare two files** — files: cleaned sample + `compare_old.csv`
1. Compare tab → **Compare two files** → upload `compare_old.csv`,
   match rows by **order_id** → **Compare files**.
2. Expect: **Added 77 · Removed 5 · Changed rows 0**.

**8l. Append files** — files: cleaned sample + `append_jan.csv` +
   `append_feb.csv`
1. Compare tab → **Append files** → upload both files →
   **Append files**.
2. Expect: **83 rows** (77 + 3 + 3).

**8m. Anomaly alerts** — files: cleaned sample + `compare_old.csv`
1. Compare tab → **Anomaly alerts** → upload `compare_old.csv` →
   **Check for anomalies**.
2. Expect: **Rows** flagged (5 → 77, a huge jump).

**8n. Pivot table** — after cleaning the sample
1. Dashboard tab → **Pivot table**: rows **region**, values
   **quantity**, Sum → **Build pivot table**.
2. Expect: East 37.0 · North 39.5 · South 30.0 · Unknown 40.5 ·
   West 51.5 (total 198.5).

**8o. Multi-sheet Excel** — file: `messy_sales.xlsx`
1. Upload it in the sidebar. A **Sheet** picker appears (Sheet1).
2. Press **Load sheet** → expect **80 rows**.

**8p. PowerPoint report** — after cleaning the sample
1. Report tab → **Download PowerPoint report (.pptx)**.
2. Expect: a real .pptx that opens with 2 slides — title, KPIs,
   cleaning log, and a data table.

**8q. Audit trail** — after cleaning the sample
1. Report tab → **Audit trail** shows the **Clean** entry with the
   time. **Download audit log (CSV)** gives you the same as a file.

**8r. Data dictionary** — file: `messy_sales.csv`
1. Preview tab → **Data dictionary** → **Download data dictionary
   (.md)**. Expect one row per column with type, missing % and samples.

**8s. Watch folder** (needs the `watch_folder.py` from the Tools tab)
1. Save a recipe, then run:
   `python watch_folder.py --watch incoming --out cleaned --recipe my_recipe.json --once`
   with `messy_sales.csv` inside `incoming`.
2. Expect: `messy_sales_cleaned.csv` (77 rows) + a cleaning log in
   `cleaned`.

**8t. New charts** — after cleaning the sample
1. Dashboard tab, Chart dropdown now has 9 options. **Heatmap**
   shows the correlation between quantity and unit_price.
   **Treemap** (group by category, size by unit_price) and **Funnel**
   (step category, value unit_price) both draw.

**8u. The three "needs your details" screens** — these are honest
   by design; they do NOT pretend to work without your details:
1. Tools tab → **Live database connections**: pick MySQL, press
   **Test connection** → it says plainly the driver is not installed
   in this build, and offers the details as a JSON download (no
   password inside).
2. Report tab → **Google Sheets export**: upload any JSON that is
   not a service-account key → it reports an error. (A real
   service-account JSON is needed for the real thing.)
3. Report tab → **Scheduled email**: without SMTP details filled in,
   the send button does nothing. Fill in your email server details
   and it sends a real test email with the PDF attached.

## Test 9 — New in v1.3

All values below were checked against the files in this pack and the
messy sample. Where a number differs between the raw file and the
cleaned file, both are given — the Preview tab searches/filters the
**raw** file, the KPIs/Dashboard tabs use the **cleaned** file.

**9a. Split & merge columns** — after cleaning the sample
1. Clean tab → **Split & merge columns**: column **customer**, mode
   **First / last word** → **Split column**.
2. Expect two new columns: `customer_first` (Aarav, Priya, Aarav…)
   and `customer_last` (Sharma, Patel, Sharma…), **77 of 77 rows**
   split. "Ananya Rao" splits to Ananya / Rao on all 13 of her rows.
3. Merge them back: first column `customer_first`, second column
   `customer_last`, new column `full_name`, separator a space →
   expect "Aarav Sharma", "Priya Patel", "Ananya Rao".

**9b. Date intelligence** — after cleaning the sample
1. Clean tab → **Date intelligence**: date column **order_date** →
   **Add year / month / weekday**.
2. Expect three new columns. First row: year **2026**, month
   **June**, weekday **Saturday** (2026-06-13).
3. Group by `order_date_month` on the Dashboard: August **12**,
   June **11**, February **11**, May **9**, April **9**, March **8**,
   July **7**, January **5**, October **2**, November **2**,
   September **1**.

**9c. Currency conversion** — file: `messy_sales.csv` (raw)
1. Clean tab → **Currency conversion**: column **Unit Price**,
   convert everything into **INR** → **Convert**.
2. Expect a new column `Unit Price_INR`: row 0 "$799.00" becomes
   **66,317** (799 × 83); row 2 bare 1199 stays **1,199**; row 5
   "Rs. 799" becomes **799**. Total **₹886,187.00** over **75
   values converted**, **5 could not be read**.
3. The screen says plainly: "Fixed estimates — not live rates.
   1 USD = ₹83, 1 EUR = ₹90, 1 GBP = ₹105". You can change the
   rates on screen.

**9d. AI insights** — after cleaning the sample
1. KPIs tab → **AI insights**. With no key set, expect a plain
   message: it needs a Groq API key, and the key goes in **Settings**
   in the sidebar.
2. Paste a free Groq API key in Settings → **Get AI insights**.
   Expect a plain-English paragraph about the data (sales by
   category, top region, growth). The key is stored in a local
   `settings.json` next to the app — never inside the app.

**9e. Paste from clipboard**
1. Sidebar → **Paste a table**: copy a small table from Excel (with
   headers) and paste it into the box → **Load pasted table**.
2. Expect the table to load exactly like an uploaded file.

**9f. Row filter builder** — file: `messy_sales.csv` (raw)
1. Preview tab → **Filter rows**: column **Category**, condition
   **equals**, value **Electronics** → **Add rule**.
2. Expect **"34 of 80 rows match"** (the raw file still holds the
   duplicate row — after cleaning it is 33 of 77).
3. **Download filtered rows (.csv)** gives you only those rows.

**9g. Sampling for huge files**
1. Clean tab → tick **Clean only a sample first (1,000 rows)**,
   then clean the sample. Expect the same result as Test 2
   (**77 rows, 9 columns**) — the sample is 80 rows, so the whole
   file is the sample. On a file over 1,000 rows, only the first
   1,000 are cleaned first.

**9h. Auto-save workspace**
1. Sidebar → tick **Auto-save my workspace**, load the sample and
   clean it, then close the app (Ctrl+C in the terminal, or close
   the browser tab and the app window).
2. Reopen the app. Expect the sample and the cleaned data to still
   be there — no loading needed. Untick the box to stop auto-saving.

**9i. Dark mode + accent colour**
1. Sidebar → **Theme** picker: try **Light** and **Neon green**.
2. Expect the app to change colour immediately (Light = white
   background; Neon green = the green accent everywhere).

**9j. Data masking** — file: `names_phones.csv`
1. Load it, clean it. Clean tab → **Data masking**: mask **phone**
   as phone and **email** as email → **Mask selected columns**.
2. Expect: 98765 43210 → **98XXX X3210**, 91234 56780 →
   **91XXX X6780**; ananya.rao@gmail.com → **a***@gmail.com**,
   priya.p@example.com → **p***@example.com**.

**9k. Versioned exports** — after cleaning the sample
1. Report tab → **Versioned export**: the download button says
   **cleaned_v1.csv**. Press **Reserve this version** → the next
   download says **cleaned_v2.csv**. Old versions are never
   overwritten.

**9l. Hindi/Urdu labels**
1. Sidebar → **Language** picker: choose **हिन्दी**.
2. Expect the title to become **डेटा क्लीनर स्टूडियो** and the
   buttons to read in Hindi ("मेरा डेटा साफ़ करें" = Clean my data).
   Choose **اردو** → title **ڈیٹا کلینر اسٹوڈیو**. Switch back to
   **English** to return.

**9m. Smart suggestions** — file: `messy_sales.csv` (raw)
1. Preview tab → **Suggestions**. Expect **12 suggestions**:
   parse Order Date as dates, set categories to one case, turn Unit
   Price into real numbers, fill the blanks in Region (16),
   Quantity (19), Unit Price (5), Status (13) and Notes (80), drop
   the duplicate rows, drop the empty Notes column.
2. Press **Apply** on one → it runs that fix on the spot.

**9n. Column type override** — file: `messy_sales.csv`
1. Preview tab → **Column type override**: pick column **quantity**,
   force it to be **text** → **Apply override**.
2. Expect the health check to show quantity as text. (The cleaner
   guesses types from the values — this is how you correct a wrong
   guess.)

**9o. Standardize phone numbers** — file: `names_phones.csv`
1. Load it, clean it. Clean tab → **Phone numbers**: column
   **phone** → **Standardize phone numbers**.
2. Expect all 4 numbers in +91 shape: **+91 98765 43210**,
   **+91 91234 56780**, **+91 99887 76655**, **+91 98765 43210**.

**9p. Strip special characters** — file: `names_phones.csv`
1. Load it, clean it. Clean tab → **Strip special characters**:
   column **note** → **Strip**.
2. Expect: "Loves it! 🎉" → **Loves it**, "Good 👍" → **Good**,
   "Nice 😊" → **Nice**. Letters, digits, spaces and basic
   punctuation (., - &) are kept.

**9q. Goal tracking** — after cleaning the sample
1. KPIs tab → **Goal tracking**: column **unit_price**, measure
   **Sum**, target **100000** → **Set goal**.
2. Expect **"78,323 of 100,000 — 78.3%"** with a progress bar.

**9r. Search the whole file** — file: `messy_sales.csv` (raw)
1. Preview tab → **Search**: type **ananya**.
2. Expect **"14 of 80 rows match"** (the raw file still holds her
   duplicate row — after cleaning it is 13 of 77). Clear the box to
   see all rows again.

**9s. Sort the preview** — after cleaning the sample
1. Preview tab → **Sort the preview**: sort by **unit_price**,
   **Descending**.
2. Expect the first row to show **1599.0**. Switch to
   **Ascending** → first row **199.0**.

**9t. Recent files**
1. Sidebar → load any file with **"Keep a copy for quick reopen"**
   ticked. It appears under **Recent files**.
2. Load a different file, then click the first file's name under
   Recent files → it reopens in one click. (Only files you tick
   are stored, locally, next to the app.)

**9u. Backup before cleaning** — file: `messy_sales.csv`
1. Clean the sample, then look in the `backups/` folder next to the
   app. Expect a file like
   `messy_sales_2026-11-06_0130.csv` — the original, saved before
   cleaning started.

**9v. One-click full flow** — after loading the sample
1. Report tab → **One-click full flow** → **Run everything**.
2. Expect: cleaning + KPIs + report all built in one go. The email
   step says plainly it needs your SMTP details and skips sending
   without them.

**9w. Standalone HTML dashboard** — after cleaning the sample
1. Report tab → **Standalone HTML dashboard** →
   **Download dashboard (.html)**. Open it in any browser.
2. Expect: the KPIs (Total unit_price **78,323.0**), a green chart,
   and it works with no internet.

**9x. Publish to portfolio** — after cleaning the sample
1. Report tab → **Publish to portfolio** →
   **Download case study (.zip)**.
2. Expect a ZIP with `cleaned_data.csv`, `README.md` (mentions
   Total unit_price **78,323.0** and Electronics **(33)**) and a
   chart PNG.

**9y. Chart as image** — after cleaning the sample
1. Dashboard tab → **Download chart (.png)**. Expect a PNG of the
   chart you are looking at.

**9z. Conditional colours in exports** — after cleaning the sample
1. Report tab → **Styled Excel export** →
   **Download styled Excel (.xlsx)**. Open it in Excel.
2. Expect: the header row highlighted green, bad cells red, good
   cells green.

**9aa. Correlation finder** — after cleaning the sample
1. Dashboard tab → **What moves together?**
2. Expect: no pair of numbers scores 0.3 or above. At a 0.05
   threshold, quantity ↔ unit_price shows **r = −0.098** (almost
   no relationship).

**9ab. Trend forecast** — after cleaning the sample
1. Dashboard tab → **Trend forecast**: number column
   **unit_price**, date column **order_date** →
   **Forecast the next day**.
2. Expect: slope **+0.38/day**, the guess for **2026-11-09** is
   **1,083.28**, last real value **1,599.00** — and the screen says
   plainly it is a rough guess, not a prediction.

**9ac. What-if slider** — after cleaning the sample
1. KPIs tab → **What if...?**: number column **unit_price**, move
   the slider to **+10%**.
2. Expect: total **78,323.00 → 86,155.30** (difference
   **+7,832.30**), updating instantly as you move the slider.

**9ad. Row trust score** — after cleaning the sample
1. Preview tab → **Row trust scores**. Expect the worst rows
   listed first: **10 rows score 95** (the ten quantity-5 rows),
   the other **67 rows score 100**.

**9ae. Saved views** — after cleaning the sample
1. Dashboard tab → **Saved views**: name the current chart
   **Sales by region** → **Save this view**.
2. Change the chart, then pick "Sales by region" in the Saved
   views dropdown → **Go to this view**. Expect the chart and
   slicers to jump back.

**9af. Client mode**
1. Sidebar → tick **Client mode (simple view)**.
2. Expect only **5 tabs**: Preview, Clean, KPIs, Dashboard,
   Report. Join, Compare and Tools are hidden. Untick → all
   **8 tabs** return.

**9ag. Shareable recipes** — after cleaning the sample
1. Clean tab → **Cleaning recipes** → save a recipe, then
   **Download recipe** → a small .json file.
2. Load a different file, then **Upload a recipe** with that file
   → the same cleaning runs on it.

**9ah. Keyboard shortcuts**
1. Tools tab → **Keyboard shortcuts**. It lists: **Ctrl+O** jumps
   to the file uploader, **Ctrl+S** downloads the cleaned file.
   (Browser shortcuts — they work while the app is open.)

**9ai. Multi-file KPI screen** — files: cleaned sample +
   `append_jan.csv` + `append_feb.csv`
1. Compare tab → **Multi-file KPIs** → upload both files →
   **Compare KPIs**.
2. Expect one table, one row per file, with Rows and
   Total unit_price. The cleaned sample's row shows **78,323.0**.

**9aj. Natural-language questions** — after cleaning the sample
1. Dashboard tab → **Ask your data**: type
   **"which region sold the most?"** → **Ask**.
2. Expect **"West (19 rows)"** — answered by the built-in rule
   layer, no API key needed. With a Groq key in Settings, free-form
   questions ("why did March dip?") get an AI answer too.

**9ak. Morning auto-run**
1. Tools tab → **Morning auto-run** →
   **Download morning_run.py** and **Download setup_morning_run.bat**.
2. On your Windows PC, double-click `setup_morning_run.bat` → it
   sets a Task Scheduler job that cleans a folder every morning at
   8am. (This cannot be activated from here — the setup runs on
   your PC.)

**9al. What's-new**
1. Close the app and reopen it after this update. Expect a box
   **"What's new in v1.3"** listing all 38 new features.
2. Press **"Got it, don't show again"** → it does not come back.
   (It shows once per version.)

## Test 10 — New in v1.4

**10a. Live database (needs your server details)** — Tools tab →
**Live database connection**
1. The screen lists the three drivers: **MySQL: installed**,
   **PostgreSQL: installed**, **SQL Server: installed**.
   (If one says "not installed", that driver is missing from the
   build — report it.)
2. Pick **PostgreSQL**, type a wrong host (e.g. `db.example.com`)
   and press **Test connection**. Expect a plain one-line error
   ("Could not connect...") — no crash, no traceback.
3. With a real server: pick the database, press **Test connection**
   → expect **"Connected to ..."**. The tables list appears; pick
   one, press **Load table** → the table loads like any other file
   (clean it in the Clean tab). The password is never saved to disk.

**10b. Bigger files + Parquet** — files: `messy_sales.parquet`
1. Upload `messy_sales.parquet` (sidebar). Expect **80 rows**,
   then clean → **77 rows**, exactly the same as the CSV. The
   KPIs match Test 3 (Total unit_price **78,323.0**, Top customer
   **Ananya Rao (13)**).
2. Report tab → **Download cleaned Parquet** → a `.parquet` file
   that opens again in the app with 77 rows.
3. Uploads now accept up to **1000MB** (the uploader says so).

**10c. Daily auto-clean, one click** — Tools tab → **Daily
auto-clean — while the app is closed**
1. Pick a time (default **08:00**), press **Set up daily
   auto-clean**. On your Windows PC expect **"Done — the morning
   run is set for 08:00 every day"**. On any other computer it
   says plainly that scheduling only works on a Windows PC.
2. Press **Test it now** → it runs `morning_run.py` once and
   reports what happened. The old `setup_morning_run.bat` still
   works as a fallback (see 9ak).

**10d. White-label** — sidebar → **Brand (white-label)**
1. Set **Brand name** to `Acme Analytics`, pick an accent colour,
   press **Save brand**. Expect **"Brand saved — reports will now
   say 'Acme Analytics'."**
2. The app title at the top now reads **Acme Analytics**.
3. Report tab → download the **PDF report** → the title inside
   reads **"Acme Analytics — Report"**. The **HTML dashboard**
   and **PowerPoint report** say Acme Analytics too.
4. Set the name back to **Data Cleaner Studio** and save again
   to undo.

**10e. Built-in tutorial**
1. First time you open v1.4, a box at the top says **"First time
   here? ..."** with a **Got it** button. Press it → the box never
   comes back.
2. Open the **How to use** tab. Expect **7 steps** in plain words,
   from "Load a file" to the report. (The tab is there in client
   mode too.)

**10f. Live Excel formulas** — after cleaning the sample
1. Report tab → tick **Excel KPIs as live formulas** (on by
   default) → **Download cleaned Excel**.
2. Open the workbook in Excel: it has **4 sheets** — Cleaned
   Data, KPIs, Cleaning Log, **KPIs (live)**.
3. On **KPIs (live)**, expect these exact formulas:
   - Total quantity → `=SUM('Cleaned Data'!G2:G78)`
   - Average quantity → `=AVERAGE('Cleaned Data'!G2:G78)`
   - Total unit_price → `=SUM('Cleaned Data'!H2:H78)`
   - Average unit_price → `=AVERAGE('Cleaned Data'!H2:H78)`
   Change a number on Cleaned Data and the totals update.
4. Untick the box and download again → the workbook has only
   **3 sheets** (no "KPIs (live)").

**10g. Live currency rates** — after cleaning the sample
1. Clean tab → **Fix values** → **Currency conversion**.
2. Press **Get live rates**. Expect **"Live rates loaded."** and
   the rate boxes to show today's rates — clearly different from
   the old estimates (1 USD = ₹83, 1 EUR = ₹90, 1 GBP = ₹105).
   (On 6 Nov 2026 they were about USD ₹94.54, EUR ≈ ₹106.16,
   GBP ≈ ₹127.25 — they move every day, so expect today's numbers,
   not these.)
3. Convert the unit_price column to INR → the log line ends
   **"Rates are live rates, just fetched."**
4. With no internet the button says **"No live rates right now —
   using the fixed estimates below."** and the log ends
   **"Rates are fixed estimates, not live rates."** — an estimate
   is never labelled as live.

**10h. Mobile-friendly layout**
1. Open the app on a phone (or shrink the browser window to
   phone width). The dashboard columns stack one above the other,
   buttons are big enough to tap, and the sidebar slicers still
   work.
