# Florida county meeting-records platforms: manual sweep, first pass

Status: partial, 2026-10-26. Continues `docs/FLORIDA_SOURCE_INVENTORY.md` (Todoist
`6hm2Cxf49P22gJmp`), which covers only what token-guessing found on Legistar. This pass
looked at 16 of the 67 counties by web search, then checked the Legistar API where a
search result named a client. **No county site was opened in a browser** (the Chrome
extension was not connected), so every row marked *search only* is what a search result
said, not something I saw on the page. Do not onboard from this table without opening
the source.

Not covered here: 41 counties not searched, the 10 counties the probe already found on
Legistar (Brevard, Broward, DeSoto, Hernando, Hillsborough, Marion, Martin, Pinellas,
Polk, Seminole), Duval (Jacksonville is consolidated and already ingested), and
municipalities beyond the earlier probe. Terms-of-use have not been checked for any
source (the open Tampa/Orlando ruling `6hm2FqXfHvxVR45G` applies the same question to
these).

| County | Platform (as found) | Evidence | Verified how |
|---|---|---|---|
| Orange | **Legistar** client `occompt` (Comptroller-hosted), agendas as PDFs in `apps.ocfl.net/eAgenda`, minutes scanned in occompt.com DocumentCenter | January 2026 agenda links each item to `occompt.legistar.com`; API returned a matter modified 2026-10-26 | **API checked, live**: token `occompt` works, newest matter 2026-10-26. The probe missed it because the token is not guessable. Strong candidate for onboarding. |
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

## Takeaways

1. **One new ready candidate:** Orange County on Legistar (`occompt`), verified live.
   It would need the usual registry entry and a spot-check of kinds and sponsors
   (county level, like Broward). It is the only row here that I would call onboardable.
2. **The big counties mostly publish PDFs on county or Clerk sites, not a feed.** Palm
   Beach, Lee, Volusia, Leon, Manatee, Sarasota, Collier have no Legistar client under
   obvious tokens. Each would need a custom scraper, and each new scraper needs a terms
   check first.
3. **Two hosted products recur:** OnBase Agenda Online (Osceola, Tampa) and CivicClerk
   (Escambia). One adapter per product could cover several jurisdictions, and both
   depend on the same terms-of-use ruling as Tampa and Orlando.
4. **Clerks, not counties, often hold the record.** Escambia, Manatee, Sarasota, St.
   Johns, Lake and Clay keep minutes or agendas on the Clerk and Comptroller's site. A
   source registry should record the publisher separately from the jurisdiction.

## To finish the sweep

- Open each row's source in a browser (reconnect the Chrome extension) and confirm
  platform, newest meeting date and whether items link to backup documents.
- Search the 41 remaining counties and the municipalities from the earlier probe.
- Record `robots.txt`, a stated terms of use and any API for each platform.
