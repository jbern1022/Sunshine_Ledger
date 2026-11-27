# 2026 winners' campaign sites (Gate 1 (e))

Collected 2026-11-26 (evening ET) for the promises workflow (Todoist `6hvxrjGmcGjQ66Pp`). Campaign
sites go offline after an election, so this list preserves where each winner's own promises were
published before they disappear.

## How it was gathered

* Seats and names: the 141 winners already in `election_winners` (Division of Elections results).
* For each seat, the winner's Ballotpedia candidate page was read through the owner's own browser
  at about one request every 2.5 seconds, and only the infobox link labelled **"Campaign website"**
  was kept. Ballotpedia is a directory: it only points at a site (`discovered_via=directory`) and is
  never crawled or quoted (rules in `backend/app/promises/sites.py`). Personal social accounts were
  not collected; campaign social accounts are excluded because the crawler never visits social
  platforms.
* Each site got one plain request on 2026-11-27 03:10 UTC (column `http_2026_11_27`).

## Result

| | Seats |
|---|---|
| Winners | 141 (120 House, 21 Senate) |
| Campaign website found | **125** |
| Answered normally (200) | 92 |
| Refused a scripted request (403/406, bot protection) | 31: the crawler may be refused too; its log will show which |
| Not found (404) | 2: `mikegforflorida.com` (HD 79), `electdemi.com` (HD 114); the crawler records them offline and routes to the Internet Archive copy where one exists |
| No campaign website listed | 16 (below) |

**No site listed on Ballotpedia (16):** HD 13 Audrey Gibson (D), HD 14 Kimberly Daniels (D), HD 26 Nan
Cobb (R), HD 38 Nik Dean (D), HD 41 Bruce Hadley Antone (D), HD 48 Jon Albert (R), HD 67 Luis Viera
(D), HD 88 Jervonte "Tae" Edmonds (D), HD 89 Debra Tendrich (D), HD 92 Kelly Skidmore (D), HD 96 Dan
Daley (D), HD 97 Lisa Dunkley (D), HD 107 Wallace Aristide (D), HD 115 Omar Blanco (R), HD 117 Kevin
D. Chambliss (D), SD 32 Rosalind Osgood (D).

**Balance:** 13 of the 16 gaps are Democrats, who hold 58 of the 141 seats (22% of Democratic winners have no site listed, against 4% of Republicans). A promises record
built only from this list would cover one party better than the other. Before any promise comparison is
published, either find these sites another way (the candidates' Division of Elections filings, local
news, the House member pages) or state the gap on the page.

## Loading

`docs/grant-ready/campaign-sites-2026.csv` is in the importer's format
(`chamber,district,url,kind,discovered_via`; the extra columns are ignored). Once this file is on
`main`, the owner runs `bash ~/sunshine-aws-setup/load-campaign-sites.sh`, which imports the rows and
starts the crawler in its own container.

Snapshots are stored in the `sunshineledger_snapshots` Docker volume, which is **not** part of the
nightly S3 backup (that is the database dump only). Until it is, a lost docker-host loses the
snapshots.
