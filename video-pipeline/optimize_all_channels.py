#!/usr/bin/env python3
"""Audit and optimize all brand channel metadata for search and discovery.

For each channel:
1. Fetch current description, keywords, country, language
2. Generate SEO-optimized description, keywords, and tags
3. Update via YouTube API

Optimizations based on Richard's UgenticIQ profile:
- 3-Second Rule: Description must communicate value immediately
- Search-first: Keywords people actually search for
- Conversion clarity: Clear CTA in every description
"""

import json
import os
import sys
import time
import urllib.parse
from urllib.request import Request, urlopen
from urllib.error import HTTPError

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CHANNEL_TOKENS_PATH = os.path.join(BASE_DIR, "channel_tokens.json")
PROGRESS_PATH = os.path.join(BASE_DIR, "output", "channel_optimization_progress.json")
os.makedirs(os.path.join(BASE_DIR, "output"), exist_ok=True)

AMAZON_AFFILIATE_TAG = "richstudio0f-20"
AMAZON_STORE_ID = "7193294712"

# Channel optimization data: description, keywords, tags
CHANNEL_OPTIMIZATIONS = {
    "RichTech": {
        "description": (
            "RichTech brings you the latest in technology, gadgets, and AI tools "
            "that actually matter. No fluff, no hype — just honest breakdowns of "
            "the tech that saves you time and money.\n\n"
            "What you'll find here:\n"
            "- Budget-friendly tech gadgets that are worth every penny\n"
            "- AI tool reviews and tutorials for productivity\n"
            "- Honest tech comparisons (no sponsored bias)\n"
            "- Future tech trends explained simply\n\n"
            "New videos every week. Subscribe and hit the bell so you never miss a drop.\n\n"
            "Recommended products: https://amzn.to/3ZPDMFn\n"
            "Full store: https://www.amazon.com/shop/{store}?tag={tag}\n\n"
            "As an Amazon Associate, I earn from qualifying purchases."
        ),
        "keywords": "tech gadgets AI tools technology review budget tech 2026 best apps productivity software tech tips future tech smart home",
        "topic_categories": [],
    },
    "RichHorror": {
        "description": (
            "True horror stories. Unsolved mysteries. Haunted places you should NEVER visit alone.\n\n"
            "RichHorror delivers spine-chilling content with cinematic narration "
            "and atmospheric storytelling. Every story is researched, every detail verified.\n\n"
            "What you'll find here:\n"
            "- True horror stories that will keep you up at night\n"
            "- Unsolved mysteries that still haunt investigators\n"
            "- The most haunted locations on Earth\n"
            "- Dark history and unexplained phenomena\n\n"
            "New stories every week. Subscribe if you dare.\n\n"
            "#Horror #TrueHorror #UnsolvedMysteries #HauntedPlaces #ScaryStories"
        ),
        "keywords": "horror true horror stories unsolved mysteries haunted places scary stories creepy paranormal true crime dark history ghost stories",
    },
    "RichMind": {
        "description": (
            "Your mind is more powerful — and more dangerous — than you think.\n\n"
            "RichMind explores the hidden psychology behind human behavior: "
            "manipulation tactics, body language secrets, cognitive biases, "
            "and the dark side of the human mind.\n\n"
            "What you'll find here:\n"
            "- Dark psychology tricks manipulators use on you daily\n"
            "- Body language secrets to read anyone like a book\n"
            "- The psychology behind overthinking, anxiety, and self-sabotage\n"
            "- Mind hacks for confidence, focus, and mental clarity\n\n"
            "Knowledge is your best defense. Subscribe for weekly deep dives.\n\n"
            "Recommended reads: https://www.amazon.com/shop/{store}?tag={tag}\n\n"
            "As an Amazon Associate, I earn from qualifying purchases.\n\n"
            "#Psychology #DarkPsychology #BodyLanguage #MindHacks #SelfImprovement"
        ),
        "keywords": "psychology dark psychology body language manipulation mind hacks self improvement mental health overthinking confidence cognitive bias human behavior",
    },
    "HowToUseAI": {
        "description": (
            "AI is changing everything. Are you keeping up?\n\n"
            "How to Use AI is your go-to channel for practical AI tutorials, "
            "tool reviews, and automation strategies that save you hours every week. "
            "No jargon. No theory. Just step-by-step guides you can use TODAY.\n\n"
            "What you'll find here:\n"
            "- ChatGPT prompt engineering masterclasses\n"
            "- AI tool reviews (the ones that actually work)\n"
            "- Automation workflows that make money while you sleep\n"
            "- AI for beginners — explained simply\n\n"
            "New tutorials every week. Subscribe to stay ahead of the curve.\n\n"
            "All tools mentioned: https://www.amazon.com/shop/{store}?tag={tag}\n\n"
            "As an Amazon Associate, I earn from qualifying purchases.\n\n"
            "#AI #ChatGPT #Automation #AITools #PromptEngineering #Productivity"
        ),
        "keywords": "AI artificial intelligence ChatGPT prompt engineering AI tools automation make money with AI AI tutorial productivity AI for beginners 2026",
    },
    "RichPets": {
        "description": (
            "Your pet deserves the best. Let's make sure they get it.\n\n"
            "RichPets covers everything pet owners need to know: health tips, "
            "behavior decoded, breed guides, and the little things that make "
            "your furry friend's life amazing.\n\n"
            "What you'll find here:\n"
            "- Pet health mistakes most owners don't know they're making\n"
            "- Dog and cat behavior explained by science\n"
            "- Best breeds for your lifestyle\n"
            "- Fun facts that will change how you see your pet\n\n"
            "Subscribe for weekly pet wisdom.\n\n"
            "Recommended pet supplies: https://www.amazon.com/shop/{store}?tag={tag}\n\n"
            "As an Amazon Associate, I earn from qualifying purchases.\n\n"
            "#Pets #DogCare #CatBreeds #PetHealth #PetTips #AnimalBehavior"
        ),
        "keywords": "pets pet care dog care cat breeds pet health animal behavior dog training cat care pet tips pet owner guide best dog breeds best cat breeds",
    },
    "EvaReyes": {
        "description": (
            "You are stronger than you think. And this channel is here to prove it.\n\n"
            "Eva Reyes — Inspire & Empower is a space for women who are ready to "
            "stop shrinking and start shining. Confidence building, toxic habit "
            "breaking, and the empowerment you didn't know you needed.\n\n"
            "What you'll find here:\n"
            "- Signs you're stronger than you give yourself credit for\n"
            "- Toxic habits to stop normalizing (starting today)\n"
            "- How to build unshakeable confidence from the inside out\n"
            "- Self-care strategies backed by psychology\n\n"
            "New empowering content weekly. Subscribe and share with a woman who needs this.\n\n"
            "Recommended self-care & growth resources: https://www.amazon.com/shop/{store}?tag={tag}\n\n"
            "As an Amazon Associate, I earn from qualifying purchases.\n\n"
            "#WomensEmpowerment #Confidence #SelfImprovement #Motivation #StrongWomen"
        ),
        "keywords": "womens empowerment confidence self improvement motivation strong women personal growth self care mindset inspiration women motivation 2026 self worth toxic habits",
    },
    "RichReviews": {
        "description": (
            "Honest reviews. No sponsorship bias. Just the truth about products you're thinking of buying.\n\n"
            "RichReviews tests and compares the products everyone's talking about "
            "so you can make informed decisions before spending your money.\n\n"
            "What you'll find here:\n"
            "- In-depth product reviews with real testing\n"
            "- Side-by-side comparisons (best vs. budget)\n"
            "- Tech, home, fitness, and lifestyle product breakdowns\n"
            "- 'Is it worth it?' verdicts on trending products\n\n"
            "Subscribe for honest reviews before you buy.\n\n"
            "Products reviewed: https://www.amazon.com/shop/{store}?tag={tag}\n\n"
            "As an Amazon Associate, I earn from qualifying purchases.\n\n"
            "#ProductReview #TechReview #HonestReview #BestProducts #Comparison"
        ),
        "keywords": "product review honest review tech review best products comparison worth it budget vs premium unboxing product test 2026 buying guide",
    },
    "RichGaming": {
        "description": (
            "Level up your gaming knowledge.\n\n"
            "RichGaming covers the games, gear, and strategies that matter. "
            "From hidden gems to AAA breakdowns, tips to dominate, and the "
            "gaming news you need to know.\n\n"
            "What you'll find here:\n"
            "- Game reviews and honest first impressions\n"
            "- Pro tips and strategies to improve your gameplay\n"
            "- Best gaming gear on a budget\n"
            "- Gaming news and industry analysis\n\n"
            "Subscribe and join the squad.\n\n"
            "#Gaming #GameReview #GamingTips #BestGames #GamingGear"
        ),
        "keywords": "gaming game review gaming tips best games 2026 gaming gear PS5 Xbox PC gaming gameplay walkthrough strategy guide esports",
    },
    "RichHistory": {
        "description": (
            "History isn't just what happened — it's why everything is the way it is.\n\n"
            "RichHistory brings you fascinating stories from the past: "
            "forgotten events, powerful figures, and the moments that shaped our world. "
            "Told with cinematic narration and stunning visuals.\n\n"
            "What you'll find here:\n"
            "- Forgotten history that should never be forgotten\n"
            "- The real stories behind famous events\n"
            "- Historical figures who changed everything\n"
            "- Dark chapters of history explored honestly\n\n"
            "Subscribe to learn what they didn't teach you in school.\n\n"
            "#History #HistoryChannel #ForgottenHistory #Documentary #Education"
        ),
        "keywords": "history forgotten history documentary historical events famous figures world history ancient history dark history education facts historical documentary",
    },
    "RichNature": {
        "description": (
            "The natural world is more incredible than you can imagine.\n\n"
            "RichNature explores the wonders of wildlife, ecosystems, and "
            "the planet we call home. Breathtaking visuals. Fascinating facts. "
            "Stories that remind you why nature matters.\n\n"
            "What you'll find here:\n"
            "- Amazing animal behaviors you've never seen\n"
            "- The most beautiful places on Earth\n"
            "- Nature facts that will blow your mind\n"
            "- Conservation stories and environmental awareness\n\n"
            "Subscribe for weekly nature content.\n\n"
            "#Nature #Wildlife #Animals #NatureDocumentary #Conservation #Earth"
        ),
        "keywords": "nature wildlife animals nature documentary conservation earth planet beautiful places amazing animals ecosystem environment nature facts",
    },
    "RichScience": {
        "description": (
            "Science made simple. Curiosity made powerful.\n\n"
            "RichScience breaks down complex topics into content anyone can "
            "understand and everyone should know. From space to the human body, "
            "quantum physics to everyday chemistry.\n\n"
            "What you'll find here:\n"
            "- Mind-blowing science facts explained simply\n"
            "- Space exploration and astronomy updates\n"
            "- How things work (the science of everyday life)\n"
            "- Emerging technologies and discoveries\n\n"
            "Subscribe to feed your curiosity.\n\n"
            "#Science #Space #Physics #Education #ScienceFacts #Technology"
        ),
        "keywords": "science space physics chemistry biology astronomy education science facts how things work discoveries technology quantum emerging science 2026",
    },
    "RichFinance": {
        "description": (
            "Your money should work harder than you do.\n\n"
            "RichFinance teaches personal finance, investing strategies, and "
            "wealth-building habits that anyone can start using today. "
            "No get-rich-quick schemes — just real financial literacy.\n\n"
            "What you'll find here:\n"
            "- Investing basics for beginners\n"
            "- Budgeting strategies that actually work\n"
            "- Passive income ideas (realistic ones)\n"
            "- Money mistakes to avoid in your 20s, 30s, and beyond\n\n"
            "Subscribe to start building wealth.\n\n"
            "#PersonalFinance #Investing #MoneyTips #WealthBuilding #FinancialLiteracy"
        ),
        "keywords": "personal finance investing money tips wealth building budgeting passive income financial literacy stocks savings money mistakes 2026 beginner investing",
    },
    "RichCrypto": {
        "description": (
            "Crypto without the confusion.\n\n"
            "RichCrypto breaks down cryptocurrency, blockchain technology, and "
            "Web3 in plain English. Whether you're a beginner or experienced "
            "trader, we've got analysis you can actually use.\n\n"
            "What you'll find here:\n"
            "- Cryptocurrency explained for beginners\n"
            "- Market analysis and trend breakdowns\n"
            "- Blockchain technology and real-world use cases\n"
            "- DeFi, NFTs, and Web3 opportunities\n\n"
            "Subscribe for weekly crypto insights.\n\n"
            "#Crypto #Bitcoin #Blockchain #Web3 #Cryptocurrency #DeFi"
        ),
        "keywords": "cryptocurrency bitcoin blockchain Web3 crypto trading DeFi NFT Ethereum altcoins crypto for beginners market analysis crypto 2026",
    },
    "RichMovie": {
        "description": (
            "Movies hit different when you understand what you're watching.\n\n"
            "RichMovie dives deep into film analysis, hidden details, and the "
            "storytelling techniques that make great movies unforgettable.\n\n"
            "What you'll find here:\n"
            "- Movie breakdowns and hidden details you missed\n"
            "- Film analysis and storytelling techniques\n"
            "- Best movies you haven't seen yet\n"
            "- Ranking and comparison videos\n\n"
            "Subscribe for your weekly cinema fix.\n\n"
            "#Movies #FilmAnalysis #MovieReview #Cinema #Storytelling"
        ),
        "keywords": "movies film analysis movie review cinema storytelling hidden details movie breakdown best movies film theory movie ranking 2026",
    },
    "RichComedy": {
        "description": (
            "Life's too short not to laugh.\n\n"
            "RichComedy serves up the funniest content on YouTube: "
            "relatable humor, viral-worthy commentary, and the kind of "
            "laughs that make you share with friends.\n\n"
            "What you'll find here:\n"
            "- Relatable comedy everyone can enjoy\n"
            "- Funny commentary on trending topics\n"
            "- Humor that makes your day better\n\n"
            "Subscribe for laughs. You deserve it.\n\n"
            "#Comedy #Funny #Humor #Entertainment #Laughs"
        ),
        "keywords": "comedy funny humor entertainment laughs relatable comedy commentary viral funny videos sketch comedy stand up 2026",
    },
    "RichSports": {
        "description": (
            "The sports breakdowns you've been looking for.\n\n"
            "RichSports covers the biggest moments, hottest takes, and "
            "deepest analysis across all major sports.\n\n"
            "What you'll find here:\n"
            "- Game analysis and breakdowns\n"
            "- Player rankings and comparisons\n"
            "- Sports news and hot takes\n"
            "- Historical moments in sports\n\n"
            "Subscribe for weekly sports content.\n\n"
            "#Sports #NFL #NBA #Football #Basketball #SportsAnalysis"
        ),
        "keywords": "sports NFL NBA football basketball analysis player rankings sports news hot takes game breakdown highlights 2026 MLB soccer",
    },
    "RichMusic": {
        "description": (
            "Feel the music. Understand the artistry.\n\n"
            "RichMusic explores the stories behind the songs, the artists "
            "who shaped genres, and the music that moves us.\n\n"
            "What you'll find here:\n"
            "- Music analysis and song breakdowns\n"
            "- Artist stories and behind-the-scenes\n"
            "- Genre deep dives and music history\n"
            "- Best new music discoveries\n\n"
            "Subscribe for your weekly music fix.\n\n"
            "#Music #MusicAnalysis #Songs #Artists #MusicHistory"
        ),
        "keywords": "music music analysis song breakdown artists music history genre hip hop R&B pop rock best new music 2026 album review",
    },
    "RichTravel": {
        "description": (
            "The world is waiting. Let's explore it together.\n\n"
            "RichTravel takes you to incredible destinations, shares "
            "travel hacks that save you money, and shows you places "
            "most tourists never find.\n\n"
            "What you'll find here:\n"
            "- Hidden travel gems around the world\n"
            "- Budget travel tips and money-saving hacks\n"
            "- Destination guides and itineraries\n"
            "- Travel gear reviews and packing tips\n\n"
            "Subscribe for weekly wanderlust.\n\n"
            "Travel gear picks: https://www.amazon.com/shop/{store}?tag={tag}\n\n"
            "As an Amazon Associate, I earn from qualifying purchases.\n\n"
            "#Travel #TravelTips #HiddenGems #BudgetTravel #Wanderlust"
        ),
        "keywords": "travel travel tips hidden gems budget travel destination guide wanderlust travel hacks packing tips best places to visit 2026 travel vlog",
    },
    "RichFood": {
        "description": (
            "Good food doesn't have to be complicated.\n\n"
            "RichFood brings you easy recipes, food hacks, and culinary "
            "discoveries that make cooking fun and eating amazing.\n\n"
            "What you'll find here:\n"
            "- Quick and easy recipes anyone can make\n"
            "- Food hacks that save time and money\n"
            "- Restaurant-quality meals at home\n"
            "- Food reviews and taste tests\n\n"
            "Subscribe for weekly food content.\n\n"
            "Kitchen essentials: https://www.amazon.com/shop/{store}?tag={tag}\n\n"
            "As an Amazon Associate, I earn from qualifying purchases.\n\n"
            "#Food #Recipes #Cooking #FoodHacks #EasyRecipes"
        ),
        "keywords": "food recipes cooking easy recipes food hacks kitchen meal prep quick dinner healthy eating food review taste test 2026 cooking tips",
    },
    "RichFitness": {
        "description": (
            "Stronger body. Stronger mind. No gym required.\n\n"
            "RichFitness delivers workout routines, nutrition tips, and "
            "fitness science that gets real results — whether you're a "
            "beginner or experienced athlete.\n\n"
            "What you'll find here:\n"
            "- Home workouts that actually build muscle\n"
            "- Nutrition tips backed by science\n"
            "- Fitness mistakes that are holding you back\n"
            "- Workout plans for every fitness level\n\n"
            "Subscribe to start your transformation.\n\n"
            "Fitness gear: https://www.amazon.com/shop/{store}?tag={tag}\n\n"
            "As an Amazon Associate, I earn from qualifying purchases.\n\n"
            "#Fitness #Workout #Exercise #Nutrition #HomeWorkout #GymTips"
        ),
        "keywords": "fitness workout exercise nutrition home workout gym tips muscle building weight loss healthy living workout plan beginner fitness 2026 health",
    },
    "RichEducation": {
        "description": (
            "Learning never stops. Let's make it interesting.\n\n"
            "RichEducation makes complex topics simple and boring subjects "
            "fascinating. Study tips, life skills, and knowledge that "
            "actually matters.\n\n"
            "What you'll find here:\n"
            "- Study tips and learning strategies\n"
            "- Fascinating facts about the world\n"
            "- Life skills they don't teach in school\n"
            "- Educational content made engaging\n\n"
            "Subscribe to level up your knowledge.\n\n"
            "#Education #Learning #StudyTips #Knowledge #LifeSkills"
        ),
        "keywords": "education learning study tips knowledge life skills school college self education facts educational content how to learn 2026 study hacks",
    },
    "RichLifestyle": {
        "description": (
            "Design a life you don't need a vacation from.\n\n"
            "RichLifestyle covers productivity, self-improvement, and the "
            "daily habits that make successful people different.\n\n"
            "What you'll find here:\n"
            "- Morning routines and daily habits of successful people\n"
            "- Productivity hacks that free up hours\n"
            "- Self-improvement strategies that actually stick\n"
            "- Minimalism, organization, and intentional living\n\n"
            "Subscribe for weekly lifestyle upgrades.\n\n"
            "Lifestyle essentials: https://www.amazon.com/shop/{store}?tag={tag}\n\n"
            "As an Amazon Associate, I earn from qualifying purchases.\n\n"
            "#Lifestyle #Productivity #SelfImprovement #Habits #Minimalism"
        ),
        "keywords": "lifestyle productivity self improvement habits morning routine minimalism organization intentional living success tips daily routine 2026 life hacks",
    },
    "HowToMeditate": {
        "description": (
            "Peace of mind isn't a luxury. It's a skill.\n\n"
            "How to Meditate is your guided journey into mindfulness, "
            "meditation, and inner calm. Whether you've never meditated "
            "or you're deepening your practice, we meet you where you are.\n\n"
            "What you'll find here:\n"
            "- Guided meditations for beginners and beyond\n"
            "- Mindfulness techniques for stress and anxiety\n"
            "- Sleep meditations and relaxation exercises\n"
            "- The science of meditation explained\n\n"
            "Subscribe for weekly peace.\n\n"
            "#Meditation #Mindfulness #GuidedMeditation #InnerPeace #StressRelief"
        ),
        "keywords": "meditation mindfulness guided meditation stress relief anxiety relaxation sleep meditation inner peace calm how to meditate beginner meditation 2026",
    },
    "RichBeauty": {
        "description": (
            "Beauty that's real, accessible, and affordable.\n\n"
            "RichBeauty brings you honest product reviews, tutorials, "
            "and skincare science that cuts through the marketing hype.\n\n"
            "What you'll find here:\n"
            "- Skincare routines that actually work\n"
            "- Makeup tutorials for every skill level\n"
            "- Product reviews (drugstore vs. luxury)\n"
            "- Beauty tips backed by dermatology\n\n"
            "Subscribe for weekly beauty content.\n\n"
            "Beauty favorites: https://www.amazon.com/shop/{store}?tag={tag}\n\n"
            "As an Amazon Associate, I earn from qualifying purchases.\n\n"
            "#Beauty #Skincare #Makeup #BeautyTips #ProductReview"
        ),
        "keywords": "beauty skincare makeup beauty tips product review tutorial drugstore luxury dermatology routine skin care 2026 affordable beauty",
    },
    "RichCooking": {
        "description": (
            "From kitchen beginner to confident cook.\n\n"
            "RichCooking teaches you real cooking skills with easy-to-follow "
            "recipes, kitchen hacks, and techniques that level up every meal.\n\n"
            "What you'll find here:\n"
            "- Step-by-step recipes for every skill level\n"
            "- Kitchen hacks that save time and money\n"
            "- Cooking techniques the pros use\n"
            "- Meal prep and budget-friendly cooking\n\n"
            "Subscribe to become a better cook.\n\n"
            "Kitchen tools I use: https://www.amazon.com/shop/{store}?tag={tag}\n\n"
            "As an Amazon Associate, I earn from qualifying purchases.\n\n"
            "#Cooking #Recipes #KitchenHacks #MealPrep #CookingTips"
        ),
        "keywords": "cooking recipes kitchen hacks meal prep cooking tips easy recipes budget cooking beginner chef techniques how to cook 2026 kitchen tools",
    },
    "RichFamily": {
        "description": (
            "Family life is beautiful, messy, and everything in between.\n\n"
            "RichFamily shares parenting tips, family activities, and the "
            "real talk about raising kids in today's world.\n\n"
            "What you'll find here:\n"
            "- Parenting tips that actually help\n"
            "- Fun family activities and adventures\n"
            "- Real talk about the challenges of parenthood\n"
            "- Educational content for kids and parents\n\n"
            "Subscribe for weekly family content.\n\n"
            "#Family #Parenting #Kids #FamilyLife #ParentingTips"
        ),
        "keywords": "family parenting kids family life parenting tips activities children education family fun mom dad raising kids 2026 family vlog",
    },
    "RichFashion": {
        "description": (
            "Style doesn't have to cost a fortune.\n\n"
            "RichFashion breaks down trends, affordable finds, and the "
            "style fundamentals that make anyone look put-together.\n\n"
            "What you'll find here:\n"
            "- Affordable fashion finds and dupes\n"
            "- Style tips for men and women\n"
            "- Trend breakdowns (what's worth trying)\n"
            "- Wardrobe essentials and capsule wardrobes\n\n"
            "Subscribe for weekly style content.\n\n"
            "Fashion picks: https://www.amazon.com/shop/{store}?tag={tag}\n\n"
            "As an Amazon Associate, I earn from qualifying purchases.\n\n"
            "#Fashion #Style #AffordableFashion #Trends #WardrobeEssentials"
        ),
        "keywords": "fashion style affordable fashion trends wardrobe essentials capsule wardrobe outfit ideas mens fashion womens fashion 2026 style tips",
    },
    "RichCars": {
        "description": (
            "Cars, trucks, and everything automotive.\n\n"
            "RichCars covers the vehicles people love: reviews, comparisons, "
            "maintenance tips, and the car culture that drives us.\n\n"
            "What you'll find here:\n"
            "- Car reviews and comparisons\n"
            "- Maintenance tips that save you money\n"
            "- Best cars for every budget\n"
            "- Automotive news and industry trends\n\n"
            "Subscribe for weekly automotive content.\n\n"
            "Car accessories: https://www.amazon.com/shop/{store}?tag={tag}\n\n"
            "As an Amazon Associate, I earn from qualifying purchases.\n\n"
            "#Cars #Automotive #CarReview #BestCars #CarMaintenance"
        ),
        "keywords": "cars automotive car review best cars car maintenance buying guide trucks SUV electric vehicles EV 2026 car comparison used cars new cars",
    },
    "RichDIY": {
        "description": (
            "Build it yourself. Save money. Feel proud.\n\n"
            "RichDIY teaches you practical home improvement, crafts, and "
            "projects that anyone can tackle — no experience needed.\n\n"
            "What you'll find here:\n"
            "- Home improvement projects step by step\n"
            "- DIY crafts and creative builds\n"
            "- Money-saving repairs you can do yourself\n"
            "- Tool reviews and workshop tips\n\n"
            "Subscribe and start building.\n\n"
            "Tools I use: https://www.amazon.com/shop/{store}?tag={tag}\n\n"
            "As an Amazon Associate, I earn from qualifying purchases.\n\n"
            "#DIY #HomeImprovement #Crafts #DoItYourself #Projects"
        ),
        "keywords": "DIY home improvement crafts do it yourself projects woodworking repairs tools workshop beginner DIY how to build 2026 home renovation",
    },
    "RichDesign": {
        "description": (
            "Great design is invisible. Bad design is everywhere.\n\n"
            "RichDesign explores graphic design, UI/UX, and the creative "
            "process behind work that converts.\n\n"
            "What you'll find here:\n"
            "- Graphic design tutorials and tips\n"
            "- UI/UX design breakdowns\n"
            "- Design tool reviews (Adobe, Figma, Canva)\n"
            "- Portfolio and freelance design advice\n\n"
            "Subscribe to level up your design skills.\n\n"
            "#GraphicDesign #UIUX #DesignTips #Figma #AdobeFresco"
        ),
        "keywords": "graphic design UI UX design tips tutorial Adobe Figma Canva Fresco logo design web design portfolio freelance designer 2026 creative",
    },
    "RichBusiness": {
        "description": (
            "Build a business that works for you, not the other way around.\n\n"
            "Rich Business delivers practical strategies for entrepreneurs, "
            "solopreneurs, and anyone ready to turn ideas into income.\n\n"
            "What you'll find here:\n"
            "- Business strategies that actually work\n"
            "- Side hustle ideas with real potential\n"
            "- Marketing and sales tactics for small businesses\n"
            "- Entrepreneurship lessons from real experience\n\n"
            "Subscribe to build something real.\n\n"
            "#Business #Entrepreneurship #SideHustle #SmallBusiness #Marketing"
        ),
        "keywords": "business entrepreneurship side hustle small business marketing sales solopreneur startup online business passive income 2026 business tips",
    },
    "CumquatMotivation": {
        "description": (
            "The motivation you need. The discipline to keep going.\n\n"
            "Cumquat Motivation delivers powerful speeches, mindset shifts, "
            "and the daily fuel to push through when life gets hard.\n\n"
            "What you'll find here:\n"
            "- Motivational speeches for tough days\n"
            "- Mindset strategies from the world's top performers\n"
            "- Daily motivation and discipline habits\n"
            "- Success stories that inspire action\n\n"
            "Subscribe for your daily dose of motivation.\n\n"
            "#Motivation #Mindset #Discipline #Success #Inspiration"
        ),
        "keywords": "motivation mindset discipline success inspiration motivational speech self improvement positive thinking goals perseverance 2026 daily motivation",
    },
    "RichPhotography": {
        "description": (
            "See the world through a better lens.\n\n"
            "RichPhotography teaches you how to take stunning photos "
            "with any camera — from smartphone to DSLR. Composition, "
            "lighting, editing, and the eye that makes a great photographer.\n\n"
            "What you'll find here:\n"
            "- Photography tips for beginners and intermediates\n"
            "- Editing tutorials (Lightroom, Photoshop, mobile)\n"
            "- Composition techniques that transform your shots\n"
            "- Camera and gear reviews on every budget\n\n"
            "Subscribe to level up your photography.\n\n"
            "Camera gear picks: https://www.amazon.com/shop/{store}?tag={tag}\n\n"
            "As an Amazon Associate, I earn from qualifying purchases.\n\n"
            "#Photography #PhotoTips #Lightroom #CameraGear #PhotoEditing"
        ),
        "keywords": "photography photo tips camera gear Lightroom editing composition DSLR iPhone photography beginner photography 2026 portrait landscape street photography",
    },
    "RichAnimation": {
        "description": (
            "Bring your ideas to life — one frame at a time.\n\n"
            "RichAnimation covers animation techniques, tools, and tutorials "
            "for creators at every level. From 2D to 3D, motion graphics "
            "to character animation.\n\n"
            "What you'll find here:\n"
            "- Animation tutorials for beginners\n"
            "- Motion graphics tips and techniques\n"
            "- Tool reviews (After Effects, Blender, Procreate)\n"
            "- Behind-the-scenes of animated projects\n\n"
            "Subscribe to start animating.\n\n"
            "#Animation #MotionGraphics #2DAnimation #3DAnimation #AfterEffects"
        ),
        "keywords": "animation motion graphics 2D animation 3D animation After Effects Blender tutorial beginner animation character animation 2026 animated video",
    },
    "RichDance": {
        "description": (
            "Move your body. Free your mind.\n\n"
            "RichDance brings you dance tutorials, choreography breakdowns, "
            "and the culture behind the moves.\n\n"
            "What you'll find here:\n"
            "- Dance tutorials for every style\n"
            "- Choreography breakdowns step by step\n"
            "- Dance culture and history\n"
            "- Trending moves and challenges\n\n"
            "Subscribe and start moving.\n\n"
            "#Dance #DanceTutorial #Choreography #HipHop #DanceMoves"
        ),
        "keywords": "dance tutorial choreography hip hop dance moves trending dance challenge beginner dance 2026 dance class dance culture street dance",
    },
    "RichKids": {
        "description": (
            "Fun, safe, and educational content kids actually love.\n\n"
            "RichKids creates engaging content for young minds — stories, "
            "fun facts, and adventures that entertain while they learn.\n\n"
            "What you'll find here:\n"
            "- Fun facts and science for kids\n"
            "- Stories and animated adventures\n"
            "- Educational content that's actually entertaining\n"
            "- Creative activities and challenges\n\n"
            "Subscribe for weekly fun!\n\n"
            "#KidsContent #EducationalKids #FunFacts #Learning #KidsVideos"
        ),
        "keywords": "kids content educational kids fun facts learning kids videos children entertainment stories activities 2026 kids channel family friendly",
    },
    "RichMemes": {
        "description": (
            "The internet's funniest moments, curated just for you.\n\n"
            "RichMemes brings you meme compilations, internet culture commentary, "
            "and the viral content everyone's talking about.\n\n"
            "What you'll find here:\n"
            "- Daily meme compilations\n"
            "- Internet culture explained\n"
            "- Viral trends and reactions\n"
            "- Commentary on the funniest corners of the internet\n\n"
            "Subscribe for daily laughs.\n\n"
            "#Memes #Funny #ViralMemes #InternetCulture #MemeCompilation"
        ),
        "keywords": "memes funny viral memes internet culture meme compilation trending memes 2026 humor comedy reaction best memes daily memes",
    },
    "RichVlogging": {
        "description": (
            "Real life. Real stories. No filter.\n\n"
            "RichVlogging captures the everyday moments, creative process, "
            "and behind-the-scenes of building something from nothing.\n\n"
            "What you'll find here:\n"
            "- Day-in-the-life vlogs\n"
            "- Behind the scenes of content creation\n"
            "- Real talk about the creator journey\n"
            "- Travel and lifestyle adventures\n\n"
            "Subscribe for the real side of things.\n\n"
            "#Vlog #DayInTheLife #BehindTheScenes #CreatorLife #Lifestyle"
        ),
        "keywords": "vlog day in the life behind the scenes creator life lifestyle vlogging 2026 daily vlog content creator journey real life",
    },
}


def refresh_channel_token(creds):
    """Refresh OAuth token for a channel."""
    data = urllib.parse.urlencode({
        "client_id": creds["client_id"],
        "client_secret": creds["client_secret"],
        "refresh_token": creds["refresh_token"],
        "grant_type": "refresh_token",
    }).encode()
    req = Request("https://oauth2.googleapis.com/token", data=data)
    try:
        resp = json.loads(urlopen(req).read())
        return resp["access_token"]
    except HTTPError as e:
        err = e.read().decode("utf-8") if hasattr(e, "read") else str(e)
        print(f"    Token refresh error: {err[:200]}")
        return None


def get_channel_info(access_token):
    """Get current channel metadata."""
    url = "https://www.googleapis.com/youtube/v3/channels?part=snippet,brandingSettings,statistics&mine=true"
    req = Request(url, headers={"Authorization": f"Bearer {access_token}"})
    try:
        with urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if data.get("items"):
            return data["items"][0]
    except HTTPError as e:
        err = e.read().decode("utf-8") if hasattr(e, "read") else str(e)
        print(f"    Fetch error: {err[:200]}")
    return None


def update_channel_branding(channel_id, description, keywords, access_token):
    """Update channel branding settings (description + keywords).
    Returns dict on success, 'quota' on quota error, None on other error."""
    # Format description with affiliate info
    description = description.replace("{store}", AMAZON_STORE_ID).replace("{tag}", AMAZON_AFFILIATE_TAG)

    url = "https://www.googleapis.com/youtube/v3/channels?part=brandingSettings"
    payload = json.dumps({
        "id": channel_id,
        "brandingSettings": {
            "channel": {
                "description": description,
                "keywords": keywords,
                "defaultLanguage": "en",
                "country": "US",
            }
        }
    }).encode("utf-8")

    req = Request(url, data=payload, headers={
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }, method="PUT")

    try:
        with urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        err = e.read().decode("utf-8") if hasattr(e, "read") else str(e)
        print(f"    Update error: {err[:300]}")
        if "quota" in err.lower() or e.code == 403:
            return "quota"
        return None


def update_channel_snippet_country(channel_id, current_snippet, access_token):
    """Update snippet.country for monetization readiness.

    YouTube requires country in the snippet (not just brandingSettings) for
    monetization eligibility. We must include existing title/description in
    the payload or they get wiped.

    Returns dict on success, 'quota' on quota error, None on other error.
    """
    url = "https://www.googleapis.com/youtube/v3/channels?part=snippet"
    payload = json.dumps({
        "id": channel_id,
        "snippet": {
            "title": current_snippet.get("title", ""),
            "description": current_snippet.get("description", ""),
            "defaultLanguage": "en",
            "country": "US",
        }
    }).encode("utf-8")

    req = Request(url, data=payload, headers={
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }, method="PUT")

    try:
        with urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        err = e.read().decode("utf-8") if hasattr(e, "read") else str(e)
        print(f"    Snippet update error: {err[:300]}")
        if "quota" in err.lower() or e.code == 403:
            return "quota"
        return None


def check_monetization_readiness(info):
    """Check channel metadata against YouTube monetization requirements.

    Returns list of issues found. Empty list = monetization-ready metadata.
    """
    issues = []
    snippet = info.get("snippet", {})
    branding = info.get("brandingSettings", {}).get("channel", {})
    stats = info.get("statistics", {})

    # Country must be set (critical for monetization)
    if not snippet.get("country") and not branding.get("country"):
        issues.append("MISSING country (required for monetization)")

    # Description should be substantive
    desc = branding.get("description", snippet.get("description", ""))
    if len(desc) < 50:
        issues.append(f"Description too short ({len(desc)} chars, need 50+)")

    # Keywords should be present
    if not branding.get("keywords", "").strip():
        issues.append("MISSING keywords (hurts discoverability)")

    # Default language should be set
    if not snippet.get("defaultLanguage") and not branding.get("defaultLanguage"):
        issues.append("MISSING defaultLanguage")

    return issues


def load_progress():
    """Load progress from previous runs."""
    if os.path.exists(PROGRESS_PATH):
        with open(PROGRESS_PATH) as f:
            return json.load(f)
    return {"updated": [], "failed": []}


def save_progress(progress):
    """Save progress for resume on quota reset."""
    with open(PROGRESS_PATH, "w") as f:
        json.dump(progress, f, indent=2)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "audit"

    print("Channel Optimization System")
    print("=" * 60)

    with open(CHANNEL_TOKENS_PATH) as f:
        all_tokens = json.load(f)

    progress = load_progress()
    already_done = set(progress.get("updated", []))

    print(f"Found {len(all_tokens)} channel tokens.")
    if already_done:
        print(f"Already optimized from previous runs: {len(already_done)}")
    print()

    # Token name -> optimization key mapping
    TOKEN_KEY_MAP = {
        "How to Use AI": "HowToUseAI",
        "How to Meditate": "HowToMeditate",
        "Eva Reyes": "EvaReyes",
        "Rich Business": "RichBusiness",
        "Cumquat Motivation": "CumquatMotivation",
    }

    audit_results = []
    quota_hit = False

    for token_name, creds in sorted(all_tokens.items()):
        if quota_hit:
            break

        # Skip already-updated channels in update mode
        if mode == "update" and token_name in already_done:
            print(f"\n--- {token_name} --- ALREADY DONE (skipping)")
            continue

        print(f"\n--- {token_name} ---")

        access_token = refresh_channel_token(creds)
        if not access_token:
            print("  SKIP: Token refresh failed")
            continue

        info = get_channel_info(access_token)
        if not info:
            print("  SKIP: Could not fetch channel info")
            # Check if this is a quota error (get_channel_info prints the error)
            continue

        channel_id = info["id"]
        snippet = info.get("snippet", {})
        branding = info.get("brandingSettings", {}).get("channel", {})
        stats = info.get("statistics", {})

        current_desc = branding.get("description", snippet.get("description", ""))
        current_keywords = branding.get("keywords", "")
        sub_count = stats.get("subscriberCount", "0")
        video_count = stats.get("videoCount", "0")

        desc_len = len(current_desc)
        has_keywords = bool(current_keywords.strip())

        # Monetization readiness check
        monetization_issues = check_monetization_readiness(info)
        snippet_country = snippet.get("country", "")
        branding_country = branding.get("country", "")

        status = "OK" if desc_len > 100 and has_keywords and not monetization_issues else "NEEDS WORK"

        print(f"  ID: {channel_id}")
        print(f"  Subscribers: {sub_count} | Videos: {video_count}")
        print(f"  Description: {desc_len} chars {'(too short!)' if desc_len < 100 else ''}")
        print(f"  Keywords: {'Yes' if has_keywords else 'MISSING'}")
        print(f"  Country (snippet): {snippet_country or 'NOT SET'}")
        print(f"  Country (branding): {branding_country or 'NOT SET'}")
        print(f"  Language: {snippet.get('defaultLanguage', 'NOT SET')}")
        if monetization_issues:
            print(f"  MONETIZATION ISSUES:")
            for issue in monetization_issues:
                print(f"    - {issue}")
        print(f"  Status: {status}")

        audit_results.append({
            "name": token_name,
            "channel_id": channel_id,
            "subscribers": sub_count,
            "videos": video_count,
            "desc_length": desc_len,
            "has_keywords": has_keywords,
            "has_country": bool(snippet_country or branding_country),
            "monetization_issues": monetization_issues,
            "status": status,
        })

        if mode == "update":
            # Find matching optimization data
            opt_key = None
            for key in CHANNEL_OPTIMIZATIONS:
                if key == token_name or key.replace(" ", "") == token_name.replace(" ", ""):
                    opt_key = key
                    break
                if token_name in TOKEN_KEY_MAP and TOKEN_KEY_MAP[token_name] == key:
                    opt_key = key
                    break

            if opt_key and opt_key in CHANNEL_OPTIMIZATIONS:
                opt = CHANNEL_OPTIMIZATIONS[opt_key]
                print(f"  Updating description and keywords...")
                result = update_channel_branding(
                    channel_id, opt["description"], opt["keywords"], access_token
                )
                if result == "quota":
                    print(f"  -> QUOTA LIMIT — stopping. Re-run after midnight PT.")
                    quota_hit = True
                elif result and isinstance(result, dict):
                    print(f"  -> Branding UPDATED!")
                    progress["updated"].append(token_name)
                    save_progress(progress)
                else:
                    print(f"  -> UPDATE FAILED (non-quota error)")
                    progress.setdefault("failed", []).append(token_name)
                    save_progress(progress)
            else:
                print(f"  No optimization data for '{token_name}' — skipping branding update")

            # Always set snippet.country for monetization (even if branding already done)
            if not quota_hit and not snippet_country:
                print(f"  Setting snippet.country for monetization...")
                snippet_result = update_channel_snippet_country(
                    channel_id, snippet, access_token
                )
                if snippet_result == "quota":
                    print(f"  -> QUOTA LIMIT on snippet update — stopping.")
                    quota_hit = True
                elif snippet_result and isinstance(snippet_result, dict):
                    print(f"  -> snippet.country = US (set!)")
                    progress.setdefault("country_set", []).append(token_name)
                    save_progress(progress)
                else:
                    print(f"  -> snippet.country update FAILED")

            time.sleep(1)  # Rate limit

    # Print summary
    print(f"\n{'=' * 60}")
    print("OPTIMIZATION SUMMARY")
    print(f"{'=' * 60}")

    total_done = len(progress.get("updated", []))
    total_channels = len(all_tokens)
    remaining = total_channels - total_done

    print(f"Total channels: {total_channels}")
    print(f"Successfully optimized: {total_done}")
    print(f"Remaining: {remaining}")

    if progress.get("updated"):
        print(f"\nOptimized channels:")
        for name in sorted(progress["updated"]):
            print(f"  [done] {name}")

    # Monetization readiness summary
    not_monetization_ready = [r for r in audit_results if r.get("monetization_issues")]
    if not_monetization_ready:
        print(f"\nMONETIZATION ISSUES ({len(not_monetization_ready)} channels):")
        for r in not_monetization_ready:
            print(f"  {r['name']}:")
            for issue in r["monetization_issues"]:
                print(f"    - {issue}")

    no_country = [r for r in audit_results if not r.get("has_country")]
    if no_country:
        print(f"\nMISSING COUNTRY ({len(no_country)} channels):")
        for r in no_country:
            print(f"  {r['name']}")

    needs_work = [r for r in audit_results if r["status"] == "NEEDS WORK"]
    if needs_work:
        print(f"\nStill need optimization:")
        for r in needs_work:
            if r["name"] not in already_done:
                issues = []
                if r["desc_length"] < 100:
                    issues.append(f"short desc ({r['desc_length']} chars)")
                if not r["has_keywords"]:
                    issues.append("no keywords")
                if not r.get("has_country"):
                    issues.append("no country")
                print(f"  {r['name']}: {', '.join(issues)}")

    if quota_hit:
        print(f"\nQuota hit — re-run this script after midnight PT to continue.")
        print(f"Progress saved to {PROGRESS_PATH}")
    elif mode == "audit":
        print(f"\nThis was a dry run. Use 'python3 optimize_all_channels.py update' to apply changes.")
    elif remaining == 0:
        print(f"\nAll channels optimized! Clearing progress file.")
        if os.path.exists(PROGRESS_PATH):
            os.remove(PROGRESS_PATH)


if __name__ == "__main__":
    main()
