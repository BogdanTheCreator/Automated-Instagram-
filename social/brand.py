"""
brand.py — niche / brand strategy presets and the creative frameworks that make
the generated content feel intentional instead of generic.

A `Brand` bundles everything that defines an account's identity: voice, visual
palette (used by the animated preview + the ffmpeg renderer), reusable hook and
CTA frameworks, a curated hashtag bank organised by reach tier, and topic seeds
for a content calendar.

THE RECOMMENDED NICHE
---------------------
`ai_income` is the default. Rationale: it is faceless-friendly (no camera, fully
automatable), evergreen *and* news-fed (so you never run out of ideas), and it
has the strongest monetisation surface of any beginner niche — affiliate links
to AI tools, your own digital products/templates, and brand sponsorships. It
also matches the creator's own motivation (building income outside a 9-to-5),
which reads as authentic instead of manufactured.

`privacy` is the differentiated alternative: less saturated, genuinely
important, evergreen, and equally faceless. The engine supports any topic, so
you can A/B two accounts with the same pipeline.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class Palette:
    """Colours used by the animated preview and the ffmpeg renderer."""
    bg: str          # scene background
    bg2: str         # gradient partner
    text: str        # primary caption text
    accent: str      # highlight / keyword colour
    accent2: str     # secondary highlight
    subtle: str      # progress bar / chrome


@dataclass
class Brand:
    key: str
    display_name: str
    handle_ideas: List[str]
    tagline: str
    # Voice
    voice: str                       # short description of tone
    tts_voice: str                   # provider-neutral voice id hint
    # Visual identity
    palette: Palette
    font_family: str
    # Creative frameworks (templates use {topic}, {point}, {n})
    hook_templates: List[str]
    cta_templates: List[str]
    point_lead_ins: List[str]
    payoff_templates: List[str]
    caption_openers: List[str]
    # Distribution
    hashtag_bank: Dict[str, List[str]]   # tier -> tags  (broad/mid/niche/branded)
    topic_seeds: List[str]
    best_post_times_utc: List[str] = field(default_factory=lambda: ["13:00", "17:00", "23:00"])
    series_name: str = "Daily Drop"
    # Month-planning fuel: pillars group the calendar, themes are concrete
    # sub-topics combined with formats to produce varied daily prompts.
    content_pillars: List[str] = field(default_factory=list)
    themes: List[str] = field(default_factory=list)
    # --- Long-form / storytelling support (optional; defaults keep short-form
    #     "tips" presets working unchanged) ------------------------------------
    # niche_kind selects the generator: "tips" = short value videos (Reels),
    # "story" = long-form narrated storytelling (8-12 min YouTube videos).
    niche_kind: str = "tips"
    # YouTube title frameworks. Use {t} for the title-cased topic. When empty,
    # the engine falls back to a generic set.
    title_templates: List[str] = field(default_factory=list)
    # Thumbnail concepts (mobile-first). {topic} is substituted if present.
    thumbnail_concepts: List[str] = field(default_factory=list)
    # Default length (seconds) used when niche_kind == "story" and the caller
    # does not pass an explicit duration. 600s ~= 10 minutes.
    default_long_seconds: int = 600


# --------------------------------------------------------------------------- #
# Preset library
# --------------------------------------------------------------------------- #

_AI_INCOME = Brand(
    key="ai_income",
    display_name="AI Income Lab",
    handle_ideas=["@ai.income.lab", "@the.ai.leverage", "@quit.the.cubicle", "@automate.or.die"],
    tagline="Build income with AI before everyone else figures it out.",
    voice="confident, fast, slightly contrarian; talks to a smart friend who is tired of the 9-5",
    tts_voice="male_energetic",
    palette=Palette(bg="#0B0F1A", bg2="#13203B", text="#F5F7FF", accent="#27E5B4", accent2="#7C5CFF", subtle="#33415C"),
    font_family="Inter, 'Helvetica Neue', Arial, sans-serif",
    hook_templates=[
        "Stop trading hours for money. {topic} changes the math.",
        "Nobody is talking about this: {topic}.",
        "I wish I knew this about {topic} a year ago.",
        "{topic} — and why your 9-to-5 should be scared.",
        "Most people use AI wrong. Here's {topic} done right.",
        "This is how broke people stay broke: ignoring {topic}.",
    ],
    cta_templates=[
        "Follow for the AI playbook they don't teach you.",
        "Save this before the algorithm buries it.",
        "Comment 'AI' and I'll send you the toolkit.",
        "Follow @ — one AI money move a day.",
    ],
    point_lead_ins=[
        "Step {n}:",
        "Move {n}:",
        "Here's the part nobody mentions —",
        "The leverage play:",
        "Most people skip this:",
    ],
    payoff_templates=[
        "Do this for 30 days and you'll have a skill the market actually pays for.",
        "That's the whole edge: small AI leverage, compounded daily.",
        "This is how you turn one prompt into an asset that earns while you sleep.",
    ],
    caption_openers=[
        "Save this — your future self (the one not stuck in a cubicle) will thank you.",
        "The 9-to-5 isn't the only option. Here's proof:",
        "AI won't take your job. Someone using AI will. Be that someone.",
    ],
    hashtag_bank={
        "broad": ["#ai", "#artificialintelligence", "#sidehustle", "#entrepreneur", "#passiveincome"],
        "mid": ["#aitools", "#makemoneyonline", "#sidehustleideas", "#digitalproducts",
                "#automation", "#solopreneur", "#chatgpt", "#aiautomation", "#onlinebusiness"],
        "niche": ["#aisidehustle", "#aiincome", "#promptengineering", "#facelessincome",
                  "#aimarketing", "#nocode", "#aiforbusiness", "#buildinpublic", "#aiworkflow"],
        "branded": ["#aiincomelab"],
    },
    topic_seeds=[
        "3 free AI tools that replace a marketing team",
        "the $0 faceless content workflow",
        "how to sell a digital product you make with AI in a weekend",
        "AI automations that save 10 hours a week",
        "prompt that turns one idea into 30 posts",
        "the AI side hustle nobody is saturating yet",
    ],
    series_name="AI Money Move",
    content_pillars=["AI tools", "faceless content", "selling digital products", "automations", "mindset"],
    themes=[
        "AI tools that replace freelancers", "faceless YouTube automation",
        "writing a month of posts with one prompt", "AI voiceovers for videos",
        "selling Notion templates", "AI logo and brand kits", "automating customer emails",
        "turning a PDF into a paid product", "AI for cold outreach that isn't spammy",
        "building a lead magnet in an afternoon", "AI image generation for ads",
        "repurposing one video into ten posts", "AI spreadsheets that do the work",
        "chatbots that qualify leads", "AI research for niche selection",
        "pricing your first digital product", "the $0 starter tool stack",
        "AI scripts for short-form video", "automating your invoicing",
        "turning skills into an online course",
    ],
)

_PRIVACY = Brand(
    key="privacy",
    display_name="Stay Private",
    handle_ideas=["@stay.private", "@delete.the.data", "@privacy.pilot", "@your.data.matters"],
    tagline="Take your data back, one setting at a time.",
    voice="calm, trustworthy, no fear-mongering; practical security for normal people",
    tts_voice="neutral_calm",
    palette=Palette(bg="#0A0E12", bg2="#0F2027", text="#EAF6F6", accent="#36D399", accent2="#38BDF8", subtle="#2B3640"),
    font_family="'IBM Plex Sans', system-ui, Arial, sans-serif",
    hook_templates=[
        "Your phone is leaking this right now: {topic}.",
        "Delete this in 30 seconds: {topic}.",
        "They're selling your data. Here's how to stop it — {topic}.",
        "{topic} — the privacy setting almost everyone misses.",
        "Big Tech hopes you never learn {topic}.",
    ],
    cta_templates=[
        "Follow for one privacy fix a day.",
        "Save this and do it tonight.",
        "Share with someone who overshares online.",
        "Follow @ — take your data back.",
    ],
    point_lead_ins=["Step {n}:", "Fix {n}:", "Then this:", "The setting to change:", "Most people miss this:"],
    payoff_templates=[
        "Five minutes now, far less of you for sale later.",
        "That's a smaller footprint and a calmer inbox.",
        "Privacy isn't paranoia — it's hygiene.",
    ],
    caption_openers=[
        "Save this — future you (with way less spam) says thanks.",
        "You don't have to be a hacker to be private. Start here:",
        "Two minutes today buys you real peace of mind:",
    ],
    hashtag_bank={
        "broad": ["#privacy", "#cybersecurity", "#technology", "#security", "#tech"],
        "mid": ["#dataprivacy", "#onlineprivacy", "#infosec", "#digitalprivacy", "#cybersecuritytips",
                "#privacymatters", "#opsec", "#datasecurity", "#techtips"],
        "niche": ["#privacytips", "#deletefacebook", "#degoogle", "#privacyfirst", "#securitytips",
                  "#privacytools", "#dataprotection", "#surveillancecapitalism", "#privacymindset"],
        "branded": ["#stayprivate"],
    },
    topic_seeds=[
        "the iPhone setting that tracks you everywhere",
        "how to delete yourself from data broker sites",
        "why you should use a password manager today",
        "the browser extensions that stop trackers",
        "how to lock down your Google account in 5 minutes",
    ],
    series_name="Privacy Fix",
    content_pillars=["phone settings", "data brokers", "passwords", "browsing", "accounts"],
    themes=[
        "iPhone location tracking settings", "Android ad personalization",
        "removing yourself from data broker sites", "password managers explained",
        "two-factor authentication done right", "private browsers vs Chrome",
        "blocking trackers with extensions", "locking down your Google account",
        "what your apps actually collect", "private search engines",
        "email aliases to stop spam", "VPNs: when they help and when they don't",
        "deleting old accounts you forgot", "securing your home WiFi",
        "phishing red flags everyone misses", "metadata hidden in your photos",
        "encrypted messaging apps", "credit freezes to stop identity theft",
        "smart TV and IoT privacy", "checking if your data was breached",
    ],
)

_MONEY = Brand(
    key="money",
    display_name="Money Mechanics",
    handle_ideas=["@money.mechanics", "@the.money.blueprint", "@cashflow.club"],
    tagline="The money lessons school skipped.",
    voice="clear, encouraging, no jargon; financial literacy for people in their 20s-30s",
    tts_voice="female_warm",
    palette=Palette(bg="#0C0A06", bg2="#241B0E", text="#FFF8EC", accent="#F4C04E", accent2="#46D17F", subtle="#3A2F1E"),
    font_family="'Sora', 'Helvetica Neue', Arial, sans-serif",
    hook_templates=[
        "School never taught you this: {topic}.",
        "Broke at 30 is a choice once you know {topic}.",
        "{topic} — the money move that pays you back for life.",
        "Rich people quietly do this: {topic}.",
        "Your bank hopes you ignore {topic}.",
    ],
    cta_templates=[
        "Follow for the money lessons school skipped.",
        "Save this — your future bank account will thank you.",
        "Comment 'PLAN' for the free breakdown.",
        "Follow @ for one money move a day.",
    ],
    point_lead_ins=["Step {n}:", "Rule {n}:", "Here's the trick:", "The part that matters:", "Do this first:"],
    payoff_templates=[
        "Small, boring, repeated — that's how wealth is actually built.",
        "That's money working for you instead of the other way around.",
        "Start with $10. The habit is worth more than the amount.",
    ],
    caption_openers=[
        "Save this — it's the lesson that pays for itself.",
        "Nobody is coming to fix your finances. Good news: you can.",
        "Money is a skill, not a personality trait. Here's a rep:",
    ],
    hashtag_bank={
        "broad": ["#money", "#finance", "#personalfinance", "#investing", "#wealth"],
        "mid": ["#financialfreedom", "#moneytips", "#budgeting", "#financialliteracy", "#investingtips",
                "#moneymanagement", "#savingmoney", "#wealthbuilding", "#financialeducation"],
        "niche": ["#moneymindset", "#moneyhabits", "#financetips", "#debtfreejourney", "#firemovement",
                  "#moneymechanics", "#financeforbeginners", "#budgetingtips", "#sidehustlemoney"],
        "branded": ["#moneymechanics"],
    },
    topic_seeds=[
        "the 50/30/20 budget that actually works",
        "how compound interest makes you rich slowly",
        "index funds explained in 30 seconds",
        "the emergency fund mistake everyone makes",
        "how to pay off debt without feeling broke",
    ],
    series_name="Money Move",
    content_pillars=["budgeting", "saving", "investing", "debt", "mindset"],
    themes=[
        "the 50/30/20 budget", "building a first emergency fund",
        "compound interest explained simply", "index funds for beginners",
        "paying off debt without feeling broke", "automating your savings",
        "the difference between good and bad debt", "credit scores demystified",
        "Roth vs traditional retirement accounts", "lifestyle creep and how to beat it",
        "sinking funds for big expenses", "the latte factor myth",
        "negotiating a raise with data", "high-yield savings accounts",
        "dollar-cost averaging", "the order to pay things in",
        "tracking net worth monthly", "cutting subscriptions you forgot",
        "the real cost of buy-now-pay-later", "first $1000 invested, step by step",
    ],
)

_LONGEVITY = Brand(
    key="longevity",
    display_name="Health Span",
    handle_ideas=["@health.span", "@the.longevity.lab", "@age.slower"],
    tagline="Add good years, not just years.",
    voice="evidence-based, calm, motivating; cites the idea not medical advice",
    tts_voice="neutral_calm",
    palette=Palette(bg="#06100C", bg2="#0E2A22", text="#EAFBF2", accent="#5EEAD4", accent2="#A3E635", subtle="#23362E"),
    font_family="'Manrope', system-ui, Arial, sans-serif",
    hook_templates=[
        "This free habit may add years to your life: {topic}.",
        "{topic} — what the longest-lived people do daily.",
        "Stop wasting money on supplements. Start with {topic}.",
        "Your future self is begging you to learn {topic}.",
        "The science is clear on {topic}.",
    ],
    cta_templates=[
        "Follow for one longevity habit a day.",
        "Save this and try it for a week.",
        "Send this to someone you want around longer.",
        "Follow @ — age slower, on purpose.",
    ],
    point_lead_ins=["Step {n}:", "Habit {n}:", "The research says:", "Start here:", "Most people skip this:"],
    payoff_templates=[
        "Tiny, daily, consistent — that's how health span is built.",
        "No gadget required. Just repetition.",
        "Not medical advice — talk to your doctor — but the pattern is striking.",
    ],
    caption_openers=[
        "Save this — your 80-year-old self is watching.",
        "You can't buy more time, but you can earn better years:",
        "Longevity isn't a pill. It's a routine. Here's one rep:",
    ],
    hashtag_bank={
        "broad": ["#health", "#longevity", "#wellness", "#fitness", "#healthylifestyle"],
        "mid": ["#healthspan", "#healthyhabits", "#biohacking", "#wellnesstips", "#healthyaging",
                "#nutrition", "#sleephealth", "#mobility", "#healthtips"],
        "niche": ["#longevitytips", "#bluezones", "#metabolichealth", "#vo2max", "#zone2",
                  "#agewell", "#healthspanlab", "#longevitymindset", "#preventivehealth"],
        "branded": ["#healthspan"],
    },
    topic_seeds=[
        "the 2-minute habit linked to a longer life",
        "why zone 2 cardio matters more than you think",
        "the protein target most people miss",
        "how sleep quietly controls your lifespan",
        "the strength test that predicts longevity",
    ],
    series_name="Longevity Habit",
    content_pillars=["movement", "nutrition", "sleep", "stress", "prevention"],
    themes=[
        "zone 2 cardio for beginners", "the protein target most people miss",
        "why grip strength predicts longevity", "morning sunlight and your sleep",
        "the daily step count that matters", "strength training after 40",
        "fiber and your gut microbiome", "VO2 max and lifespan",
        "the case for walking after meals", "magnesium and sleep quality",
        "breathing exercises for stress", "the Blue Zones daily habits",
        "why muscle is the organ of longevity", "hydration myths debunked",
        "balance tests you can do at home", "the sitting-rising test",
        "limiting ultra-processed foods", "consistent sleep schedule benefits",
        "social connection and lifespan", "cold and heat exposure basics",
    ],
)


_BETRAYAL_REVENGE = Brand(
    key="betrayal_revenge",
    display_name="Betrayal & Revenge Stories",
    handle_ideas=["@quiet.revenge.stories", "@the.betrayal.files",
                  "@served.cold.stories", "@they.chose.wrong"],
    tagline="Betrayal, karma, and the quiet revenge that follows.",
    voice=("a grounded, slow-burn storytime narrator; tense and empathetic, never "
           "tabloid or cheesy; builds believable tension to a satisfying, earned payoff"),
    tts_voice="neutral_calm",
    palette=Palette(bg="#0B0B0F", bg2="#1C0E14", text="#F3EEF2",
                    accent="#E4584C", accent2="#C9A36B", subtle="#33262C"),
    font_family="Georgia, 'Times New Roman', 'Playfair Display', serif",
    # Hooks double as cold-open lines and thumbnail-adjacent angles. {topic} is
    # the cleaned prompt (e.g. "my sister forged our mother's will").
    hook_templates=[
        "They thought I'd never find out about {topic}. They were wrong.",
        "I trusted them completely — until {topic}.",
        "Everyone said to let it go. But {topic}? That I could not forgive.",
        "{Topic}. So I stayed quiet, and I started paying attention.",
        "The day I learned the truth about {topic}, everything changed.",
        "They betrayed the wrong person. This is the story of {topic}.",
    ],
    cta_templates=[
        "If this story hit home, subscribe — there's a new one every week.",
        "Subscribe for more real-feeling betrayal and revenge stories.",
        "Hit subscribe, then tell me in the comments: did they deserve it?",
        "Follow for the stories people are too afraid to tell.",
    ],
    point_lead_ins=[
        "Then this happened:", "Here's where it turned:", "What they didn't know:",
        "The part that still gets me:", "And then everything shifted:",
    ],
    payoff_templates=[
        "By the time they understood what was happening, it was already too late.",
        "I never had to raise my voice. The truth did all the damage.",
        "Karma didn't knock. It walked in, sat down, and made itself at home.",
    ],
    caption_openers=[
        "Some betrayals don't get loud. They get even.",
        "The best revenge is letting the truth arrive right on schedule.",
        "Save this one — the ending earns it.",
    ],
    # Reused as the YouTube tag bank (the '#' is stripped for tags).
    hashtag_bank={
        "broad": ["#storytime", "#revenge", "#betrayal", "#drama", "#truestory"],
        "mid": ["#redditstories", "#cheatingstories", "#revengestory", "#familydrama",
                "#karma", "#storytimevideo", "#relationshipdrama", "#reddit"],
        "niche": ["#quietrevenge", "#prorevenge", "#cheatingspouse", "#inheritancedrama",
                  "#workplacebetrayal", "#maliciouscompliance", "#narcissist", "#cheatingpartner"],
        "branded": ["#thebetrayalfiles"],
    },
    topic_seeds=[
        "my husband's affair with my best friend",
        "the business partner who secretly drained our company",
        "my sister forged our mother's will",
        "the coworker who took credit for my work for years",
        "my fiance's secret second family",
        "the landlord who tried to keep our deposit and lied about it",
    ],
    series_name="The Betrayal Files",
    best_post_times_utc=["18:00", "22:00", "00:00"],
    content_pillars=["cheating & affairs", "family betrayal", "workplace betrayal",
                     "inheritance revenge", "quiet / delayed justice", "karma"],
    themes=[
        "a cheating spouse exposed at the worst possible moment",
        "a best friend who betrayed a private confidence",
        "a sibling who quietly stole an inheritance",
        "parents who played favorites for decades",
        "a business partner who forged signatures",
        "a boss who stole an employee's idea",
        "a coworker who sabotaged a promotion",
        "in-laws who tried to break up a marriage",
        "a landlord who refused to return a deposit",
        "an ex who spread lies after the breakup",
        "a friend who copied a business and undercut it",
        "a relative who borrowed money and vanished",
        "a wedding nearly ruined by a jealous sibling",
        "a fake friend who used someone for years",
        "a stepparent who hid a will",
        "a manager who took credit, then got exposed",
        "a cheating partner caught by one small mistake",
        "a scammer who targeted the wrong grandmother",
        "a coworker who framed someone and got caught",
        "a neighbor who crossed a line and regretted it",
    ],
    niche_kind="story",
    title_templates=[
        "{t}",
        "They Never Thought I'd Find Out",
        "{t} — I Waited for the Right Moment",
        "I Stayed Quiet. Then Everything Changed.",
        "The Truth About {t}",
        "How It All Came Back Around",
    ],
    thumbnail_concepts=[
        "Split frame: a warm family photo torn down the middle. Overlay 2 words "
        "like \"SHE LIED\" in bold condensed type, red accent. High contrast for mobile.",
        "A hand hiding a phone behind a back, screen glowing. Overlay \"THE TEXT\". "
        "Dark, cinematic, single light source.",
        "An empty chair at a dinner table with one place setting removed. Overlay "
        "\"NOT INVITED\". Moody, lots of negative space so it reads at thumbnail size.",
    ],
    default_long_seconds=600,
)


PRESETS: Dict[str, Brand] = {
    b.key: b for b in (_AI_INCOME, _PRIVACY, _MONEY, _LONGEVITY, _BETRAYAL_REVENGE)
}

DEFAULT_BRAND = "ai_income"


def get_brand(key: str) -> Brand:
    key = (key or DEFAULT_BRAND).strip().lower()
    if key not in PRESETS:
        raise KeyError(
            f"Unknown brand '{key}'. Available: {', '.join(sorted(PRESETS))}"
        )
    return PRESETS[key]


def list_brands() -> List[str]:
    return sorted(PRESETS)
