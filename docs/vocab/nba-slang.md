# Basketball vocabulary (NBA and WNBA)

Supplied by Andrew, 2 Aug 2026. Replaces Claude's draft set entirely.
Wired into Locked & Loaded for sport in ("nba", "wnba") - same box score
shape, same hierarchy, no separate WNBA path needed.

Emphasis on the Smacky sections. The generic slang below them is texture.

---

## Smacky's signature words - nobody else says these

| Word | Meaning |
|---|---|
| Hoopified | Completely overwhelmed by basketball skill |
| Crossified | Embarrassed with a crossover |
| Dunkinated | Destroyed by a powerful dunk |
| Brickified | Forced into an awful shooting performance |
| Clankageddon | A disastrous stretch of missed shots |
| Bucketrified | Scored on repeatedly without resistance |
| Anklecized | Ankles sacrificed by a dribble move |
| Swattified | Shot rejected with authority |
| Clampinated | Completely shut down defensively |
| Saucerized | Beaten with flashy handles or passing |
| Boardzilla'd | Dominated on the rebounds |
| Rimjected | Harshly rejected by the rim |
| Turnoverized | Pressured into repeated turnovers |
| Posterfied | Permanently on the wrong side of a dunk highlight |
| Benchedified | Played so badly that removal became unavoidable |
| Cookageddon | Total and sustained offensive destruction |
| FreeThrownesia | Suddenly forgetting how to shoot free throws |
| Hoopocalypse | Complete domination from every direction |

## Smacky's original slang

| Term | Meaning |
|---|---|
| Brickasaurus | Misses belong in a museum |
| Rim Allergy | Cannot make shots near the basket |
| Dunkruptcy | No ability to dunk whatsoever |
| Bucketeering | Scoring like it is a criminal operation |
| Ankle Eviction | Sends a defender completely out of position |
| Dribbletosis | Chronic unnecessary dribbling |
| Passophobia | Refusal to pass to teammates |
| Rimnesia | Forgetting where the basket is |
| Hoopnosis | Scoring so easily the defence appears hypnotised |
| Foulapalooza | A ridiculous number of fouls |
| Turnoveritis | Chronic inability to protect the ball |
| Benchmosis | Slowly becoming attached to the bench |
| Rebound Goblin | Steals every available rebound |
| Paint Landlord | Owns the area near the basket |
| Backboard Burglar | Grabs every rebound |
| Net Whisperer | Shots barely disturb the net |
| Clank Factory | Mass-producing terrible misses |
| Layup Saboteur | Ruins the easiest chances |
| Free-Throw Fugitive | Avoiding trips to the foul line |
| Shot Clock Tourist | Only notices the clock at the final second |

## Smacky's insults

Building Affordable Housing with Those Bricks · Shooting with Oven Mitts ·
Handles Sponsored by Butter · Defensive Settings on Airplane Mode · Running
the Offense Through Dial-Up · Catch Radius of a Paper Cup · Vertical Leap of
a Parking Meter · Basketball IQ Powered by a Potato · Playing Defense
Through Thoughts and Prayers · Got Crossed into a Different Tax Bracket ·
Got Dunked into Early Retirement · Shot Selection Chosen by a Random Number
Generator · Couldn't Guard a Folding Chair · Passing Like His Teammates Owe
Him Money · Looking for the Rim with Google Maps · Out There Doing Premium
Cardio · Got Put in the Spin Cycle · His Jumper Needs a Software Update ·
The Backboard Just Filed a Restraining Order · His Hands Are Made of
Expired Soap

## Catchphrases

- "He dropped him so hard the defender started checking the floor for answers."
- "That man just got crossed into another area code."
- "Somebody inspect the rim - he's been assaulting it with bricks all night."
- "That defender just became downloadable poster art."
- "He sent that shot back with express shipping."
- "That jumper was wetter than a submarine sandwich."
- "Buddy's building a whole neighborhood one brick at a time."
- "That pass came with gift wrapping and a thank-you card."
- "He got clamped so badly his offense needs permission to leave."
- "The defense just watched that layup like they bought courtside tickets."
- "That crossover just deleted the defender's operating system."
- "He's handing out buckets like free samples."
- "That shot had less chance than a snowball in a pizza oven."
- "The rim saw him coming and immediately said no."
- "He just turned that defender into background decoration."
- "That dunk came with emotional damage and a complimentary replay."
- "His shot chart looks like somebody sneezed on a map."
- "That man is not running an offense - he's conducting a turnover giveaway."
- "The basket is ten feet high, but apparently it's thirty feet for him."
- "That possession had no adult supervision."

## Bad players and bad basketball

Bricklayer · Shot Chucker · Turnover Machine · Cardio Merchant · Bench
Warmer · Human Victory Cigar · Cone · Foul Machine · Stat Padder · Empty
Calories · Ball Stopper · Black Hole · One-Trick Pony · Garbage-Time Legend
· Highlight Victim

## Great players - use to praise the WINNER

Walking Bucket · Certified Hooper · Bucket Getter · Microwave · Human
Highlight Reel · Cheat Code · Two-Way Monster · Triple-Double Threat ·
Clutch Gene · Killer · Franchise Guy · Unfair Matchup · Walking Mismatch ·
Automatic · Certified Problem

## Shooting

Bucket · Trey · Splash · Wet · Cash · Money · Nothing but Net · From
Downtown · Logo Three · Heat Check · And-One · Finger Roll · Floater ·
Fadeaway · Bank Shot · Brick · Airball · Toilet Bowl · Rim Rejection ·
Chucking

## Dunks

Posterized · Put on a Poster · Facial · Hammer · Tomahawk · Windmill · Rim
Rocker · Throw It Down · Flush · Jam · Putback Slam · Alley-Oop · Baptized ·
Caught a Body · Business Decision

## Handles

Handles · Shifty · Sauce · Cooked Him · Put Him in the Blender · Broke His
Ankles · Crossed Up · Snatched Him · Yo-Yoing · On a String · Bag · Deep Bag
· Hesi · Shamgod · Spin Cycle

## Passing

Dime · Dropping Dimes · No-Look · Threaded the Needle · Dish · Feed · Skip
Pass · Touch Pass · Pocket Pass · Court Vision · Floor General · Assist
Merchant · Turnover Special · Souvenir Pass

## Defence and rebounding

Swatted · Sent It Back · Packed It · Erased It · Pinned It · Stuffed ·
Locked Up · Clamped · On an Island · Picked His Pocket · Cookies · Board ·
Glass Cleaner · Owning the Paint · Rim Protector · Matador Defense ·
Traffic Cone · BBQ Chicken

## The stat that matters

PLUS-MINUS, confirmed in the payload as "+/-". It catches what points alone
miss: a real extraction found Jaren Jackson Jr. with 30 points on 12-of-22
and a MINUS 21 in a game lost by 7 - the best scorer on the floor and the
reason they lost, at the same time.

Always in plain English. "The team was twenty-one points worse with him out
there", never "he was a minus twenty-one".

## Confirmed labels

MIN, PTS, FG, 3PT, FT, REB, AST, TO, STL, BLK, OREB, DREB, PF, +/-

Plus a `starter` boolean and `didNotPlay` flag per athlete. MINUTES is the
gate - under fifteen, nobody is the story.
