"""
Nutrient Research Data for Nigerian Foods

This file contains researched nutrient values for the 8 NEW nutrients:
- fiber (g)
- sodium (mg)
- magnesium (mg)
- vitamin_a (mcg RAE - Retinol Activity Equivalents)
- vitamin_c (mg)
- vitamin_d (mcg)
- vitamin_b12 (mcg)
- folate (mcg DFE - Dietary Folate Equivalents)

Sources:
- USDA FoodData Central (https://fdc.nal.usda.gov/)
- West African Food Composition Tables
- FAO/INFOODS Food Composition Database

All values are per 100g of food.
"""

# New nutrients to add (per 100g)
# Format: food_id -> {fiber, sodium, magnesium, vitamin_a, vitamin_c, vitamin_d, vitamin_b12, folate}

NUTRIENT_DATA = {
    # ==================== STARCHES ====================
    "boiled_yam": {
        "fiber": 1.8,        # USDA: yam, cooked, boiled
        "sodium": 8.0,       # USDA: very low sodium
        "magnesium": 18.0,   # USDA
        "vitamin_a": 7.0,    # USDA: minimal
        "vitamin_c": 12.0,   # USDA: some retained after cooking
        "vitamin_d": 0.0,    # Not a source
        "vitamin_b12": 0.0,  # Plant food - no B12
        "folate": 16.0       # USDA
    },
    "fried_plantain_ripe": {
        "fiber": 2.3,        # USDA: plantains, fried
        "sodium": 4.0,       # Low unless salted
        "magnesium": 32.0,   # USDA
        "vitamin_a": 56.0,   # Ripe plantain has beta-carotene
        "vitamin_c": 10.0,   # Reduced from frying
        "vitamin_d": 0.0,
        "vitamin_b12": 0.0,
        "folate": 20.0       # USDA
    },
    "jollof_rice": {
        "fiber": 1.5,        # Rice + tomato sauce
        "sodium": 320.0,     # Seasoned dish - moderate sodium
        "magnesium": 20.0,   # From rice and tomatoes
        "vitamin_a": 42.0,   # From tomatoes and palm oil
        "vitamin_c": 6.0,    # Some from tomatoes (reduced by cooking)
        "vitamin_d": 0.0,
        "vitamin_b12": 0.0,
        "folate": 12.0       # White rice has low folate
    },
    "white_rice_boiled": {
        "fiber": 0.4,        # USDA: white rice, cooked - very low fiber
        "sodium": 1.0,       # USDA: unsalted
        "magnesium": 12.0,   # USDA
        "vitamin_a": 0.0,    # USDA: none
        "vitamin_c": 0.0,    # USDA: none
        "vitamin_d": 0.0,
        "vitamin_b12": 0.0,
        "folate": 3.0        # USDA: very low (not enriched)
    },
    "fried_yam": {
        "fiber": 1.6,        # Similar to boiled yam
        "sodium": 12.0,      # Slightly higher from frying
        "magnesium": 17.0,
        "vitamin_a": 7.0,
        "vitamin_c": 8.0,    # Reduced from frying
        "vitamin_d": 0.0,
        "vitamin_b12": 0.0,
        "folate": 14.0
    },
    "boiled_plantain_unripe": {
        "fiber": 2.0,        # USDA: plantains, green, boiled
        "sodium": 3.0,
        "magnesium": 36.0,   # USDA: good source
        "vitamin_a": 38.0,   # Less than ripe
        "vitamin_c": 15.0,   # Better retained when boiled
        "vitamin_d": 0.0,
        "vitamin_b12": 0.0,
        "folate": 22.0       # USDA
    },
    "fried_rice": {
        "fiber": 1.2,        # Rice + vegetables
        "sodium": 450.0,     # Higher due to soy sauce/seasoning
        "magnesium": 18.0,
        "vitamin_a": 180.0,  # From carrots, peas
        "vitamin_c": 8.0,    # From vegetables
        "vitamin_d": 0.0,
        "vitamin_b12": 0.0,
        "folate": 15.0
    },
    "boiled_plantain_ripe": {
        "fiber": 1.8,        # USDA
        "sodium": 3.0,
        "magnesium": 30.0,
        "vitamin_a": 50.0,   # Beta-carotene from ripeness
        "vitamin_c": 12.0,
        "vitamin_d": 0.0,
        "vitamin_b12": 0.0,
        "folate": 20.0
    },
    "boli": {  # Roasted plantain
        "fiber": 2.0,
        "sodium": 4.0,
        "magnesium": 34.0,
        "vitamin_a": 52.0,
        "vitamin_c": 14.0,   # Better retained than fried
        "vitamin_d": 0.0,
        "vitamin_b12": 0.0,
        "folate": 22.0
    },
    "coconut_rice": {
        "fiber": 1.8,        # From coconut milk
        "sodium": 280.0,     # Seasoned
        "magnesium": 25.0,   # Coconut adds magnesium
        "vitamin_a": 0.0,
        "vitamin_c": 1.0,
        "vitamin_d": 0.0,
        "vitamin_b12": 0.0,
        "folate": 8.0
    },
    "white_bread": {
        "fiber": 2.7,        # USDA: white bread
        "sodium": 491.0,     # USDA: moderate-high
        "magnesium": 23.0,   # USDA
        "vitamin_a": 0.0,    # USDA
        "vitamin_c": 0.0,    # USDA
        "vitamin_d": 0.0,
        "vitamin_b12": 0.0,
        "folate": 98.0       # USDA: often enriched
    },
    "agege_bread": {
        "fiber": 2.5,        # Similar to white bread
        "sodium": 480.0,     # Nigerian bread, salted
        "magnesium": 22.0,
        "vitamin_a": 0.0,
        "vitamin_c": 0.0,
        "vitamin_d": 0.0,
        "vitamin_b12": 0.0,
        "folate": 85.0       # May not be enriched
    },
    "whole_wheat_bread": {
        "fiber": 6.8,        # USDA: whole wheat - HIGH fiber
        "sodium": 450.0,     # USDA
        "magnesium": 75.0,   # USDA: good source
        "vitamin_a": 0.0,
        "vitamin_c": 0.0,
        "vitamin_d": 0.0,
        "vitamin_b12": 0.0,
        "folate": 42.0       # USDA
    },

    # ==================== SWALLOWS ====================
    "eba_garri": {
        "fiber": 1.8,        # Cassava fiber
        "sodium": 2.0,       # Very low
        "magnesium": 21.0,
        "vitamin_a": 1.0,    # Minimal (unless yellow garri)
        "vitamin_c": 0.0,    # Lost in processing
        "vitamin_d": 0.0,
        "vitamin_b12": 0.0,
        "folate": 24.0       # USDA: cassava
    },
    "pounded_yam": {
        "fiber": 1.5,
        "sodium": 6.0,
        "magnesium": 16.0,
        "vitamin_a": 6.0,
        "vitamin_c": 8.0,    # Some retained
        "vitamin_d": 0.0,
        "vitamin_b12": 0.0,
        "folate": 14.0
    },
    "amala": {
        "fiber": 1.6,        # Yam flour
        "sodium": 4.0,
        "magnesium": 18.0,
        "vitamin_a": 5.0,
        "vitamin_c": 2.0,    # Mostly lost in drying
        "vitamin_d": 0.0,
        "vitamin_b12": 0.0,
        "folate": 12.0
    },
    "fufu_cassava": {
        "fiber": 1.5,
        "sodium": 3.0,
        "magnesium": 18.0,
        "vitamin_a": 1.0,
        "vitamin_c": 0.0,    # Lost in fermentation
        "vitamin_d": 0.0,
        "vitamin_b12": 0.0,
        "folate": 20.0
    },
    "pounded_yam_traditional": {
        "fiber": 1.5,
        "sodium": 6.0,
        "magnesium": 16.0,
        "vitamin_a": 6.0,
        "vitamin_c": 8.0,
        "vitamin_d": 0.0,
        "vitamin_b12": 0.0,
        "folate": 14.0
    },
    "semovita": {
        "fiber": 2.5,        # Semolina-based
        "sodium": 3.0,
        "magnesium": 35.0,   # Wheat semolina has magnesium
        "vitamin_a": 0.0,
        "vitamin_c": 0.0,
        "vitamin_d": 0.0,
        "vitamin_b12": 0.0,
        "folate": 35.0       # Wheat has folate
    },
    "tuwo_shinkafa": {
        "fiber": 0.5,        # Rice-based swallow
        "sodium": 2.0,
        "magnesium": 10.0,
        "vitamin_a": 0.0,
        "vitamin_c": 0.0,
        "vitamin_d": 0.0,
        "vitamin_b12": 0.0,
        "folate": 4.0
    },

    # ==================== PROTEINS ====================
    "grilled_chicken_breast": {
        "fiber": 0.0,        # Animal protein - no fiber
        "sodium": 74.0,      # USDA: unseasoned
        "magnesium": 29.0,   # USDA
        "vitamin_a": 6.0,    # USDA: minimal
        "vitamin_c": 0.0,    # USDA
        "vitamin_d": 0.2,    # USDA: small amount
        "vitamin_b12": 0.34, # USDA: good source
        "folate": 4.0        # USDA
    },
    "grilled_tilapia": {
        "fiber": 0.0,
        "sodium": 56.0,      # USDA
        "magnesium": 34.0,   # USDA: fish is good source
        "vitamin_a": 0.0,    # USDA
        "vitamin_c": 0.0,    # USDA
        "vitamin_d": 3.1,    # USDA: fish has vitamin D
        "vitamin_b12": 1.86, # USDA: excellent source
        "folate": 24.0       # USDA
    },
    "brown_beans_boiled": {
        "fiber": 6.5,        # USDA: cowpeas - HIGH fiber
        "sodium": 4.0,       # USDA: low
        "magnesium": 53.0,   # USDA: excellent source
        "vitamin_a": 1.0,    # USDA
        "vitamin_c": 0.4,    # USDA: minimal
        "vitamin_d": 0.0,
        "vitamin_b12": 0.0,  # Plant food
        "folate": 208.0      # USDA: EXCELLENT source
    },
    "hard_boiled_eggs": {
        "fiber": 0.0,
        "sodium": 124.0,     # USDA
        "magnesium": 10.0,   # USDA
        "vitamin_a": 149.0,  # USDA: eggs are good source
        "vitamin_c": 0.0,    # USDA
        "vitamin_d": 2.2,    # USDA: one of few food sources
        "vitamin_b12": 1.11, # USDA: good source
        "folate": 44.0       # USDA
    },
    "fried_chicken": {
        "fiber": 0.4,        # From breading
        "sodium": 320.0,     # Seasoned
        "magnesium": 22.0,
        "vitamin_a": 12.0,
        "vitamin_c": 0.0,
        "vitamin_d": 0.2,
        "vitamin_b12": 0.32,
        "folate": 8.0
    },
    "beef_stewed": {
        "fiber": 0.0,
        "sodium": 65.0,      # USDA: cooked beef
        "magnesium": 22.0,   # USDA
        "vitamin_a": 0.0,    # USDA: lean beef
        "vitamin_c": 0.0,    # USDA
        "vitamin_d": 0.1,    # USDA
        "vitamin_b12": 2.64, # USDA: excellent source
        "folate": 8.0        # USDA
    },
    "goat_meat_stewed": {
        "fiber": 0.0,
        "sodium": 82.0,      # USDA
        "magnesium": 23.0,   # USDA
        "vitamin_a": 0.0,    # USDA
        "vitamin_c": 0.0,    # USDA
        "vitamin_d": 0.1,
        "vitamin_b12": 1.13, # USDA
        "folate": 5.0        # USDA
    },
    "fried_fish": {
        "fiber": 0.3,        # From breading
        "sodium": 280.0,     # Seasoned
        "magnesium": 30.0,
        "vitamin_a": 12.0,
        "vitamin_c": 0.0,
        "vitamin_d": 2.8,
        "vitamin_b12": 1.5,
        "folate": 18.0
    },
    "fried_eggs": {
        "fiber": 0.0,
        "sodium": 207.0,     # USDA: slightly higher from cooking
        "magnesium": 11.0,   # USDA
        "vitamin_a": 175.0,  # USDA
        "vitamin_c": 0.0,
        "vitamin_d": 2.0,    # USDA
        "vitamin_b12": 1.0,  # USDA
        "folate": 51.0       # USDA
    },
    "suya": {
        "fiber": 0.0,
        "sodium": 520.0,     # High from suya spice
        "magnesium": 24.0,
        "vitamin_a": 8.0,    # From spices
        "vitamin_c": 0.0,
        "vitamin_d": 0.1,
        "vitamin_b12": 2.5,
        "folate": 6.0
    },
    "moi_moi": {
        "fiber": 4.5,        # Beans-based - good fiber
        "sodium": 380.0,     # Seasoned
        "magnesium": 45.0,   # From beans
        "vitamin_a": 25.0,   # From peppers, palm oil
        "vitamin_c": 2.0,
        "vitamin_d": 0.0,
        "vitamin_b12": 0.0,  # Unless egg added
        "folate": 150.0      # Beans are excellent
    },
    "ponmo": {
        "fiber": 0.0,
        "sodium": 45.0,
        "magnesium": 5.0,
        "vitamin_a": 0.0,
        "vitamin_c": 0.0,
        "vitamin_d": 0.0,
        "vitamin_b12": 0.5,
        "folate": 2.0
    },
    "kilishi": {
        "fiber": 0.0,
        "sodium": 680.0,     # Very high - dried/seasoned
        "magnesium": 28.0,
        "vitamin_a": 15.0,   # From spices
        "vitamin_c": 0.0,
        "vitamin_d": 0.1,
        "vitamin_b12": 3.2,  # Concentrated from drying
        "folate": 8.0
    },
    "fried_catfish": {
        "fiber": 0.3,
        "sodium": 260.0,
        "magnesium": 28.0,
        "vitamin_a": 15.0,
        "vitamin_c": 0.0,
        "vitamin_d": 12.5,   # Catfish is high in vitamin D
        "vitamin_b12": 2.4,
        "folate": 10.0
    },
    "smoked_fish_panla": {
        "fiber": 0.0,
        "sodium": 520.0,     # High from smoking/curing
        "magnesium": 35.0,
        "vitamin_a": 20.0,
        "vitamin_c": 0.0,
        "vitamin_d": 4.8,
        "vitamin_b12": 3.2,  # Concentrated
        "folate": 12.0
    },
    "stock_fish": {
        "fiber": 0.0,
        "sodium": 350.0,     # Preserved
        "magnesium": 40.0,
        "vitamin_a": 10.0,
        "vitamin_c": 0.0,
        "vitamin_d": 3.5,
        "vitamin_b12": 4.0,  # High - concentrated
        "folate": 15.0
    },
    "snail_cooked": {
        "fiber": 0.0,
        "sodium": 70.0,      # USDA
        "magnesium": 250.0,  # USDA: very high!
        "vitamin_a": 30.0,   # USDA
        "vitamin_c": 0.0,
        "vitamin_d": 0.0,
        "vitamin_b12": 0.5,
        "folate": 6.0
    },
    "egg_sauce_nigerian": {
        "fiber": 1.2,        # From tomatoes, onions
        "sodium": 350.0,     # Seasoned
        "magnesium": 14.0,
        "vitamin_a": 180.0,  # Eggs + tomatoes + palm oil
        "vitamin_c": 8.0,    # From tomatoes
        "vitamin_d": 1.8,    # From eggs
        "vitamin_b12": 0.9,  # From eggs
        "folate": 48.0
    },

    # ==================== VEGETABLES ====================
    "fresh_tomatoes": {
        "fiber": 1.2,        # USDA
        "sodium": 5.0,       # USDA: very low
        "magnesium": 11.0,   # USDA
        "vitamin_a": 42.0,   # USDA: beta-carotene
        "vitamin_c": 13.7,   # USDA
        "vitamin_d": 0.0,
        "vitamin_b12": 0.0,
        "folate": 15.0       # USDA
    },
    "bell_peppers": {
        "fiber": 2.1,        # USDA
        "sodium": 4.0,       # USDA
        "magnesium": 12.0,   # USDA
        "vitamin_a": 157.0,  # USDA: red peppers high in beta-carotene
        "vitamin_c": 127.7,  # USDA: EXCELLENT source
        "vitamin_d": 0.0,
        "vitamin_b12": 0.0,
        "folate": 46.0       # USDA
    },
    "raw_onions": {
        "fiber": 1.7,        # USDA
        "sodium": 4.0,       # USDA
        "magnesium": 10.0,   # USDA
        "vitamin_a": 0.0,    # USDA
        "vitamin_c": 7.4,    # USDA
        "vitamin_d": 0.0,
        "vitamin_b12": 0.0,
        "folate": 19.0       # USDA
    },
    "spinach_raw": {
        "fiber": 2.2,        # USDA
        "sodium": 79.0,      # USDA: moderate
        "magnesium": 79.0,   # USDA: excellent source
        "vitamin_a": 469.0,  # USDA: EXCELLENT source
        "vitamin_c": 28.1,   # USDA
        "vitamin_d": 0.0,
        "vitamin_b12": 0.0,
        "folate": 194.0      # USDA: excellent source
    },
    "cucumber": {
        "fiber": 0.5,        # USDA
        "sodium": 2.0,       # USDA
        "magnesium": 13.0,   # USDA
        "vitamin_a": 5.0,    # USDA
        "vitamin_c": 2.8,    # USDA
        "vitamin_d": 0.0,
        "vitamin_b12": 0.0,
        "folate": 7.0        # USDA
    },
    "ugwu_leaves": {
        "fiber": 2.8,        # Nigerian pumpkin leaves
        "sodium": 45.0,
        "magnesium": 85.0,   # Very high - dark leafy green
        "vitamin_a": 680.0,  # VERY high - deep green
        "vitamin_c": 35.0,   # Good source
        "vitamin_d": 0.0,
        "vitamin_b12": 0.0,
        "folate": 220.0      # Excellent - leafy greens
    },
    "coleslaw_nigerian": {
        "fiber": 2.5,        # Cabbage + carrots
        "sodium": 180.0,     # Mayonnaise adds sodium
        "magnesium": 15.0,
        "vitamin_a": 85.0,   # From carrots
        "vitamin_c": 25.0,   # From cabbage
        "vitamin_d": 0.0,
        "vitamin_b12": 0.0,
        "folate": 35.0
    },
    "carrots_raw": {
        "fiber": 2.8,        # USDA
        "sodium": 69.0,      # USDA
        "magnesium": 12.0,   # USDA
        "vitamin_a": 835.0,  # USDA: EXCELLENT source
        "vitamin_c": 5.9,    # USDA
        "vitamin_d": 0.0,
        "vitamin_b12": 0.0,
        "folate": 19.0       # USDA
    },
    "cabbage_raw": {
        "fiber": 2.5,        # USDA
        "sodium": 18.0,      # USDA
        "magnesium": 12.0,   # USDA
        "vitamin_a": 5.0,    # USDA
        "vitamin_c": 36.6,   # USDA: good source
        "vitamin_d": 0.0,
        "vitamin_b12": 0.0,
        "folate": 43.0       # USDA
    },
    "garden_egg": {
        "fiber": 3.0,        # African eggplant
        "sodium": 2.0,
        "magnesium": 14.0,
        "vitamin_a": 23.0,
        "vitamin_c": 2.2,
        "vitamin_d": 0.0,
        "vitamin_b12": 0.0,
        "folate": 22.0
    },
    "green_beans_raw": {
        "fiber": 2.7,        # USDA
        "sodium": 6.0,       # USDA
        "magnesium": 25.0,   # USDA
        "vitamin_a": 35.0,   # USDA
        "vitamin_c": 12.2,   # USDA
        "vitamin_d": 0.0,
        "vitamin_b12": 0.0,
        "folate": 33.0       # USDA
    },
    "lettuce_raw": {
        "fiber": 1.3,        # USDA
        "sodium": 28.0,      # USDA
        "magnesium": 13.0,   # USDA
        "vitamin_a": 370.0,  # USDA: romaine
        "vitamin_c": 9.2,    # USDA
        "vitamin_d": 0.0,
        "vitamin_b12": 0.0,
        "folate": 136.0      # USDA: good source
    },

    # ==================== SOUPS ====================
    "egusi_soup": {
        "fiber": 2.5,        # From vegetables
        "sodium": 380.0,     # Seasoned
        "magnesium": 55.0,   # Melon seeds are high
        "vitamin_a": 320.0,  # Palm oil + leafy greens
        "vitamin_c": 12.0,   # From vegetables
        "vitamin_d": 0.2,    # From fish/meat if added
        "vitamin_b12": 0.8,  # From protein
        "folate": 85.0       # From vegetables
    },
    "ogbono_soup": {
        "fiber": 3.0,        # Ogbono seeds have fiber
        "sodium": 320.0,
        "magnesium": 48.0,
        "vitamin_a": 280.0,  # Palm oil
        "vitamin_c": 8.0,
        "vitamin_d": 0.2,
        "vitamin_b12": 0.6,
        "folate": 65.0
    },
    "efo_riro": {
        "fiber": 3.5,        # Vegetable-heavy
        "sodium": 350.0,
        "magnesium": 65.0,   # Leafy greens
        "vitamin_a": 520.0,  # VERY high - dark greens
        "vitamin_c": 18.0,   # From vegetables
        "vitamin_d": 0.2,
        "vitamin_b12": 0.5,
        "folate": 145.0      # Excellent - leafy greens
    },
    "pepper_soup_goat": {
        "fiber": 0.5,        # Broth-based
        "sodium": 420.0,     # Highly seasoned
        "magnesium": 22.0,
        "vitamin_a": 25.0,   # From peppers
        "vitamin_c": 5.0,
        "vitamin_d": 0.1,
        "vitamin_b12": 1.0,  # From goat meat
        "folate": 12.0
    },
    "banga_soup": {
        "fiber": 2.8,        # Palm fruit pulp
        "sodium": 280.0,
        "magnesium": 42.0,
        "vitamin_a": 450.0,  # Very high - palm fruit
        "vitamin_c": 10.0,
        "vitamin_d": 0.2,
        "vitamin_b12": 0.8,
        "folate": 55.0
    },
    "afang_soup": {
        "fiber": 4.0,        # Two types of leafy vegetables
        "sodium": 360.0,
        "magnesium": 70.0,   # High - leafy greens
        "vitamin_a": 580.0,  # Very high
        "vitamin_c": 22.0,
        "vitamin_d": 0.2,
        "vitamin_b12": 0.7,
        "folate": 165.0      # Excellent
    },
    "okro_soup": {
        "fiber": 3.2,        # Okra is high fiber
        "sodium": 320.0,
        "magnesium": 50.0,
        "vitamin_a": 280.0,  # Palm oil + vegetables
        "vitamin_c": 15.0,   # Okra has vitamin C
        "vitamin_d": 0.2,
        "vitamin_b12": 0.6,
        "folate": 88.0       # Okra is good source
    },
    "edikang_ikong": {
        "fiber": 4.5,        # Very vegetable-heavy
        "sodium": 380.0,
        "magnesium": 75.0,   # Excellent - dark greens
        "vitamin_a": 620.0,  # EXCELLENT - pumpkin leaves + waterleaf
        "vitamin_c": 25.0,
        "vitamin_d": 0.3,
        "vitamin_b12": 1.2,  # More protein typically
        "folate": 180.0      # Excellent
    },
    "tomato_stew_nigerian": {
        "fiber": 1.8,        # Tomatoes, peppers
        "sodium": 420.0,     # Seasoned
        "magnesium": 22.0,
        "vitamin_a": 180.0,  # Tomatoes + palm oil
        "vitamin_c": 12.0,   # From tomatoes/peppers
        "vitamin_d": 0.0,
        "vitamin_b12": 0.0,
        "folate": 28.0
    },
    "bitterleaf_soup": {
        "fiber": 3.8,        # Leafy vegetable soup
        "sodium": 340.0,
        "magnesium": 62.0,
        "vitamin_a": 380.0,
        "vitamin_c": 15.0,
        "vitamin_d": 0.2,
        "vitamin_b12": 0.8,
        "folate": 125.0
    },

    # ==================== SNACKS ====================
    "akara": {
        "fiber": 4.2,        # Bean-based
        "sodium": 380.0,     # Seasoned, fried
        "magnesium": 48.0,
        "vitamin_a": 20.0,
        "vitamin_c": 1.0,
        "vitamin_d": 0.0,
        "vitamin_b12": 0.0,
        "folate": 140.0      # Beans are excellent
    },
    "puff_puff": {
        "fiber": 1.2,        # Wheat flour
        "sodium": 280.0,
        "magnesium": 15.0,
        "vitamin_a": 0.0,
        "vitamin_c": 0.0,
        "vitamin_d": 0.0,
        "vitamin_b12": 0.0,
        "folate": 35.0
    },
    "chin_chin": {
        "fiber": 1.5,        # Wheat flour
        "sodium": 320.0,     # Salted
        "magnesium": 18.0,
        "vitamin_a": 15.0,   # From eggs in recipe
        "vitamin_c": 0.0,
        "vitamin_d": 0.2,
        "vitamin_b12": 0.1,
        "folate": 42.0
    },
    "groundnut_roasted": {
        "fiber": 8.5,        # USDA: peanuts - HIGH
        "sodium": 18.0,      # USDA: unsalted
        "magnesium": 168.0,  # USDA: EXCELLENT source
        "vitamin_a": 0.0,    # USDA
        "vitamin_c": 0.0,    # USDA
        "vitamin_d": 0.0,
        "vitamin_b12": 0.0,
        "folate": 240.0      # USDA: excellent source
    },

    # ==================== FRUITS ====================
    "watermelon_fresh": {
        "fiber": 0.4,        # USDA
        "sodium": 1.0,       # USDA
        "magnesium": 10.0,   # USDA
        "vitamin_a": 28.0,   # USDA
        "vitamin_c": 8.1,    # USDA
        "vitamin_d": 0.0,
        "vitamin_b12": 0.0,
        "folate": 3.0        # USDA
    },
    "pineapple_fresh": {
        "fiber": 1.4,        # USDA
        "sodium": 1.0,       # USDA
        "magnesium": 12.0,   # USDA
        "vitamin_a": 3.0,    # USDA
        "vitamin_c": 47.8,   # USDA: good source
        "vitamin_d": 0.0,
        "vitamin_b12": 0.0,
        "folate": 18.0       # USDA
    },
    "banana_fresh": {
        "fiber": 2.6,        # USDA
        "sodium": 1.0,       # USDA
        "magnesium": 27.0,   # USDA
        "vitamin_a": 3.0,    # USDA
        "vitamin_c": 8.7,    # USDA
        "vitamin_d": 0.0,
        "vitamin_b12": 0.0,
        "folate": 20.0       # USDA
    },
    "pawpaw_fresh": {
        "fiber": 1.7,        # USDA: papaya
        "sodium": 8.0,       # USDA
        "magnesium": 21.0,   # USDA
        "vitamin_a": 47.0,   # USDA
        "vitamin_c": 60.9,   # USDA: excellent source
        "vitamin_d": 0.0,
        "vitamin_b12": 0.0,
        "folate": 37.0       # USDA
    },
    "orange_fresh": {
        "fiber": 2.4,        # USDA
        "sodium": 0.0,       # USDA
        "magnesium": 10.0,   # USDA
        "vitamin_a": 11.0,   # USDA
        "vitamin_c": 53.2,   # USDA: excellent source
        "vitamin_d": 0.0,
        "vitamin_b12": 0.0,
        "folate": 30.0       # USDA
    },
    "mango_fresh": {
        "fiber": 1.6,        # USDA
        "sodium": 1.0,       # USDA
        "magnesium": 10.0,   # USDA
        "vitamin_a": 54.0,   # USDA
        "vitamin_c": 36.4,   # USDA: good source
        "vitamin_d": 0.0,
        "vitamin_b12": 0.0,
        "folate": 43.0       # USDA
    },
    "apple_fresh": {
        "fiber": 2.4,        # USDA
        "sodium": 1.0,       # USDA
        "magnesium": 5.0,    # USDA
        "vitamin_a": 3.0,    # USDA
        "vitamin_c": 4.6,    # USDA
        "vitamin_d": 0.0,
        "vitamin_b12": 0.0,
        "folate": 3.0        # USDA
    },
    "agbalumo": {
        "fiber": 3.0,        # African star apple - fibrous
        "sodium": 5.0,
        "magnesium": 18.0,
        "vitamin_a": 35.0,
        "vitamin_c": 25.0,   # Good source
        "vitamin_d": 0.0,
        "vitamin_b12": 0.0,
        "folate": 15.0
    },

    # ==================== BEVERAGES ====================
    "zobo": {
        "fiber": 0.5,        # Hibiscus tea
        "sodium": 8.0,
        "magnesium": 12.0,
        "vitamin_a": 15.0,   # From hibiscus
        "vitamin_c": 18.0,   # Hibiscus is good source
        "vitamin_d": 0.0,
        "vitamin_b12": 0.0,
        "folate": 5.0
    },
    "kunu": {
        "fiber": 1.5,        # Millet-based
        "sodium": 15.0,
        "magnesium": 25.0,   # Millet has magnesium
        "vitamin_a": 2.0,
        "vitamin_c": 0.0,
        "vitamin_d": 0.0,
        "vitamin_b12": 0.0,
        "folate": 20.0       # Millet has folate
    },

    # ==================== CONDIMENT ====================
    "palm_oil": {
        "fiber": 0.0,
        "sodium": 0.0,
        "magnesium": 0.0,
        "vitamin_a": 5000.0, # VERY HIGH - red palm oil
        "vitamin_c": 0.0,
        "vitamin_d": 0.0,
        "vitamin_b12": 0.0,
        "folate": 0.0
    },
}


def get_nutrient_data(food_id: str) -> dict:
    """Get new nutrient data for a food item."""
    return NUTRIENT_DATA.get(food_id, None)


def get_all_food_ids() -> list:
    """Get all food IDs with nutrient data."""
    return list(NUTRIENT_DATA.keys())


if __name__ == "__main__":
    # Verification
    print(f"Total foods with nutrient data: {len(NUTRIENT_DATA)}")

    # Check for any missing nutrients
    required_nutrients = ["fiber", "sodium", "magnesium", "vitamin_a", "vitamin_c", "vitamin_d", "vitamin_b12", "folate"]

    for food_id, nutrients in NUTRIENT_DATA.items():
        missing = [n for n in required_nutrients if n not in nutrients]
        if missing:
            print(f"WARNING: {food_id} missing: {missing}")

    print("\nAll nutrients validated successfully!")
