# Florida county meeting-records platforms: manual sweep, first pass

Status: search-level pass complete for all 67 counties, 2026-10-27. Continues `docs/FLORIDA_SOURCE_INVENTORY.md` (Todoist
`6hm2Cxf49P22gJmp`), which covers only what token-guessing found on Legistar. This pass
looked at the counties by web search (16 in the first batch, 16 in the second, 25 in the third: the 24 small counties plus
a second look at Santa Rosa), then checked the Legistar API where a search result named a client or a token could be guessed. **No county site was opened in a browser** (the Chrome
extension was not connected), so every row marked *search only* is what a search result
said, not something I saw on the page. Do not onboard from this table without opening
the source.

Not covered here: the 10 counties the probe already found on
Legistar (Brevard, Broward, DeSoto, Hernando, Hillsborough, Marion, Martin, Pinellas,
Polk, Seminole), Duval (Jacksonville is consolidated and already ingested), and
municipalities beyond the earlier probe. Terms-of-use have not been checked for any
source (the open Tampa/Orlando ruling `6hm2FqXfHvxVR45G` applies the same question to
these).

| County | Platform (as found) | Evidence | Verified how |
|---|---|---|---|
| Orange | **Legistar** client `occompt` (Comptroller-hosted), agendas as PDFs in `apps.ocfl.net/eAgenda`, minutes scanned in occompt.com DocumentCenter | January 2026 agenda links each item to `occompt.legistar.com`; API returned a matter modified 2026-10-26 | **API checked, live**: token `occompt` works, newest matter 2026-10-26. The probe missed it because the token is not guessable. Registered on branch `feat/county-legistar-hernando-desoto` (not deployed). |
| Miami-Dade | In-house Legistar database published under `miamidade.gov/govaction/legistarfiles` (agenda PDFs by meeting key, item files by year) | Office of Agenda Coordination page; agendas and `MinMatters` files | Search only. The cloud client `miamidade` answers but its newest matter is 2018, so the cloud API is not the live source. A scrape of the county-hosted pages would be needed. |
| Palm Beach | County-hosted agenda archive (`discover.pbc.gov/countycommissioners/Agenda_Master_HTML/`), PDF/HTML | Search results show HTML agendas through 2023 | Search only; currency unconfirmed. Legistar tokens `pbcgov` and `palmbeachcounty` do not exist. Minutes probably at the Clerk & Comptroller. |
| Lee | County site (`leegov.com`), "Blue Sheet" PDF agenda items | Only 2007 archive pages surfaced | Search only; current system unknown. Token `leegov` does not exist. |
| Volusia | County site: Council meetings page with agenda/minutes section and action lists (PDF) | `volusia.org/government/county-council/county-council-meetings/`; a January 2026 action list | Search only. Token `volusia` does not exist. |
| Pasco | BOCC site "Meetings & Agendas" with per-meeting documents and video; Clerk FAQ explains navigation | Clerk's FAQ | Search only. The site looks like a meeting-management product, unidentified. Token `pascocounty` does not exist. |
| Sarasota | Clerk "Board Records Public Access Portal" (minutes, ordinances, resolutions, 2002 to present) plus county "Meetings on Demand" video and document archive | Clerk and county pages | Search only. Token `sarasota` does not exist. |
| Leon | County-hosted agenda books (`www2.leoncountyfl.gov/coadmin/agenda/book/<date>/agenda.pdf`) | Agenda PDFs 2017 to 2025 | Search only. One PDF per meeting; minutes location changed over time (Clerk, then county site). Token `leoncounty` does not exist. |
| Osceola | County site; recent agendas as PDFs via GovDelivery; an OnBase Agenda Online instance at `docs.osceola.org/OnBaseAgendaOnline` | July 2026 agenda; the OnBase URL appeared in another search | Search only. OnBase Agenda Online is the same product as Tampa (`6hm2FqXfHvxVR45G`): meeting-level, blocked on the same terms ruling. |
| Collier | County site documents plus the Clerk's Minutes & Records department; no single archive found | Clerk page | Search only; unknown platform. |
| Manatee | Clerk-hosted `records.manateeclerk.com/BoardRecords/Browse/Agendas/Board-of-County-Commissioners/<year>/<month>/BCyyyymmddDOCnnn.pdf`, plus county BCC meetings page | 2026 agenda PDFs with predictable names | Search only. Predictable URLs, but several revisions of the same agenda exist. |
| Escambia | **CivicClerk** (agendas, backup, minutes, e-voting), Clerk's MuniDocs archive for older records | Clerk's FAQ | Search only. CivicClerk is a hosted product with a public portal; whether it has a usable API is unchecked. |
| St. Johns | Clerk-hosted pages by year (`stjohnsclerk.com/…bocc-agendas/`), items link to backup | 2023 pages only | Search only; 2026 page not seen. |
| Lake | Clerk-hosted minutes as HTML by date (`lakecountyclerk.org/forms/board_minutes/<yyyy>/<mm>/…`) through 2024; current agenda location not found | Clerk archive | Search only. HTML minutes are easy to read; agendas are the gap. |
| Okaloosa | County site `myokaloosa.gov`, PDFs | Only a 2020 schedule and committee PDFs surfaced | Search only; BCC archive not found. |
| Clay | Clerk's "Clerk to the Board" minutes page; Swagit video agendas (`clayfl.swagit.com`) 2012 to 2019 | Results old | Search only; current 2026 platform unconfirmed. |
| St. Lucie | County WebLink archive (`documents.stlucieco.gov/WebLink`) for older agendas and minutes; county site publishes recent agendas as documents | Archive pages 2012+; recent meetings only as third-party summaries | Search only. Legistar token `stlucie` does not exist. Current official BOCC agenda page not found. |
| Indian River | County site "BCC Agendas, Minutes, & Video" with an archive search and browse | `indianriver.gov` Government menu | Search only; looks like a county-built archive. Token `indianriver` does not exist. |
| Charlotte | County site: minutes page for the past 365 days (`charlottecountyfl.gov/agendas/minutes.stml`); agendas as PDFs named by date on `data.charlottecountyfl.gov/agenda/<yyyymmdd>/<yyyymmdd>Agenda.pdf`; older minutes via the Clerk | Agenda PDFs through 2025 | Search only. Predictable PDF names make discovery easy; no 2026 listing seen. |
| Monroe | County "BOCC Meetings & Agendas" page (condensed agenda, full packet with bookmarked backup, video); minutes linked from the Clerk; Archive Center by date | `monroecounty-fl.gov/meetings` | Search only. Platform unidentified (county-built "AMID" archive URLs). |
| Citrus | **CivicClerk** hosted by the Clerk (`citrusclerk.org/728/BOCC-Meeting-Portal`), moved there in 2022; older meetings on the Clerk's site | County BOCC page and news item | Search only. Same product as Escambia. |
| Santa Rosa | Not found | No relevant result | Nothing found; needs a manual look. |
| Bay | **NovusAgenda** for meetings on or after 2015-08-18 (searchable by date and meeting type); minutes from the Clerk | `baycountyfl.gov/129/Agendas-Minutes` | Search only. A hosted product I have not seen elsewhere in this sweep. |
| Alachua | `meetingdocs.alachuacounty.us` agenda PDFs (2020 to 2023 seen) whose items link to Legistar; the Legistar client `alachua` is stale (newest matter 2025-01-15) | Agenda PDFs; **API checked** | Platform changed or the county moved off Legistar around early 2025; the current system is unknown. |
| Flagler | County event pages per meeting (`flaglercounty.gov/Events/2026-BOCC-Meetings/<date>-<time>-BOCC-Regular-Meeting`) with the agenda PDF and backup links; minutes at the Clerk | 2026 meeting pages through August | Search only. Current and predictable; one page per meeting. |
| Highlands | County "Board Agenda & Board Meeting Live Broadcast" page; minutes online only for meetings on or after 2025-09-16 | `highlandsfl.gov/county_commissioners/board_meetings.php` | Search only. Minutes before Sept 2025 are not online. |
| Nassau | Clerk hosts resolutions as PDFs (`files.nassauclerk.com/Repository/Resolutions/<year> Resolutions/...`); current agenda page not found | Resolution PDFs 1999 to 2013 | Search only; current system unknown. |
| Putnam | County site (`putnam-fl.gov`) with "Minutes & Agenda Search"; agenda PDFs at `apps.putnam-fl.com/bocc/uploads/<id>.pdf`; a separate "Ordinance & Resolutions" page | Agenda PDF and site menu | Search only. County-built; the ordinances/resolutions page may be a clean legislation source. |
| Sumter | Clerk "Public Access Portal" for recorded meetings, agendas and minutes (2009 onward; closed captions run through an automated platform from 2021) | `sumterclerk.com/public-records/county-commissioners/` | Search only. Clerk-held. |
| Walton | Clerk hosts minutes PDFs (`waltonclerkfl.gov`); a 2014 forum post says agendas were on `walton.legistar.com` | Old Clerk PDFs and a forum post | **API checked**: Legistar client `walton` does not exist, so the 2014 claim is no longer true. Current system unknown. |
| Columbia | County site: meeting calendar with per-meeting pages (`columbiacountyfla.com/MeetingDetails.aspx?Id=<n>`), agendas with backup and minutes as downloadable documents | Meeting detail pages through June 2026 | Search only. Per-meeting pages and a document download service; county-built. |
| Jackson | County site "Meeting Agendas" and "Meeting Minutes" under Government; announcements recap meetings | `jacksoncountyfl.gov` | Search only; agendas and minutes not opened. |
| Santa Rosa | County site `santarosa.fl.gov`; a listing says minutes are viewable online; commission meets 2nd and 4th Thursday in Milton | Second look: still no agenda or minutes page surfaced, only third-party meeting summaries | Search only; platform still unidentified. Needs a manual look. |
| Baker | County site PDFs with predictable names (`bakercountyfl.org/board/agenda/CountyCommission_<mdyyyy>_1.pdf`); minutes through 2025-11-19 | Agenda PDFs 2023 to 2025 | Search only. Cheap to read if the terms allow; no index page seen. |
| Bradford | County WordPress uploads (`bradfordcountyfl.gov/wp-content/uploads/BoCC_Agenda_-_<m-d-yyyy>.pdf`) plus an agenda-packet PDF | Agendas 2021 to 2023 only in results | Search only; current location unconfirmed. |
| Calhoun | County site uploads of minutes PDFs (`calhouncountyfl.gov/uploads/2019/01/<yyyymmdd>officialminutesregular.pdf`) | Minutes 1985 to 2014 | Search only; nothing after 2014 surfaced. Current system unknown. |
| Dixie | Clerk site `dixieclerk.com` (WordPress uploads): agendas, "APPROVED" minutes, yearly BOCC schedule | Minutes and agendas 2018 to 2023; 2025 schedule | Search only. Clerk-held; 2024+ minutes not seen. |
| Franklin | County site with an Agendas & Minutes page (`franklincountyflorida.com/resources/agendas-minutes/`) and an event page per meeting | Meeting notices through August 2026 | Search only. Active and structured; the archive page was not opened. |
| Gadsden | County site documents via `gadsdencountyfl.gov/home/showpublisheddocument/<id>/<stamp>` and a calendar component | Agendas 2013 and Jan to Feb 2024 | Search only. CivicPlus-style document URLs; nothing newer than Feb 2024 indexed. |
| Gilchrist | County agenda PDF for the 2026-04-20 meeting (reached through a third-party host); the county's own archive not found | One 2026 agenda | Search only. City of Trenton meets in the county facility, so city and county results mix. |
| Glades | Clerk site `gladesclerk.com` (WordPress uploads of tagged minutes PDFs) | Minutes 2016 to 2019 | Search only; newer records not seen. |
| Gulf | County site `gulfcounty-fl.gov` and a CivicLive-hosted notices page (`gulfcounty-fl.hosted.civiclive.com/meeting/public_notices`) | FAQ gives the schedule; no official agenda or minutes found | Search only. 2025 to 2026 meetings appear only in third-party summaries. |
| Hamilton | County site not found in results | A 2016 agenda on an advocacy site; a 2026 session described by a third party | Search only; nothing official surfaced. Needs a manual look. |
| Hardee | County site `hardeecountyfl.gov/meetings/<slug>/`, one page per meeting | A June 2026 meeting page | Search only. Per-meeting pages; whether agenda and minutes attach was not checked. |
| Hendry | County `hendryfla.net`; a 2021 news item links an agenda packet on a Clerk "Weblink" server | One 2021 article | Search only; current system unknown. Results were mostly Henry County, Alabama. |
| Holmes | Clerk site `holmesclerk.com` (WordPress uploads): agendas and minutes as PDFs, minutes also as mp3; sections for 2024, 2025 and 2026 | Agendas and minutes 2016 to Sept 2024 | Search only. Clerk-held and dated; looks regular. |
| Jefferson | County site `jeffersoncountyfl.gov` with live video; agendas and minutes linked from the Board page | Meeting schedule and video page | Search only; archive page not opened. Many results were for Jefferson counties in other states. |
| Lafayette | Clerk site `lafayetteclerk.com` (scanned minutes and agenda PDFs) | 2017 to 2019 only | Search only. Scans; some pages cut off, so text extraction would be unreliable. |
| Levy | County site `levycounty.org` (schedule) and Clerk `levyclerk.com` (minutes PDFs since 2012) | Minutes through 2022; schedule for 2024 | Search only; no current agenda located. |
| Liberty | County site `libertybocc.com` with an "Agendas & Minutes" menu | Navigation only; most results were Liberty County, Georgia | Search only; archive not opened. |
| Madison | County WordPress uploads of full packets (`madisoncountyfl.com/wp-content/uploads/BOCC-Packet-<mm.dd.yy>.pdf`) that embed the prior meeting's minutes | Packets 2023 to 2024-07-10 | Search only. **Legistar client `madison` exists but is Madison, Wisconsin** (checked bodies and matters): a name hit must be verified as Florida. |
| Okeechobee | County calendar page links the Board's agenda on **IQM2** ("Board of County Commissioners Regular Session - Web Outline"); meetings also streamed | One county calendar entry | Search only; the IQM2 address was not opened. Same product the Miami adapter (`miami_iqm2.py`) reads, so a candidate for reuse. |
| Suwannee | County WordPress uploads of tentative-agenda packets (`suwanneecountyfl.gov/wp-content/uploads/<Month>-<D>-<YYYY>-Packet-1.pdf`) that include prior minutes | Packets 2023 to May 2024 | Search only; nothing after mid-2024 indexed. |
| Taylor | County site `taylorcountygov.com` commission page with some agendas and minutes as PDFs; the office holds the rest | Schedule page; 2026 meetings only in third-party summaries | Search only. Page looks partly out of date. |
| Union | County agenda PDF for the 2026-04-20 meeting (via a third-party host); official archive not found | One 2026 agenda | Search only. Many results were other states' Union counties. |
| Wakulla | County site `mywakulla.com` (draft agenda outline PDFs, meeting notices as news items) | Agenda 2023-08-07; notices 2024 | Search only. 2026 meetings seen only in third-party summaries. |
| Washington | County CMS files (`washingtonfl.com/site/assets/files/<id>/<name>.pdf`): meeting notices, agendas, 2026 workshop schedule | Emergency-meeting agenda 2026-05-07; 2025 notices | Search only. Active in 2026; minutes not seen. |


## Takeaways

1. **One new ready candidate:** Orange County on Legistar (`occompt`), verified live and
   now registered on the county-Legistar branch. It still needs a hand-run first ingest and
   a spot-check of kinds and sponsors. It is the only row here that I would call onboardable.
2. **The big counties mostly publish PDFs on county or Clerk sites, not a feed.** Palm
   Beach, Lee, Volusia, Leon, Manatee, Sarasota, Collier have no Legistar client under
   obvious tokens. Each would need a custom scraper, and each new scraper needs a terms
   check first.
3. **Three hosted products recur:** OnBase Agenda Online (Osceola, Tampa), CivicClerk
   (Escambia, Citrus) and NovusAgenda (Bay). One adapter per product could cover several jurisdictions, and each
   depends on the same terms-of-use ruling as Tampa and Orlando.
4. **Clerks, not counties, often hold the record.** Escambia, Manatee, Sarasota, St.
   Johns, Lake, Clay, Sumter and Citrus keep minutes or agendas on the Clerk and Comptroller's site. A
   source registry should record the publisher separately from the jurisdiction.

5. **Several mid-size counties publish one predictable URL per meeting** (Charlotte,
   Flagler, Columbia, Manatee, Leon): the cheapest scrapers to write, subject to the
   terms check.
6. **Alachua moved off Legistar** (stale since 2025-01-15) and Walton's 2014-era
   Legistar no longer exists, so a stale registry row is a signal to re-sweep, not to
   keep polling.
7. **Okeechobee's agenda is on IQM2**, the product behind the Miami adapter. If its
   terms allow, that adapter may need only a new base address and mapping rather than new code.
8. **The small counties mostly publish by uploading PDFs** to a WordPress site (Baker,
   Bradford, Madison, Suwannee, Dixie, Glades, Lafayette, Holmes, Levy's Clerk) with dates in the
   file name. Cheap to list, but every item is a document, not a structured record, and several
   archives stop in 2019 to 2024 in what a search can see. Several current meetings surfaced only on
   aggregators (Starbridge, CitizenPortal, Govly), which are not sources we should read from.
9. **Legistar names collide across states.** `madison` answers, but it is Wisconsin. Any
   token hit must be checked for Florida before it counts (bodies, then a recent matter).

## Searched in the third batch (25)

Santa Rosa (second look) and the 24 small counties: Baker, Bradford, Calhoun, Dixie,
Franklin, Gadsden, Gilchrist, Glades, Gulf, Hamilton, Hardee, Hendry, Holmes, Jefferson,
Lafayette, Levy, Liberty, Madison, Okeechobee, Suwannee, Taylor, Union, Wakulla, Washington.
For these, 125 guessed Legistar client names (`<county>`, `<county>county`, `<county>fl`,
`<county>countyfl`, `<county>bocc`) were also tried: the only answer was `madison`, which is
Madison, Wisconsin. No Florida small county was found on Legistar by guessing.

## To finish the sweep

- Open each row's source in a browser (reconnect the Chrome extension) and confirm
  platform, newest meeting date and whether items link to backup documents.
- Open the sources for the 25 counties of the third batch (all search-level), starting with
  Okeechobee's IQM2 portal, Franklin, Hardee and Washington (active in 2026), and look for
  Santa Rosa, Hamilton and Gilchrist's own archives.
- Municipalities from the earlier probe remain.
- Record `robots.txt`, a stated terms of use and any API for each platform.
