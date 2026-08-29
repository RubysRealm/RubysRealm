import hashlib, os, random

ROLES=[
 ('Storage Auction Buyer','abandoned self-storage facility','unit 214','a red inventory tag','a sealed metal cash box','an old delivery van','the county records office','a freight company that disappeared twelve years ago'),
 ('Closed Theater Owner','shuttered downtown movie theater','projection booth four','a brass film canister','a locked wall safe','a gray sedan','the city archives','a property company dissolved after a fire'),
 ('Marina Manager','half-empty lakeside marina','dock C-17','a blue key float','a waterproof document tube','a black fishing boat','the harbor office','a development company with no current address'),
 ('Warehouse Buyer','vacant industrial warehouse','bay twelve','a yellow security badge','a bolted floor compartment','a white box truck','the zoning office','a logistics company that vanished from state records'),
 ('Mountain Lodge Owner','closed mountain lodge','room 308','a numbered wooden key tag','a hidden steel lockbox','a dark green SUV','the county planning office','a land company created for one transaction'),
 ('Old Diner Owner','roadside diner that has been closed for years','the basement pantry','a chipped ceramic token','a fireproof document case','a faded pickup','the courthouse records room','a restaurant supplier that no longer exists'),
 ('Drive-In Owner','abandoned drive-in theater','screen tower access room','a stamped aluminum token','a weatherproof case','an old tow truck','the county tax office','a shell company listed on a forgotten easement'),
 ('Radio Station Buyer','silent local radio station','studio B','a handwritten transmitter key','a locked archive drawer','a dark station wagon','the communications records desk','a holding company whose officers are all deceased'),
 ('Greenhouse Owner','neglected commercial greenhouse','propagation room six','a numbered irrigation tag','a sealed records tube','a white utility van','the agricultural extension office','a nursery company dissolved after a lawsuit'),
 ('Ferry Terminal Manager','decommissioned river ferry terminal','maintenance locker nineteen','a brass locker key','a locked survey case','a black pickup','the county transportation office','a construction partnership that disappeared before the project ended'),
]

HOOKS=[
 'because the auction price is lower than the value of the equipment still sitting inside',
 'after the county lists it for less than the cost of a new truck',
 'because everyone else at the auction suddenly stops bidding',
 'after you notice the land parcel is much larger than the building itself',
 'because the listing contains one sentence that does not match the public records',
]

ODDITIES=[
 'The official inventory is short by exactly one room.',
 'The utility map shows a live circuit feeding a space that supposedly does not exist.',
 'The old key board contains one tag with no matching door on the floor plan.',
 'A handwritten maintenance log continues for months after the business officially closed.',
 'One security camera is still recording even though the account was cancelled years ago.',
]

CALLS=[
 'At 1:37 in the morning an internal phone rings even though the service line is disconnected.',
 'Just after midnight a motion alarm triggers in a section with no active sensor.',
 'At 2:11 a.m. the old intercom clicks on and a voice calmly asks whether the delivery has arrived.',
 'Near midnight a printer in the office wakes up and produces a single blank page with a date stamped at the bottom.',
 'At 1:52 a.m. an exterior light turns on above a door whose breaker is switched off.',
]

MESSAGES=[
 'Do not open it until he comes back.',
 'The map is wrong. Check underneath.',
 'If you found the tag, you already found too much.',
 'The property line is not where the county thinks it is.',
 'The building was never the valuable part.',
]

REVEALS=[
 'an old easement that gives the parcel access to a planned commercial road',
 'a forgotten mineral-rights agreement tied to the land beneath the property',
 'a second deed covering a narrow strip needed for a new utility corridor',
 'a recorded option granting control of the only service road into a planned development',
 'a survey showing that a valuable access parcel was never included in the foreclosure paperwork',
]

ENDING_DETAILS=[
 'The payment is several times what you paid at auction.',
 'The settlement covers the purchase price, repairs, and enough operating cash to reopen.',
 'The county buys the disputed strip for more than the entire property cost you.',
 'The final agreement turns what looked like a terrible purchase into the best deal you have ever made.',
]

NAMES=['Cal Mercer','Dale Wynn','Mara Holt','Evan Cross','June Voss','Neil Archer','Tessa Lane','Graham Pike','Ruth Bell','Owen Vale']


def _seed_value(seed=None):
    if seed is not None:
        return int(seed)
    raw=os.getenv('STORY_SEED') or os.getenv('GITHUB_RUN_ID') or os.getenv('GITHUB_RUN_NUMBER') or os.urandom(8).hex()
    return int(hashlib.sha256(str(raw).encode()).hexdigest()[:12],16)


def generate_story(seed=None):
    sv=_seed_value(seed); r=random.Random(sv)
    role,place,hidden,token,container,vehicle,office,company=r.choice(ROLES)
    hook=r.choice(HOOKS); oddity=r.choice(ODDITIES); night=r.choice(CALLS); warning=r.choice(MESSAGES); reveal=r.choice(REVEALS); payoff=r.choice(ENDING_DETAILS)
    stranger=r.choice(NAMES); clerk=r.choice([n for n in NAMES if n!=stranger]); years=r.randint(7,19); official_close=r.randint(2,5); recent=r.randint(12,38)
    amount=r.choice(['$18,400','$27,900','$41,250','$63,000','$96,500'])
    title=f'Your Life as a {role}'

    p=[]
    p.append(f"You take control of a {place} {hook}. At first the deal looks simple: clear out the junk, repair what can be saved, and either reopen the place or sell it once the property looks respectable again. The county file says the business has been closed for {official_close} years. But before you even finish your first walk-through, you find paperwork dated only {recent} days ago.")
    p.append(f"The first day is ordinary enough. A contractor points out water damage, dead outlets, a warped exterior door, and several repairs that were clearly postponed for years. Then the two of you reach {hidden}. It is not shown on the current floor plan. {oddity} The contractor jokes that old buildings are full of bad paperwork, but he stops joking when you find {token} hanging behind the office desk.")
    p.append(f"The tag matches nothing in the county inventory. Beneath it is a ledger with dates, initials, and dollar amounts. Most pages stop {years} years ago. A few entries are newer. The last one lists {amount}, the initials of someone you do not recognize, and one word written twice: HOLD.")
    p.append(f"You spend the evening sorting files because the power has finally been restored. {night} For several seconds nothing happens. Then you hear a calm voice mention {hidden} as if the caller expects you to know exactly what that means. When you ask who is calling, the line goes dead.")
    p.append(f"You walk the property with a flashlight. Everything is dark except the area around {hidden}. A thin strip of light appears where there should be no electricity. You check the panel. The breaker feeding that section is off. By the time the contractor arrives, the light is gone, but a fresh footprint is visible in dust that had been untouched everywhere else.")
    p.append(f"The next morning you call {office}. A clerk named {clerk} sends you older scans of the property. The original plan contains a narrow service space that vanished from later drawings. The dimensions line up almost perfectly with {hidden}. More importantly, an old parcel map shows a boundary line extending beyond the fence you assumed marked the edge of your land.")
    p.append(f"You and the contractor open the concealed access point. Behind it is a narrow passage with dust on both sides and a cleaner strip through the middle. At the far end is a small room containing a desk, old filing cabinets, and a security monitor. One camera is still active. Its picture shows the property in real time.")
    p.append(f"Inside a drawer you find receipts from {company}. The business paid the former owner to hold spare keys, signed documents, cash envelopes, and survey records off the books. That explains the ledger, but it does not explain the recent entries. The company disappeared from public records years ago, and the former owner has been dead for four years.")
    p.append(f"That afternoon {vehicle} stops outside. A man who introduces himself as {stranger} gets out and looks at the construction dumpster before he looks at you. He asks whether you have opened {hidden}. You do not answer. He smiles, hands you a plain envelope, and says he will return after dark for something that belongs to him.")
    p.append(f"The envelope contains an old photograph, a receipt, and a photocopy of a survey. Someone has circled a spot beneath the property. On the back, in block letters, is the sentence: {warning}")
    p.append(f"The contractor wants to call the sheriff immediately. Before you do, you move an old desk and notice newer fasteners in a floor that has not been renovated in decades. Under the flooring is {container}. You leave it closed and call law enforcement before touching anything else.")
    p.append(f"While you wait, the security monitor flickers. The camera shows {vehicle} returning, but it stops across the road. Nobody gets out. A few minutes later the vehicle disappears from view. When a deputy finally arrives, the road is empty.")
    p.append(f"The container is opened with the deputy present. Inside are old contracts, cash envelopes, maps, and a document describing {reveal}. The paperwork appears legitimate enough that the county immediately sends it to attorneys instead of dismissing it as junk.")
    p.append("That is when the purchase starts to make sense. The structure you thought you bought cheaply was only the visible part of the deal. Someone had spent years protecting a piece of property information that mattered far more than the building itself.")
    p.append(f"Over the next several weeks investigators trace the documents, surveyors re-check the boundaries, and county attorneys locate old filings that should have been attached to the foreclosure record but were not. {stranger} never returns. His phone number belongs to a prepaid line that has already been disconnected.")
    p.append(f"Eventually the dispute becomes a negotiation. {payoff} You sign only after your attorney confirms the settlement leaves you clear title to the rest of the property and no obligation connected to the old storage arrangement.")
    p.append(f"You use part of the money to finish the repairs. The building finally reopens, but you keep {hidden} locked and use it only for records. {token.capitalize()} stays mounted behind the desk as a reminder of the first week you owned the place.")
    p.append("Every once in a while a customer notices it and asks what it opens. You give them a simple answer: old properties always have keys nobody remembers. You never mention the phone call, the hidden room, or the man who knew about it before you did.")
    story='\n\n'.join(p)
    return {'title':title,'part':'Part 1','story':story,'seed':sv,'story_id':hashlib.sha256(story.encode()).hexdigest()[:16]}
