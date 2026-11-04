#!/usr/bin/env python3
"""Generate the sample chats in examples/samples/ (all people are fictional).

Each person below has hand-written lines in their own voice, grouped into little scenes
(you ask something, they answer, maybe one more back and forth). The generator plays those
scenes over a few months with realistic times, reply delays and who-texts-first habits,
then writes each chat in a different export format so every parser gets exercised.

    python3 tools/make_samples.py        # rewrites examples/samples/ and samples.json

It's seeded, so the output only changes when this file does. After running it, rebuild the
web files with `python3 tools/build_web.py`.

A scene is a list of steps. Each step is ("me", [options]) or ("them", [options]), where a
"me" option is one text and a "them" option is a list of bubbles sent in a row. "repeat" scenes
(good morning, on my way) can happen many times; the rest happen at most `max_uses` times.
"""
from __future__ import annotations

import csv
import io
import json
import random
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "examples" / "samples"

ME, THEM = "me", "them"


def scene(*steps, repeat=False):
    return {"steps": list(steps), "repeat": repeat}


PEOPLE = [
    # ------------------------------------------------------------------ coworker
    {
        "id": "marcus", "name": "Marcus", "me": "Nina", "relationship": "coworker",
        "about": "Marcus, 34, a coworker on the same dev team. Dry humour, full punctuation, one text at a time.",
        "format": "whatsapp_dash", "seed": 11, "start": "2026-01-05", "days": 110, "chance": 0.55,
        "hours": (8, 18), "their_delay": (2, 40), "my_delay": (1, 15), "max_uses": 3,
        "scenes": [
            scene((THEM, [["Morning. Coffee run in 10, want anything?"]]), (ME, ["yes please, oat latte", "im good thanks!"]),
                  (THEM, [["On it."], ["Suit yourself."]]), repeat=True),
            scene((THEM, [["Heads up, the 2pm got moved to 3."], ["Standup is cancelled today, Ravi's out."]]),
                  (ME, ["thanks for the heads up", "nice"]), (THEM, [["No problem."]]), repeat=True),
            scene((THEM, [["Did you see the email from facilities? We're moving desks again."]]), (ME, ["ugh not again"]),
                  (THEM, [["Third time this year. I'm starting to take it personally."]])),
            scene((ME, ["can you look at my PR when you get a sec?", "got time to review my PR today?"]),
                  (THEM, [["Sure, after standup."], ["Yep, send me the link."]]), (ME, ["thanks!! no rush"]),
                  (THEM, [["Left a few comments. Mostly nits."], ["Looks good, approved."]])),
            scene((ME, ["lunch?", "lunch today?"]), (THEM, [["Yes. Usual place?"], ["Can't today, drowning in tickets. Tomorrow?"]]), repeat=True),
            scene((ME, ["the build is broken again"]), (THEM, [["Of course it is."], ["Was it me? Please say it wasn't me."]]),
                  (ME, ["lol it was the migration"]), (THEM, [["Phew. Okay, I'll take a look."], ["Classic. I'll ping Ravi."]])),
            scene((ME, ["how was your weekend?"]), (THEM, [["Good. Went climbing, now my arms don't work."], ["Quiet. Mostly fixed my sink. Riveting stuff."]]),
                  (ME, ["haha nice"]), (THEM, [["How about yours?"]])),
            scene((ME, ["are you going to the team dinner?"]), (THEM, [["Probably. I'll go if there's no karaoke."], ["Yes, but I'm leaving early."]])),
            scene((ME, ["running 10 min late", "train is delayed, be there in 15"]),
                  (THEM, [["No worries, I'll stall them."], ["All good, we haven't started."]]), repeat=True),
            scene((ME, ["do you know who owns the billing service?"]), (THEM, [["Pretty sure it's Hannah's team now."], ["Ask in #platform, they'll know."]])),
            scene((ME, ["can you cover my on-call friday?"]), (THEM, [["Yeah, I can do that. You owe me one."], ["Friday's tough, I'm out. Maybe ask Jess?"]])),
            scene((ME, ["i'm so tired today"]), (THEM, [["Same. Monday energy on a Wednesday."], ["Take a walk, it helps. Or more coffee."]])),
            scene((ME, ["did you finish the slides?"]), (THEM, [["Almost. Sending by 4."], ["Done, they're in the drive."]])),
            scene((ME, ["thanks for the help earlier"]), (THEM, [["Anytime."], ["Of course. That bug was nasty."]])),
            scene((ME, ["i got promoted!!"]), (THEM, [["That's great, congrats! Well deserved."], ["Finally. Drinks are on you then haha"]])),
            scene((ME, ["what do you think about the new roadmap?"]),
                  (THEM, [["Honestly? Ambitious. We'll see."], ["I like the first half. The second half is a wish list."]])),
            scene((ME, ["where's the retro doc?"]), (THEM, [["Pinned in the channel."], ["In the team folder, under Q3."]])),
            scene((ME, ["when is the release freeze?"]), (THEM, [["Thursday at 5. Don't merge anything big after that."]])),
            scene((ME, ["sorry i snapped in the meeting"]), (THEM, [["Don't worry about it. It was a frustrating meeting 🙃"]])),
        ],
    },
    # ------------------------------------------------------------------ client
    {
        "id": "priya", "name": "Priya", "me": "Alex", "relationship": "client",
        "about": "Priya, 41, Alex's client at a retail brand. Formal, full sentences, always punctuated.",
        "format": "csv", "seed": 12, "start": "2025-11-03", "days": 200, "chance": 0.5,
        "hours": (9, 17), "their_delay": (20, 240), "my_delay": (5, 60), "max_uses": 4,
        "scenes": [
            scene((THEM, [["Hi Alex, hope you're well. Do you have a few minutes this week to go over the proposal?"]]),
                  (ME, ["Hi Priya! Sure, how's Thursday at 2?"]), (THEM, [["Thursday at 2 works. I'll send an invite. Thanks!"]])),
            scene((THEM, [["Good morning Alex. Quick question about the invoice from last month."]]), (ME, ["Of course, what's up?"]),
                  (THEM, [["The total looks higher than the estimate. Could you send a breakdown when you have a moment?"]])),
            scene((THEM, [["Hi Alex, just following up on my email from Tuesday."]]), (ME, ["So sorry, replying now"]),
                  (THEM, [["No problem at all, thank you."]])),
            scene((ME, ["Hi Priya, the first draft is ready. Want me to send it over?"]),
                  (THEM, [["Yes please. Thank you, Alex."], ["That would be great. I'll review it by Friday."]]), (ME, ["Sent!"]),
                  (THEM, [["Received, thank you. I'll get back to you with feedback by end of week."]])),
            scene((ME, ["Are you free for a call tomorrow?"]),
                  (THEM, [["Tomorrow is busy for me. Would Wednesday morning work instead?"], ["Yes, I'm free after 11. Does 11:30 suit you?"]])),
            scene((ME, ["Just a heads up, the delivery will be two days late"]),
                  (THEM, [["Thanks for letting me know. Please keep me posted if anything else changes."],
                          ["Understood. Could you share the new date in writing so I can update the team?"]])),
            scene((ME, ["Did you get a chance to look at the mockups?"]),
                  (THEM, [["Yes, they look great. Just a couple of small comments, I'll email them over."], ["Not yet, apologies. I'll look this afternoon."]])),
            scene((ME, ["Happy Friday! Thanks for a great week"]), (THEM, [["Thank you, Alex! Have a lovely weekend."], ["Likewise, have a good weekend."]])),
            scene((ME, ["Can you approve the budget by Wednesday?"]),
                  (THEM, [["I'll do my best. I need sign-off from finance first."], ["Yes, I'll have it approved by Tuesday."]])),
            scene((ME, ["Sorry for the delay on this"]), (THEM, [["No worries at all."], ["That's alright, thank you for the update."]])),
            scene((ME, ["What do you think of option B?"]),
                  (THEM, [["I prefer option B, though I'd like to see it in our brand colours."], ["Option B is closer to what we had in mind. Let's discuss on Thursday."]])),
            scene((ME, ["Where should I send the final files?"]),
                  (THEM, [["Please send them to me and copy in Daniel. Thanks!"], ["The shared folder is best. I'll send you the link."]])),
            scene((ME, ["Who should I address the invoice to this month?"]), (THEM, [["Please address it to Daniel in finance this time."]])),
            scene((ME, ["We hit the milestone!"]), (THEM, [["Wonderful news, well done to the whole team!"], ["That's fantastic. Thank you for all the hard work."]])),
            scene((ME, ["Is the 15th still the deadline?"]), (THEM, [["Yes, the 15th still stands."], ["We have a little flexibility. The 18th at the latest."]])),
            scene((ME, ["Running about 5 minutes late for our call, apologies"]), (THEM, [["No problem, see you shortly."]]), repeat=True),
        ],
    },
    # ------------------------------------------------------------------ best friend
    {
        "id": "jordan", "name": "Jordan", "me": "Kai", "relationship": "best friend",
        "about": "Jordan, 21, Kai's best friend from college. All lowercase, bursts of texts, lots of 😭 and 💀.",
        "format": "whatsapp_bracket", "seed": 13, "start": "2026-01-10", "days": 100, "chance": 0.8,
        "hours": (11, 25), "their_delay": (0.2, 6), "my_delay": (0.3, 8), "max_uses": 3, "they_start": 0.6,
        "scenes": [
            scene((THEM, [["WAIT", "u will not believe what just happened"]]), (ME, ["what happened", "omg what"]),
                  (THEM, [["so i walked into class 10 min late", "and the prof goes 'nice of you to join us'", "in front of EVERYONE 😭"]]),
                  (ME, ["NOOO", "im crying"]), (THEM, [["i want to move to another country", "fr"]])),
            scene((THEM, [["are u up"]]), (ME, ["ya whats up", "barely lol"]), (THEM, [["cant sleep", "brain wont shut up"], ["thinking about life 💀"]]),
                  (ME, ["same honestly", "wanna call?"]), (THEM, [["omw to facetime u"], ["yes pls"]]), repeat=True),
            scene((THEM, [["ok i need ur opinion"]]), (ME, ["go"]), (THEM, [["do i text him back or nah", "be honest"]]),
                  (ME, ["make him wait lol", "honestly yes just do it"]), (THEM, [["ok ur right", "ur always right"], ["no bc ur so real for that"]])),
            scene((THEM, [["look at this 💀", "this is literally u"]]), (ME, ["LMAO", "rude but accurate"]), (THEM, [["im crying 😭"]]), repeat=True),
            scene((THEM, [["guess who texted me"]]), (ME, ["who", "no way"]), (THEM, [["MY EX", "after 6 months", "the audacity fr"]]),
                  (ME, ["blocked.", "do NOT answer"]), (THEM, [["already left on read 💅"]])),
            scene((ME, ["wanna get boba later?", "boba after class?"]), (THEM, [["YES", "4?"], ["omg yes ive been craving it all day"]]),
                  (ME, ["4 works"]), (THEM, [["see u ✨"]]), repeat=True),
            scene((ME, ["how did the interview go??"]), (THEM, [["i think good??", "they laughed at my joke so thats something"],
                                                           ["it was ok", "i blanked on one question 😭"]]),
                  (ME, ["proud of u either way"]), (THEM, [["ily 🥹"]])),
            scene((ME, ["sorry i didnt text back i fell asleep"]), (THEM, [["lmaooo ur such a grandma"], ["its ok i forgive u", "this time"]])),
            scene((ME, ["i got the internship!!!"]), (THEM, [["WAIT", "NO WAY", "IM SO PROUD OF U 😭😭"]]), (ME, ["we have to celebrate"]),
                  (THEM, [["drinks on me this weekend fr"]])),
            scene((ME, ["ugh today was so bad"]), (THEM, [["noo whats wrong", "do u want me to come over"], ["omg what happened", "talk to me"]]),
                  (ME, ["just stressed about exams"]), (THEM, [["ur gonna do amazing", "u always say this and then u ace it"]])),
            scene((ME, ["what are u wearing to the party"]), (THEM, [["idk the black top maybe", "or the green one", "help"]]),
                  (ME, ["green one 100%"]), (THEM, [["ok ur right", "trust"]])),
            scene((ME, ["did u finish the reading for tomorrow"]), (THEM, [["the what", "😭"], ["lol no", "who reads"]])),
            scene((ME, ["where are u"]), (THEM, [["omw", "5 min"], ["running late sorry 😭", "10 min max"]]), repeat=True),
            scene((ME, ["remember when we got lost in that parking garage"]), (THEM, [["LMAO yes", "3 hours of our lives"]])),
            scene((ME, ["thank u for yesterday fr"]), (THEM, [["always 🫶", "thats what im here for"]])),
            scene((ME, ["are u coming to sams thing saturday"]), (THEM, [["only if ur going", "i dont know anyone there"]])),
        ],
    },
    # ------------------------------------------------------------------ parent
    {
        "id": "mom", "name": "Mom", "me": "Emily", "relationship": "parent",
        "about": "Linda (\"Mom\"), 58, Emily's mother. Capitalised sentences, ellipses, 😊 and ❤️, checks in a lot.",
        "format": "csv", "seed": 14, "start": "2026-01-03", "days": 110, "chance": 0.65,
        "hours": (7, 21), "their_delay": (3, 90), "my_delay": (5, 180), "max_uses": 3, "they_start": 0.7,
        "scenes": [
            scene((THEM, [["Good morning sweetie! How did you sleep?"]]), (ME, ["good! u?", "ok, tired"]),
                  (THEM, [["Pretty good. Your dad snores like a train though 😂"], ["Get some rest today, ok? ❤️"]]), repeat=True),
            scene((THEM, [["Did you eat dinner?"]]), (ME, ["yes mom", "about to"]),
                  (THEM, [["Good! Something with vegetables I hope 😊"], ["Ok. Don't stay up too late."]]), repeat=True),
            scene((THEM, [["Call me when you can. Nothing urgent 😊"]]), (ME, ["will call after work"]), (THEM, [["Sounds good. Love you!"]]), repeat=True),
            scene((THEM, [["Your dad says hi. He finally figured out the TV remote..."]]), (ME, ["lol tell him hi", "took him long enough"]),
                  (THEM, [["Only took him three years 😂"]])),
            scene((THEM, [["Don't forget Grandma's birthday is Sunday!"]]), (ME, ["i know!! already got her a card"]),
                  (THEM, [["You're the best. She'll love it ❤️"]])),
            scene((THEM, [["Saw this article and thought of you. Make sure you're getting enough vitamin D!"]]), (ME, ["thanks mom lol"]),
                  (THEM, [["I worry 😊"]])),
            scene((ME, ["can i come home this weekend?"]), (THEM, [["Of course! You never have to ask. I'll make lasagna 😊"],
                                                               ["Yes!! Your room is ready. Let me know what train you're taking."]])),
            scene((ME, ["what's the recipe for your chili?"]), (THEM, [["I'll write it down for you. The secret is the cinnamon...", "Don't tell your aunt."]])),
            scene((ME, ["i got the job!!"]), (THEM, [["Oh honey that's wonderful!!! I'm so proud of you!! 🎉❤️"],
                                                  ["I KNEW you would! Call me tonight, I want to hear everything 😊"]])),
            scene((ME, ["feeling kind of down today"]), (THEM, [["I'm sorry sweetie. Do you want to talk? I'm here anytime ❤️"],
                                                             ["Oh no. Want me to call you on my lunch break?"]])),
            scene((ME, ["how do i get a wine stain out"]), (THEM, [["Salt right away, then cold water. Don't use hot water!", "What did you spill it on?"]])),
            scene((ME, ["sorry i missed your call"]), (THEM, [["That's ok! Just wanted to hear your voice 😊"], ["No problem. Call me back when you're free."]])),
            scene((ME, ["when is dad's appointment?"]), (THEM, [["Thursday at 10. I'll let you know how it goes 🙏"]])),
            scene((ME, ["did you see the photos i sent"]), (THEM, [["Yes! They're beautiful. Who is the girl in the blue dress?"],
                                                               ["I can't open them... how do I make them bigger?"]])),
            scene((ME, ["can you send me grandma's address?"]), (THEM, [["It's on the fridge... I'll text it to you tonight."]])),
            scene((ME, ["love you"]), (THEM, [["Love you more ❤️"]]), repeat=True),
        ],
    },
    # ------------------------------------------------------------------ talking stage
    {
        "id": "sam", "name": "Sam", "me": "Riley", "relationship": "talking stage",
        "about": "Sam, 26, someone Riley has been talking to for a month. Interested but unhurried; slow replies, asks questions back.",
        "format": "whatsapp_bracket", "seed": 15, "start": "2026-02-14", "days": 75, "chance": 0.75,
        "hours": (12, 24), "their_delay": (10, 200), "my_delay": (1, 20), "max_uses": 3, "they_start": 0.35,
        "scenes": [
            scene((THEM, [["hey you"]]), (ME, ["hey! whats up"]), (THEM, [["not much, just got home from the gym", "you?"]]),
                  (ME, ["just watching tv"]), (THEM, [["what are you watching? i need recs"]])),
            scene((THEM, [["morning :)"]]), (ME, ["good morning!"]), (THEM, [["sleep well?"]]), repeat=True),
            scene((THEM, [["random but i just saw a dog that looked exactly like yours"]]), (ME, ["lol send pic"]),
                  (THEM, [["it ran away before i could", "tragic"]])),
            scene((ME, ["wanna grab dinner friday?"]), (THEM, [["yes! where were you thinking?"], ["i'd love that", "7?"]]),
                  (ME, ["that thai place on 5th?"]), (THEM, [["perfect, see you there ;)"]])),
            scene((ME, ["i had fun last night"]), (THEM, [["me too :) we should do it again soon"], ["same, i'm still laughing about the waiter haha"]])),
            scene((ME, ["what are you up to this weekend?"]), (THEM, [["not sure yet, why? ;)"], ["visiting my sister saturday, free sunday though"]])),
            scene((ME, ["sorry for the late reply, crazy day"]), (THEM, [["no worries! everything ok?"]])),
            scene((ME, ["what are we?"]), (THEM, [["haha good question", "i like where this is going", "can we talk about it in person?"]])),
            scene((ME, ["i miss you"]), (THEM, [["aw", "miss you too"], ["stop i'm smiling at my phone"]])),
            scene((ME, ["how was work?"]), (THEM, [["long. my manager scheduled a meeting about meetings", "how was yours?"]]), repeat=True),
            scene((ME, ["are you seeing anyone else?"]), (THEM, [["not really, why?"], ["no, i'm not. are you?"]])),
            scene((ME, ["goodnight :)"]), (THEM, [["night :)", "text me tomorrow"]]), repeat=True),
            scene((ME, ["what's your favorite movie?"]), (THEM, [["probably spirited away. don't judge", "yours?"]])),
            scene((ME, ["i got promoted today!"]), (THEM, [["wait that's amazing!!", "we need to celebrate"]])),
            scene((ME, ["you up?"]), (THEM, [["haha barely", "what's up"]])),
        ],
    },
    # ------------------------------------------------------------------ ex
    {
        "id": "taylor", "name": "Taylor", "me": "Jamie", "relationship": "ex",
        "about": "Taylor, 28, Jamie's ex of four months. Guarded and brief, ends texts with a period, no emoji.",
        "format": "plain", "seed": 16, "start": "2026-01-02", "days": 160, "chance": 0.55,
        "hours": (17, 24), "their_delay": (30, 600), "my_delay": (1, 30), "max_uses": 3, "they_start": 0.15,
        "scenes": [
            scene((ME, ["hey"]), (THEM, [["hey."], ["hi."]]), (ME, ["how have you been?"]), (THEM, [["fine. you?"], ["busy. work mostly."]]), repeat=True),
            scene((ME, ["i miss you"]), (THEM, [["i know."], ["jamie."]]), (ME, ["sorry. i know"]), (THEM, [["it's okay. i just can't do this right now."]])),
            scene((ME, ["can i come get my stuff this weekend?"]), (THEM, [["sure. saturday after 2."], ["i'll leave it with my roommate."]])),
            scene((ME, ["do you ever think about us?"]), (THEM, [["sometimes.", "but we made the right call."]])),
            scene((ME, ["happy birthday"]), (THEM, [["thanks. that's nice of you."]])),
            scene((ME, ["are you seeing someone?"]), (THEM, [["does it matter?"], ["i'd rather not talk about that."]])),
            scene((ME, ["i heard our song on the radio"]), (THEM, [["oh.", "that one gets me too."]])),
            scene((ME, ["can we talk?"]), (THEM, [["about what?"], ["i don't know if that's a good idea."]])),
            scene((ME, ["i got the job i told you about"]), (THEM, [["that's great. congrats. you deserve it."]])),
            scene((ME, ["sorry for how things ended"]), (THEM, [["me too.", "thanks for saying that."]])),
            scene((ME, ["do you still have my grey hoodie?"]), (THEM, [["yeah. i'll drop it off."]])),
            scene((ME, ["remember the cabin trip?"]), (THEM, [["yeah.", "that was a good weekend."]])),
            scene((ME, ["goodnight"]), (THEM, [["night."]]), repeat=True),
            scene((THEM, [["hey. your mail is still coming here."]]), (ME, ["oh sorry, i'll update it"]), (THEM, [["ok."]])),
            scene((THEM, [["saw your sister at the store. she says hi."]]), (ME, ["aw tell her hi back"]), (THEM, [["will do."]])),
        ],
    },
    # ------------------------------------------------------------------ sibling
    {
        "id": "mateo", "name": "Mateo", "me": "Sofia", "relationship": "sibling",
        "about": "Mateo, 19, Sofia's little brother. Teasing, lowercase, laughs with \"jaja\", asks for favours.",
        "format": "json", "seed": 17, "start": "2026-01-08", "days": 120, "chance": 0.45,
        "hours": (10, 24), "their_delay": (1, 45), "my_delay": (2, 60), "max_uses": 3, "they_start": 0.5,
        "scenes": [
            scene((THEM, [["bro"]]), (ME, ["what"]), (THEM, [["mom is asking if you're coming sunday", "say yes or she'll call you 5 times"]]),
                  (ME, ["yes im coming"]), (THEM, [["good. bring the good chips this time"]]), repeat=True),
            scene((THEM, [["can i borrow your car saturday"]]), (ME, ["what for"]), (THEM, [["date 😎"], ["to drive it", "obviously"]]),
                  (ME, ["fine but fill the tank"]), (THEM, [["deal", "ur the best sister", "sometimes"]])),
            scene((THEM, [["jajaja look at this pic of you from 2012"]]), (ME, ["DELETE THAT"]), (THEM, [["already sent it to the family chat"]])),
            scene((ME, ["happy birthday baby bro"]), (THEM, [["thanks old lady jaja"], ["gracias 🙏", "where's my present"]])),
            scene((ME, ["did you finish your college apps?"]), (THEM, [["almost", "dont tell mom"], ["yes mom", "jk yes i did"]])),
            scene((ME, ["how was the game?"]), (THEM, [["WE WON", "scored twice btw"], ["we lost", "ref was blind"]]), repeat=True),
            scene((ME, ["can you send me abuela's tamales recipe"]), (THEM, [["ask mom", "i only know how to eat them jaja"]])),
            scene((ME, ["i got the apartment!!"]), (THEM, [["no way", "congrats sis", "do i get a key"]])),
            scene((ME, ["are you ok? mom said you were sick"]), (THEM, [["ya just a cold", "im fine dont worry"]])),
            scene((ME, ["remember when you broke the window with a baseball"]), (THEM, [["that was YOU", "i was framed"]])),
            scene((ME, ["thanks for helping me move"]), (THEM, [["anytime", "you owe me pizza tho"]])),
            scene((ME, ["what do you want for christmas"]), (THEM, [["money", "jk", "ok not jk"]])),
            scene((ME, ["where are you? mom is worried"]), (THEM, [["at marcos house", "chill jaja"], ["omw home", "tell her im alive"]]), repeat=True),
        ],
    },
    # ------------------------------------------------------------------ friend
    {
        "id": "keisha", "name": "Keisha", "me": "Dee", "relationship": "friend",
        "about": "Keisha, 44, Dee's friend from church. Long voice-to-text messages, warm, punctuated, a 😂 here and there.",
        "format": "whatsapp_dash", "seed": 18, "start": "2025-10-06", "days": 210, "chance": 0.45,
        "hours": (7, 22), "their_delay": (15, 300), "my_delay": (5, 120), "max_uses": 4, "they_start": 0.55,
        "scenes": [
            scene((THEM, [["Girl I have been meaning to call you all week but between work and the kids' practice schedule I have not had one minute to myself. How are you doing? How's the new job treating you?"]]),
                  (ME, ["omg same, it's been a lot. job is good though!"]),
                  (THEM, [["I'm so glad to hear that. You deserve a place that appreciates you. We need to do dinner soon, I miss your face 😂"]])),
            scene((THEM, [["Good morning sunshine! Just wanted to say I'm thinking about you and I hope your day is as wonderful as you are 😊"]]),
                  (ME, ["aw keisha you too!!"]), (THEM, [["Have a blessed day love"]]), repeat=True),
            scene((ME, ["are you free saturday for brunch?"]),
                  (THEM, [["Saturday morning I have Jaylen's game at 9 but I could do 11:30 if that works for you. The place by the park?"],
                          ["Yes ma'am! I need a mimosa and a long talk lol"]])),
            scene((ME, ["how did the doctor's appointment go?"]),
                  (THEM, [["It went fine thank God. They said everything looks normal, they just want me to come back in six months for a follow up. Thank you for checking on me, that means a lot."]])),
            scene((ME, ["sorry I've been so quiet lately"]),
                  (THEM, [["No need to apologize at all. Life gets busy and I know you've had a lot going on. I'm always here whenever you're ready to talk ❤️"]])),
            scene((ME, ["i got the promotion!!"]),
                  (THEM, [["WHAT! Girl I am so proud of you I literally screamed in the car 😂 You worked so hard for this. We are celebrating, no excuses."]])),
            scene((ME, ["what should i get my mom for her birthday"]),
                  (THEM, [["Honestly you can't go wrong with something personal. Last year I made my mom a photo book of all the family trips and she cried. Or a spa day, everybody loves a spa day lol"]])),
            scene((ME, ["ugh my landlord is raising the rent again"]),
                  (THEM, [["Are you serious? Again? That's the second time this year. You should look into what the rules are in your area because I don't think they can just keep doing that without notice."]])),
            scene((ME, ["did you watch the finale??"]), (THEM, [["Don't you DARE spoil it, I'm watching it tonight after the kids go to bed lol"]])),
            scene((ME, ["happy birthday!!"]), (THEM, [["Thank you love!! Another year older and wiser lol. Thank you for always being there for me 😊"]])),
            scene((ME, ["where did you get that lamp in your living room"]),
                  (THEM, [["Target believe it or not lol. It was on clearance too, I'll send you the link when I find it."]])),
            scene((ME, ["can you pick me up from the airport friday?"]),
                  (THEM, [["Of course! What time does your flight land? Send me the flight number and I'll track it."]])),
            scene((ME, ["running late, be there in 10"]), (THEM, [["No rush love, I just got here myself lol"]]), repeat=True),
        ],
    },
]


# ---- playing the scenes -------------------------------------------------------------

def _minutes(rng: random.Random, lo: float, hi: float) -> float:
    """Skewed toward the quick end, like real reply times."""
    return lo + (hi - lo) * rng.random() ** 2.2


def play(person: dict) -> list[tuple[datetime, str, str]]:
    rng = random.Random(person["seed"])
    uses = {i: 0 for i in range(len(person["scenes"]))}
    they_start = person.get("they_start", 0.4)
    day0 = datetime.fromisoformat(person["start"])
    out: list[tuple[datetime, str, str]] = []
    for d in range(person["days"]):
        if rng.random() > person["chance"]:
            continue
        theirs_first = rng.random() < they_start
        pool = [i for i, s in enumerate(person["scenes"])
                if (s["steps"][0][0] == THEM) == theirs_first and (s["repeat"] or uses[i] < person["max_uses"])]
        if not pool:
            pool = [i for i, s in enumerate(person["scenes"]) if s["repeat"]]
        # Prefer scenes not used yet, so the history covers more situations.
        fresh = [i for i in pool if uses[i] == 0]
        i = rng.choice(fresh if fresh and rng.random() < 0.7 else pool)
        uses[i] += 1
        lo, hi = person["hours"]
        t = day0 + timedelta(days=d, hours=rng.uniform(lo, hi - 1))
        prev = None
        for who, options in person["scenes"][i]["steps"]:
            pick = rng.choice(options)
            if prev is not None:
                delay = person["their_delay"] if who == THEM else person["my_delay"]
                t += timedelta(minutes=_minutes(rng, *delay))
            if who == ME:
                out.append((t, person["me"], pick))
            else:
                for j, bubble in enumerate(pick):
                    if j:
                        t += timedelta(seconds=rng.uniform(4, 40))
                    out.append((t, person["name"], bubble))
            prev = who
    return out


# ---- writing each export format --------------------------------------------------------

def _us_date(t: datetime) -> str:
    return f"{t.month}/{t.day}/{t.strftime('%y')}"


def write(person: dict, rows: list[tuple[datetime, str, str]]) -> tuple[str, str]:
    fmt = person["format"]
    if fmt == "whatsapp_bracket":
        lines = [f"[{_us_date(t)}, {t.strftime('%I:%M:%S %p').lstrip('0')}] {who}: {text}" for t, who, text in rows]
        return "\n".join(lines) + "\n", ".txt"
    if fmt == "whatsapp_dash":
        lines = [f"{_us_date(t)}, {t.strftime('%H:%M')} - {who}: {text}" for t, who, text in rows]
        return "\n".join(lines) + "\n", ".txt"
    if fmt == "plain":
        return "\n".join(f"{who}: {text}" for _, who, text in rows) + "\n", ".txt"
    if fmt == "csv":  # an iMessage-exporter style CSV
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        w.writerow(["timestamp", "sender", "text"])
        for t, who, text in rows:
            w.writerow([t.isoformat(timespec="seconds"), who, text])
        return buf.getvalue(), ".csv"
    if fmt == "json":  # a Telegram-export style JSON
        msgs = [{"id": n, "type": "message", "date": t.isoformat(timespec="seconds"), "from": who, "text": text}
                for n, (t, who, text) in enumerate(rows, 1)]
        return json.dumps({"name": person["me"] + " & " + person["name"], "type": "personal_chat", "messages": msgs},
                          ensure_ascii=False, indent=1) + "\n", ".json"
    raise ValueError(fmt)


FORMAT_NAMES = {"whatsapp_bracket": "WhatsApp (iPhone)", "whatsapp_dash": "WhatsApp (Android)", "plain": "plain \"Name: text\"",
                "csv": "iMessage CSV", "json": "Telegram JSON"}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = [{
        "id": "dana", "name": "Dana", "target": "Dana", "me": "Alex", "relationship": "boss",
        "about": "Dana, Alex's manager. Short, lowercase, bursts of two texts, a 👍 or 🙌 now and then.",
        "file": "examples/sample_chat.txt", "format": "WhatsApp (iPhone)",
    }]
    for person in PEOPLE:
        rows = play(person)
        body, ext = write(person, rows)
        path = OUT / f"{person['id']}{ext}"
        path.write_text(body, encoding="utf-8")
        manifest.append({
            "id": person["id"], "name": person["name"], "target": person["name"], "me": person["me"],
            "relationship": person["relationship"], "about": person["about"],
            "file": str(path.relative_to(ROOT)), "format": FORMAT_NAMES[person["format"]],
        })
    # Count what each file really holds, through the same parser the app uses.
    import sys
    sys.path.insert(0, str(ROOT))
    from tools.chat_parser import parse_file
    for entry in manifest:
        msgs = parse_file(ROOT / entry["file"])
        entry["messages"] = len(msgs)
        entry["their_messages"] = sum(m.sender == entry["target"] for m in msgs)
    (OUT / "samples.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for e in manifest:
        print(f"{e['id']:8s} {e['relationship']:14s} {e['format']:22s} {e['messages']:4d} messages ({e['their_messages']} from {e['name']})")


if __name__ == "__main__":
    main()
