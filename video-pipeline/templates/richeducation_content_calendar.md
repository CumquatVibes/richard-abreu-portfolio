# Rich Education — Content Calendar & Business Tracker

## Sheet 1: Video Pipeline

| Column | Header               | Notes                                                                         |
| ------ | -------------------- | ----------------------------------------------------------------------------- |
| A      | Video #              | Auto-number: 001, 002, 003...                                                |
| B      | Grade                | e.g. 8th                                                                     |
| C      | Subject              | e.g. U.S. History                                                            |
| D      | Unit / Topic         | e.g. Civil War & Reconstruction                                              |
| E      | Video Title          | Full YouTube title                                                           |
| F      | Hook Line            | First line of the script hook                                                |
| G      | Status               | Dropdown: Idea / Scripting / Visuals / Recording / Editing / Scheduled / Live |
| H      | Script Link          | Google Doc URL                                                               |
| I      | Shot List Link       | Google Doc URL                                                               |
| J      | Thumbnail Brief Link | Google Doc URL                                                               |
| K      | Thumbnail File Link  | Drive URL of final thumbnail                                                 |
| L      | Upload Date          | Target or actual date                                                        |
| M      | YouTube URL          | Once live                                                                    |
| N      | Study Product        | e.g. "Civil War Study Pack PDF"                                              |
| O      | Product Link         | Gumroad / Shopify URL                                                        |
| P      | Affiliate Offer      | e.g. "Khan Academy Plus affiliate"                                           |
| Q      | Affiliate Link       | URL                                                                          |
| R      | First 28-Day Views   | Pull from Viewstats API later                                                |
| S      | First 28-Day Subs    | Pull from Viewstats API later                                                |
| T      | Notes                | Anything extra                                                               |

## Sheet 2: Study Products

| Column | Header        | Notes                                      |
| ------ | ------------- | ------------------------------------------ |
| A      | Product #     | Auto-number                                |
| B      | Product Name  | e.g. "8th Grade Civil War Study Pack"      |
| C      | Format        | PDF / Notion Template / Flashcard Deck     |
| D      | Price         | e.g. $4.99                                 |
| E      | Platform      | Gumroad / Shopify / Etsy                   |
| F      | Product URL   | Live link                                  |
| G      | Linked Videos | Comma-separated video numbers from Sheet 1 |
| H      | Units Sold    | Manual or API-pulled                       |
| I      | Revenue       | Auto-calc: Units Sold x Price              |
| J      | Status        | Idea / In Progress / Live                  |

## Sheet 3: Affiliate Programs

| Column | Header            | Notes                                 |
| ------ | ----------------- | ------------------------------------- |
| A      | Affiliate Program | e.g. Khan Academy, Quizlet, Grammarly |
| B      | Category          | EdTech / Books / Tools                |
| C      | Commission Rate   | e.g. 20% / $5 per signup             |
| D      | Affiliate Link    | Your unique URL                       |
| E      | Best-fit Videos   | Which video topics match this offer   |
| F      | Clicks            | If trackable                          |
| G      | Conversions       | If trackable                          |
| H      | Notes             | Payout terms, cookie window, etc.     |

## Sheet 4: Dashboard

| Row | Label                     | Formula                       |
| --- | ------------------------- | ----------------------------- |
| 1   | Total Videos Live         | =COUNTIF(Sheet1!G:G,"Live")   |
| 2   | Videos In Progress        | =COUNTIF(Sheet1!G:G,"<>Live") |
| 3   | Total Study Products Live | =COUNTIF(Sheet2!J:J,"Live")   |
| 4   | Total Product Revenue     | =SUM(Sheet2!I:I)              |
| 5   | Avg Views Per Video       | =AVERAGE(Sheet1!R:R)          |
| 6   | Total 28-Day Views        | =SUM(Sheet1!R:R)              |
| 7   | Total 28-Day Subs         | =SUM(Sheet1!S:S)              |

## Notion Version

Database: **Rich Education HQ**

Properties:
- Title (title) — Video title
- Grade (select) — 6th / 7th / 8th / 9th / 10th / 11th / 12th
- Subject (select) — U.S. History / Science / Math / ELA / etc.
- Topic (text)
- Status (status) — Idea > Scripting > Visuals > Editing > Scheduled > Live
- Script (URL)
- Shot List (URL)
- Thumbnail (URL)
- Upload Date (date)
- YouTube URL (URL)
- Study Product (text)
- Product Link (URL)
- Affiliate Offer (text)
- Affiliate Link (URL)
- 28-Day Views (number)
- 28-Day Subs (number)
- Notes (text)

Views:
- **Board view** grouped by Status — production kanban
- **Table view** filtered by Subject — all History videos at once
- **Gallery view** filtered by Status = Live — live video library
