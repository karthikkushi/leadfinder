"""What the agents look for: business categories, countries and website rules."""

# Each category matches Overture Maps taxonomy names (any level of the place's hierarchy;
# "=name" means the place's own category must be exactly that) and OpenStreetMap tags.
# Order matters: a place goes to the first category it matches.
CATEGORIES = [
    # key, label, overture taxonomy names, OSM (tag, value regex), value weight for scoring
    ("dentist", "Dentists", ["dental_clinic", "dentist", "general_dentistry", "orthodontist", "cosmetic_dentist",
                             "pediatric_dentist", "endodontist", "periodontist", "oral_surgeon", "prosthodontist"],
     [("amenity", "dentist"), ("healthcare", "dentist")], 8),
    ("dermatologist", "Dermatologists & skin clinics", ["dermatology", "medical_skin_care", "dermatologist"],
     [("healthcare:speciality", ".*dermatology.*")], 8),
    ("physio", "Physiotherapy", ["physical_therapy", "physical_medicine_and_rehabilitation", "chiropractor"],
     [("healthcare", "physiotherapist")], 6),
    ("eye_clinic", "Eye clinics & opticians", ["vision_or_eye_care_clinic", "eyewear_store", "optometrist",
                                               "ophthalmologist", "optician"],
     [("shop", "optician"), ("healthcare:speciality", ".*ophthalmology.*")], 6),
    ("vet", "Vets", ["veterinarian", "animal_hospital", "emergency_pet_hospital"], [("amenity", "veterinary")], 6),
    ("pet_shop", "Pet shops & grooming", ["animal_and_pet_store", "pet_store", "animal_or_pet_service",
                                          "pet_groomer", "pet_services", "pet_boarding", "pet_sitting", "dog_trainer"],
     [("shop", "pet|pet_grooming")], 6),
    ("clinic", "Clinics & doctors", ["doctors_office", "pediatric_clinic", "obstetrics_and_gynecology", "orthopedics",
                                     "ear_nose_and_throat", "family_practice", "general_practitioner", "medical_center",
                                     "naturopathic_medicine", "ayurveda", "homeopathic_medicine",
                                     "complementary_and_alternative_medicine", "counseling", "psychiatrist",
                                     "psychologist", "outpatient_care_facility", "specialized_health_care"],
     [("amenity", "clinic|doctors"), ("healthcare", "clinic|doctor|alternative|psychotherapist")], 6),
    ("pharmacy", "Pharmacies & medical stores", ["pharmacy", "pharmacy_and_drug_store", "medical_supply_store"],
     [("amenity", "pharmacy"), ("shop", "chemist|medical_supply")], 3),
    ("clothing", "Clothing, boutiques & sarees", ["fashion_and_apparel_store", "clothing_store", "womens_clothing_store",
                                                 "mens_clothing_store", "childrens_clothing_store", "fashion_boutique",
                                                 "fabric_store", "bridal_shop", "tailor", "clothing_company",
                                                 "sewing_and_alterations"],
     [("shop", "clothes|boutique|fabric|fashion|tailor|bag"), ("craft", "tailor|dressmaker")], 7),
    ("jewellery", "Jewellery shops", ["jewelry_store", "jewelry_and_watches_manufacturer", "watch_store"],
     [("shop", "jewelry|watches")], 7),
    ("footwear", "Footwear shops", ["shoe_store", "shoe_repair"], [("shop", "shoes")], 5),
    ("mobile_electronics", "Mobile & electronics shops", ["mobile_phone_store", "electronics_store", "computer_store",
                                                         "appliance_store", "electronics_repair_shop",
                                                         "mobile_phone_repair", "it_service_and_computer_repair"],
     [("shop", "mobile_phone|electronics|computer|appliance|hifi"), ("craft", "electronics_repair")], 5),
    ("furniture_home", "Furniture & home decor", ["furniture_store", "home_goods_store", "lighting_store",
                                                 "carpet_store", "home_decor", "mattress_store", "kitchen_and_bath",
                                                 "interior_design"],
     [("shop", "furniture|interior_decoration|lighting|carpet|houseware|bed|curtain|kitchen")], 7),
    ("hardware", "Hardware & building supplies", ["hardware_store", "home_improvement_store", "building_supply_store",
                                                  "nursery_and_gardening_store", "paint_store", "tile_store"],
     [("shop", "hardware|doityourself|paint|garden_centre|trade|tiles|bathroom_furnishing")], 5),
    ("grocery", "Grocery & supermarkets", ["grocery_store", "convenience_store", "supermarket", "organic_grocery_store",
                                           "health_food_store", "butcher_shop", "fruits_and_vegetables",
                                           "food_and_beverage_store", "seafood_market", "dairy_store"],
     [("shop", "convenience|supermarket|greengrocer|butcher|health_food|dairy|seafood|grocery|frozen_food")], 4),
    ("bakery_sweets", "Bakeries & sweet shops", ["bakery", "candy_store", "patisserie_cake_shop", "dessert_shop",
                                                 "chocolatier", "cupcake_shop", "indian_sweets_shop"],
     [("shop", "bakery|confectionery|pastry|chocolate")], 5),
    ("gifts_books", "Gifts, toys, books & stationery", ["flowers_and_gifts_store", "florist", "gift_shop", "toy_store",
                                                        "toys_and_games_store", "bookstore",
                                                        "books_music_and_video_store", "arts_crafts_and_hobby_store",
                                                        "stationery_store", "office_supply_store", "party_supply"],
     [("shop", "gift|florist|toys|books|stationery|craft|party|art")], 5),
    ("sports", "Sports & cycle shops", ["sporting_goods_store", "bike_store", "outdoor_gear"],
     [("shop", "sports|bicycle|outdoor")], 5),
    ("auto_parts", "Auto parts & garages", ["auto_parts_store", "vehicle_parts_store", "tire_shop", "automotive_repair",
                                            "car_wash", "motorcycle_repair", "auto_body_shop"],
     [("shop", "car_parts|tyres|car_repair|motorcycle"), ("amenity", "car_wash")], 4),
    ("salon_beauty", "Salons, spas & makeup artists", ["beauty_salon", "hair_salon", "barber", "nail_salon",
                                                       "makeup_artist", "spa", "day_spa", "skin_care_and_makeup",
                                                       "beauty_supply_store", "tattoo_and_piercing", "eyebrow_service",
                                                       "personal_care_and_beauty_store"],
     [("shop", "hairdresser|beauty|cosmetics|massage|tattoo"), ("amenity", "spa")], 6),
    ("gym_fitness", "Gyms, yoga & fitness", ["gym", "fitness_studio", "yoga_studio", "martial_arts_club",
                                             "dance_studio", "pilates_studio", "boxing_class"],
     [("leisure", "fitness_centre|sports_centre"), ("amenity", "dancing_school")], 5),
    ("restaurant_cafe", "Restaurants, cafes & caterers", ["restaurant", "casual_eatery", "cafe", "coffee_shop",
                                                          "fast_food_restaurant", "caterer", "juice_bar",
                                                          "ice_cream_shop", "food_truck"],
     [("amenity", "restaurant|cafe|fast_food|ice_cream")], 4),
    ("tuition", "Tuition, preschools & classes", ["tutoring_service", "preschool", "day_care_preschool",
                                                  "specialty_school", "music_school", "language_school",
                                                  "driving_school", "art_school", "cooking_school"],
     [("amenity", "kindergarten|language_school|music_school|driving_school|prep_school|childcare")], 5),
    ("events_photo", "Events, weddings & photographers", ["party_and_event_planning", "event_photography_service",
                                                          "wedding_planning", "photography_service",
                                                          "photography_store_and_services", "event_or_party_service",
                                                          "florist_wedding"],
     [("craft", "photographer"), ("shop", "photo")], 5),
    ("laundry", "Laundry & dry cleaning", ["dry_cleaning", "laundry_service", "laundromat"],
     [("shop", "laundry|dry_cleaning")], 4),
    ("general_shop", "Other shops", ["=shopping", "department_store", "warehouse_club_store", "specialty_store",
                                     "discount_store", "variety_store"],
     [("shop", "general|variety_store|department_store|wholesale")], 4),
]

CATEGORY_KEYS = [c[0] for c in CATEGORIES]
CATEGORY_LABELS = {c[0]: c[1] for c in CATEGORIES}
CATEGORY_WEIGHT = {c[0]: c[4] for c in CATEGORIES}

COUNTRIES = {
    "IN": ("India", ["Bengaluru", "Mysuru", "Mangaluru", "Hubballi", "Chennai", "Hyderabad", "Mumbai", "Pune",
                     "Delhi", "Kochi", "Coimbatore"]),
    "AU": ("Australia", ["Sydney", "Melbourne", "Brisbane", "Perth", "Adelaide"]),
    "US": ("United States", ["New York", "Los Angeles", "Chicago", "Houston", "Phoenix", "Dallas", "San Diego",
                             "Miami", "Seattle", "Atlanta"]),
    "GB": ("United Kingdom", ["London", "Manchester", "Birmingham", "Leeds", "Glasgow", "Bristol", "Liverpool"]),
    "IE": ("Ireland", ["Dublin", "Cork", "Galway", "Limerick"]),
    "IT": ("Italy", ["Rome", "Milan", "Naples", "Turin", "Florence", "Bologna"]),
    "AE": ("United Arab Emirates", ["Dubai", "Abu Dhabi", "Sharjah"]),
    "CA": ("Canada", ["Toronto", "Vancouver", "Calgary", "Montreal"]),
    "NZ": ("New Zealand", ["Auckland", "Wellington", "Christchurch"]),
    "SG": ("Singapore", ["Singapore"]),
}

SEARCH_REGION = {"IN": "in-en", "AU": "au-en", "US": "us-en", "GB": "uk-en", "IE": "ie-en", "IT": "it-it",
                 "AE": "xa-en", "CA": "ca-en", "NZ": "nz-en", "SG": "sg-en"}

# A "website" on one of these is not the business's own site.
SOCIAL_DOMAINS = {
    "facebook.com", "fb.com", "fb.me", "instagram.com", "instagr.am", "twitter.com", "x.com", "youtube.com",
    "youtu.be", "linkedin.com", "wa.me", "whatsapp.com", "linktr.ee", "t.me", "pinterest.com", "tiktok.com",
    "threads.net", "snapchat.com", "telegram.me", "bio.link", "beacons.ai", "linkin.bio",
}
# Matched on the domain name without its ending, so yelp.com, yelp.co.uk and yelp.ie all count.
DIRECTORY_NAMES = {
    "justdial", "indiamart", "sulekha", "practo", "magicpin", "zomato", "swiggy", "yelp", "yellowpages", "tripadvisor",
    "lybrate", "credihealth", "clinicspots", "quikr", "olx", "urbancompany", "urbanclap", "booksy", "fresha",
    "treatwell", "hotfrog", "cylex", "yell", "checkatrade", "bark", "healthgrades", "zocdoc", "ratemds", "whatclinic",
    "opentable", "thefork", "paginegialle", "paginebianche", "goldenpages", "truelocal", "hipages", "localsearch",
    "dubizzle", "yellowpages-uae", "2gis", "about", "idbf", "asklaila", "grotal", "mouthshut", "nearbuy", "dial4trade",
    "tradeindia", "exportersindia", "foursquare", "mapquest", "nextdoor", "houzz", "angi", "homeadvisor", "thumbtack",
    "bbb", "manta", "chamberofcommerce", "doctoralia", "miodottore", "topdoctors", "infobel", "tuugo", "brownbook",
    "n49", "ezlocal", "citysearch", "superpages", "merchantcircle", "locanto", "gumtree", "craigslist", "airbnb",
    "booking", "agoda", "makemytrip", "goibibo", "dineout", "eazydiner", "ubereats", "doordash", "grubhub", "deliveroo",
    "justeat", "just-eat", "talabat", "menulog", "google", "goo", "g", "apple", "bing", "waze", "dentagama",
    "singleinterface", "nowfloats-listing", "jdmart", "sitejabber", "trustpilot", "glassdoor", "ambitionbox",
    "bharatbz", "promallu", "cybo", "placedigger", "healthdial", "eyehospitalnearme", "mysorebiz", "bangalorebiz",
    "dentalimplantprice", "grexa", "zaubacorp", "tofler", "indiacom", "getmeashop", "shopsnearme", "local",
    "allevents", "joonsquare", "storeboard", "find-us-here", "wheree", "yably", "worldorgs", "bizdb", "ourbis",
    "infoisinfo", "near", "nearbyshops", "callupcontact", "medindia", "docindia", "sehat", "credihealth", "hexahealth",
    "pristyncare", "clinicspots", "drlogy", "lybrate", "1mg", "practo", "skinkraft", "dentalkart", "findatopdoc",
    "whatsupdoc", "vymaps", "mapcarta", "wanderlog", "restaurantguru", "menupages", "zmenu", "petbacker",
    "dogspot", "justlanded", "expatica", "loc8nearme", "cataloxy", "ezyfind", "yellowpages-uae", "dubaibizdir",
}
# Domain marketplaces: the shop's domain is up for sale, so it has no working site.
FOR_SALE_NAMES = {"atom", "dan", "sedo", "afternic", "hugedomains", "squadhelp", "brandbucket", "undeveloped",
                  "buydomains", "domainmarket", "brandpa"}
# Words every shop uses; ignored when comparing a shop name with a web address.
GENERIC_WORDS = {
    "the", "and", "sri", "shri", "shree", "sree", "new", "dental", "dentist", "dentistry", "clinic", "clinics",
    "hospital", "care", "centre", "center", "shop", "store", "stores", "mart", "enterprises", "enterprise", "traders",
    "trading", "agency", "agencies", "pvt", "ltd", "llc", "inc", "co", "company", "salon", "beauty", "spa", "pet",
    "pets", "skin", "hair", "medical", "medicals", "pharmacy", "boutique", "fashion", "fashions", "collection",
    "collections", "textiles", "garments", "silks", "silk", "jewellers", "jewellery", "jewelry", "jewels", "bakery",
    "sweets", "cafe", "restaurant", "gym", "fitness", "studio", "of", "in", "at", "bangalore", "bengaluru", "mysore",
    "mysuru", "services", "service", "solutions", "world", "point", "house", "hub", "dr", "doctor", "multispeciality",
    "speciality", "specialty", "family", "best", "top", "india", "indian",
}
# Free website builders: still the business's own site, but usually a weak one.
BUILDER_SUFFIXES = (
    "wixsite.com", "blogspot.com", "wordpress.com", "weebly.com", "godaddysites.com", "square.site",
    "sites.google.com", "webnode.com", "webnode.page", "jimdosite.com", "mystrikingly.com", "strikingly.com",
    "carrd.co", "nowfloats.com", "ueniweb.com", "ueni.com", "myshopify.com", "mydukaan.io", "site123.me",
    "business.site", "webflow.io", "framer.website", "my.canva.site", "canva.site",
)
# Google shut down Business Profile websites in 2024, so these links are dead.
DEAD_SUFFIXES = ("business.site",)

# Many small shops only have the generic "shopping" label; their name usually says what they sell.
NAME_HINTS = [
    (r"\bjewel|\bgold\b|\bornaments?\b", "jewellery"),
    (r"\b(silks?|sarees?|sari|textiles?|boutique|garments?|fashions?|tailors?|readymades?|apparels?|clothing|"
     r"dresses|kurtis?|ethnic|menswear|ladies wear|kids wear|hosiery|uniforms?)\b", "clothing"),
    (r"\bdental|\bdentist|\bteeth\b", "dentist"),
    (r"\b(skin|derma)", "dermatologist"),
    (r"\bpets?\b|\baquarium|\bpuppy|\bkennel", "pet_shop"),
    (r"\b(bakery|bakers|sweets?|cakes?|confectioner)", "bakery_sweets"),
    (r"\bfurniture|\binteriors?\b|\bdecor\b|\bcurtains?\b|\bmattress", "furniture_home"),
    (r"\b(mobiles?|electronics?|computers?|laptops?|cell ?phones?)\b", "mobile_electronics"),
    (r"\boptical|\bopticians?\b|\bspectacles?\b|\beye\b", "eye_clinic"),
    (r"\b(salon|parlou?r|spa|makeup|unisex|barber)\b", "salon_beauty"),
    (r"\b(medicals?|pharma|chemists?|druggists?)\b", "pharmacy"),
    (r"\b(hardware|paints?|sanitary|tiles|plywood|ply|electricals?|plumbing)\b", "hardware"),
    (r"\b(footwear|shoes?|chappals?|sandals?)\b", "footwear"),
    (r"\b(gym|fitness|yoga)\b", "gym_fitness"),
    (r"\b(stationery|stationers|books?|gifts?|toys?|florists?|flowers?|novelties)\b", "gifts_books"),
    (r"\b(provision|provisions|kirana|supermarket|super market|grocer|general stores?|departmental)\b", "grocery"),
    (r"\b(tyres?|motors|spares|auto parts|automobiles?)\b", "auto_parts"),
    (r"\b(photography|photo studio|events?|caterers?|catering|decorators?)\b", "events_photo"),
]

# The morning run works down this list: one new city whenever the previous ones are checked.
# A city is scanned again after 30 days to pick up new shops.
DAILY_TARGETS = [
    ("IN", "Bengaluru"), ("IN", "Mysuru"), ("IN", "Mangaluru"), ("IN", "Hubballi"), ("IN", "Chennai"),
    ("IN", "Hyderabad"), ("IN", "Pune"), ("IN", "Mumbai"), ("IN", "Kochi"), ("IN", "Coimbatore"), ("IN", "Delhi"),
    ("AE", "Dubai"), ("AU", "Sydney"), ("AU", "Melbourne"), ("GB", "London"), ("IE", "Dublin"), ("US", "New York"),
    ("GB", "Manchester"), ("AU", "Brisbane"), ("IE", "Cork"), ("IT", "Milan"), ("IT", "Rome"), ("US", "Chicago"),
    ("US", "Houston"), ("AE", "Abu Dhabi"), ("AU", "Perth"), ("GB", "Birmingham"), ("US", "Los Angeles"),
]
