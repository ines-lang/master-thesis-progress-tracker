# Ground truth: official ignition / discovery times (Step 2a)

Date: 3 Nov 2026. Window: fires igniting 8 to 15 Aug 2025 (UTC). Wildfires only (decision 2, strategy v3.0).
T0 reference hierarchy (decision 3): official ignition > first GEO detection > none.

Verification levels:
- **verified (official)**: value read from the official database by a script in this folder.
- **verified (API, research)**: value read from an official API during the research, no script yet.
- **news**: reported by media, possibly citing an official body.
- **unverified**: not confirmed.

Leads come from the exploratory FIRMS screen (strategy v3.0, Section 3).

## Summary

| Continent | Proposed event | Official ignition hour? | T0 reference | GEO for path B |
|---|---|---|---|---|
| Europe | Larouco, Molezuelas (done) | Yes (regional governments) | official | SEVIRI (on disk) |
| North America | **Red Canyon, WY**; alternative Mount Underwood, BC | Yes, verified (official) | official | GOES-West / GOES-East |
| Africa | Derdara / Chefchaouen, Morocco | News only (hour unverified) | official if ANEF confirms, else GEO | SEVIRI (on disk) |
| Asia (Siberia / Far East) | New Irkutsk / Yakutia complex, to be chosen from FIRMS | No | GEO | Himawari-9 [verify view angle at 61 N] |
| South America | **Excluded** (decision of 3 Nov 2026) | | | |
| Oceania | **Excluded** (decision of 3 Nov 2026) | | | |

## North America

Official sources:

| Source | Access | Hour? | Aug 2025? |
|---|---|---|---|
| NIFC WFIGS Incident Locations | ArcGIS FeatureServer, field `FireDiscoveryDateTime` (UTC, ms) | Yes, minute | Yes, verified (official) |
| BC Wildfire Service public API | `wildfiresituation-api.nrs.gov.bc.ca/publicPublishedIncident/<FIRE_NUMBER>?fireYear=2025`, field `discoveryDate` | Yes, second | Yes, verified (API, research) |
| BC open data `PROT_HISTORICAL_INCIDENTS_SP` | openmaps.gov.bc.ca WFS, field `IGNITION_DATE` | Date only | Yes |
| CWFIS / CNFDB | cwfis.cfs.nrcan.gc.ca WFS `public:NFDB_point` | Date only | No 2025 records yet |
| NWT Fire | gov.nt.ca per-fire pages | Not checked (server timeout) | ? |

Candidates (US rows: `processed/wfigs_candidates.csv`, from `scripts/00_wfigs_query.py`, verified (official)):

| Fire | ID | Lat, lon | Discovery (UTC) | Size | Cause | FIRMS lead |
|---|---|---|---|---|---|---|
| **Red Canyon, WY** | 2025-WYWBD-000254 | 43.6514, -108.01 | 2025-08-14T00:09Z (13 Aug 18:09 MDT) | 124,709 ac = 50,468 ha | Natural (lightning), BLM rangeland | 43.6 N 107.9 W, first FIRMS 14 Aug 07:56Z |
| Sleeper Ranch, WY | 2025-WYPAX-000256 | 44.252, -108.777 | 2025-08-14T13:44Z | 8,360 ha | Natural | |
| Mission Butte, MT | 2025-MTCRA-250811 | 45.592, -107.593 | 2025-08-13T03:26Z | 2,488 ha | Undetermined | |
| Box, ID | 2025-IDBOD-000997 | 42.5178, -117.0 | 2025-08-13T17:00Z | 1,747 ha | Natural | 42.5 N 117.0 W |
| Spring Creek, WY | 2025-WYWAX-000252 | 43.952, -107.247 | 2025-08-13T19:32Z | 1,454 ha | Natural | |
| Rock, ID | 2025-IDBOF-000991 | 44.6495, -116.1617 | 2025-08-13T06:27Z | 1,132 ha | Natural | 44.7 N 116.2 W |
| Mount Underwood, BC | V71498 | 49.1252, -124.7763 | 2025-08-12T01:30:42Z (11 Aug 18:30 PDT) | 3,518 ha | Unknown | 49.1 N 124.8 W, first FIRMS 12 Aug 09:47Z |
| NWT lead | ? | 65.7 N 123.7 W | not found | | | unidentified (possibly VQ018-25, unverified) |

Notes:
- WFIGS times are UTC. Red Canyon cross-check: local report of a lightning start at about 6:09 p.m. MDT on 13 Aug (wyodaily, 21 Aug 2025) matches 00:09Z.
- Mount Underwood: `discoveryDate` equals `createDate` in the BC record, so it is the record creation time, not necessarily the discovery. News: "discovered Monday 11 Aug" (richmond-news). verified (API, research), script pending.
- Red Canyon: the incident team reported 126,683 ac in the news; WFIGS gives 124,709 ac.

**Recommendation: Red Canyon.** Largest, lightning-caused, official minute-level UTC time, ignition 7.8 h before the first FIRMS detection of the lead cluster. The FIRMS data end (15 Aug 21:26Z) leaves about 45 h after ignition, enough for T0.

## Asia (Siberia / Russian Far East)

Official sources: ISDM-Rosleskhoz (Avialesookhrana) holds detection dates but has no public per-fire download (aviales.ru did not respond). Daily summaries give regional totals only. MChS PDFs cover structural fires.

| Lead | Finding | Level |
|---|---|---|
| 56.0 N 160.6 E (Kamchatka, 9 Aug) | **Klyuchevskoy volcano** (about 56.06 N 160.64 E), erupting with lava flows since 30 to 31 Jul. **Not a wildfire: excluded.** The screen must mask volcanoes | Eruption: news (MChS Kamchatka via eastrussia.ru). Hotspot = lava: inference from coordinates |
| 61.4 N 112.8 E (10 Aug) | Lensky / Mirninsky district, Yakutia, near the Irkutsk border. No named fire found. **Check for persistent gas flaring** at nearby oil and gas fields | unverified |

Regional context (news, unverified): 12 Aug, Krasnoyarsk 61 fires / 145,495 ha; Irkutsk 54 / 121,629 ha; Yakutia 14 / 1,187 ha.

**Recommendation:** choose a new Irkutsk / Yakutia complex from FIRMS, after masking flares and volcanoes. T0 reference = first Himawari-9 detection.

## South America

Official sources: INPE BDQueimadas (satellite detections, not ignitions); Bolivian ministry daily reports (counts only; national emergency DS 5447 on 20 Aug); ICMBio / Prevfogo and Pantanal bulletins (date only); Argentina SNMF (date only); CONAF Chile (hour, but August is off-season).

No wildfire with an official start time in 8 to 15 Aug was found. The FIRMS leads (Bolivia 13.5 S 62.2 W, Amazon 7.0 S 59.6 W) are likely land clearing or savanna burning. The nearest documented protected-area wildfire, Chapada dos Veadeiros NP (829 ha), burned 22 to 24 Aug: outside the window.

**Decision (Ines, 3 Nov 2026): South America is excluded.** August is austral winter; the fires in the window are dry-season clearing, agricultural or savanna burns, and no officially recorded wildfire ignited 8 to 15 Aug 2025. Reported as a result of the selection.

## Africa

| Fire | Lat, lon | Ignition | Size | Land | Level |
|---|---|---|---|---|---|
| **Derdara forest fire, Chefchaouen, Morocco** | about 35.1 N 5.3 W (unverified) | Tue 12 Aug 2025 "around 2:00 pm" local (UTC+1) = about 13:00Z | about 500 ha (ANEF) | Forest, mainly cork oak; contained 14 Aug | Date and size: news citing ANEF (North Africa Post, AA, Hespress). **Hour unverified**: not attributed to ANEF; TelQuel says "night of 12 to 13 Aug" |
| Ghanzi, Botswana (23.7 S 21.3 E, about 79 x 72 km) | | none found | | Kalahari veld fire, cause unknown | unverified, no official record |

The FIRMS screen has a Morocco complex at 35.10 N 5.31 W, first seen 12 Aug 13:10Z (125 VIIRS detections), which fits Derdara. To be checked in Step 2.

**Recommendation:** Derdara, with SEVIRI (already on disk). Confirm the hour with an ANEF / MAP communique; if not confirmed, T0 reference = first SEVIRI detection. Ghanzi has no ground truth.

## Oceania

Official sources: Emergency WA / DFES and Bushfires NT give warning or notification times only, not ignitions; QFD nothing found for Aug 2025.

| Fire | Location | Time | Notes | Level |
|---|---|---|---|---|
| El Questro / King River, East Kimberley WA | about 15.9 to 16.1 S, 128.1 to 128.4 E | Bushfire Advice "since 13 Aug" | Not contained on 19 Aug; cause unknown, could be pastoral or prescribed burning | news (Broome Advertiser, 19 Aug 2025); match with the FIRMS lead 16.1 S 128.4 E is an inference |
| Mckinlay Rd Ext, Black Jungle NT | not given | Watch and Act 10 Aug, timezone unclear | Small peri-urban fire | unverified |

**Decision (Ines, 3 Nov 2026): Oceania is excluded.** Same reason as South America: austral winter, the fires in the window are dry-season (often prescribed) savanna burns, and no official ignition record exists.

## Consequences for Step 2
1. The FIRMS screen must exclude volcanoes and gas flares (type flag is not enough: Klyuchevskoy passed the type filter).
2. A wildfire check is needed per candidate: official record, protected-area / forest mask, or news.
3. Only North America has a verified official ignition hour. Africa may have one.
4. South America and Oceania are excluded (austral winter, no officially recorded wildfire in the window). Remaining new events: North America, Africa, Asia.

## Update after the global FIRMS screen (3 Nov 2026)
Scripts `scripts/01_screen_firms.py`, `02_criteria.py`, `03_figures.py`; candidates and decisions in `notes/candidates_ground_truth.csv`.
- **Hemisphere rule (decision of Ines):** every complex south of the equator is excluded (austral winter), not only South America and Oceania. Ghanzi (Botswana) is excluded with it.
- **Africa:** Derdara is the only African complex north of the equator passing all criteria; the rest are Saharan point sources (Algeria, Libya) or do not spread. No official hour exists: press says 14:00 local (North Africa Post) or the night of 12 to 13 Aug (Medias24). T0 reference: first SEVIRI detection.
- **Asia:** Kamchatka is removed by the vegetation criterion (73% flagged); the six Siberian complexes are point sources (1.7 to 3.8 km, 6 to 13 cells), likely gas flares. No eligible Asian event.
- **North America:** the 1 km screen gives Red Canyon's first detection at 14 Aug 04:20Z (+4.2 h after discovery). Mission Butte has no detection within 5 km of its WFIGS point.
- The screen reproduces both Spanish T0s (Larouco 13 Aug 21:45Z, Molezuelas 10 Aug 12:32Z).
