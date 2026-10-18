import { PORTS } from './yard-demo.ts';
import type { DemoPort } from './yard-demo.ts';
// English source keys keep the existing LA interface unchanged. Dutch labels are explicit,
// with parameterized messages for IDs/counts; user-entered notes are never translated.
const dutch: Record<string, string> = Object.fromEntries(`
Agent suggestions panel|Paneel met agentaanbevelingen
Generate|Genereren
Generating…|Bezig met genereren…
Generate suggested actions and a fault email from the current evidence.|Genereer voorgestelde acties en een storingsmail op basis van de actuele gegevens.
Problem|Probleem
Perishable goods|Bederfelijke goederen
Delayed perishables · priority raised|Bederfelijke lading vertraagd · hogere prioriteit
Perishable cargo|Bederfelijke lading
Fresh produce|Verse producten
Seafood|Vis en zeevruchten
Pharmaceuticals|Geneesmiddelen
General cargo|Algemene lading
Perishable pickup delayed|Ophalen bederfelijke lading vertraagd
Perishable delay|Vertraging bederfelijke lading
Prioritize pickup and confirm cold-chain care|Geef ophalen voorrang en bevestig koelketenzorg
Gate / trucking + reefer coordinator|Coördinator poort / transport en reefer
Scenario priority changes|Prioriteitswijzigingen door scenario
Congestion emergency · priorities recalculated|Verkeersopstopping · prioriteiten herberekend
Power emergency · priorities recalculated|Stroomstoring · prioriteiten herberekend
Whole-yard impact · same containers, current server scores|Impact op het hele terrein · dezelfde containers, actuele serverscores
Do-first containers|Containers met hoogste prioriteit
Newly high priority|Nieuwe hoge prioriteit
Perishables delayed|Bederfelijke lading vertraagd
Demo pickup delay|Demovertraging bij ophalen
Routine inventory|Reguliere voorraad
min pickup delay|min ophaalvertraging
Raised to Do first|Verhoogd naar Direct aanpakken
Urgent care / perishable delay|Spoedzorg / vertraagde bederfelijke lading
Demo pickup window|Demo-ophaalvenster
Margin after delay|Marge na vertraging
Routine score|Reguliere score
Routine inventory · no exception action|Reguliere voorraad · geen afwijkingsactie
This container|Deze container
 do first| hoogste prioriteit
Now|Nu
Keep cold-chain care in place; confirm a usable pickup appointment and escalate the time-critical case to the supervisor. Resolve independent holds in parallel.|Houd de koelketenzorg in stand; bevestig een bruikbare ophaalafspraak en escaleer de tijdkritische situatie naar de supervisor. Los afzonderlijke blokkades gelijktijdig op.
Perishable cargo depends on the congested pickup corridor, including units still in reefer storage.|Bederfelijke lading is afhankelijk van de verstopte ophaalroute, ook containers die nog in reeferopslag staan.
Confirm cold-chain care and coordinate an authorized pickup alternative; delay alone does not establish spoilage.|Bevestig koelketenzorg en stem een toegestaan ophaalalternatief af; vertraging alleen bewijst geen bederf.
Congestion raises the consequence and urgency of this perishable prerequisite; responsible staff must reconcile it without bypassing the control.|Opstopping verhoogt de impact en urgentie van deze voorwaarde voor bederfelijke lading; bevoegde medewerkers moeten dit oplossen zonder controles over te slaan.
120 min demo pickup delay · C03/C04 access and dependent perishable cargo are affected|120 min demo-ophaalvertraging · toegang C03/C04 en afhankelijke bederfelijke lading zijn getroffen
R1 power loss + 120 min demo pickup delay · separate cargo care from release|Stroomuitval R1 + 120 min demo-ophaalvertraging · scheid ladingzorg en vrijgave
Pickup route|Ophaalroute
Cargo profile|Ladingprofiel
Use HTTPS or localhost to connect the agent.|Gebruik HTTPS of localhost om de agent te verbinden.
The agent provider did not respond in time. No action was taken. Try a shorter drafting request or generate again later.|De agentaanbieder reageerde niet op tijd. Er is geen actie uitgevoerd. Probeer een korter verzoek of genereer later opnieuw.
Agent suggestions|Agentaanbevelingen
Agent connected|Agent verbonden
Connect agent|Agent verbinden
Agent connection|Agentverbinding
Refresh agent connection|Agentverbinding vernieuwen
Disconnect agent|Agent loskoppelen
Connect team agent|Teamagent verbinden
Team access needs API credentials and a separate access code configured on the server.|Teamtoegang vereist API-inloggegevens en een aparte toegangscode op de server.
Provider API key|API-sleutel van aanbieder
Generating suggestions…|Aanbevelingen genereren…
Refresh suggestions|Aanbevelingen vernieuwen
Generate suggestions|Aanbevelingen genereren
Could not load the agent connection.|De agentverbinding kon niet worden geladen.
Connect the agent above to generate. Opening this panel makes no model call.|Verbind de agent hierboven om te genereren. Het openen van dit paneel start geen modelaanroep.
Agent-generated|Door agent gegenereerd
Claude fault assistant|Claude-assistent voor storingen
This Claude key requires a workspace. Set ANTHROPIC_WORKSPACE_ID on the server and restart, or use a workspace-scoped key.|Deze Claude-sleutel vereist een werkruimte. Stel ANTHROPIC_WORKSPACE_ID in op de server en herstart, of gebruik een sleutel voor één werkruimte.
Claude rejected the API key (401). Update ANTHROPIC_API_KEY on the server and restart before generating again.|Claude heeft de API-sleutel geweigerd (401). Werk ANTHROPIC_API_KEY bij op de server en herstart voordat u opnieuw genereert.
The Claude account has insufficient API credit. Check billing in Claude Console before generating again.|Het Claude-account heeft onvoldoende API-tegoed. Controleer de facturering in Claude Console voordat u opnieuw genereert.
Claude denied access (403). Check the key and workspace permissions.|Claude heeft toegang geweigerd (403). Controleer de rechten van de sleutel en werkruimte.
Claude could not find the configured model or resource. Check ANTHROPIC_MODEL and workspace access.|Claude kon het ingestelde model of de resource niet vinden. Controleer ANTHROPIC_MODEL en werkruimtetoegang.
Claude rate or quota limit reached (429). Wait before generating again.|Claude-snelheidslimiet of quotum bereikt (429). Wacht voordat u opnieuw genereert.
Claude rejected or could not complete the request. Check model configuration and provider availability.|Claude heeft het verzoek geweigerd of kon het niet voltooien. Controleer het model en de beschikbaarheid van de aanbieder.
Claude assistant|Claude-assistent
DRAFT ONLY|ALLEEN CONCEPT
Ask about this exception or draft a fault email from the recorded evidence.|Stel een vraag over deze afwijking of maak een storingsmail op basis van geregistreerde gegevens.
Claude connected|Claude verbonden
Team access required|Teamtoegang vereist
Connect Claude|Claude verbinden
Claude connection|Claude-verbinding
Refresh Claude connection|Claude-verbinding vernieuwen
Team key stays on the server.|De teamsleutel blijft op de server.
Personal key is held in temporary server memory.|De persoonlijke sleutel wordt tijdelijk in het servergeheugen bewaard.
Disconnect Claude|Claude loskoppelen
Team access code|Teamtoegangscode
Connect team Claude|Team-Claude verbinden
Team Claude needs ANTHROPIC_API_KEY, ANTHROPIC_MODEL and CONSOLE_TEAM_ACCESS_CODE on the server.|Team-Claude vereist ANTHROPIC_API_KEY, ANTHROPIC_MODEL en CONSOLE_TEAM_ACCESS_CODE op de server.
Use a temporary personal key|Een tijdelijke persoonlijke sleutel gebruiken
Claude API key|Claude-API-sleutel
Exact model ID|Exact model-ID
Connect temporarily|Tijdelijk verbinden
Credentials are cleared on submit and never saved in browser storage. Access lasts up to 15 minutes.|Inloggegevens worden na verzenden gewist en niet in browseropslag bewaard. Toegang duurt maximaal 15 minuten.
Use HTTPS or localhost to connect Claude.|Gebruik HTTPS of localhost om Claude te verbinden.
Question or drafting request|Vraag of verzoek voor een concept
What should we verify first?|Wat moeten we eerst controleren?
Claude is drafting…|Claude schrijft een concept…
Generate a new draft|Nieuw concept genereren
Generate with Claude|Met Claude genereren
Connect Claude above to generate. Opening this panel makes no model call.|Verbind Claude hierboven om te genereren. Het openen van dit paneel start geen modelaanroep.
Check the same request|Hetzelfde verzoek controleren
Could not load the Claude connection.|De Claude-verbinding kon niet worden geladen.
Could not load saved drafts.|Opgeslagen concepten konden niet worden geladen.
Draft status is unavailable. Reconnect to check; generation is not repeated.|Conceptstatus is niet beschikbaar. Verbind opnieuw om te controleren; genereren wordt niet herhaald.
Claude connection failed.|Claude-verbinding mislukt.
Draft request failed.|Conceptverzoek mislukt.
Select and copy the draft text manually.|Selecteer en kopieer de concepttekst handmatig.
Yard data changed. This draft is out of date; generate again before using it.|Terreingegevens zijn gewijzigd. Dit concept is verouderd; genereer opnieuw voordat u het gebruikt.
Assistant output|Assistentresultaat
Suggestions|Aanbevelingen
Fault email|Storingsmail
Source facts|Brongegevens
Escalate to supervisor now|Nu escaleren naar supervisor
Coordinate with responsible team|Afstemmen met verantwoordelijk team
Still needs verification|Nog te controleren
To role|Aan rol
Subject|Onderwerp
Email draft|E-mailconcept
Copied|Gekopieerd
Copy draft|Concept kopiëren
Advisory only. No email is sent and no container status is changed.|Alleen advies. Er wordt geen e-mail verzonden en geen containerstatus gewijzigd.
YARD DECISION SUPPORT|BESLISONDERSTEUNING CONTAINERTERREIN
Server rules|Serverregels
Observation version|Waarnemingsversie
Last observation|Laatste waarneming
New observation requires follow-up|Nieuwe waarneming vereist opvolging
Database-backed review decisions. Detailed task progress is in Post-action.|Beoordelingen opgeslagen in de database. Taakvoortgang staat onder Opvolging.
Connection interrupted. Showing the last acknowledged yard data.|Verbinding onderbroken. De laatst bevestigde terreingegevens worden getoond.
Yard database temporarily unavailable. Retry the same request.|Terreindatabase tijdelijk niet beschikbaar. Probeer hetzelfde verzoek opnieuw.
Yard workspace expired or unavailable. Reconnect to continue.|De terreinwerkruimte is verlopen of niet beschikbaar. Verbind opnieuw om door te gaan.
Work completion needs result verification. A normal container remains in inventory; only confirmed physical gate-out releases its occupied tier slot. This is a database-backed simulation.|Voltooiing vereist resultaatverificatie. Een normale container blijft in voorraad; alleen bevestigde fysieke uitrit maakt de positie vrij. Deze simulatie wordt in de database opgeslagen.
Connected · SQLite|Verbonden · SQLite
Saving to database…|Opslaan in database…
Connection interrupted|Verbinding onderbroken
Connecting to the yard database…|Verbinden met de terreindatabase…
Retry connection|Opnieuw verbinden
Retry save|Opslag opnieuw proberen
Refresh data|Gegevens vernieuwen
Saved in database|Opgeslagen in database
Server database · synthetic observations|Serverdatabase · gesimuleerde waarnemingen
Simulate a new observation|Nieuwe waarneming simuleren
Adds a server-recorded synthetic event. Existing independent holds remain active.|Voegt een gesimuleerde waarneming toe aan de server. Afzonderlijke blokkades blijven actief.
New server demo run created. Previous run retained in audit history.|Nieuwe demonstratie op de server aangemaakt. De vorige blijft in de historie bewaard.
New observation requires another check.|Een nieuwe waarneming vereist een extra controle.
Connection interrupted. The save may have reached the server; retry the same request to confirm.|Verbinding onderbroken. Het verzoek kan opgeslagen zijn; probeer hetzelfde verzoek opnieuw ter bevestiging.
The yard changed. Current data has been refreshed; review the action before trying again.|Het terrein is gewijzigd. Actuele gegevens zijn vernieuwd; beoordeel de actie opnieuw.
Task stage changed. Refresh its current state before continuing.|De taakstatus is gewijzigd. Vernieuw de huidige status voordat u verdergaat.
The yard API saves synthetic inventory, observations, decisions, task progress and gate-outs in SQLite. Changes are verified by the server. Foreground pages refresh every two seconds. No agent, Terminal49 or equipment is called. Browser-only history from the previous prototype is retained separately and is not imported as verified evidence.|De terrein-API bewaart gesimuleerde voorraad, waarnemingen, beoordelingen, taken en uitritten in SQLite. De server controleert wijzigingen. Actieve pagina’s vernieuwen elke twee seconden. Geen aanroepen naar agent, Terminal49 of materieel. Eerdere browserhistorie blijft apart bewaard en wordt niet als geverifieerd bewijs geïmporteerd.
Cancel|Annuleren
Also active:|Ook actief:
pending actions|openstaande acties
containers in stack ·|containers in stapel ·
· inspect action|· actie bekijken
Choose a container|Kies een container
Demo port|Demohaven
Demo terminal|Demoterminal
SYNTHETIC|GESIMULEERD
DEMO ONLY|ALLEEN DEMO
Saved in this browser|Opgeslagen in deze browser
Storage unavailable · keep tab open|Opslag niet beschikbaar · houd dit tabblad open
About this prototype|Over deze demo
About this yard prototype|Over deze terreindemo
Workspace navigation|Werkruimtenavigatie
Inventory query|Voorraad zoeken
Query|Zoeken
Yard|Terrein
Yard overview|Terreinoverzicht
Decision queue|Actiewachtrij
Actions|Acties
Post-action|Opvolgen
Post-action queue|Opvolgingswachtrij
Post-action status|Opvolgingsstatus
Review history|Beoordelingsgeschiedenis
History|Historie
Human|Menselijke
in control|regie
Current yard inventory query|Zoeken in terreinvoorraad
Find containers|Containers zoeken
Close inventory query|Voorraadzoeker sluiten
Close inventory query overlay|Zoekpaneel sluiten
CURRENT YARD INVENTORY|ACTUELE TERREINVOORRAAD
Container number|Containernummer
Full or partial number|Volledig of gedeeltelijk nummer
Company / carrier|Bedrijf / rederij
e.g. Maersk or MAEU|bijv. Maersk of MAEU
matching /|gevonden /
in yard|op het terrein
Clear|Wissen
Show matching inventory|Gevonden voorraad tonen
Container query results|Zoekresultaten containers
No containers found|Geen containers gevonden
Try a shorter number, carrier name or code. Both fields must match when filled.|Probeer een korter nummer, rederijnaam of code. Ingevulde velden moeten beide overeenkomen.
Previous query results|Vorige zoekresultaten
Next query results|Volgende zoekresultaten
of|van
Bay|Vak
Block|Blok
Row|Rij
Tier|Laag
· row|· rij
· tier|· laag
/ Row|/ Rij
/ Tier|/ Laag
Back|Terug
Back to previous view|Terug naar vorige weergave
Expanded view|Uitvergrote weergave
ESC TO RETURN|ESC OM TERUG TE GAAN
OPERATIONS /|OPERATIE /
REVIEW LOG|BEOORDELINGSLOG
YARD COORDINATION|TERREINCOÖRDINATIE
Your yard. A clearer next move.|Uw terrein. De volgende stap in beeld.
The right action. At the right time.|De juiste actie. Op het juiste moment.
Every action. Followed through.|Elke actie. Volledig opgevolgd.
A record of your decisions.|Een overzicht van uw beslissingen.
Different zones. Finite infrastructure. Evidence before action.|Verschillende zones. Beperkte capaciteit. Eerst verifiëren, dan handelen.
Importance × urgency. Reassessed against the current scenario, one action at a time.|Belang × urgentie. Per actie opnieuw beoordeeld voor het actuele scenario.
Track work, verify the result, and keep inventory in step with physical gate-out.|Volg werkzaamheden, verifieer het resultaat en werk de voorraad bij na fysieke uitrit.
Locally saved review decisions. Detailed task progress is in Post-action.|Lokaal opgeslagen beoordelingen. De voortgang van taken staat onder Opvolging.
A larger spatial reference. Select a block to inspect its stacks and inventory.|Een uitvergroot terreinoverzicht. Selecteer een blok voor stapels en voorraad.
DEMO SCENARIO|DEMOSCENARIO
Routine operations|Reguliere operatie
Reefer circuit R1 outage|Stroomuitval reefercircuit R1
Outbound congestion|Congestie bij de uitrit
Combined disruption|Gecombineerde verstoring
Normal conditions · review day-to-day exceptions|Normale omstandigheden · beoordeel dagelijkse afwijkingen
Only connected reefers in B01/B02 lose supply; circuit R2 in C01 remains energized|Alleen aangesloten reefers in B01/B02 verliezen voeding; circuit R2 in C01 blijft onder spanning
Synthetic access restriction affects blocks C03 and C04|Gesimuleerde toegangsbeperking voor blokken C03 en C04
R1 power loss + C03/C04 outbound restriction · separate care from pickup|Stroomuitval R1 + uitritbeperking C03/C04 · scheid ladingzorg van afhaling
Containers in yard|Containers op terrein
Slot utilization|Bezettingsgraad
Flagged containers|Containers met afwijkingen
Free modeled tier slots|Vrije gesimuleerde laagposities
Synthetic yard metrics|Gesimuleerde terreinmetingen
Reset scenario|Scenario herstellen
. Existing clearance restrictions remain visible.|. Bestaande vrijgavebeperkingen blijven zichtbaar.
BLOCK DETAIL|BLOKDETAIL
REFERENCE VIEW|REFERENTIE
Expand|Vergroten
Expand yard section|Terreingedeelte vergroten
Hide yard view|Terreinoverzicht verbergen
Show yard view|Terreinoverzicht tonen
Map color layer|Kaartkleuren
Exceptions|Afwijkingen
Cargo type|Ladingtype
Power infrastructure|Stroomvoorziening
Select a stack to inspect its tiers|Selecteer een stapel om de lagen te bekijken
Zoom out|Uitzoomen
Zoom in|Inzoomen
Reset map zoom|Zoom herstellen
WATERSIDE / BERTH APRON|WATERZIJDE / KADE
SCHEMATIC · DEMO DATA|SCHEMATISCH · DEMODATA
LANDSIDE / GATE ACCESS|LANDZIJDE / POORTTOEGANG
LAYOUT NOT TO SCALE|NIET OP SCHAAL
Synthetic yard block schematic. Open a block for more detail.|Gesimuleerd terreinschema. Open een blok voor meer details.
Colors show|Kleuren tonen
No flag|Geen afwijking
Hold / access|Blokkade / toegang
Weight conflict|Gewichtsafwijking
Temperature / power|Temperatuur / stroom
Sensor|Sensor
Energized connection|Aansluiting onder spanning
Interrupted connection|Onderbroken aansluiting
No reefer connection|Geen reeferaansluiting
Dry cargo|Droge lading
Refrigerated|Gekoeld
Hazardous cargo|Gevaarlijke lading
Empty equipment|Lege containers
Synthetic infrastructure · not real LA positions|Gesimuleerde infrastructuur · geen echte terminalposities
Synthetic infrastructure · not real terminal positions|Gesimuleerde infrastructuur · geen echte terminalposities
Finite reefer infrastructure|Beperkte reeferinfrastructuur
modeled plugs ·|gesimuleerde aansluitingen ·
blocks equipped|blokken uitgerust
connections occupied|aansluitingen bezet
Only rows 1–2 have modeled reefer connections; other rows have none. Free capacity is not a transfer approval. Availability, compatibility, safe access and authorization must be verified.|Alleen rijen 1–2 hebben gesimuleerde reeferaansluitingen. Vrije capaciteit is geen toestemming voor verplaatsing. Controleer beschikbaarheid, compatibiliteit, veilige toegang en toestemming.
No reefer plug infrastructure in this block|Geen reeferaansluitingen in dit blok
A general yard slot is not a powered reefer position. Powered storage would need to be assessed in an equipped block.|Een gewone terreinpositie heeft geen reeferstroom. Beoordeel een geschikte positie in een uitgerust blok.
Selected stack|Geselecteerde stapel
Selected stack contents|Inhoud geselecteerde stapel
Selected container outside this block|Geselecteerde container buiten dit blok
Stack tiers, highest to lowest|Stapellagen, van hoog naar laag
TIER|LAAG
TOP|BOVEN
GROUND|ONDER
GROUND LEVEL|GRONDNIVEAU
tier slots occupied|laagposities bezet
Container details|Containerdetails
View selected container details|Geselecteerde container bekijken
Empty slot|Lege positie
No container at this tier|Geen container op deze laag
Vacant · modeled position|Vrij · gesimuleerde positie
is in block|staat in blok
You are still viewing|U bekijkt nog steeds
. This selection does not change the page or this block’s metrics.|. Deze selectie verandert de pagina en blokmetingen niet.
Container inventory|Containervoorraad
Pending action queue|Openstaande actiewachtrij
Export view|Weergave exporteren
Search demo containers|Democontainers zoeken
Search container, carrier or block…|Zoek container, rederij of blok…
Filter yard block|Terreinblok filteren
All blocks|Alle blokken
Exceptions only|Alleen afwijkingen
Clear filters|Filters wissen
Clear search|Zoekopdracht wissen
Clear query filter|Voorraadfilter wissen
Current inventory query:|Actuele voorraadzoekopdracht:
Any number|Elk nummer
All carriers|Alle rederijen
· includes normal containers|· inclusief containers zonder afwijkingen
Showing pending “|Openstaande acties voor “
” actions. One row per action.|”. Eén rij per actie.
Show all quadrants|Alle kwadranten tonen
Container / cargo|Container / lading
Location|Locatie
Exception|Afwijking
Suggested next action|Voorgestelde volgende actie
Review|Beoordeling
Needs review|Te beoordelen
Accepted|Geaccepteerd
Dismissed|Afgewezen
Normal inventory|Normale voorraad
Routine|Regulier
independent flag(s)|afzonderlijke afwijking(en)
No pending actions in this view|Geen openstaande acties in deze weergave
No matching containers|Geen overeenkomende containers
Adjust the quadrant or filters, or review recorded decisions in History.|Pas het kwadrant of de filters aan, of bekijk eerdere beoordelingen onder Geschiedenis.
Change the search, block or exception filter.|Pas de zoekopdracht of het blok- of afwijkingsfilter aan.
Show inventory|Voorraad tonen
Previous|Vorige
Next|Volgende
actions|acties
records|records
Saved in this browser|Opgeslagen in deze browser
Suggestion accepted|Voorstel geaccepteerd
Suggestion dismissed|Voorstel afgewezen
· Previous scenario|· Eerder scenario
No decisions recorded yet|Nog geen beoordelingen vastgelegd
Inspect a flagged container and accept or dismiss a suggestion.|Bekijk een container met een afwijking en accepteer of wijs het voorstel af.
Go to yard overview|Naar terreinoverzicht
Decision support only. No equipment, gate or external message is controlled.|Alleen beslisondersteuning. Geen aansturing van materieel, poorten of externe berichten.
Regenerate demo data|Nieuwe demodata genereren
Selected container decision|Beslissing geselecteerde container
CONTAINER DETAIL|CONTAINERDETAIL
DEMO|DEMO
Gated out · removed from current stock|Uitgereden · uit actuele voorraad verwijderd
Last position shown below. One modeled tier slot has been freed; the audit record is retained.|Hieronder staat de laatste positie. Eén gesimuleerde laagpositie is vrijgekomen; de historie blijft bewaard.
Open post-action records|Opvolgingshistorie openen
What needs attention|Wat aandacht nodig heeft
No flagged exception|Geen afwijking gemeld
Recorded customs hold|Geregistreerde douaneblokkade
Declaration mismatch|Afwijkende aangifte
Temperature excursion|Temperatuurafwijking
Sensor report missing|Sensormelding ontbreekt
Reefer circuit R1 interrupted|Reefercircuit R1 onderbroken
Outbound access constrained|Uitrit beperkt
Customs|Douane
Temperature|Temperatuur
Power loss|Stroomuitval
Access|Toegang
Demo rules|Demoregels
Coordinate with|Afstemmen met
Terminal coordinator|Terminalcoördinator
Broker / customs liaison|Douanevertegenwoordiger
Carrier / inspection coordinator|Rederij / inspectiecoördinator
Reefer maintenance|Reeferonderhoud
Yard supervisor + reefer maintenance|Terreinleiding + reeferonderhoud
Gate / trucking coordinator|Poort- / transportcoördinator
Review pickup readiness|Controleer gereedheid voor afhaling
Request hold-status follow-up|Vraag de status van de blokkade op
Request weight and identity verification|Laat gewicht en identiteit controleren
Request a reefer condition check|Laat de reeferconditie controleren
Request telemetry / unit verification|Laat telemetrie en unit controleren
Assess power recovery / safe transfer|Beoordeel stroomherstel / veilige verplaatsing
Review pickup sequence and appointments|Beoordeel afhaalvolgorde en afspraken
Verify line release, customs clearance, appointment and receiving arrangements.|Controleer rederijvrijgave, douanevrijgave, afspraak en ontvangstafspraken.
The responsible authority must confirm clearance. A recommendation does not remove a hold.|De bevoegde instantie moet vrijgave bevestigen. Een advies heft geen blokkade op.
Confirm container identity, weighing basis and tare. Arrange an authorized reweigh if required.|Controleer containernummer, weegbasis en eigen gewicht. Regel zo nodig een bevoegde herweging.
Verify the reading, power supply and cargo requirements with authorized staff.|Controleer meetwaarde, stroomvoorziening en ladingeisen met bevoegd personeel.
A missing report is not proof of cargo damage. Confirm the actual unit condition.|Een ontbrekende melding bewijst geen ladingschade. Controleer de werkelijke conditie van de unit.
Verify live capacity, compatibility, safe access and on-site approval before moving. Unoccupied plugs are not an allocation. Independent holds remain active.|Controleer actuele capaciteit, compatibiliteit, veilige toegang en lokale toestemming vóór verplaatsing. Vrije aansluitingen zijn niet toegewezen. Afzonderlijke blokkades blijven gelden.
Confirm which access is affected and coordinate a valid pickup window. Do not assume all gates are closed.|Controleer welke toegang is beperkt en stem een geldig afhaalmoment af. Ga niet uit van sluiting van alle poorten.
Importance considers consequence and prerequisites; urgency considers active disruption and synthetic response windows. Classifications are demo policy, not an industry SOP. Legal and safety constraints apply in every quadrant.|Belang volgt uit gevolgen en voorwaarden; urgentie uit de actuele verstoring en gesimuleerde reactietijden. Dit zijn demoregels, geen industriële werkinstructies. Wettelijke en veiligheidsvoorwaarden gelden in elk kwadrant.
Action importance and urgency matrix|Actiematrix voor belang en urgentie
Action priorities|Actieprioriteiten
Scenario-aware|Scenariogestuurd
Each action is classified independently. The same container can need urgent care and planned clearance follow-up.|Elke actie wordt apart beoordeeld. Dezelfde container kan urgente zorg én geplande vrijgaveopvolging nodig hebben.
↑ IMPORTANCE|↑ BELANG
URGENCY ←|URGENTIE ←
Do first|Direct aanpakken
Plan & unblock|Plannen en deblokkeren
Coordinate promptly|Snel afstemmen
Monitor|Bewaken
Important + urgent|Belangrijk + urgent
Important · less urgent|Belangrijk · minder urgent
Less important · urgent|Minder belangrijk · urgent
Less important · less urgent|Minder belangrijk · minder urgent
Urgent human coordination|Directe menselijke afstemming
Assign an owner and next review|Wijs een eigenaar en herbeoordeling toe
Route to the responsible team|Zet door naar het verantwoordelijke team
Batch follow-up and reassess|Bundel opvolging en herbeoordeel
No pending actions in this quadrant for the current filters.|Geen openstaande acties in dit kwadrant met deze filters.
Clear quadrant filter|Kwadrantfilter wissen
Demo policy: importance ≥70, urgency ≥60. “Less important” means lower operational impact of this follow-up, never permission to skip a control. Accepted/dismissed suggestions leave this pending matrix; physical flags remain.|Demoregels: belang ≥70, urgentie ≥60. Minder belangrijk betekent lagere operationele impact, nooit toestemming om controles over te slaan. Beoordeelde voorstellen verlaten deze matrix; afwijkingen blijven actief.
Importance|Belang
Urgency|Urgentie
New action triggered by this scenario|Nieuwe actie door dit scenario
Open action matrix|Actiematrix openen
Evidence snapshot|Overzicht bewijsmateriaal
active flag|actieve melding
active flags|actieve meldingen
No active flags|Geen actieve meldingen
Weight mismatch|Gewicht wijkt af
Temperature deviation|Temperatuurafwijking
Declared|Aangegeven
Measured|Gemeten
Observed|Gemeten
Setpoint|Instelwaarde
Difference from declaration|Verschil met aangifte
Difference from setpoint|Verschil met instelwaarde
Release blocked|Vrijgave geblokkeerd
Report missing|Melding ontbreekt
Power interrupted|Voeding onderbroken
Access restricted|Toegang beperkt
Source|Bron
Fixture + verified demo updates|Demodata + geverifieerde updates
Declared / measured|Aangegeven / gemeten
Customs hold|Douaneblokkade
Recorded · remains active|Vastgelegd · blijft actief
Verified cleared · demo|Vrijgave geverifieerd · demo
None in fixture|Geen in demodata
Observed / setpoint|Gemeten / instelwaarde
Last report|Laatste melding
min ago|min geleden
Assigned reefer plug|Toegewezen reeferaansluiting
None · no connection assigned|Geen · geen aansluiting toegewezen
Reefer supply|Reefervoeding
Handling window|Afhandelvenster
min · synthetic|min · gesimuleerd
Scenario|Scenario
not-connected|niet aangesloten
energized|onder spanning
interrupted|onderbroken
verified-unit-backup|noodvoeding unit geverifieerd
Operator review|Beoordeling door medewerker
Recorded locally. Cargo status is unchanged.|Lokaal vastgelegd. Ladingstatus blijft ongewijzigd.
Follow the work through completion and result verification. Acceptance alone leaves the exception active.|Volg de werkzaamheden tot afronding en resultaatverificatie. Alleen accepteren laat de afwijking actief.
Open post-action queue|Opvolgingswachtrij openen
Normal · in current inventory. The container continues to occupy its slot.|Normaal · in actuele voorraad. De container blijft zijn positie bezetten.
Review note|Beoordelingsnotitie
Optional|Optioneel
Add a handoff note or missing condition…|Voeg een overdrachtsnotitie of ontbrekende voorwaarde toe…
Dismiss|Afwijzen
Accept suggestion|Voorstel accepteren
Acceptance queues work; verification resolves it.|Accepteren maakt een taak; verificatie lost de afwijking op.
Inventory disposition|Voorraadafhandeling
Gate-out is blocked until active exceptions and accepted work are resolved.|Uitrit geblokkeerd totdat actieve afwijkingen en geaccepteerde taken zijn afgehandeld.
This container stays in stock until both release permissions and physical gate-out are confirmed.|Deze container blijft op voorraad totdat vrijgavetoestemming en fysieke uitrit zijn bevestigd.
Release & gate-out|Vrijgave en uitrit
Dismiss notice|Melding sluiten
Containers in this block|Containers in dit blok
Reefer connections|Reeferaansluitingen
None|Geen
No reefer plug infrastructure|Geen reeferaansluitingen
Import storage|Importopslag
Export staging|Exportbuffer
Reefer storage|Reeferopslag
DG-designated storage|Opslag gevaarlijke stoffen
Reefer reserve / buffer|Reeferreserve / buffer
Inspection staging|Inspectiebuffer
Import pickup staging|Importafhaalbuffer
Empty pickup staging|Afhaalbuffer lege containers
Vessel discharge → pickup|Lossen schip → afhaling
Gate receipt → vessel load|Ontvangst poort → laden schip
Powered cargo care|Ladingzorg met stroomvoorziening
Empty return / reuse|Lege retour / hergebruik
Compatibility review required|Compatibiliteitscontrole vereist
Capacity assessment · not reserved|Capaciteitsbeoordeling · niet gereserveerd
Authorized verification|Bevoegde verificatie
Outbound gate handoff|Overdracht bij uitrit
IMPORT|IMPORT
EXPORT|EXPORT
REEFER|REEFER
EMPTY|LEEG
DG AREA|GEVAARLIJKE STOFFEN
REEFER BUFFER|REEFERBUFFER
INSPECTION|INSPECTIE
PICKUP|AFHALING
EMPTY PICKUP|AFHALING LEEG
SUPPLY INTERRUPTED|VOEDING ONDERBROKEN
ENERGIZED|ONDER SPANNING
ACCESS|TOEGANG
OFF|UIT
NO REEFER PLUGS|GEEN REEFERAANSLUITINGEN
slots|posities
flagged|afwijkingen
supply interrupted|voeding onderbroken
Active cold-chain interruption: supervisor and maintenance review now.|Actieve koelketenonderbreking: terreinleiding en onderhoud nu laten beoordelen.
Observed excursion requires prompt verification; damage is not inferred.|De gemeten afwijking vereist snelle verificatie; schade wordt niet verondersteld.
Identity / weight evidence must be reconciled before dependent handling.|Stem identiteit en gewichtsgegevens af vóór afhankelijke afhandeling.
Authorized clearance is a hard prerequisite; this action is follow-up, not release.|Bevoegde vrijgave is een harde voorwaarde; deze actie betreft opvolging, geen vrijgave.
Telemetry follow-up only; missing data does not establish loss of power.|Alleen telemetrieopvolging; ontbrekende data bewijst geen stroomuitval.
Scenario circuit outage raises verification impact and urgency.|Circuituitval verhoogt het belang en de urgentie van verificatie.
Affected outbound block needs prompt coordination to contain queue spillback.|Stem het getroffen uitritblok snel af om terugslag van wachtrijen te beperken.
Pickup is also blocked by this scenario; plan prerequisite work while access/care is addressed.|Afhaling is ook geblokkeerd; plan voorbereidende taken terwijl toegang of ladingzorg wordt hersteld.
No exception is flagged by this prototype’s fixture policy.|Geen afwijking gemeld volgens de demoregels.
A synthetic customs hold is recorded. Clearance must be confirmed by the responsible authority.|Een gesimuleerde douaneblokkade is vastgelegd. De bevoegde instantie moet vrijgave bevestigen.
This block is affected by the demo outbound access restriction.|Dit blok valt onder de gesimuleerde uitritbeperking.
This container has physically left the simulated yard. It is excluded from current inventory.|Deze container heeft het gesimuleerde terrein verlaten en is uit de actuele voorraad verwijderd.
Active tasks|Actieve taken
Resolved tasks · in yard|Opgeloste taken · op terrein
Confirmed gate-outs|Bevestigde uitritten
Acceptance starts the follow-through.|Acceptatie start de opvolging.
Work completion needs result verification. A normal container remains in inventory; only confirmed physical gate-out releases its occupied tier slot. This is a locally saved simulation.|Voltooiing vereist resultaatverificatie. Een normale container blijft in de voorraad; alleen bevestigde fysieke uitrit maakt de laagpositie vrij. Deze simulatie wordt lokaal opgeslagen.
Active|Actief
Resolved|Opgelost
Gated out|Uitgereden
Search post-action queue|Opvolgingswachtrij doorzoeken
Container, carrier or block…|Container, rederij of blok…
Queued|In wachtrij
In progress|In uitvoering
Verify result|Resultaat verifiëren
Handoff|Overdracht
Work reported|Uitgevoerd werk
Verified evidence|Geverifieerd bewijs
Normal · back in inventory|Normaal · terug in voorraad
The container still occupies its slot. Resolving a task does not imply departure.|De container bezet nog zijn positie. Een opgeloste taak betekent geen vertrek.
Updated|Bijgewerkt
Start work|Werk starten
Report work completed|Werk gereedmelden
Verify & resolve|Verifiëren en oplossen
View in inventory|In voorraad bekijken
Task history ·|Taakgeschiedenis ·
events|gebeurtenissen
· accepted in|· geaccepteerd bij
· last location|· laatste positie
Removed from current inventory · 1 modeled tier slot freed|Uit actuele voorraad verwijderd · 1 gesimuleerde laagpositie vrij
Remaining stack positions are retained; a ground cell becomes empty when its last container leaves.|Overige stapelposities blijven bewaard; een grondpositie is leeg zodra de laatste container vertrekt.
Gate-out evidence|Bewijs van uitrit
Confirmed|Bevestigd
Retained in audit · excluded from yard queries|Bewaard in historie · uitgesloten van voorraadzoekopdrachten
No matching records|Geen overeenkomende records
No active post-action tasks|Geen actieve opvolgingstaken
No verified resolutions yet|Nog geen geverifieerde oplossingen
No confirmed gate-outs yet|Nog geen bevestigde uitritten
Accept a suggestion in Actions or the container detail to start its follow-through.|Accepteer een voorstel onder Acties of in de containerdetails om de opvolging te starten.
Complete work and verify the result to move a task here.|Rond het werk af en verifieer het resultaat om de taak hier te plaatsen.
Release permission and physical exit must both be confirmed.|Vrijgavetoestemming en fysieke uitrit moeten beide zijn bevestigd.
Verify result & resolve|Resultaat verifiëren en oplossen
Describe the completed work. The exception stays active until the result is verified.|Beschrijf het uitgevoerde werk. De afwijking blijft actief totdat het resultaat is geverifieerd.
Work summary|Werkverslag
Evidence reference / verification note|Bewijsreferentie / verificatienotitie
What was done, and by whom?|Wat is gedaan en door wie?
For demo use, enter a clearly labeled simulated verification reference.|Voer een duidelijk als gesimuleerd gemarkeerde verificatiereferentie in.
I have verified the stated result for this container in the demo.|Ik heb het genoemde resultaat voor deze container in de demo geverifieerd.
This updates simulated state only. Independent exceptions remain active; no equipment or external authority is controlled.|Dit wijzigt alleen de simulatie. Afzonderlijke afwijkingen blijven actief; geen aansturing van materieel of bevoegde instanties.
Send for verification|Ter verificatie aanbieden
Confirm resolved|Oplossing bevestigen
Confirm release & physical gate-out|Vrijgave en fysieke uitrit bevestigen
Release clearance alone leaves the container in inventory. Confirm its physical exit to remove it from the yard and free one modeled tier slot.|Vrijgave alleen laat de container in voorraad. Bevestig de fysieke uitrit om deze te verwijderen en één gesimuleerde laagpositie vrij te maken.
Gate-out is blocked|Uitrit geblokkeerd
Required carrier/customs permissions and pickup conditions are confirmed for this demo.|De vereiste rederij- en douanetoestemmingen en afhaalvoorwaarden zijn bevestigd voor deze demo.
The container has physically gated out in the simulation.|De container is fysiek uitgereden in de simulatie.
Gate-out reference / confirmation note|Uitritreferentie / bevestigingsnotitie
e.g. SIMULATED gate-out ticket and operator confirmation|bijv. GESIMULEERD uitritbewijs en bevestiging medewerker
The record is removed from active stock and queries. Its last position and evidence remain in the Gated out audit tab.|Het record verdwijnt uit de actuele voorraad en zoekresultaten. De laatste positie en het bewijs blijven onder Uitgereden bewaard.
Confirm gate-out|Uitrit bevestigen
Confirm permission and actual gate-out|Toestemming en werkelijke uitrit bevestigen
The responsible authority’s clearance has been confirmed for this container.|De vrijgave door de bevoegde instantie is bevestigd voor deze container.
Container identity and weighing basis were checked; the verified weight now agrees with the corrected record.|Identiteit en weegbasis zijn gecontroleerd; het geverifieerde gewicht klopt met het gecorrigeerde record.
A verified reading is back at the required setpoint for this demo container.|Een geverifieerde meting is terug op de vereiste instelwaarde voor deze democontainer.
Fresh telemetry and the actual unit condition have been verified.|Actuele telemetrie en de werkelijke unitconditie zijn geverifieerd.
Backup power for this specific unit has been verified. This does not restore the entire R1 circuit.|Noodvoeding voor deze unit is geverifieerd. Dit herstelt niet het volledige R1-circuit.
An authorized, usable alternate pickup access has been confirmed for this specific container.|Een toegestane en bruikbare alternatieve afhaaltoegang is bevestigd voor deze container.
Work started|Werk gestart
A valid event time is required.|Een geldig tijdstip is vereist.
Container not found in this demo run.|Container niet gevonden in deze demonstratie.
This container has already gated out. No second slot can be released.|Deze container is al uitgereden. Er kan geen tweede positie vrijkomen.
This exception is no longer active. Refresh the selected action.|Deze afwijking is niet meer actief. Vernieuw de geselecteerde actie.
This action is already in the post-action workflow.|Deze actie staat al in de opvolgingswachtrij.
Resolve every active exception and finish accepted work before release and gate-out.|Los alle actieve afwijkingen op en rond geaccepteerde taken af vóór vrijgave en uitrit.
Confirm both release permissions and physical gate-out. Clearance alone does not free a slot.|Bevestig vrijgavetoestemming en fysieke uitrit. Vrijgave alleen maakt geen positie vrij.
Add a gate-out reference or confirmation note.|Voeg een uitritreferentie of bevestigingsnotitie toe.
Post-action task not found.|Opvolgingstaak niet gevonden.
This update predates the latest task event. Refresh and try again.|Deze update is ouder dan de laatste taakwijziging. Vernieuw en probeer opnieuw.
This container has already left the yard.|Deze container heeft het terrein al verlaten.
Only queued tasks can be started.|Alleen taken in de wachtrij kunnen worden gestart.
Start the work before reporting completion.|Start het werk vóór gereedmelding.
Add a short work-completion summary.|Voeg een kort werkverslag toe.
Only completed work awaiting verification can be resolved.|Alleen gereedgemeld werk dat op verificatie wacht kan worden opgelost.
Confirm the result and add its evidence reference before resolving.|Bevestig het resultaat en voeg een bewijsreferentie toe vóór afsluiting.
Gate-out confirmed. Current inventory and the empty slot are updated.|Uitrit bevestigd. Actuele voorraad en vrije positie zijn bijgewerkt.
Result verified. Independent exceptions remain active; normal stock stays in inventory.|Resultaat geverifieerd. Afzonderlijke afwijkingen blijven actief; normale containers blijven in voorraad.
Added to Post-action. The exception stays active until verification.|Toegevoegd aan Opvolging. De afwijking blijft actief tot verificatie.
Suggestion dismissed. Inventory is unchanged.|Voorstel afgewezen. Voorraad blijft ongewijzigd.
Post-action task updated.|Opvolgingstaak bijgewerkt.
New synthetic dataset generated. Saved workflow and departures cleared.|Nieuwe demodata gegenereerd. Opgeslagen taken en uitritten gewist.
An interactive design study for terminal decision support.|Een interactieve ontwerpstudie voor beslisondersteuning op terminals.
Every container, position, metric, alert and scenario is generated locally. Blocks are a schematic, not a map of a real Los Angeles terminal.|Alle containers, posities, metingen, meldingen en scenario’s zijn lokaal gegenereerd. De blokken vormen een schema, geen kaart van een echte Rotterdamse terminal.
Click a container to inspect it without changing pages. Click empty block background to open a larger block-only page. Use Back or Escape to return. The Query panel searches current inventory by number and carrier independently of exception filters. Company represents carrier here, not cargo owner.|Klik op een container om deze op dezelfde pagina te bekijken. Klik op lege blokruimte om het blok uit te vergroten. Ga terug met Terug of Escape. Zoeken gebruikt containernummer en rederij, onafhankelijk van afwijkingsfilters. Bedrijf betekent hier rederij, niet ladingeigenaar.
Explore blocks, zoom and drag the empty space between blocks, filter containers, switch disruption scenarios, and review a suggestion. Acceptance adds a Post-action task. Start work, report completion and verify evidence before resolving its exception. Independent flags remain active. Only confirmed physical gate-out removes a container from current stock and frees its tier slot.|Verken blokken, zoom en verschuif de lege ruimte ertussen, filter containers en wissel scenario’s. Accepteren maakt een opvolgingstaak. Start het werk, meld het gereed en verifieer het bewijs. Afzonderlijke afwijkingen blijven actief. Alleen bevestigde fysieke uitrit verwijdert een container en maakt een positie vrij.
There are no backend, Terminal49, Claude or equipment calls. Synthetic review history, task progress and gate-outs are saved in this browser and survive reload. Regenerating data clears them. This preview has no server database or multi-user synchronization.|Geen verbindingen met backend, Terminal49, Claude of materieel. Gesimuleerde beoordelingen, taken en uitritten worden per haven in deze browser bewaard, ook na herladen. Nieuwe demodata wist deze gegevens. Deze demo heeft geen serverdatabase of synchronisatie tussen gebruikers.
Only designated rows have finite reefer plugs. Circuit R1 affects B01/B02; R2 in C01 stays energized. Zone purposes and capacities are invented. In Actions, the four-quadrant matrix updates per scenario, with independent importance / urgency and visible reasons.|Alleen aangewezen rijen hebben reeferaansluitingen. Circuit R1 betreft B01/B02; R2 in C01 blijft onder spanning. Blokfuncties en capaciteit zijn verzonnen. De actiematrix verandert per scenario, met afzonderlijk belang en urgentie en zichtbare redenen.
Choose routine, power outage, congestion or combined conditions to see the same cohort respond. This prototype is separate from the existing operations console.|Kies reguliere operatie, stroomuitval, congestie of een combinatie. Deze demo staat los van de bestaande operationele console.
Explore the workspace|Werkruimte verkennen
GATE TRIAGE WORKSPACE|GATE TRIAGE WERKRUIMTE
Close dialog|Dialoog sluiten
Click a stack to preview its tiers, then choose a container. Empty block background opens a block-only workspace with the map on the left and container details on the right. Back or Escape returns to the previous view. Query searches current inventory by number and carrier.|Klik op een stapel voor een voorvertoning van de lagen en kies dan een container. Lege blokruimte opent een werkruimte met links de kaart en rechts de containerdetails. Terug of Escape herstelt de vorige weergave. Zoeken gebruikt containernummer en rederij.
No reefer connections|Geen reeferaansluitingen
demo exception flags|gesimuleerde afwijkingen
modeled reefer connections|gesimuleerde reeferaansluitingen
cargo types|ladingtypen
Container|Container
Cargo|Lading
Carrier|Rederij
Carrier name|Rederijnaam
Yard status|Terreinstatus
Suggested action|Voorgestelde actie
Quadrant|Kwadrant
in-yard|op terrein
departed|vertrokken
`.trim().split('\n').map(line => { const at = line.indexOf('|'); return [line.slice(0, at), line.slice(at + 1)]; }));

// Parameterized messages use explicit whole-message templates, not word replacement.
const templates: [string, string][] = [
  ['{n} temperature / power alerts across tiers', '{n} temperatuur- / stroommeldingen in de stapel'],
  ['{n} perishable containers delayed · queue priority raised', '{n} bederfelijke containers vertraagd · hogere wachtrijprioriteit'],
  ['{n} high-priority containers', '{n} containers met hoge prioriteit'],
  ['{n} do first', '{n} hoogste prioriteit'],
  ['Demo delay {delay} min versus pickup window {window} min; remaining margin {margin} min.', 'Demovertraging {delay} min tegenover ophaalvenster {window} min; resterende marge {margin} min.'],
  ['{cargo} depends on pickup route {route}, with {delay} min of demo delay. Current location: {block}.', '{cargo} is afhankelijk van ophaalroute {route}, met {delay} min demovertraging. Huidige locatie: {block}.'],

  ['Block {id}', 'Blok {id}'], ['{id} · stack layout', '{id} · stapelindeling'],
  ['{n} synthetic blocks', '{n} gesimuleerde blokken'], ['{a} / {b} modeled slots', '{a} / {b} gesimuleerde posities'],
  ['{n} temperature / power flags', '{n} temperatuur- / stroommeldingen'], ['{n} confirmed gate-outs · fixed capacity', '{n} bevestigde uitritten · vaste capaciteit'],
  ['{n} pending actions', '{n} openstaande acties'], ['{name} · queue', '{name} · wachtrij'],
  ['{id} only · current yard inventory', 'Alleen {id} · actuele terreinvoorraad'],
  ['{id} · {n} unoccupied energized', '{id} · {n} vrije aansluitingen onder spanning'], ['{n} unoccupied energized plugs', '{n} vrije aansluitingen onder spanning'],
  ['{n} units without verified backup · 0 energized free plugs', '{n} units zonder geverifieerde noodvoeding · 0 vrije aansluitingen onder spanning'],
  ['{id} · supply interrupted', '{id} · voeding onderbroken'],
  ['{id} · SUPPLY INTERRUPTED', '{id} · VOEDING ONDERBROKEN'], ['{id} · ENERGIZED', '{id} · ONDER SPANNING'],
  ['{n} modeled plugs · rows 1–2 only · {id}', '{n} gesimuleerde aansluitingen · alleen rijen 1–2 · {id}'],
  ['{n} plugs occupied · rows 1–2 · {id}', '{n} aansluitingen bezet · rijen 1–2 · {id}'],
  ['Inspect {issue} action for {id}', 'Bekijk actie {issue} voor {id}'],
  ['Equipped position · {circuit} · {n} modeled plug slots', 'Uitgeruste positie · {circuit} · {n} gesimuleerde aansluitingen'],
  ['Inspect power in {id}', 'Stroomvoorziening in {id} bekijken'],
  ['{kind} · {id} OFF', '{kind} · {id} UIT'], ['{kind} · ACCESS', '{kind} · TOEGANG'],
  ['Locate {id} in block {block}', 'Zoek {id} in blok {block}'], ['Block {id} metrics', 'Metingen blok {id}'],
  ['Open block {id} from empty background, {n} containers, {m} flagged', 'Open blok {id} via lege ruimte, {n} containers, {m} afwijkingen'],
  ['Select stack {id} bay {bay}, row {row}, {n} containers', 'Selecteer stapel {id} vak {bay}, rij {row}, {n} containers'],
  ['Select tier {tier}, {id}', 'Selecteer laag {tier}, {id}'], ['Tier {tier}, empty slot', 'Laag {tier}, lege positie'],
  ['Block {id} enlarged stack layout', 'Uitvergrote stapelindeling blok {id}'], ['Block {id}, enlarged layout.', 'Blok {id}, uitvergrote indeling.'],
  ['Synthetic yard layout with {n} blocks.', 'Gesimuleerd terrein met {n} blokken.'],
  ['Routine: {before} → Now: {after}', 'Regulier: {before} → Nu: {after}'],
  ['{n} min without a report; {kind} demo cargo.', '{n} min zonder melding; {kind} demolading.'],
  ['Synthetic next handling window: {n} min (not an operational deadline).', 'Gesimuleerd volgend afhandelvenster: {n} min (geen operationele deadline).'],
  ['Assigned plug {id} is on interrupted {circuit}.', 'Toegewezen aansluiting {id} zit op onderbroken {circuit}.'],
  ['Assigned plug {id} is on interrupted circuit {circuit}. Other circuits and nonconnected cargo are not assumed affected.', 'Toegewezen aansluiting {id} zit op onderbroken circuit {circuit}. Andere circuits en niet-aangesloten lading worden niet als getroffen beschouwd.'],
  ['{temp}°C observed against a {setpoint}°C setpoint in the fixture.', '{temp}°C gemeten bij een instelwaarde van {setpoint}°C in de demodata.'],
  ['Declared {a} kg vs {b} kg in the fixture.', 'Aangegeven {a} kg tegenover {b} kg in de demodata.'],
  ['No synthetic sensor report for {n} minutes.', 'Geen gesimuleerde sensormelding gedurende {n} minuten.'],
  ['{n} independent exceptions still active', '{n} afzonderlijke afwijkingen nog actief'], ['{n} independent exception still active', '{n} afzonderlijke afwijking nog actief'],
  ['{state} · in Post-action', '{state} · in Opvolging'], ['Show {n} actions in queue', 'Toon {n} acties in wachtrij'],
  ['Bay {bay} · row {row} · tier {tier}', 'Vak {bay} · rij {row} · laag {tier}'],
  ['{block} · bay {bay} / row {row} / tier {tier}', '{block} · vak {bay} / rij {row} / laag {tier}'],
  ['Reefer connection {id} is no longer occupied. Circuit state is evaluated separately.', 'Reeferaansluiting {id} is niet meer bezet. Circuitstatus wordt apart beoordeeld.'],
  ['Exported {n} synthetic {kind} from this view.', '{n} gesimuleerde {kind} geëxporteerd uit deze weergave.'],
  ['{id} · {issue}', '{id} · {issue}'],
  ['{issue}: {state}', '{issue}: {state}'],
];
const escape = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const patterns = templates.map(([source, target]) => {
  const keys: string[] = []; let cursor = 0, pattern = '';
  for (const match of source.matchAll(/\{(\w+)\}/g)) { pattern += escape(source.slice(cursor, match.index)) + '(.+?)'; keys.push(match[1]); cursor = match.index! + match[0].length; }
  return { regex: new RegExp('^' + pattern + escape(source.slice(cursor)) + '$'), target, keys };
});
export function translateYard<T>(value: T, port: DemoPort): T {
  if (port !== 'rotterdam' || typeof value !== 'string') return value;
  const key = value.trim(), exact = dutch[key];
  if (exact) return value.replace(key, exact) as T;
  for (const { regex, target, keys } of patterns) {
    const match = key.match(regex); if (!match) continue;
    const translated = target.replace(/\{(\w+)\}/g, (_, name: string) => {
      const part = match[keys.indexOf(name) + 1]; return dutch[part] || (part === 'higher-sensitivity' ? 'extra gevoelige' : part === 'standard' ? 'standaard' : part);
    });
    return value.replace(key, translated) as T;
  }
  return value;
}
export const formatYardNumber = (n: number, port: DemoPort) => new Intl.NumberFormat(PORTS[port].locale).format(n);
export const formatYardTime = (at: string, port: DemoPort) => new Intl.DateTimeFormat(PORTS[port].locale, { timeZone: PORTS[port].timeZone, dateStyle: 'short', timeStyle: 'short' }).format(new Date(at));
