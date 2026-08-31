import hashlib, os, random

# High-interest "Your Life..." concepts. Every title must describe the PERSON,
# never the place/object ("Greenhouse Owner", not "Greenhouse").
CONCEPTS=[
 ("Lottery Winner","Your Life After Winning the Lottery"),
 ("Casino Owner","Your Life as a Casino Owner"),
 ("Mob Boss","Your Life as a Mob Boss"),
 ("Cartel Insider","Your Life Working Inside a Drug Cartel"),
]

def _seed_value(seed=None):
    if seed is not None: return int(seed)
    raw=os.getenv('STORY_SEED') or os.getenv('GITHUB_RUN_ID') or os.getenv('GITHUB_RUN_NUMBER') or os.urandom(8).hex()
    return int(hashlib.sha256(str(raw).encode()).hexdigest()[:12],16)

def _lottery_story(r):
    amount=r.choice(["$38 million","$64 million","$112 million","$187 million"])
    cash=r.choice(["$21.4 million","$36.8 million","$61.7 million","$103.2 million"])
    return f"""It is 6:12 on a Tuesday morning when you scan a lottery ticket you almost forgot in your truck. The screen does not show a dollar amount. It says SEE RETAILER. You scan it again. Same message.

You carry the ticket inside. The clerk checks the numbers, looks at you, then checks them a second time. You matched every number. The advertised jackpot is {amount}. You do not celebrate yet. You fold the ticket, sign the back, photograph both sides, and drive home with your hands shaking.

For the next two hours, nobody knows. That silence becomes your first real decision as a winner. Before calling family or posting anything online, you put the ticket in a safe place and contact an attorney who has handled large financial settlements.

By noon, the attorney has you sitting in a conference room with a tax adviser. They explain the choice between the annuity and the lump-sum payment. After estimated federal and state taxes, the cash option would leave you with roughly {cash}, depending on final withholding and your tax situation.

That is the moment the jackpot stops feeling like a giant number on television. You now have to decide what your actual life will look like.

You tell only three people: your spouse, your attorney, and your accountant. Your phone stays quiet for exactly one day. Then a local news page posts that the winning ticket was sold in your town.

By Wednesday night, people are guessing who bought it. A former coworker messages you out of nowhere. A cousin you have not spoken to in four years calls twice. You realize that claiming the money is going to change more than your bank account.

On Thursday, your attorney creates a plan for the claim and for the money after it arrives. There is a separate account for taxes, a conservative investment account, and a smaller amount you can actually spend without touching the long-term plan.

You make your first list. Pay off the house. Clear every debt. Replace the old truck. Help your parents. Take one ridiculous vacation. Then you write one rule across the top: do not buy anything expensive for thirty days.

Claim day arrives the following week. You walk into the lottery office carrying the same ticket that spent days hidden inside your house. There are forms, identity checks, photographs, and signatures. Then someone takes the ticket away.

That part bothers you more than expected. For a week, that piece of paper was worth more than everything you owned. Now it is gone, and all you have is paperwork saying the claim is being processed.

Nine days later, your attorney calls. The funds have cleared.

You open your banking app and stare at a balance that looks fake. You refresh the screen. It is still there. You close the app, open it again, and laugh because you genuinely do not know what else to do.

The first purchase is not a supercar. It is the remaining balance on your mortgage. You watch the confirmation page appear and realize the house you slept in last night now belongs completely to you.

The second payment clears every other debt. Credit cards, truck loan, everything. In less than an hour, years of monthly payments disappear.

Then comes the fun purchase. You walk into a dealership intending to buy one vehicle and leave having ordered two: the truck you always wanted and a sports car you would never have considered a month earlier.

But the strangest change is not what you buy. It is how people treat you once they know.

Friends joke about loans. Distant relatives suddenly have business ideas. Someone you barely remember sends you a five-page message explaining why twenty thousand dollars would change their life.

So you create another rule: nobody gets an answer about money on the same day they ask.

A month after the win, you take your family on the vacation from your list. For the first time, you choose the flights because they are convenient, not because they are cheapest. You reserve the rooms you actually want. You stop checking the price of every meal.

Sitting on the balcony one night, you realize winning did not make life feel unreal forever. It simply replaced your old problems with decisions you never had to make before.

Six months later, most of the jackpot is still invested. Your house is paid for, your family is secure, and you have enough set aside that working is now a choice instead of a requirement.

You still keep the original losing tickets from the week before the jackpot in a drawer. Not because they are worth anything, but because they remind you how ordinary your life looked seven days before everything changed.

And every Tuesday morning, at exactly 6:12, your phone still gives you the reminder you set years ago: check lottery ticket. You never turned it off."""

def _casino_story(r):
    return """Your first morning as a casino owner starts at 4:47 a.m., not under neon lights but in a security office. Overnight reports are waiting: cash counts, machine faults, staffing notes, and one high-limit player who is still downstairs.

At 5:15, the night manager walks you through every incident before the day shift arrives. Nothing dramatic has happened, but you learn the first rule immediately: a casino never really closes, so yesterday and today overlap.

By 7:00, you are on the gaming floor before most guests wake up. Technicians are opening machines for scheduled maintenance. Dealers are changing shifts. Surveillance is checking camera coverage. The glamorous room customers see is being rebuilt around them without ever appearing to stop.

At 9:30, finance sends the previous day's numbers. Some tables won. Some lost. Hotel rooms, restaurants, entertainment, and gaming all tell different stories. Owning the casino means understanding all of them together, not staring at one lucky table.

Just before lunch, a restaurant manager tells you a refrigeration unit failed. Ten minutes later, hotel operations needs approval for an overbooked weekend. Then marketing wants a decision on next month's promotion. Your calendar is useless by noon.

At 2:00, you finally walk through the high-limit room. A regular guest recognizes you and asks whether being the owner means you can make the house win whenever you want. You laugh, because by now you know the opposite problem keeps you awake: making sure every game is fair, compliant, staffed, and operating correctly.

That evening, the property fills. The lights look perfect. Music carries across the floor. Guests see a giant machine built for entertainment. You see hundreds of employees and thousands of tiny decisions happening at once.

At 11:40 p.m., you are back in surveillance reviewing an incident from the floor. It is resolved correctly, but you stay until the report is complete.

You leave after midnight. The valet asks whether you had a good night.

You look back at the building, still glowing and crowded, and realize the strangest part of owning a casino: you can go home, but the business never does."""

def generate_story(seed=None):
    sv=_seed_value(seed); r=random.Random(sv)
    forced=os.getenv("STORY_CONCEPT","").strip().lower()
    if forced in ("casino","casino owner"):
        role,title="Casino Owner","Your Life as a Casino Owner"; story=_casino_story(r)
    else:
        # Next review render intentionally uses the strongest, easiest-to-follow concept.
        role,title="Lottery Winner","Your Life After Winning the Lottery"; story=_lottery_story(r)
    # Semantic title guard: reject incomplete "Your Life as a <place/object>" phrasing.
    banned={"greenhouse","casino","marina","hotel","warehouse","theater","diner"}
    tail=title.lower().replace("your life as a ","").strip()
    if title.lower().startswith("your life as a ") and tail in banned:
        raise ValueError("Incomplete occupation title: "+title)
    story='\n\n'.join(p.strip() for p in story.split("\n\n") if p.strip())
    return {'title':title,'part':'Part 1','story':story,'seed':sv,'story_id':hashlib.sha256(story.encode()).hexdigest()[:16]}
