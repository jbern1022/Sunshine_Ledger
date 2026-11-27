# Amazon Translate evaluation: Spanish and Haitian Creole (2026-11-27)

Todoist `6hxjxV4W8jHcCh8p` (part of the AWS $100 gate). Builds on `docs/LOCALIZATION_PROPOSAL.md`.

## Findings

* **Both languages are supported** in this AWS project (us-east-2): `es` Spanish, `ht` Haitian Creole.
* **Cost** is $15 per million characters (standard real-time translation; verify on the AWS pricing page
  before budgeting). Text on the site today (production, 2026-11-27):

  | Text | Records | Characters | Cost per language, all at once |
  |---|---|---|---|
  | Summaries ("what it does") | 20,213 | 6.79 M | about $102 |
  | Layer statements (current versions) | 107,653 | 19.94 M | about $299 |

  Translating everything up front in both languages would cost about **$800**, and again every time a summary
  is regenerated. **Translate on demand and cache** (keyed by the English text's hash, so a regenerated
  summary is translated fresh and an unchanged one never twice): cost then follows what readers open.
* **Quality needs a fluent reviewer before anything is shown.** Things a non-fluent read can already see in
  the sample below, for the reviewer to confirm:
  * Spanish renders "This item" (an agenda item) as "Este artículo"; "Este punto" is the usual word.
  * Haitian Creole renders "extends the deadline" as "fin dat limit la"; "fin" usually means *end*, the
    opposite. "Mixed-use" became a literal compound ("melanje-itilize").
  * The Jacksonville source summary itself says "This bill" for an ordinance (local re-summarization has not
    reached it yet); translation copies the English error into both languages. Fix English first.
* Per the localization proposal and the ticket: label every translation as a machine translation of the
  English original, link the English, and keep the English authoritative.

## Recommendation

Pilot on demand for **summaries only** (not layers) behind a language switch on the bill page, cached, with
the machine-translation label, after a fluent Spanish and Haitian Creole reviewer has checked about 30
summaries each and the corrections are recorded as a glossary (Translate custom terminology: "bill",
"ordinance", "agenda item", "committee substitute", "mixed-use"). Expected cost at pilot traffic: cents
per month.

## Sample (4 summaries, 1,606 characters per language, cost about $0.05 for both)

### H1389

**English (site):** This bill requires counties and municipalities in Florida to allow multifamily and mixed-use residential developments on certain properties, such as those owned by counties, municipalities, or school districts. These developments must have at least 40% of their units be affordable rentals for at least 30 years, and must not be restricted by local zoning laws or regulations. The bill also clarifies what types of land uses are considered commercial, industrial, and mixed-use, and limits the restrictions that counties and municipalities can impose on these types of developments.

**Spanish (Amazon Translate):** Este proyecto de ley exige que los condados y municipios de Florida permitan desarrollos residenciales multifamiliares y de uso mixto en ciertas propiedades, como las que son propiedad de condados, municipios o distritos escolares. Estos desarrollos deben tener al menos el 40% de sus unidades como alquileres asequibles durante al menos 30 años, y no deben estar restringidos por las leyes o regulaciones locales de zonificación. El proyecto de ley también aclara qué tipos de usos del suelo se consideran comerciales, industriales y de uso mixto, y limita las restricciones que los condados y municipios pueden imponer a este tipo de desarrollos.

**Haitian Creole (Amazon Translate):** Bòdwo sa a mande pou konte ak minisipalite nan Florid pou pèmèt devlopman rezidansyèl multifanmi ak melanje-itilize sou pwopriyete sèten, tankou sa yo ki posede pa konte, minisipalite, oswa distri lekòl yo. Devlopman sa yo dwe gen omwen 40% nan inite yo dwe lwaye abòdab pou omwen 30 ane, epi yo pa dwe restriksyon pa lwa zòn lokal oswa règleman yo. Bòdwo a tou klarifye ki kalite itilizasyon tè yo konsidere kòm komèsyal, endistriyèl, ak melanje-itilize, ak limite restriksyon yo ke konte ak minisipalite ka enpoze sou kalite sa yo nan devlopman.

### S1166

**English (site):** This bill requires health insurers to notify people and their doctors at least 60 days before making changes to the list of covered prescription drugs. If a doctor certifies that a prescription is medically necessary, the insurer must continue to cover it at the current level, even if the change would have otherwise reduced or eliminated coverage. The insurer also has to report changes to the list of covered drugs to the state and explain why they made the changes.

**Spanish (Amazon Translate):** Este proyecto de ley exige que las aseguradoras de salud notifiquen a las personas y a sus médicos al menos 60 días antes de realizar cambios en la lista de medicamentos recetados cubiertos. Si un médico certifica que una receta es necesaria desde el punto de vista médico, la aseguradora debe seguir cubriéndola al nivel actual, incluso si el cambio hubiera reducido o eliminado la cobertura. La aseguradora también tiene que informar al estado sobre los cambios en la lista de medicamentos cubiertos y explicar por qué los hizo.

**Haitian Creole (Amazon Translate):** Bòdwo sa a mande pou asirans sante yo avize moun ak doktè yo omwen 60 jou anvan yo fè chanjman nan lis dwòg preskripsyon kouvri yo. Si yon doktè sètifye ke yon preskripsyon medikalman nesesè, asirans lan dwe kontinye kouvri li nan nivo aktyèl la, menm si chanjman an ta gen otreman redwi oswa elimine pwoteksyon. Asirans lan gen tou rapòte chanjman nan lis dwòg ki kouvri nan eta a epi eksplike poukisa yo te fè chanjman yo.

### 2026-0851-E

**English (site):** This bill extends the deadline for spending funds allocated for a housing program. The original deadline was June 30, 2026, but it has been extended to March 31, 2027. This change allows cities to use these funds over a longer period. The mayor and corporation secretary are authorized to sign documents to make this extension official.

**Spanish (Amazon Translate):** Este proyecto de ley extiende la fecha límite para gastar los fondos asignados a un programa de vivienda. La fecha límite original era el 30 de junio de 2026, pero se ha extendido hasta el 31 de marzo de 2027. Este cambio permite a las ciudades utilizar estos fondos durante un período más largo. El alcalde y el secretario de la corporación están autorizados a firmar documentos para oficializar esta extensión.

**Haitian Creole (Amazon Translate):** Bòdwo sa a fin dat limit la pou depans lajan asiyen pou yon pwogram lojman. Data limit orijinal la te 30 jen 2026, men li te pwolonje nan 31 mas 2027. Chanjman sa a pèmèt lavil yo sèvi ak lajan sa yo sou yon peryòd ki pi long. Majistra a ak sekretè kòporasyon yo otorize siyen dokiman pou fè ekstansyon sa a ofisyèl.

### 20224

**English (site):** This item is a record of comments submitted by members of the public to the City Commission through an online system for their November 19, 2026, meeting. The published record gives no further detail about the comments.

**Spanish (Amazon Translate):** Este artículo es un registro de los comentarios enviados por miembros del público a la Comisión Municipal a través de un sistema en línea para su reunión del 19 de noviembre de 2026. El registro publicado no proporciona más detalles sobre los comentarios.

**Haitian Creole (Amazon Translate):** Atik sa a se yon dosye kòmantè ki soumèt pa manm nan piblik la nan Komisyon vil la atravè yon sistèm sou entènèt pou reyinyon 19 novanm 2026 yo. Dosye pibliye a pa bay okenn detay plis sou kòmantè yo.
