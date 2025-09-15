# genre_maps.py (เวอร์ชันอัปเกรด: อิงตาม Official Genres ของ Spotify)

# -----------------------------------------------------------------------------
# ARTIST_POOL_BY_LANG
# คลังศิลปินสำหรับเป็นจุดเริ่มต้นในการค้นหาเพลง
# Key ของ Genre ในนี้เป็นชื่อที่เราตั้งขึ้นเองเพื่อความเข้าใจง่าย
# -----------------------------------------------------------------------------
ARTIST_POOL_BY_LANG = {
    "jp": {
        "j-rock": [ # Maps to official genres: j-rock, rock, anime
            "ONE OK ROCK", "L'Arc-en-Ciel", "RADWIMPS", "B'z", "X JAPAN", 
            "Asian Kung-Fu Generation", "MAN WITH A MISSION", "UVERworld", "SCANDAL", 
            "BAND-MAID", "DIR EN GREY", "King Gnu", "THE ORAL CIGARETTES", "SiM"
        ],
        "j-pop": [ # Maps to official genres: j-pop, pop, anime
            "YOASOBI", "Official HIGE DANdism", "Kenshi Yonezu", "Aimyon", "Gen Hoshino",
            "Hikaru Utada", "Ado", "Vaundy", "ZUTOMAYO", "Mrs. GREEN APPLE",
            "Arashi", "AKB48", "Perfume", "LiSA"
        ],
        "city-pop": [ # Maps to official genres: city-pop, j-pop, jazz
            "Mariya Takeuchi", "Tatsuro Yamashita", "Anri", "Toshiki Kadomatsu", "Miki Matsubara",
            "Taeko Onuki", "Junko Ohashi", "Tomoko Aran", "Yurie Kokubu", "Meiko Nakahara"
        ],
        "anime": [ # Maps to official genres: anime, j-pop, j-rock
            "LiSA", "Aimer", "EGOIST", "Linked Horizon", "FLOW", "Kalafina",
            "ClariS", "ReoNa", "Hiroyuki Sawano", "Yuki Kajiura", "TK from Ling tosite sigure"
        ]
    },
    "th": {
        "thai-indie": [ # Maps to official genres: thai-indie, indie, pop
            "Safeplanet", "Whal & Dolph", "Dept", "HYBS", "Polycat", "Desktop Error",
            "Tattoo Colour", "The Toys", "Phum Viphurit", "Moving and Cut", "Yented",
            "TELEx TELEXs", "Anatomy Rabbit"
        ],
        "thai-pop": [ # Maps to official genres: pop, thai-pop (unofficial but common)
            "STAMP", "Ink Waruntorn", "Billkin", "PP Krit", "NONT TANONT", "Three Man Down",
            "Tilly Birds", "Getsunova", "Cocktail", "Potato", "Bodyslam", "BOWKYLION"
        ],
        "thai-rock": [ # Maps to official genres: rock, alternative
            "Bodyslam", "Silly Fools", "Big Ass", "Potato", "Slot Machine", "Retrospect",
            "Sweet Mullet", "Loso", "Sek Loso", "Carabao", "Paradox"
        ],
        "luk-thung": [ # Maps to official genres: world-music, molam
            "Monkaen Kaenkoon", "Tai Orathai", "Phai Phongsathon", "Pumpuang Duangjan", 
            "Suraphol Sombatcharoen", "Jintara Poonlarp", "Got Jakrapun", "Mike Phiromphorn"
        ]
    },
    "kr": {
        "k-pop": [ # Maps to official genres: k-pop, pop
            "BTS", "BLACKPINK", "TWICE", "Stray Kids", "NewJeans", "IVE",
            "SEVENTEEN", "Red Velvet", "NCT 127", "aespa", "LE SSERAFIM", "BIGBANG"
        ],
        "k-rock": [ # Maps to official genres: k-rock, rock, k-indie
            "The Rose", "DAY6", "FTISLAND", "CNBLUE", "Nell", "ONEWE", "N.Flying",
            "Jaurim", "LUCY"
        ],
        "k-indie": [ # Maps to official genres: k-indie, indie
            "Hyukoh", "BOL4", "10cm", "Jannabi", "The Black Skirts", "Stella Jang",
            "Standing Egg", "Car, the garden"
        ],
        "k-rnb": [ # Maps to official genres: k-r-n-b, r-n-b
            "DEAN", "Crush", "Heize", "Zion.T", "Epik High", "DPR LIVE", "Jay Park"
        ]
    },
    "en": {
        "classic-rock": [ # Maps to official genres: rock, classic-rock, hard-rock
            "Queen", "Led Zeppelin", "The Beatles", "Pink Floyd", "The Rolling Stones", 
            "AC/DC", "Eagles", "Fleetwood Mac", "Guns N' Roses", "Aerosmith"
        ],
        "pop": [ # Maps to official genres: pop, dance-pop
            "Taylor Swift", "Ed Sheeran", "Ariana Grande", "Dua Lipa", "The Weeknd", 
            "Harry Styles", "Billie Eilish", "Justin Bieber", "Olivia Rodrigo", "Bruno Mars"
        ],
        "hip-hop": [ # Maps to official genres: hip-hop, rap
            "Kendrick Lamar", "Drake", "J. Cole", "Kanye West", "Eminem", "Jay-Z",
            "Travis Scott", "Post Malone", "21 Savage"
        ],
        "alternative-rock": [ # Maps to official genres: alternative, rock, indie-rock
            "Nirvana", "Radiohead", "Arctic Monkeys", "The Strokes", "Foo Fighters",
            "Red Hot Chili Peppers", "Linkin Park", "Muse", "Coldplay", "Tame Impala"
        ],
        "synthwave": [ # Maps to official genres: synth-pop, electronic
            "The Midnight", "Kavinsky", "Carpenter Brut", "Gunship", "Timecop1983",
            "FM-84", "Lazerhawk", "Com Truise"
        ],
        "r-n-b": [ # Maps to official genres: r-n-b, soul
            "Frank Ocean", "SZA", "Daniel Caesar", "H.E.R.", "Miguel", "Jhené Aiko",
            "Giveon", "Brent Faiyaz"
        ]
    }
}

# -----------------------------------------------------------------------------
# DISCOVERY_SEEDS_BY_COUNTRY
# คลังข้อมูลสำหรับ Discovery Mode (ใช้ Genre ที่เป็นทางการของ Spotify เท่านั้น)
# นี่คือส่วนที่แก้ไขปัญหา 404 Not Found โดยตรง
# -----------------------------------------------------------------------------
DISCOVERY_SEEDS_BY_COUNTRY = {
    "TH": ['pop', 'indie', 'rock', 'hip-hop', 'r-n-b'],
    "JP": ['j-pop', 'j-rock', 'anime', 'pop', 'rock'],
    "KR": ['k-pop', 'k-rock', 'r-n-b', 'hip-hop', 'indie'],
    "US": ['pop', 'hip-hop', 'rock', 'r-n-b', 'country'],
    # "default" จะถูกใช้สำหรับประเทศอื่นๆ ที่ไม่มีการตั้งค่าเฉพาะ
    "default": ['pop', 'rock', 'electronic', 'hip-hop', 'indie']
}