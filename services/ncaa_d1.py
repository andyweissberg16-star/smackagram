"""
Every NCAA Division I school, with the conference it plays each sport in.

Built from NCAA.com's own standings pages (men's basketball, FBS football,
FCS football) plus a verified pass over Division I baseball membership.

Why this file exists: CHAT_LEAGUES only ever held the four power football
conferences and a hand-picked slice of basketball, so searching "UNLV" - or
Boise State, Notre Dame football, Navy, Memphis, and about a hundred others -
came back empty.

The data is a single text block rather than nested dicts because it is
transcribed by hand into a terminal, and one pipe-separated row per school
survives that trip far better than 1,500 lines of Python punctuation. It is
parsed once at import into the dicts below.

Row format:
    key | school shown | mascot | football conf | FBS/FCS | m. hoops conf | baseball conf

An empty field means the school does not play that sport. Conferences differ
by sport and that is not a mistake: Hawaii plays baseball in the Big West,
UMass in the MAC, Notre Dame football is independent while everything else
is ACC.
"""

_SCHOOL_ROWS = """
A&M-Corpus Christi|Texas A&M-Corpus Christi|Islanders|||Southland|Southland
Abilene Christian|Abilene Christian|Wildcats|United Athletic|FCS|WAC|WAC
Air Force|Air Force|Falcons|Mountain West|FBS|Mountain West|Mountain West
Akron|Akron|Zips|MAC|FBS|MAC|MAC
Alabama|Alabama|Crimson Tide|SEC|FBS|SEC|SEC
Alabama A&M|Alabama A&M|Bulldogs|SWAC|FCS|SWAC|SWAC
Alabama St.|Alabama State|Hornets|SWAC|FCS|SWAC|SWAC
Alcorn|Alcorn State|Braves|SWAC|FCS|SWAC|SWAC
American|American|Eagles|||Patriot|
App State|Appalachian State|Mountaineers|Sun Belt|FBS|Sun Belt|Sun Belt
Arizona|Arizona|Wildcats|Big 12|FBS|Big 12|Big 12
Arizona St.|Arizona State|Sun Devils|Big 12|FBS|Big 12|Big 12
Ark.-Pine Bluff|Arkansas-Pine Bluff|Golden Lions|SWAC|FCS|SWAC|SWAC
Arkansas|Arkansas|Razorbacks|SEC|FBS|SEC|SEC
Arkansas St.|Arkansas State|Red Wolves|Sun Belt|FBS|Sun Belt|Sun Belt
Army West Point|Army|Black Knights|American|FBS|Patriot|Patriot
Auburn|Auburn|Tigers|SEC|FBS|SEC|SEC
Austin Peay|Austin Peay|Governors|United Athletic|FCS|ASUN|ASUN
BYU|BYU|Cougars|Big 12|FBS|Big 12|Big 12
Ball St.|Ball State|Cardinals|MAC|FBS|MAC|MAC
Baylor|Baylor|Bears|Big 12|FBS|Big 12|Big 12
Bellarmine|Bellarmine|Knights|||ASUN|ASUN
Belmont|Belmont|Bruins|||MVC|MVC
Bethune-Cookman|Bethune-Cookman|Wildcats|SWAC|FCS|SWAC|SWAC
Binghamton|Binghamton|Bearcats|||America East|America East
Boise St.|Boise State|Broncos|Mountain West|FBS|Mountain West|
Boston College|Boston College|Eagles|ACC|FBS|ACC|ACC
Boston U.|Boston University|Terriers|||Patriot|
Bowling Green|Bowling Green|Falcons|MAC|FBS|MAC|MAC
Bradley|Bradley|Braves|||MVC|MVC
Brown|Brown|Bears|Ivy League|FCS|Ivy League|Ivy League
Bryant|Bryant|Bulldogs|CAA|FCS|America East|America East
Bucknell|Bucknell|Bison|Patriot|FCS|Patriot|Patriot
Buffalo|Buffalo|Bulls|MAC|FBS|MAC|
Butler|Butler|Bulldogs|Pioneer|FCS|Big East|Big East
CSU Bakersfield|Cal State Bakersfield|Roadrunners|||Big West|Big West
CSUN|Cal State Northridge|Matadors|||Big West|Big West
Cal Poly|Cal Poly|Mustangs|Big Sky|FCS|Big West|Big West
Cal St. Fullerton|Cal State Fullerton|Titans|||Big West|Big West
California|California|Golden Bears|ACC|FBS|ACC|ACC
California Baptist|California Baptist|Lancers|||WAC|WAC
Campbell|Campbell|Fighting Camels|CAA|FCS|CAA|CAA
Canisius|Canisius|Golden Griffins|||MAAC|MAAC
Central Ark.|Central Arkansas|Bears|United Athletic|FCS|ASUN|ASUN
Central Conn. St.|Central Connecticut|Blue Devils|NEC|FCS|NEC|NEC
Central Mich.|Central Michigan|Chippewas|MAC|FBS|MAC|MAC
Charleston So.|Charleston Southern|Buccaneers|Big South-OVC|FCS|Big South|Big South
Charlotte|Charlotte|49ers|American|FBS|American|American
Chattanooga|Chattanooga|Mocs|SoCon|FCS|SoCon|
Chicago St.|Chicago State|Cougars|||NEC|
Cincinnati|Cincinnati|Bearcats|Big 12|FBS|Big 12|Big 12
Clemson|Clemson|Tigers|ACC|FBS|ACC|ACC
Cleveland St.|Cleveland State|Vikings|||Horizon|
Coastal Carolina|Coastal Carolina|Chanticleers|Sun Belt|FBS|Sun Belt|Sun Belt
Col. of Charleston|Charleston|Cougars|||CAA|CAA
Colgate|Colgate|Raiders|Patriot|FCS|Patriot|
Colorado|Colorado|Buffaloes|Big 12|FBS|Big 12|
Colorado St.|Colorado State|Rams|Mountain West|FBS|Mountain West|
Columbia|Columbia|Lions|Ivy League|FCS|Ivy League|Ivy League
Coppin St.|Coppin State|Eagles|||MEAC|NEC
Cornell|Cornell|Big Red|Ivy League|FCS|Ivy League|Ivy League
Creighton|Creighton|Bluejays|||Big East|Big East
Dartmouth|Dartmouth|Big Green|Ivy League|FCS|Ivy League|Ivy League
Davidson|Davidson|Wildcats|Pioneer|FCS|Atlantic 10|Atlantic 10
Dayton|Dayton|Flyers|Pioneer|FCS|Atlantic 10|Atlantic 10
DePaul|DePaul|Blue Demons|||Big East|
Delaware|Delaware|Blue Hens|CUSA|FBS|CUSA|CUSA
Delaware St.|Delaware State|Hornets|MEAC|FCS|MEAC|NEC
Denver|Denver|Pioneers|||Summit League|
Detroit Mercy|Detroit Mercy|Titans|||Horizon|
Drake|Drake|Bulldogs|Pioneer|FCS|MVC|
Drexel|Drexel|Dragons|||CAA|
Duke|Duke|Blue Devils|ACC|FBS|ACC|ACC
Duquesne|Duquesne|Dukes|NEC|FCS|Atlantic 10|
ETSU|ETSU|Buccaneers|SoCon|FCS|SoCon|SoCon
East Carolina|East Carolina|Pirates|American|FBS|American|American
East Texas A&M|East Texas A&M|Lions|Southland|FCS|Southland|
Eastern Ill.|Eastern Illinois|Panthers|Big South-OVC|FCS|OVC|OVC
Eastern Ky.|Eastern Kentucky|Colonels|United Athletic|FCS|ASUN|ASUN
Eastern Mich.|Eastern Michigan|Eagles|MAC|FBS|MAC|MAC
Eastern Wash.|Eastern Washington|Eagles|Big Sky|FCS|Big Sky|
Elon|Elon|Phoenix|CAA|FCS|CAA|CAA
Evansville|Evansville|Purple Aces|||MVC|MVC
FDU|Fairleigh Dickinson|Knights|||NEC|NEC
FGCU|Florida Gulf Coast|Eagles|||ASUN|ASUN
FIU|FIU|Panthers|CUSA|FBS|CUSA|CUSA
Fairfield|Fairfield|Stags|||MAAC|MAAC
Fla. Atlantic|Florida Atlantic|Owls|American|FBS|American|American
Florida|Florida|Gators|SEC|FBS|SEC|SEC
Florida A&M|Florida A&M|Rattlers|SWAC|FCS|SWAC|SWAC
Florida St.|Florida State|Seminoles|ACC|FBS|ACC|ACC
Fordham|Fordham|Rams|Patriot|FCS|Atlantic 10|Atlantic 10
Fresno St.|Fresno State|Bulldogs|Mountain West|FBS|Mountain West|Mountain West
Furman|Furman|Paladins|SoCon|FCS|SoCon|
Ga. Southern|Georgia Southern|Eagles|Sun Belt|FBS|Sun Belt|Sun Belt
Gardner-Webb|Gardner-Webb|Runnin' Bulldogs|Big South-OVC|FCS|Big South|Big South
George Mason|George Mason|Patriots|||Atlantic 10|Atlantic 10
George Washington|George Washington|Revolutionaries|||Atlantic 10|Atlantic 10
Georgetown|Georgetown|Hoyas|Patriot|FCS|Big East|Big East
Georgia|Georgia|Bulldogs|SEC|FBS|SEC|SEC
Georgia St.|Georgia State|Panthers|Sun Belt|FBS|Sun Belt|Sun Belt
Georgia Tech|Georgia Tech|Yellow Jackets|ACC|FBS|ACC|ACC
Gonzaga|Gonzaga|Bulldogs|||WCC|WCC
Grambling|Grambling State|Tigers|SWAC|FCS|SWAC|SWAC
Grand Canyon|Grand Canyon|Antelopes|||Mountain West|Mountain West
Green Bay|Green Bay|Phoenix|||Horizon|
Hampton|Hampton|Pirates|CAA|FCS|CAA|
Harvard|Harvard|Crimson|Ivy League|FCS|Ivy League|Ivy League
Hawaii|Hawaii|Rainbow Warriors|Mountain West|FBS|Big West|Big West
High Point|High Point|Panthers|||Big South|Big South
Hofstra|Hofstra|Pride|||CAA|CAA
Holy Cross|Holy Cross|Crusaders|Patriot|FCS|Patriot|Patriot
Houston|Houston|Cougars|Big 12|FBS|Big 12|Big 12
Houston Christian|Houston Christian|Huskies|Southland|FCS|Southland|Southland
Howard|Howard|Bison|MEAC|FCS|MEAC|
IU Indy|IU Indianapolis|Jaguars|||Horizon|
Idaho|Idaho|Vandals|Big Sky|FCS|Big Sky|
Idaho St.|Idaho State|Bengals|Big Sky|FCS|Big Sky|
Illinois|Illinois|Fighting Illini|Big Ten|FBS|Big Ten|Big Ten
Illinois St.|Illinois State|Redbirds|MVFC|FCS|MVC|MVC
Indiana|Indiana|Hoosiers|Big Ten|FBS|Big Ten|Big Ten
Indiana St.|Indiana State|Sycamores|MVFC|FCS|MVC|MVC
Iona|Iona|Gaels|||MAAC|MAAC
Iowa|Iowa|Hawkeyes|Big Ten|FBS|Big Ten|Big Ten
Iowa St.|Iowa State|Cyclones|Big 12|FBS|Big 12|
Jackson St.|Jackson State|Tigers|SWAC|FCS|SWAC|SWAC
Jacksonville|Jacksonville|Dolphins|||ASUN|ASUN
Jacksonville St.|Jacksonville State|Gamecocks|CUSA|FBS|CUSA|CUSA
James Madison|James Madison|Dukes|Sun Belt|FBS|Sun Belt|Sun Belt
Kansas|Kansas|Jayhawks|Big 12|FBS|Big 12|Big 12
Kansas City|Kansas City|Roos|||Summit League|
Kansas St.|Kansas State|Wildcats|Big 12|FBS|Big 12|Big 12
Kennesaw St.|Kennesaw State|Owls|CUSA|FBS|CUSA|CUSA
Kent St.|Kent State|Golden Flashes|MAC|FBS|MAC|MAC
Kentucky|Kentucky|Wildcats|SEC|FBS|SEC|SEC
LIU|LIU|Sharks|NEC|FCS|NEC|NEC
LMU (CA)|Loyola Marymount|Lions|||WCC|WCC
LSU|LSU|Tigers|SEC|FBS|SEC|SEC
La Salle|La Salle|Explorers|||Atlantic 10|Atlantic 10
Lafayette|Lafayette|Leopards|Patriot|FCS|Patriot|Patriot
Lamar University|Lamar|Cardinals|Southland|FCS|Southland|Southland
Le Moyne|Le Moyne|Dolphins|||NEC|NEC
Lehigh|Lehigh|Mountain Hawks|Patriot|FCS|Patriot|Patriot
Liberty|Liberty|Flames|CUSA|FBS|CUSA|CUSA
Lindenwood|Lindenwood|Lions|Big South-OVC|FCS|OVC|OVC
Lipscomb|Lipscomb|Bisons|||ASUN|ASUN
Little Rock|Little Rock|Trojans|||OVC|OVC
Long Beach St.|Long Beach State|Beach|||Big West|Big West
Longwood|Longwood|Lancers|||Big South|Big South
Louisiana|Louisiana|Ragin' Cajuns|Sun Belt|FBS|Sun Belt|Sun Belt
Louisiana Tech|Louisiana Tech|Bulldogs|CUSA|FBS|CUSA|CUSA
Louisville|Louisville|Cardinals|ACC|FBS|ACC|ACC
Loyola Chicago|Loyola Chicago|Ramblers|||Atlantic 10|
Loyola Maryland|Loyola Maryland|Greyhounds|||Patriot|
Maine|Maine|Black Bears|CAA|FCS|America East|America East
Manhattan|Manhattan|Jaspers|||MAAC|MAAC
Marist|Marist|Red Foxes|Pioneer|FCS|MAAC|MAAC
Marquette|Marquette|Golden Eagles|||Big East|
Marshall|Marshall|Thundering Herd|Sun Belt|FBS|Sun Belt|Sun Belt
Maryland|Maryland|Terrapins|Big Ten|FBS|Big Ten|Big Ten
Massachusetts|UMass|Minutemen|MAC|FBS|MAC|MAC
McNeese|McNeese|Cowboys|Southland|FCS|Southland|Southland
Memphis|Memphis|Tigers|American|FBS|American|American
Mercer|Mercer|Bears|SoCon|FCS|SoCon|SoCon
Mercyhurst|Mercyhurst|Lakers|NEC|FCS|NEC|NEC
Merrimack|Merrimack|Warriors|FCS Independent|FCS|MAAC|MAAC
Miami (FL)|Miami|Hurricanes|ACC|FBS|ACC|ACC
Miami (OH)|Miami (OH)|RedHawks|MAC|FBS|MAC|MAC
Michigan|Michigan|Wolverines|Big Ten|FBS|Big Ten|Big Ten
Michigan St.|Michigan State|Spartans|Big Ten|FBS|Big Ten|Big Ten
Middle Tenn.|Middle Tennessee|Blue Raiders|CUSA|FBS|CUSA|CUSA
Milwaukee|Milwaukee|Panthers|||Horizon|Horizon
Minnesota|Minnesota|Golden Gophers|Big Ten|FBS|Big Ten|Big Ten
Mississippi St.|Mississippi State|Bulldogs|SEC|FBS|SEC|SEC
Mississippi Val.|Mississippi Valley State|Delta Devils|SWAC|FCS|SWAC|SWAC
Missouri|Missouri|Tigers|SEC|FBS|SEC|SEC
Missouri St.|Missouri State|Bears|CUSA|FBS|CUSA|CUSA
Monmouth|Monmouth|Hawks|CAA|FCS|CAA|CAA
Montana|Montana|Grizzlies|Big Sky|FCS|Big Sky|
Montana St.|Montana State|Bobcats|Big Sky|FCS|Big Sky|
Morehead St.|Morehead State|Eagles|Pioneer|FCS|OVC|OVC
Morgan St.|Morgan State|Bears|MEAC|FCS|MEAC|
Mount St. Mary's|Mount St. Mary's|Mountaineers|||MAAC|MAAC
Murray St.|Murray State|Racers|MVFC|FCS|MVC|MVC
N.C. A&T|North Carolina A&T|Aggies|CAA|FCS|CAA|CAA
N.C. Central|North Carolina Central|Eagles|MEAC|FCS|MEAC|
NC State|NC State|Wolfpack|ACC|FBS|ACC|ACC
NIU|Northern Illinois|Huskies|MAC|FBS|MAC|MAC
NJIT|NJIT|Highlanders|||America East|America East
Navy|Navy|Midshipmen|American|FBS|Patriot|Patriot
Nebraska|Nebraska|Cornhuskers|Big Ten|FBS|Big Ten|Big Ten
Nevada|Nevada|Wolf Pack|Mountain West|FBS|Mountain West|Mountain West
New Hampshire|New Hampshire|Wildcats|CAA|FCS|America East|
New Haven|New Haven|Chargers|||NEC|NEC
New Mexico|New Mexico|Lobos|Mountain West|FBS|Mountain West|Mountain West
New Mexico St.|New Mexico State|Aggies|CUSA|FBS|CUSA|CUSA
New Orleans|New Orleans|Privateers|||Southland|Southland
Niagara|Niagara|Purple Eagles|||MAAC|MAAC
Nicholls|Nicholls|Colonels|Southland|FCS|Southland|Southland
Norfolk St.|Norfolk State|Spartans|MEAC|FCS|MEAC|NEC
North Ala.|North Alabama|Lions|United Athletic|FCS|ASUN|ASUN
North Carolina|North Carolina|Tar Heels|ACC|FBS|ACC|ACC
North Dakota|North Dakota|Fighting Hawks|MVFC|FCS|Summit League|
North Dakota St.|North Dakota State|Bison|MVFC|FCS|Summit League|Summit League
North Florida|North Florida|Ospreys|||ASUN|ASUN
North Texas|North Texas|Mean Green|American|FBS|American|
Northeastern|Northeastern|Huskies|||CAA|CAA
Northern Ariz.|Northern Arizona|Lumberjacks|Big Sky|FCS|Big Sky|
Northern Colo.|Northern Colorado|Bears|Big Sky|FCS|Big Sky|Summit League
Northern Ky.|Northern Kentucky|Norse|||Horizon|Horizon
Northwestern|Northwestern|Wildcats|Big Ten|FBS|Big Ten|Big Ten
Northwestern St.|Northwestern State|Demons|Southland|FCS|Southland|Southland
Notre Dame|Notre Dame|Fighting Irish|FBS Independent|FBS|ACC|ACC
Oakland|Oakland|Golden Grizzlies|||Horizon|Horizon
Ohio|Ohio|Bobcats|MAC|FBS|MAC|MAC
Ohio St.|Ohio State|Buckeyes|Big Ten|FBS|Big Ten|Big Ten
Oklahoma|Oklahoma|Sooners|SEC|FBS|SEC|SEC
Oklahoma St.|Oklahoma State|Cowboys|Big 12|FBS|Big 12|Big 12
Old Dominion|Old Dominion|Monarchs|Sun Belt|FBS|Sun Belt|Sun Belt
Ole Miss|Ole Miss|Rebels|SEC|FBS|SEC|SEC
Omaha|Omaha|Mavericks|||Summit League|Summit League
Oral Roberts|Oral Roberts|Golden Eagles|||Summit League|Summit League
Oregon|Oregon|Ducks|Big Ten|FBS|Big Ten|Big Ten
Oregon St.|Oregon State|Beavers|Pac-12|FBS|WCC|Independent
Pacific|Pacific|Tigers|||WCC|WCC
Penn|Penn|Quakers|Ivy League|FCS|Ivy League|Ivy League
Penn St.|Penn State|Nittany Lions|Big Ten|FBS|Big Ten|Big Ten
Pepperdine|Pepperdine|Waves|||WCC|WCC
Pittsburgh|Pittsburgh|Panthers|ACC|FBS|ACC|ACC
Portland|Portland|Pilots|||WCC|WCC
Portland St.|Portland State|Vikings|Big Sky|FCS|Big Sky|
Prairie View|Prairie View A&M|Panthers|SWAC|FCS|SWAC|SWAC
Presbyterian|Presbyterian|Blue Hose|Pioneer|FCS|Big South|Big South
Princeton|Princeton|Tigers|Ivy League|FCS|Ivy League|Ivy League
Providence|Providence|Friars|||Big East|
Purdue|Purdue|Boilermakers|Big Ten|FBS|Big Ten|Big Ten
Purdue Fort Wayne|Purdue Fort Wayne|Mastodons|||Horizon|
Queens (NC)|Queens|Royals|||ASUN|ASUN
Quinnipiac|Quinnipiac|Bobcats|||MAAC|MAAC
Radford|Radford|Highlanders|||Big South|Big South
Rhode Island|Rhode Island|Rams|CAA|FCS|Atlantic 10|Atlantic 10
Rice|Rice|Owls|American|FBS|American|American
Richmond|Richmond|Spiders|Patriot|FCS|Atlantic 10|Atlantic 10
Rider|Rider|Broncs|||MAAC|MAAC
Robert Morris|Robert Morris|Colonials|NEC|FCS|Horizon|
Rutgers|Rutgers|Scarlet Knights|Big Ten|FBS|Big Ten|Big Ten
SFA|Stephen F. Austin|Lumberjacks|Southland|FCS|Southland|Southland
SIUE|SIU Edwardsville|Cougars|||OVC|OVC
SMU|SMU|Mustangs|ACC|FBS|ACC|
Sacramento St.|Sacramento State|Hornets|Big Sky|FCS|Big Sky|WAC
Sacred Heart|Sacred Heart|Pioneers|FCS Independent|FCS|MAAC|MAAC
Saint Francis|Saint Francis|Red Flash|NEC|FCS|NEC|
Saint Joseph's|Saint Joseph's|Hawks|||Atlantic 10|Atlantic 10
Saint Louis|Saint Louis|Billikens|||Atlantic 10|Atlantic 10
Saint Mary's (CA)|Saint Mary's|Gaels|||WCC|WCC
Saint Peter's|Saint Peter's|Peacocks|||MAAC|MAAC
Sam Houston|Sam Houston|Bearkats|CUSA|FBS|CUSA|CUSA
Samford|Samford|Bulldogs|SoCon|FCS|SoCon|SoCon
San Diego|San Diego|Toreros|Pioneer|FCS|WCC|WCC
San Diego St.|San Diego State|Aztecs|Mountain West|FBS|Mountain West|Mountain West
San Francisco|San Francisco|Dons|||WCC|WCC
San Jose St.|San Jose State|Spartans|Mountain West|FBS|Mountain West|Mountain West
Santa Clara|Santa Clara|Broncos|||WCC|WCC
Seattle U|Seattle|Redhawks|||WCC|WCC
Seton Hall|Seton Hall|Pirates|||Big East|Big East
Siena|Siena|Saints|||MAAC|MAAC
South Alabama|South Alabama|Jaguars|Sun Belt|FBS|Sun Belt|Sun Belt
South Carolina|South Carolina|Gamecocks|SEC|FBS|SEC|SEC
South Carolina St.|South Carolina State|Bulldogs|MEAC|FCS|MEAC|
South Dakota|South Dakota|Coyotes|MVFC|FCS|Summit League|
South Dakota St.|South Dakota State|Jackrabbits|MVFC|FCS|Summit League|Summit League
South Fla.|South Florida|Bulls|American|FBS|American|American
Southeast Mo. St.|Southeast Missouri State|Redhawks|Big South-OVC|FCS|OVC|OVC
Southeastern La.|Southeastern Louisiana|Lions|Southland|FCS|Southland|Southland
Southern California|USC|Trojans|Big Ten|FBS|Big Ten|Big Ten
Southern Ill.|Southern Illinois|Salukis|MVFC|FCS|MVC|MVC
Southern Ind.|Southern Indiana|Screaming Eagles|||OVC|OVC
Southern Miss.|Southern Miss|Golden Eagles|Sun Belt|FBS|Sun Belt|Sun Belt
Southern U.|Southern|Jaguars|SWAC|FCS|SWAC|SWAC
Southern Utah|Southern Utah|Thunderbirds|United Athletic|FCS|WAC|
St. Bonaventure|St. Bonaventure|Bonnies|||Atlantic 10|Atlantic 10
St. John's (NY)|St. John's|Red Storm|||Big East|Big East
St. Thomas (MN)|St. Thomas|Tommies|Pioneer|FCS|Summit League|Summit League
Stanford|Stanford|Cardinal|ACC|FBS|ACC|ACC
Stetson|Stetson|Hatters|Pioneer|FCS|ASUN|ASUN
Stonehill|Stonehill|Skyhawks|NEC|FCS|NEC|NEC
Stony Brook|Stony Brook|Seawolves|CAA|FCS|CAA|CAA
Syracuse|Syracuse|Orange|ACC|FBS|ACC|
TCU|TCU|Horned Frogs|Big 12|FBS|Big 12|Big 12
Tarleton St.|Tarleton State|Texans|United Athletic|FCS|WAC|WAC
Temple|Temple|Owls|American|FBS|American|
Tennessee|Tennessee|Volunteers|SEC|FBS|SEC|SEC
Tennessee St.|Tennessee State|Tigers|Big South-OVC|FCS|OVC|
Tennessee Tech|Tennessee Tech|Golden Eagles|Big South-OVC|FCS|OVC|OVC
Texas|Texas|Longhorns|SEC|FBS|SEC|SEC
Texas A&M|Texas A&M|Aggies|SEC|FBS|SEC|SEC
Texas Southern|Texas Southern|Tigers|SWAC|FCS|SWAC|SWAC
Texas St.|Texas State|Bobcats|Sun Belt|FBS|Sun Belt|Sun Belt
Texas Tech|Texas Tech|Red Raiders|Big 12|FBS|Big 12|Big 12
The Citadel|The Citadel|Bulldogs|SoCon|FCS|SoCon|SoCon
Toledo|Toledo|Rockets|MAC|FBS|MAC|MAC
Towson|Towson|Tigers|CAA|FCS|CAA|CAA
Troy|Troy|Trojans|Sun Belt|FBS|Sun Belt|Sun Belt
Tulane|Tulane|Green Wave|American|FBS|American|American
Tulsa|Tulsa|Golden Hurricane|American|FBS|American|
UAB|UAB|Blazers|American|FBS|American|American
UAlbany|Albany|Great Danes|CAA|FCS|America East|America East
UC Davis|UC Davis|Aggies|Big Sky|FCS|Big West|Big West
UC Irvine|UC Irvine|Anteaters|||Big West|Big West
UC Riverside|UC Riverside|Highlanders|||Big West|Big West
UC San Diego|UC San Diego|Tritons|||Big West|Big West
UC Santa Barbara|UC Santa Barbara|Gauchos|||Big West|Big West
UCF|UCF|Knights|Big 12|FBS|Big 12|Big 12
UCLA|UCLA|Bruins|Big Ten|FBS|Big Ten|Big Ten
UConn|UConn|Huskies|FBS Independent|FBS|Big East|Big East
UIC|UIC|Flames|||MVC|MVC
UIW|Incarnate Word|Cardinals|Southland|FCS|Southland|Southland
ULM|Louisiana-Monroe|Warhawks|Sun Belt|FBS|Sun Belt|Sun Belt
UMBC|UMBC|Retrievers|||America East|America East
UMES|Maryland Eastern Shore|Hawks|||MEAC|NEC
UMass Lowell|UMass Lowell|River Hawks|||America East|America East
UNC Asheville|UNC Asheville|Bulldogs|||Big South|Big South
UNC Greensboro|UNC Greensboro|Spartans|||SoCon|SoCon
UNCW|UNC Wilmington|Seahawks|||CAA|CAA
UNI|Northern Iowa|Panthers|MVFC|FCS|MVC|
UNLV|UNLV|Rebels|Mountain West|FBS|Mountain West|Mountain West
USC Upstate|USC Upstate|Spartans|||Big South|Big South
UT Arlington|UT Arlington|Mavericks|||WAC|WAC
UT Martin|UT Martin|Skyhawks|Big South-OVC|FCS|OVC|OVC
UTEP|UTEP|Miners|CUSA|FBS|CUSA|
UTRGV|UTRGV|Vaqueros|Southland|FCS|Southland|Southland
UTSA|UTSA|Roadrunners|American|FBS|American|American
Utah|Utah|Utes|Big 12|FBS|Big 12|Big 12
Utah St.|Utah State|Aggies|Mountain West|FBS|Mountain West|
Utah Tech|Utah Tech|Trailblazers|United Athletic|FCS|WAC|WAC
Utah Valley|Utah Valley|Wolverines|||WAC|WAC
VCU|VCU|Rams|||Atlantic 10|Atlantic 10
VMI|VMI|Keydets|SoCon|FCS|SoCon|SoCon
Valparaiso|Valparaiso|Beacons|Pioneer|FCS|MVC|MVC
Vanderbilt|Vanderbilt|Commodores|SEC|FBS|SEC|SEC
Vermont|Vermont|Catamounts|||America East|
Villanova|Villanova|Wildcats|CAA|FCS|Big East|Big East
Virginia|Virginia|Cavaliers|ACC|FBS|ACC|ACC
Virginia Tech|Virginia Tech|Hokies|ACC|FBS|ACC|ACC
Wagner|Wagner|Seahawks|NEC|FCS|NEC|NEC
Wake Forest|Wake Forest|Demon Deacons|ACC|FBS|ACC|ACC
Washington|Washington|Huskies|Big Ten|FBS|Big Ten|Big Ten
Washington St.|Washington State|Cougars|Pac-12|FBS|WCC|Mountain West
Weber St.|Weber State|Wildcats|Big Sky|FCS|Big Sky|
West Ga.|West Georgia|Wolves|United Athletic|FCS|ASUN|ASUN
West Virginia|West Virginia|Mountaineers|Big 12|FBS|Big 12|Big 12
Western Caro.|Western Carolina|Catamounts|SoCon|FCS|SoCon|SoCon
Western Ill.|Western Illinois|Leathernecks|Big South-OVC|FCS|OVC|OVC
Western Ky.|Western Kentucky|Hilltoppers|CUSA|FBS|CUSA|CUSA
Western Mich.|Western Michigan|Broncos|MAC|FBS|MAC|MAC
Wichita St.|Wichita State|Shockers|||American|American
William & Mary|William & Mary|Tribe|CAA|FCS|CAA|CAA
Winthrop|Winthrop|Eagles|||Big South|Big South
Wisconsin|Wisconsin|Badgers|Big Ten|FBS|Big Ten|
Wofford|Wofford|Terriers|SoCon|FCS|SoCon|SoCon
Wright St.|Wright State|Raiders|||Horizon|Horizon
Wyoming|Wyoming|Cowboys|Mountain West|FBS|Mountain West|
Xavier|Xavier|Musketeers|||Big East|Big East
Yale|Yale|Bulldogs|Ivy League|FCS|Ivy League|Ivy League
Youngstown St.|Youngstown State|Penguins|MVFC|FCS|Horizon|Horizon
"""

# sport | school key | the team code SportsDataIO sends. Only schools listed
# here can be joined to a live game; the rest are searchable but the game
# lookup has no code to match them on.
_FEED_ROWS = """
ncaaf|Alabama|ALA
ncaaf|App State|APPLST
ncaaf|Arizona|ARZ
ncaaf|Arizona St.|ARZST
ncaaf|Arkansas|ARK
ncaaf|Army West Point|ARMY
ncaaf|Auburn|AUBRN
ncaaf|BYU|BYU
ncaaf|Baylor|BAYL
ncaaf|Boise St.|BOISE
ncaaf|Boston College|BOSCOL
ncaaf|California|CAH
ncaaf|Cincinnati|CIN
ncaaf|Clemson|CLMSN
ncaaf|Coastal Carolina|COAST
ncaaf|Colorado|COL
ncaaf|Duke|DUKE
ncaaf|Florida|FL
ncaaf|Florida St.|FLST
ncaaf|Georgia|GA
ncaaf|Georgia Tech|GTECH
ncaaf|Hawaii|HAWAII
ncaaf|Houston|HOU
ncaaf|Illinois|ILL
ncaaf|Indiana|IND
ncaaf|Iowa|IOWA
ncaaf|Iowa St.|IOWAST
ncaaf|James Madison|JMAD
ncaaf|Kansas|KAN
ncaaf|Kansas St.|KANST
ncaaf|Kentucky|UK
ncaaf|LSU|LSU
ncaaf|Liberty|LIBRTY
ncaaf|Louisiana|LOULAF
ncaaf|Louisville|LOU
ncaaf|Marshall|MARSH
ncaaf|Maryland|MARY
ncaaf|Memphis|MPHS
ncaaf|Miami (FL)|MIA
ncaaf|Michigan|MICH
ncaaf|Michigan St.|MST
ncaaf|Minnesota|MINNST
ncaaf|Mississippi St.|MSPST
ncaaf|Missouri|MISSR
ncaaf|NC State|NCST
ncaaf|Navy|NAVY
ncaaf|Nebraska|NEBR
ncaaf|Nevada|NEVADA
ncaaf|North Carolina|NCAR
ncaaf|Northwestern|NW
ncaaf|Notre Dame|ND
ncaaf|Ohio St.|OHIOST
ncaaf|Oklahoma|OKL
ncaaf|Oklahoma St.|OKST
ncaaf|Ole Miss|MISS
ncaaf|Oregon|ORE
ncaaf|Penn St.|PENNST
ncaaf|Pittsburgh|PITT
ncaaf|Purdue|PUR
ncaaf|Rutgers|RUTGER
ncaaf|SMU|SMU
ncaaf|San Diego St.|SDST
ncaaf|South Carolina|SC
ncaaf|Southern California|USC
ncaaf|Stanford|STAN
ncaaf|Syracuse|SYRA
ncaaf|TCU|TCU
ncaaf|Tennessee|TENN
ncaaf|Texas|TX
ncaaf|Texas A&M|TXAM
ncaaf|Texas Tech|TXTECH
ncaaf|Troy|TROY
ncaaf|Tulane|TULANE
ncaaf|Tulsa|TULSA
ncaaf|UAB|UAB
ncaaf|UCF|UCF
ncaaf|UCLA|UCLA
ncaaf|UNLV|UNLV
ncaaf|UTSA|UTSA
ncaaf|Utah|UTAH
ncaaf|Vanderbilt|VAND
ncaaf|Virginia|VIR
ncaaf|Virginia Tech|VTECH
ncaaf|Wake Forest|WAKE
ncaaf|Washington|WASH
ncaaf|West Virginia|WVIR
ncaaf|Wisconsin|WISC
ncaab|Alabama|ALA
ncaab|Arizona|ARZ
ncaab|Arizona St.|ARZST
ncaab|Arkansas|ARK
ncaab|Auburn|AUBRN
ncaab|BYU|BYU
ncaab|Baylor|BAYL
ncaab|Boston College|BOSCOL
ncaab|Butler|BUTL
ncaab|California|CAH
ncaab|Cincinnati|CIN
ncaab|Clemson|CLMSN
ncaab|Colorado|COL
ncaab|Creighton|CREIGH
ncaab|Dayton|DAY
ncaab|DePaul|DEPAUL
ncaab|Duke|DUKE
ncaab|Florida|FL
ncaab|Florida St.|FLST
ncaab|Georgetown|GEORGE
ncaab|Georgia|GA
ncaab|Georgia Tech|GTECH
ncaab|Gonzaga|GNZG
ncaab|Harvard|HARVRD
ncaab|Houston|HOU
ncaab|Illinois|ILL
ncaab|Indiana|IND
ncaab|Iowa|IOWA
ncaab|Iowa St.|IOWAST
ncaab|Kansas|KAN
ncaab|Kansas St.|KANST
ncaab|Kentucky|UK
ncaab|LSU|LSU
ncaab|Louisville|LOU
ncaab|Marquette|MARQ
ncaab|Maryland|MARY
ncaab|Memphis|MPHS
ncaab|Miami (FL)|MIA
ncaab|Michigan|MICH
ncaab|Michigan St.|MST
ncaab|Minnesota|MINNST
ncaab|Mississippi St.|MSPST
ncaab|Missouri|MISSR
ncaab|NC State|NCST
ncaab|Nebraska|NEBR
ncaab|North Carolina|NCAR
ncaab|Northwestern|NW
ncaab|Ohio St.|OHIOST
ncaab|Oklahoma|OKL
ncaab|Oklahoma St.|OKST
ncaab|Ole Miss|MISS
ncaab|Oregon|ORE
ncaab|Penn St.|PENNST
ncaab|Pittsburgh|PITT
ncaab|Providence|PROV
ncaab|Purdue|PUR
ncaab|Richmond|RICH
ncaab|Rutgers|RUTGER
ncaab|SMU|SMU
ncaab|Saint Louis|STLOU
ncaab|San Diego St.|SDST
ncaab|Seton Hall|SETON
ncaab|South Carolina|SC
ncaab|Southern California|USC
ncaab|Stanford|STAN
ncaab|Syracuse|SYRA
ncaab|TCU|TCU
ncaab|Tennessee|TENN
ncaab|Texas|TX
ncaab|Texas A&M|TXAM
ncaab|Texas Tech|TXTECH
ncaab|UCF|UCF
ncaab|UCLA|UCLA
ncaab|UConn|UCONN
ncaab|Utah|UTAH
ncaab|Vanderbilt|VAND
ncaab|Villanova|VILL
ncaab|Virginia|VIR
ncaab|Virginia Tech|VTECH
ncaab|Wake Forest|WAKE
ncaab|Washington|WASH
ncaab|West Virginia|WVIR
ncaab|Wichita St.|WICHST
ncaab|Wisconsin|WISC
ncaab|Xavier|XAV
ncaawb|Arkansas|ARK
ncaawb|Auburn|AUBRN
ncaawb|BYU|BYU
ncaawb|Baylor|BAYL
ncaawb|Boston College|BOSCOL
ncaawb|California|CAH
ncaawb|Cincinnati|CIN
ncaawb|Clemson|CLMSN
ncaawb|Duke|DUKE
ncaawb|Florida|FL
ncaawb|Florida St.|FLST
ncaawb|Georgia|GA
ncaawb|Georgia Tech|GTECH
ncaawb|Gonzaga|GNZG
ncaawb|Houston|HOU
ncaawb|Indiana|IND
ncaawb|Iowa|IOWA
ncaawb|Iowa St.|IOWAST
ncaawb|Kansas St.|KANST
ncaawb|LSU|LSU
ncaawb|Louisville|LOU
ncaawb|Maryland|MARY
ncaawb|Miami (FL)|MIA
ncaawb|Michigan|MICH
ncaawb|Michigan St.|MST
ncaawb|Minnesota|MINNST
ncaawb|Mississippi St.|MSPST
ncaawb|Missouri|MISSR
ncaawb|NC State|NCST
ncaawb|Nebraska|NEBR
ncaawb|North Carolina|NCAR
ncaawb|Northwestern|NW
ncaawb|Notre Dame|ND
ncaawb|Ohio St.|OHIOST
ncaawb|Oklahoma|OKL
ncaawb|Oklahoma St.|OKST
ncaawb|Ole Miss|MISS
ncaawb|Oregon|ORE
ncaawb|Penn St.|PENNST
ncaawb|Pittsburgh|PITT
ncaawb|Purdue|PUR
ncaawb|Rutgers|RUTGER
ncaawb|SMU|SMU
ncaawb|South Carolina|SC
ncaawb|Southern California|USC
ncaawb|Stanford|STAN
ncaawb|Syracuse|SYRA
ncaawb|TCU|TCU
ncaawb|Tennessee|TENN
ncaawb|Texas|TX
ncaawb|Texas A&M|TXAM
ncaawb|Texas Tech|TXTECH
ncaawb|UCF|UCF
ncaawb|UCLA|UCLA
ncaawb|UConn|UCONN
ncaawb|Utah|UTAH
ncaawb|Vanderbilt|VAND
ncaawb|Virginia|VIR
ncaawb|Virginia Tech|VTECH
ncaawb|Wake Forest|WAKE
ncaawb|Washington|WASH
ncaawb|West Virginia|WVIR
ncaawb|Wisconsin|WISC
"""

SCHOOLS = {}          # key -> (school name shown to people, mascot)
FOOTBALL_FBS = {}     # key -> conference
FOOTBALL_FCS = {}
BASKETBALL = {}
BASEBALL = {}
FEED_CODES = {}       # sport -> {key: feed code}


def _load():
    for line in _SCHOOL_ROWS.strip().splitlines():
        key, school, mascot, fb, div, mbb, bsb = line.split("|")
        SCHOOLS[key] = (school, mascot)
        if fb:
            (FOOTBALL_FBS if div == "FBS" else FOOTBALL_FCS)[key] = fb
        if mbb:
            BASKETBALL[key] = mbb
        if bsb:
            BASEBALL[key] = bsb
    for line in _FEED_ROWS.strip().splitlines():
        sport, key, code = line.split("|")
        FEED_CODES.setdefault(sport, {})[key] = code


_load()
