# Florida county meeting-records platforms: manual sweep, first pass

Status: partial, 2026-10-27. Continues `docs/FLORIDA_SOURCE_INVENTORY.md` (Todoist
`6hm2Cxf49P22gJmp`), which covers only what token-guessing found on Legistar. This pass
looked at 32 of the 67 counties by web search (16 in the first batch, 16 more in the second), then checked the Legistar API where a
search result named a client. **No county site was opened in a browser** (the Chrome
extension was not connected), so every row marked *search only* is what a search result
said, not something I saw on the page. Do not onboard from this table without opening
the source.

Not covered here: 24 small counties not searched (listed at the end), the 10 counties the probe already found on
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

## Not searched (24 small counties)

Baker, Bradford, Calhoun, Dixie, Franklin, Gadsden, Gilchrist, Glades, Gulf, Hamilton,
Hardee, Hendry, Holmes, Jefferson, Lafayette, Levy, Liberty, Madison, Okeechobee,
Suwannee, Taylor, Union, Wakulla, Washington. Each has well under 100,000 residents; most
use the county website or the Clerk, and the earlier probe found no Legistar client for
any of them by guessing. Santa Rosa (above) also needs a manual look.

## To finish the sweep

- Open each row's source in a browser (reconnect the Chrome extension) and confirm
  platform, newest meeting date and whether items link to backup documents.
- Search the 24 small counties and Santa Rosa, and the municipalities from the earlier probe.
- Record `robots.txt`, a stated terms of use and any API for each platform.
