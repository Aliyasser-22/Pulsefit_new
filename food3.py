"""
food_logger_v3.py — Egyptian Food Logger for AI Gym Trainer (V3 Hybrid)

Architecture:
  • Base: V1's full FOOD_DB (~170 items), FRANCO_MAP, and COOKING_METHODS system.
  • Search pipeline: Exact Match → Franco Normalisation → Fuzzy Match → Groq AI Fallback.
  • Cooking: ask_cooking: True items trigger COOKING_METHODS macro multipliers (no oil prompts).
  • Groq AI: unknown foods are looked up on demand. Results are NOT cached — add
    confirmed foods directly to FOOD_DB to make them permanent.

All foods per 100g base. Integrates with user_profile.py for calorie targets.
"""

import os
import json
import datetime
from pathlib import Path
from difflib import get_close_matches

# ─────────────────────────────────────────────
# FRANCO-ARABIC -> ENGLISH LOCAL MAP  (from V1)
# ─────────────────────────────────────────────

FRANCO_MAP = {
    # proteins
    "fera5": "chicken", "fra5": "chicken", "ferakh": "chicken", "ferakha": "chicken",
    "la7ma": "beef", "la7m": "beef", "lahma": "beef",
    "samak": "fish", "beed": "eggs", "bed": "eggs", "beid": "eggs",
    "kebda": "liver", "kofta": "kofta", "kebab": "kebab",
    "gambari": "shrimp", "hamam": "pigeon",
    # grains / starches
    "roz": "rice", "makarona": "pasta", "macarona": "pasta",
    "sha3reya": "vermicelli", "aish": "bread", "d2ee2": "flour", "de2ee2": "flour",
    "shofan": "oats", "bleela": "oatmeal",
    # vegetables
    "batates": "potato", "betingan": "eggplant", "kousa": "zucchini",
    "felfel": "pepper", "tamatem": "tomato", "tomatem": "tomato",
    "bassal": "onion", "toom": "garlic", "sabanekh": "spinach",
    "molokhia": "molokhia", "bamia": "okra", "qolqas": "taro",
    "gazr": "carrot", "khyar": "cucumber", "5yar": "cucumber",
    "brokli": "broccoli", "arnabeet": "cauliflower", "kronb": "cabbage",
    "khass": "lettuce", "5ass": "lettuce", "figl": "radish",
    "dooh": "corn", "dora": "corn",
    # fruits
    "mooz": "banana", "manga": "mango", "farawla": "strawberry",
    "bortoan": "orange", "bortoaan": "orange", "bortqan": "orange",
    "tofah": "apple", "tofa7": "apple", "ananas": "pineapple",
    "pinabl": "pineapple", "pineabl": "pineapple",
    "3enab": "grapes", "enab": "grapes", "teen": "figs",
    "bate5": "watermelon", "bate7": "watermelon",
    "shamam": "cantaloupe", "rumman": "pomegranate", "lemon": "lemon",
    "lamoon": "lemon", "gawafa": "guava", "2agaz": "pear", "agaz": "pear",
    "khoo5": "peach", "5oo5": "peach", "meshmesh": "apricot",
    "karaz": "cherries", "kiwi": "kiwi",
    # dairy
    "laban": "milk", "zabadi": "yogurt", "gebna": "cheese",
    "gibna": "cheese", "qeshta": "cream", "zebda": "butter", "samna": "ghee",
    # cooking style keywords
    "mashwy": "grilled", "mashweya": "grilled",
    "maqli": "fried", "maqliya": "fried",
    "maslooq": "boiled", "maslooqa": "boiled",
    "mehamara": "roasted", "banee": "breaded",
    # dishes
    "ful": "fava beans", "ads": "lentils", "ta3mya": "falafel",
    "koshary": "koshary", "mahshi": "stuffed", "shorbet": "soup",
    "termis": "lupini", "sudani": "peanuts", "tarb": "tarb",
    "mombar": "mombar", "fesikh": "fesikh", "renga": "renga",
    "kawaree": "trotters", "ro2a2": "roqaq", "roqaq": "roqaq",
    "goulash": "goulash", "qatayef": "qatayef", "zalabia": "zalabia",
    "sahlab": "sahlab", "karkadeh": "hibiscus", "asab": "sugarcane",
    "bashamel": "bechamel", "besarah": "besarah", "fatteh": "fatteh",
    "hawawshi": "hawawshi", "taamya": "falafel",
}

# ─────────────────────────────────────────────
# COOKING METHOD PROFILES  (from V1)
# Deltas applied per 100g on top of raw macros
# ─────────────────────────────────────────────

COOKING_METHODS = {
    "1": {"label": "مشوي (Grilled)",       "fat_add": 0,  "cal_add": 0,   "carb_add": 0},
    "2": {"label": "مسلوق (Boiled)",       "fat_add": 0,  "cal_add": 0,   "carb_add": 0},
    "3": {"label": "محمر (Roasted)",       "fat_add": 5,  "cal_add": 45,  "carb_add": 0},
    "4": {"label": "مقلي (Fried)",         "fat_add": 10, "cal_add": 90,  "carb_add": 0},
    "5": {"label": "باني (Breaded Fried)", "fat_add": 12, "cal_add": 130, "carb_add": 10},
}

# ─────────────────────────────────────────────
# FOOD DATABASE (per 100g)  (from V1 — full set)
#
# ask_cooking: True  → raw ingredient; user picks cooking method → macro delta applied
# ask_cooking: False → complete/prepared dish; log as-is
# is_oil: True       → oil/fat; searchable, no cooking question
# ─────────────────────────────────────────────

FOOD_DB = [

    # ══ COMPLETE DISHES (ask_cooking: False) ══════════════════════════

    # Street food & staples
    {"id": 1,  "name": "Koshary",
     "arabic_names": ["كشري", "koshary", "kushari"],
     "calories": 160, "protein": 5,  "carbs": 30, "fat": 2,  "ask_cooking": False},
    {"id": 2,  "name": "Ful Medames",
     "arabic_names": ["فول", "ful", "fool", "فول مدمس"],
     "calories": 110, "protein": 8,  "carbs": 18, "fat": 2,  "ask_cooking": False},
    {"id": 3,  "name": "Taameya (Egyptian Falafel)",
     "arabic_names": ["طعمية", "ta3mya", "taamya", "ta3meya", "فلافل"],
     "calories": 330, "protein": 13, "carbs": 31, "fat": 17, "ask_cooking": False},
    {"id": 4,  "name": "Hawawshi",
     "arabic_names": ["حواوشي", "hawawshi", "7awawshi"],
     "calories": 280, "protein": 14, "carbs": 25, "fat": 15, "ask_cooking": False},
    {"id": 5,  "name": "Macarona Bechamel",
     "arabic_names": ["مكرونة بشاميل", "makarona bashamel", "macarona bechamel", "باستا بشاميل"],
     "calories": 220, "protein": 9,  "carbs": 22, "fat": 10, "ask_cooking": False},
    {"id": 6,  "name": "Molokhia",
     "arabic_names": ["ملوخية", "molokhia", "molo5ia"],
     "calories": 60,  "protein": 3,  "carbs": 5,  "fat": 3,  "ask_cooking": False},
    {"id": 7,  "name": "Fatteh",
     "arabic_names": ["فتة", "fatteh", "fatta"],
     "calories": 210, "protein": 10, "carbs": 25, "fat": 8,  "ask_cooking": False},
    {"id": 8,  "name": "Bamia (Okra Stew)",
     "arabic_names": ["بامية", "bamia", "bamya"],
     "calories": 90,  "protein": 4,  "carbs": 8,  "fat": 5,  "ask_cooking": False},
    {"id": 9,  "name": "Torly (Mixed Veg Stew)",
     "arabic_names": ["طرلي", "torly", "torli", "خضار مشكل"],
     "calories": 85,  "protein": 3,  "carbs": 10, "fat": 4,  "ask_cooking": False},
    {"id": 10, "name": "Mahshi Kromb (Stuffed Cabbage)",
     "arabic_names": ["محشي كرنب", "mahshi kromb", "ma7shy kromb"],
     "calories": 130, "protein": 3,  "carbs": 20, "fat": 5,  "ask_cooking": False},
    {"id": 11, "name": "Mahshi Waraq Enab (Grape Leaves)",
     "arabic_names": ["محشي ورق عنب", "wara2 3enab", "waraq enab"],
     "calories": 160, "protein": 4,  "carbs": 22, "fat": 7,  "ask_cooking": False},
    {"id": 12, "name": "Mahshi Kousa (Stuffed Zucchini)",
     "arabic_names": ["محشي كوسة", "mahshi kousa", "kousa ma7shy"],
     "calories": 90,  "protein": 3,  "carbs": 14, "fat": 3,  "ask_cooking": False},
    {"id": 13, "name": "Mahshi Felfel (Stuffed Peppers)",
     "arabic_names": ["محشي فلفل", "mahshi felfel"],
     "calories": 85,  "protein": 2,  "carbs": 13, "fat": 3,  "ask_cooking": False},
    {"id": 14, "name": "Mahshi Betingan (Stuffed Eggplant)",
     "arabic_names": ["محشي باذنجان", "mahshi betingan", "ma7shy betingan"],
     "calories": 110, "protein": 3,  "carbs": 16, "fat": 4,  "ask_cooking": False},
    {"id": 15, "name": "Qolqas (Taro Stew)",
     "arabic_names": ["قلقاس", "qolqas", "2ol2as"],
     "calories": 120, "protein": 3,  "carbs": 20, "fat": 4,  "ask_cooking": False},
    {"id": 16, "name": "Bisilla (Pea & Carrot Stew)",
     "arabic_names": ["بسلة", "bisilla", "besella", "بسلة وجزر"],
     "calories": 100, "protein": 5,  "carbs": 14, "fat": 3,  "ask_cooking": False},
    {"id": 17, "name": "Fasoulia (White Bean Stew)",
     "arabic_names": ["فاصوليا", "fasoulia", "fasolia"],
     "calories": 110, "protein": 6,  "carbs": 15, "fat": 3,  "ask_cooking": False},
    {"id": 18, "name": "Sabanekh (Spinach Stew)",
     "arabic_names": ["سبانخ", "sabanekh", "sabanek"],
     "calories": 70,  "protein": 4,  "carbs": 6,  "fat": 4,  "ask_cooking": False},
    {"id": 19, "name": "Batates Saniya (Potato Tray)",
     "arabic_names": ["بطاطس صينية", "batates saniya", "batates saneyya"],
     "calories": 140, "protein": 4,  "carbs": 18, "fat": 6,  "ask_cooking": False},
    {"id": 20, "name": "Besarah",
     "arabic_names": ["بصارة", "besarah", "bisara"],
     "calories": 110, "protein": 7,  "carbs": 16, "fat": 2,  "ask_cooking": False},

    # Grilled/prepared meat dishes
    {"id": 21, "name": "Kebab (Grilled Beef/Lamb)",
     "arabic_names": ["كباب", "kebab", "kibab"],
     "calories": 250, "protein": 25, "carbs": 0,  "fat": 16, "ask_cooking": False},
    {"id": 22, "name": "Kofta (Grilled Minced Meat)",
     "arabic_names": ["كفتة", "kofta", "kufta"],
     "calories": 280, "protein": 20, "carbs": 4,  "fat": 20, "ask_cooking": False},
    {"id": 23, "name": "Tarb (Fat-wrapped Kofta)",
     "arabic_names": ["ترب", "tarb"],
     "calories": 350, "protein": 18, "carbs": 2,  "fat": 30, "ask_cooking": False},
    {"id": 24, "name": "Hamam Mahshi (Stuffed Pigeon)",
     "arabic_names": ["حمام محشي", "hamam mahshi", "7amam ma7shy"],
     "calories": 260, "protein": 22, "carbs": 15, "fat": 12, "ask_cooking": False},
    {"id": 25, "name": "Kebda Eskandarani (Alex Liver)",
     "arabic_names": ["كبدة إسكندراني", "kebda eskandarani", "كبدة إسكندرية"],
     "calories": 190, "protein": 24, "carbs": 5,  "fat": 8,  "ask_cooking": False},
    {"id": 26, "name": "Shish Tawook",
     "arabic_names": ["شيش طاووق", "shish tawook", "shish tawuk"],
     "calories": 170, "protein": 24, "carbs": 3,  "fat": 7,  "ask_cooking": False},
    {"id": 27, "name": "Moza (Slow-cooked Meat Shank)",
     "arabic_names": ["موزة", "moza", "mauza"],
     "calories": 230, "protein": 25, "carbs": 0,  "fat": 14, "ask_cooking": False},

    # Fish — complete (already named by cooking method)
    {"id": 28, "name": "Samak Mashwy (Grilled Fish)",
     "arabic_names": ["سمك مشوي", "samak mashwy", "grilled fish", "سمكة مشوية"],
     "calories": 130, "protein": 20, "carbs": 1,  "fat": 5,  "ask_cooking": False},
    {"id": 29, "name": "Samak Maqli (Fried Fish)",
     "arabic_names": ["سمك مقلي", "samak maqli", "fried fish", "سمكة مقلية"],
     "calories": 210, "protein": 18, "carbs": 8,  "fat": 12, "ask_cooking": False},
    {"id": 30, "name": "Gambari Mashwy (Grilled Shrimp)",
     "arabic_names": ["جمبري مشوي", "gambari mashwy", "grilled shrimp"],
     "calories": 120, "protein": 20, "carbs": 1,  "fat": 3,  "ask_cooking": False},
    {"id": 31, "name": "Gambari Maqli (Fried Shrimp)",
     "arabic_names": ["جمبري مقلي", "gambari maqli", "fried shrimp"],
     "calories": 240, "protein": 16, "carbs": 12, "fat": 14, "ask_cooking": False},
    {"id": 32, "name": "Sayadeya (Spiced Fish Rice)",
     "arabic_names": ["صيادية", "sayadeya", "sayadeyya"],
     "calories": 160, "protein": 6,  "carbs": 28, "fat": 3,  "ask_cooking": False},

    # Soups
    {"id": 33, "name": "Shorbet Ads (Lentil Soup)",
     "arabic_names": ["شوربة عدس", "shorbet ads", "شوربة العدس"],
     "calories": 90,  "protein": 6,  "carbs": 14, "fat": 1,  "ask_cooking": False},
    {"id": 34, "name": "Shorbet Ferakh (Chicken Soup)",
     "arabic_names": ["شوربة فراخ", "shorbet fera5", "chicken soup"],
     "calories": 40,  "protein": 4,  "carbs": 1,  "fat": 2,  "ask_cooking": False},
    {"id": 35, "name": "Shorbet Lahma (Meat Broth)",
     "arabic_names": ["شوربة لحمة", "shorbet la7ma", "meat soup"],
     "calories": 45,  "protein": 5,  "carbs": 1,  "fat": 2,  "ask_cooking": False},

    # Salads & dips
    {"id": 36, "name": "Salata Baladi (Traditional Salad)",
     "arabic_names": ["سلطة بلدي", "salata baladi", "سلطة"],
     "calories": 30,  "protein": 1,  "carbs": 6,  "fat": 0,  "ask_cooking": False},
    {"id": 37, "name": "Torshi (Mixed Pickles)",
     "arabic_names": ["طرشي", "torshi", "pickles"],
     "calories": 15,  "protein": 0,  "carbs": 3,  "fat": 0,  "ask_cooking": False},
    {"id": 38, "name": "Baba Ghanoush",
     "arabic_names": ["بابا غنوش", "baba ghanoush", "baba ghannouj"],
     "calories": 120, "protein": 3,  "carbs": 10, "fat": 8,  "ask_cooking": False},
    {"id": 39, "name": "Tehina (Tahini Dip)",
     "arabic_names": ["طحينة", "tehina", "tahini", "ta7ina"],
     "calories": 300, "protein": 8,  "carbs": 12, "fat": 25, "ask_cooking": False},
    {"id": 40, "name": "Salata Zabadi (Yogurt & Cucumber)",
     "arabic_names": ["سلطة زبادي", "salata zabadi", "zabadi w 5yar"],
     "calories": 60,  "protein": 4,  "carbs": 5,  "fat": 3,  "ask_cooking": False},
    {"id": 41, "name": "Hummus (Halabessa)",
     "arabic_names": ["حمص الشام", "hummus", "7ommos", "حلبسة"],
     "calories": 90,  "protein": 5,  "carbs": 15, "fat": 2,  "ask_cooking": False},

    # Bread & pastry
    {"id": 42, "name": "Aish Baladi (Egyptian Pita)",
     "arabic_names": ["عيش بلدي", "aish baladi", "خبز بلدي", "bread", "عيش"],
     "calories": 270, "protein": 9,  "carbs": 55, "fat": 1,  "ask_cooking": False},
    {"id": 43, "name": "Aish Fino (Egyptian Baguette)",
     "arabic_names": ["عيش فينو", "aish fino", "fino"],
     "calories": 290, "protein": 8,  "carbs": 58, "fat": 3,  "ask_cooking": False},
    {"id": 44, "name": "Fiteer Meshaltet (Flaky Pastry)",
     "arabic_names": ["فطير مشلتت", "feteer", "fiteer", "فطير"],
     "calories": 400, "protein": 6,  "carbs": 40, "fat": 25, "ask_cooking": False},

    # Rice & pasta (cooked, as eaten)
    {"id": 45, "name": "Roz Shaereya (Rice w/ Vermicelli)",
     "arabic_names": ["رز شعرية", "roz sha3reya", "رز بالشعرية"],
     "calories": 150, "protein": 3,  "carbs": 30, "fat": 2,  "ask_cooking": False},
    {"id": 46, "name": "Roz Abyad (Plain White Rice)",
     "arabic_names": ["رز أبيض", "roz abyad", "white rice", "roz", "رز"],
     "calories": 130, "protein": 3,  "carbs": 28, "fat": 0,  "ask_cooking": False},
    {"id": 47, "name": "Makarona Maslooqa (Plain Pasta)",
     "arabic_names": ["مكرونة مسلوقة", "makarona", "pasta", "مكرونة"],
     "calories": 158, "protein": 6,  "carbs": 31, "fat": 1,  "ask_cooking": False},

    # Cheese & dairy
    {"id": 48, "name": "Gibna Roumi (Aged Egyptian Cheese)",
     "arabic_names": ["جبنة رومي", "gibna roumi", "gebna roumi", "رومي"],
     "calories": 380, "protein": 25, "carbs": 2,  "fat": 30, "ask_cooking": False},
    {"id": 49, "name": "Gibna Domiati (Soft White Cheese)",
     "arabic_names": ["جبنة دمياطي", "gibna domiati", "domiati"],
     "calories": 260, "protein": 14, "carbs": 3,  "fat": 21, "ask_cooking": False},
    {"id": 50, "name": "Gibna Qareesh (Cottage Cheese)",
     "arabic_names": ["جبنة قريش", "gibna qareesh", "qareesh", "2areesh"],
     "calories": 100, "protein": 15, "carbs": 4,  "fat": 2,  "ask_cooking": False},
    {"id": 51, "name": "Gebna Barmil (Salty Barrel Cheese)",
     "arabic_names": ["جبنة برميل", "gebna barmil", "barmil"],
     "calories": 280, "protein": 14, "carbs": 2,  "fat": 24, "ask_cooking": False},
    {"id": 52, "name": "Zabadi (Plain Yogurt)",
     "arabic_names": ["زبادي", "zabadi", "yogurt"],
     "calories": 60,  "protein": 4,  "carbs": 5,  "fat": 3,  "ask_cooking": False},
    {"id": 53, "name": "Laban (Whole Milk)",
     "arabic_names": ["لبن", "laban", "milk", "حليب"],
     "calories": 60,  "protein": 3,  "carbs": 5,  "fat": 3,  "ask_cooking": False},
    {"id": 54, "name": "Qeshta (Clotted Cream)",
     "arabic_names": ["قشطة", "qeshta", "2eshta"],
     "calories": 350, "protein": 2,  "carbs": 3,  "fat": 36, "ask_cooking": False},

    # Eggs (already cooked)
    {"id": 55, "name": "Beed Maslooq (Boiled Eggs)",
     "arabic_names": ["بيض مسلوق", "beed maslooq", "boiled eggs"],
     "calories": 155, "protein": 13, "carbs": 1,  "fat": 11, "ask_cooking": False},
    {"id": 56, "name": "Beed Maqli (Fried Eggs)",
     "arabic_names": ["بيض مقلي", "beed maqli", "fried eggs"],
     "calories": 200, "protein": 14, "carbs": 1,  "fat": 15, "ask_cooking": False},
    {"id": 57, "name": "Shakshouka",
     "arabic_names": ["شكشوكة", "shakshouka", "sha5shouka"],
     "calories": 150, "protein": 10, "carbs": 8,  "fat": 10, "ask_cooking": False},
    {"id": 58, "name": "Eggs with Basterma",
     "arabic_names": ["بيض بسطرمة", "beed basterma", "eggs basterma"],
     "calories": 220, "protein": 18, "carbs": 2,  "fat": 15, "ask_cooking": False},

    # Tuna (canned)
    {"id": 59, "name": "Tuna in Water",
     "arabic_names": ["تونة في ماء", "tuna water", "تونة", "tuna"],
     "calories": 110, "protein": 24, "carbs": 0,  "fat": 1,  "ask_cooking": False},
    {"id": 60, "name": "Tuna in Oil (Drained)",
     "arabic_names": ["تونة في زيت", "tuna oil", "tuna zeet"],
     "calories": 190, "protein": 20, "carbs": 0,  "fat": 12, "ask_cooking": False},

    # Processed / cured meats
    {"id": 61, "name": "Sogoq Baladi (Egyptian Sausage)",
     "arabic_names": ["سجق بلدي", "sogoq", "so2o2", "سجق"],
     "calories": 320, "protein": 14, "carbs": 3,  "fat": 28, "ask_cooking": False},
    {"id": 62, "name": "Mombar (Stuffed Intestines)",
     "arabic_names": ["ممبار", "mombar"],
     "calories": 280, "protein": 12, "carbs": 20, "fat": 16, "ask_cooking": False},
    {"id": 63, "name": "Fesikh (Fermented Salted Mullet)",
     "arabic_names": ["فسيخ", "fesikh", "fasikh"],
     "calories": 200, "protein": 25, "carbs": 0,  "fat": 10, "ask_cooking": False},
    {"id": 64, "name": "Renga (Smoked Herring)",
     "arabic_names": ["رنجة", "renga", "ringa"],
     "calories": 210, "protein": 22, "carbs": 0,  "fat": 13, "ask_cooking": False},
    {"id": 65, "name": "Kawaree (Cow Trotters Stew)",
     "arabic_names": ["كوارع", "kawaree", "kawary"],
     "calories": 180, "protein": 20, "carbs": 2,  "fat": 10, "ask_cooking": False},

    # Sweets & desserts
    {"id": 66, "name": "Om Ali (Bread Pudding)",
     "arabic_names": ["أم علي", "om ali", "2om ali"],
     "calories": 300, "protein": 6,  "carbs": 35, "fat": 16, "ask_cooking": False},
    {"id": 67, "name": "Basbousa",
     "arabic_names": ["بسبوسة", "basbousa", "bas2ousa"],
     "calories": 330, "protein": 4,  "carbs": 55, "fat": 10, "ask_cooking": False},
    {"id": 68, "name": "Konafa",
     "arabic_names": ["كنافة", "konafa", "kunafa", "knafeh"],
     "calories": 350, "protein": 5,  "carbs": 45, "fat": 18, "ask_cooking": False},
    {"id": 69, "name": "Roz Bel Laban (Rice Pudding)",
     "arabic_names": ["رز باللبن", "roz bel laban", "رز بالحليب"],
     "calories": 140, "protein": 4,  "carbs": 22, "fat": 4,  "ask_cooking": False},
    {"id": 70, "name": "Mehalabiya (Milk Pudding)",
     "arabic_names": ["محلبية", "mehalabiya", "m7alabeya"],
     "calories": 130, "protein": 3,  "carbs": 20, "fat": 4,  "ask_cooking": False},
    {"id": 71, "name": "Halawa Tahinia (Halva)",
     "arabic_names": ["حلاوة طحينية", "halawa", "7alawa", "halva"],
     "calories": 480, "protein": 12, "carbs": 50, "fat": 28, "ask_cooking": False},
    {"id": 72, "name": "Qatayef (Stuffed Pancakes)",
     "arabic_names": ["قطايف", "qatayef", "2atayef"],
     "calories": 270, "protein": 6,  "carbs": 38, "fat": 11, "ask_cooking": False},
    {"id": 73, "name": "Zalabia (Fried Dough in Syrup)",
     "arabic_names": ["زلابية", "zalabia", "luqma", "لقمة القاضي"],
     "calories": 290, "protein": 4,  "carbs": 45, "fat": 12, "ask_cooking": False},
    {"id": 74, "name": "Bleela (Warm Oatmeal Porridge)",
     "arabic_names": ["بليلة", "bleela", "bli2la"],
     "calories": 130, "protein": 4,  "carbs": 22, "fat": 3,  "ask_cooking": False},

    # Snacks & drinks
    {"id": 75, "name": "Termis (Lupini Beans)",
     "arabic_names": ["ترمس", "termis", "lupini"],
     "calories": 120, "protein": 15, "carbs": 10, "fat": 3,  "ask_cooking": False},
    {"id": 76, "name": "Sudani (Roasted Peanuts)",
     "arabic_names": ["سوداني", "sudani", "peanuts", "فول سوداني"],
     "calories": 560, "protein": 26, "carbs": 16, "fat": 49, "ask_cooking": False},
    {"id": 77, "name": "Karkadeh (Sweetened Hibiscus)",
     "arabic_names": ["كركديه", "karkadeh", "hibiscus"],
     "calories": 40,  "protein": 0,  "carbs": 10, "fat": 0,  "ask_cooking": False},
    {"id": 78, "name": "Sahlab (Hot Milk Beverage)",
     "arabic_names": ["سحلب", "sahlab", "sa7lab"],
     "calories": 120, "protein": 3,  "carbs": 20, "fat": 3,  "ask_cooking": False},
    {"id": 79, "name": "Asab (Sugarcane Juice)",
     "arabic_names": ["عصير قصب", "asab", "2asab", "sugarcane"],
     "calories": 80,  "protein": 0,  "carbs": 20, "fat": 0,  "ask_cooking": False},
    {"id": 80, "name": "Shay (Sweet Tea)",
     "arabic_names": ["شاي", "shay", "tea"],
     "calories": 20,  "protein": 0,  "carbs": 5,  "fat": 0,  "ask_cooking": False},

    # ══ RAW INGREDIENTS — ask cooking method (ask_cooking: True) ══════

    {"id": 101, "name": "Chicken (Raw)",
     "arabic_names": ["فراخ", "fera5", "fra5", "ferakh", "chicken", "دجاج"],
     "calories": 120, "protein": 22, "carbs": 0,  "fat": 3,  "ask_cooking": True},
    {"id": 102, "name": "Beef / Lahma (Raw)",
     "arabic_names": ["لحمة", "la7ma", "lahma", "beef", "لحم بقري"],
     "calories": 215, "protein": 26, "carbs": 0,  "fat": 12, "ask_cooking": True},
    {"id": 103, "name": "Fish / Samak (Raw)",
     "arabic_names": ["سمكة", "samak", "fish", "سمك"],
     "calories": 90,  "protein": 18, "carbs": 0,  "fat": 2,  "ask_cooking": True},
    {"id": 104, "name": "Shrimp / Gambari (Raw)",
     "arabic_names": ["جمبري", "gambari", "shrimp"],
     "calories": 85,  "protein": 18, "carbs": 1,  "fat": 1,  "ask_cooking": True},
    {"id": 105, "name": "Eggs (Raw)",
     "arabic_names": ["بيض", "beed", "bed", "eggs", "بيضة"],
     "calories": 155, "protein": 13, "carbs": 1,  "fat": 11, "ask_cooking": True},
    {"id": 106, "name": "Liver / Kebda (Raw)",
     "arabic_names": ["كبدة", "kebda", "kibda", "liver"],
     "calories": 135, "protein": 20, "carbs": 4,  "fat": 5,  "ask_cooking": True},
    {"id": 107, "name": "Batates (Potato — Raw)",
     "arabic_names": ["بطاطس", "batates", "potato"],
     "calories": 77,  "protein": 2,  "carbs": 17, "fat": 0,  "ask_cooking": True},

    # ══ DRY INGREDIENTS / STAPLES ══════════════════════════════════════

    {"id": 110, "name": "Daqeeq (Plain Flour)",
     "arabic_names": ["دقيق", "d2ee2", "de2ee2", "flour", "دقيق أبيض"],
     "calories": 364, "protein": 10, "carbs": 76, "fat": 1,  "ask_cooking": False},
    {"id": 111, "name": "Shofan (Oats)",
     "arabic_names": ["شوفان", "shofan", "oats"],
     "calories": 389, "protein": 17, "carbs": 66, "fat": 7,  "ask_cooking": False},
    {"id": 112, "name": "Ads (Lentils — Dry)",
     "arabic_names": ["عدس", "ads", "lentils", "عدس جاف"],
     "calories": 353, "protein": 25, "carbs": 60, "fat": 1,  "ask_cooking": False},

    # ══ VEGETABLES (raw / as eaten) ════════════════════════════════════

    {"id": 120, "name": "Tamatem (Tomato)",
     "arabic_names": ["طماطم", "tamatem", "tomatem", "tomato"],
     "calories": 18,  "protein": 1,  "carbs": 4,  "fat": 0,  "ask_cooking": False},
    {"id": 121, "name": "Khyar (Cucumber)",
     "arabic_names": ["خيار", "khyar", "5yar", "cucumber"],
     "calories": 15,  "protein": 1,  "carbs": 3,  "fat": 0,  "ask_cooking": False},
    {"id": 122, "name": "Khass (Lettuce)",
     "arabic_names": ["خس", "khass", "5ass", "lettuce"],
     "calories": 15,  "protein": 1,  "carbs": 2,  "fat": 0,  "ask_cooking": False},
    {"id": 123, "name": "Gazr (Carrot)",
     "arabic_names": ["جزر", "gazr", "carrot"],
     "calories": 41,  "protein": 1,  "carbs": 10, "fat": 0,  "ask_cooking": False},
    {"id": 124, "name": "Bassal (Onion)",
     "arabic_names": ["بصل", "bassal", "onion"],
     "calories": 40,  "protein": 1,  "carbs": 9,  "fat": 0,  "ask_cooking": False},
    {"id": 125, "name": "Felfel Romany (Bell Pepper)",
     "arabic_names": ["فلفل روماني", "felfel", "pepper", "bell pepper", "فلفل"],
     "calories": 31,  "protein": 1,  "carbs": 6,  "fat": 0,  "ask_cooking": False},
    {"id": 126, "name": "Kousa (Zucchini)",
     "arabic_names": ["كوسة", "kousa", "zucchini"],
     "calories": 17,  "protein": 1,  "carbs": 3,  "fat": 0,  "ask_cooking": False},
    {"id": 127, "name": "Betingan (Eggplant)",
     "arabic_names": ["باذنجان", "betingan", "eggplant"],
     "calories": 25,  "protein": 1,  "carbs": 6,  "fat": 0,  "ask_cooking": False},
    {"id": 128, "name": "Arnabeet (Cauliflower)",
     "arabic_names": ["قرنبيط", "arnabeet", "cauliflower"],
     "calories": 25,  "protein": 2,  "carbs": 5,  "fat": 0,  "ask_cooking": False},
    {"id": 129, "name": "Kronb (Cabbage)",
     "arabic_names": ["كرنب", "kronb", "cabbage"],
     "calories": 25,  "protein": 1,  "carbs": 6,  "fat": 0,  "ask_cooking": False},
    {"id": 130, "name": "Brokli (Broccoli)",
     "arabic_names": ["بروكلي", "brokli", "broccoli"],
     "calories": 34,  "protein": 3,  "carbs": 7,  "fat": 0,  "ask_cooking": False},
    {"id": 131, "name": "Figl (Radish)",
     "arabic_names": ["فجل", "figl", "radish"],
     "calories": 16,  "protein": 1,  "carbs": 3,  "fat": 0,  "ask_cooking": False},
    {"id": 132, "name": "Dora (Corn)",
     "arabic_names": ["ذرة", "dora", "dooh", "corn"],
     "calories": 86,  "protein": 3,  "carbs": 19, "fat": 1,  "ask_cooking": False},
    {"id": 133, "name": "Batata Helwa (Sweet Potato)",
     "arabic_names": ["بطاطا حلوة", "batata helwa", "sweet potato", "بطاطا"],
     "calories": 86,  "protein": 2,  "carbs": 20, "fat": 0,  "ask_cooking": False},
    {"id": 134, "name": "Toom (Garlic)",
     "arabic_names": ["ثوم", "toom", "garlic"],
     "calories": 149, "protein": 6,  "carbs": 33, "fat": 1,  "ask_cooking": False},

    # ══ FRUITS ══════════════════════════════════════════════════════════

    {"id": 150, "name": "Mooz (Banana)",
     "arabic_names": ["موز", "mooz", "banana"],
     "calories": 89,  "protein": 1,  "carbs": 23, "fat": 0,  "ask_cooking": False},
    {"id": 151, "name": "Tofah (Apple)",
     "arabic_names": ["تفاح", "tofah", "tofa7", "apple"],
     "calories": 52,  "protein": 0,  "carbs": 14, "fat": 0,  "ask_cooking": False},
    {"id": 152, "name": "Bortoan (Orange)",
     "arabic_names": ["برتقال", "bortoan", "bortoaan", "bortqan", "orange"],
     "calories": 47,  "protein": 1,  "carbs": 12, "fat": 0,  "ask_cooking": False},
    {"id": 153, "name": "Manga (Mango)",
     "arabic_names": ["مانجو", "manga", "mango"],
     "calories": 60,  "protein": 1,  "carbs": 15, "fat": 0,  "ask_cooking": False},
    {"id": 154, "name": "Farawla (Strawberry)",
     "arabic_names": ["فراولة", "farawla", "strawberry"],
     "calories": 32,  "protein": 1,  "carbs": 8,  "fat": 0,  "ask_cooking": False},
    {"id": 155, "name": "3enab (Grapes)",
     "arabic_names": ["عنب", "3enab", "enab", "grapes"],
     "calories": 67,  "protein": 1,  "carbs": 17, "fat": 0,  "ask_cooking": False},
    {"id": 156, "name": "Bate5 (Watermelon)",
     "arabic_names": ["بطيخ", "bate5", "bate7", "watermelon"],
     "calories": 30,  "protein": 1,  "carbs": 8,  "fat": 0,  "ask_cooking": False},
    {"id": 157, "name": "Shamam (Cantaloupe)",
     "arabic_names": ["شمام", "shamam", "cantaloupe"],
     "calories": 34,  "protein": 1,  "carbs": 8,  "fat": 0,  "ask_cooking": False},
    {"id": 158, "name": "Rumman (Pomegranate)",
     "arabic_names": ["رمان", "rumman", "pomegranate"],
     "calories": 83,  "protein": 2,  "carbs": 19, "fat": 1,  "ask_cooking": False},
    {"id": 159, "name": "Gawafa (Guava)",
     "arabic_names": ["جوافة", "gawafa", "guava"],
     "calories": 68,  "protein": 3,  "carbs": 14, "fat": 1,  "ask_cooking": False},
    {"id": 160, "name": "Ananas (Pineapple)",
     "arabic_names": ["أناناس", "ananas", "pinabl", "pineapple"],
     "calories": 50,  "protein": 1,  "carbs": 13, "fat": 0,  "ask_cooking": False},
    {"id": 161, "name": "Teen (Figs)",
     "arabic_names": ["تين", "teen", "figs"],
     "calories": 74,  "protein": 1,  "carbs": 19, "fat": 0,  "ask_cooking": False},
    {"id": 162, "name": "2agaz (Pear)",
     "arabic_names": ["إجاص", "agaz", "2agaz", "pear"],
     "calories": 57,  "protein": 0,  "carbs": 15, "fat": 0,  "ask_cooking": False},
    {"id": 163, "name": "Khoo5 (Peach)",
     "arabic_names": ["خوخ", "khoo5", "5oo5", "peach"],
     "calories": 39,  "protein": 1,  "carbs": 10, "fat": 0,  "ask_cooking": False},
    {"id": 164, "name": "Meshmesh (Apricot)",
     "arabic_names": ["مشمش", "meshmesh", "apricot"],
     "calories": 48,  "protein": 1,  "carbs": 11, "fat": 0,  "ask_cooking": False},
    {"id": 165, "name": "Karaz (Cherries)",
     "arabic_names": ["كرز", "karaz", "cherries"],
     "calories": 63,  "protein": 1,  "carbs": 16, "fat": 0,  "ask_cooking": False},
    {"id": 166, "name": "Kiwi",
     "arabic_names": ["كيوي", "kiwi"],
     "calories": 61,  "protein": 1,  "carbs": 15, "fat": 1,  "ask_cooking": False},
    {"id": 167, "name": "Lamoon (Lemon)",
     "arabic_names": ["ليمون", "lamoon", "lemon"],
     "calories": 29,  "protein": 1,  "carbs": 9,  "fat": 0,  "ask_cooking": False},


    # ══ FROM GROQ CACHE — migrated to DB ══════════════════════════════
    {"id": 206, "name": "Salmon (Raw)",
     "arabic_names": ["سلمون", "salmon", "سمك السلمون"],
     "calories": 208, "protein": 20, "carbs": 0, "fat": 13, "ask_cooking": True},

    # ══ OILS (is_oil: True) ══════════════════════════════════════════════

    {"id": 200, "name": "Zeet Zatoon (Olive Oil)",
     "arabic_names": ["زيت زيتون", "olive oil", "zeet zatoon"],
     "calories": 884, "protein": 0, "carbs": 0, "fat": 100, "ask_cooking": False, "is_oil": True},
    {"id": 201, "name": "Zeet Dora (Corn Oil)",
     "arabic_names": ["زيت ذرة", "corn oil", "zeet dora"],
     "calories": 884, "protein": 0, "carbs": 0, "fat": 100, "ask_cooking": False, "is_oil": True},
    {"id": 202, "name": "Zeet Abbad El Shams (Sunflower Oil)",
     "arabic_names": ["زيت عباد الشمس", "sunflower oil", "sunflower"],
     "calories": 884, "protein": 0, "carbs": 0, "fat": 100, "ask_cooking": False, "is_oil": True},
    {"id": 203, "name": "Samna Nabati (Vegetable Ghee)",
     "arabic_names": ["سمنة نباتي", "samna nabati", "vegetable ghee"],
     "calories": 884, "protein": 0, "carbs": 0, "fat": 100, "ask_cooking": False, "is_oil": True},
    {"id": 204, "name": "Samna Baladi (Clarified Butter/Ghee)",
     "arabic_names": ["سمنة بلدي", "samna baladi", "ghee", "سمنة"],
     "calories": 900, "protein": 0, "carbs": 0, "fat": 100, "ask_cooking": False, "is_oil": True},
    {"id": 205, "name": "Zebda (Butter)",
     "arabic_names": ["زبدة", "zebda", "butter"],
     "calories": 717, "protein": 1, "carbs": 0,  "fat": 81,  "ask_cooking": False, "is_oil": True},
    # ══ ADDED BY GROQ ════════════════════════════════════════════════════════
    {"id": 207, "name": "Konafah with Pistachio",
     "arabic_names": ["كنافه بالفسدق", "knafah bil fustuq"],
     "calories": 420.0, "protein": 10.0, "carbs": 55.0, "fat": 20.0, "ask_cooking": False},
    {"id": 208, "name": "Kunafa Nabulsia (Nablus Knafeh)",
     "arabic_names": ["كنافة نابلسية", "كنافة نابولسية", "knafeh nabulsia", "kunafa nabulsia"],
     "calories": 318.0, "protein": 7.0, "carbs": 43.0, "fat": 17.0, "ask_cooking": False},

    {"id": 209, "name": "Rice with Milk",
     "arabic_names": ["رز بلبن", "roz bil laban"],
     "calories": 130.0, "protein": 2.0, "carbs": 28.0, "fat": 2.0, "ask_cooking": False},

    {"id": 210, "name": "Dates with Milk",
     "arabic_names": ["بلح باللبن", "bal7 bal laban"],
     "calories": 140.0, "protein": 3.0, "carbs": 34.0, "fat": 2.0, "ask_cooking": False},

    {"id": 211, "name": "Sambusa",
     "arabic_names": ["سمبوسة", "sambosa"],
     "calories": 220.0, "protein": 9.0, "carbs": 20.0, "fat": 13.0, "ask_cooking": False},

    {"id": 212, "name": "Creme Caramel",
     "arabic_names": ["كريم كراميل", "creme caramel"],
     "calories": 121.0, "protein": 3.0, "carbs": 22.0, "fat": 5.0, "ask_cooking": False},

    {"id": 213, "name": "Kunafa with Nutella",
     "arabic_names": ["كنافة بالنوتيلا", "knafeh bil nutella"],
     "calories": 380.0, "protein": 10.0, "carbs": 50.0, "fat": 20.0, "ask_cooking": False},

]

OIL_OPTIONS = [f for f in FOOD_DB if f.get("is_oil", False)]
DATA_DIR    = Path("data/food_logs")
FOOD_DB_PATH = Path(__file__).resolve()  # this .py file itself

# ─────────────────────────────────────────────
# GROQ SYSTEM PROMPT
# ─────────────────────────────────────────────

GROQ_SYSTEM_PROMPT = """
You are a nutrition expert specialised in Egyptian food and Egyptian Franco-Arabic
(Arabic written in English letters/numbers, where 3=ع, 7=ح, 5=خ, 2=ء/ق, 9=ص).

Common Franco-Arabic food vocabulary:
  fera5 / fra5 / ferakh = chicken | la7ma = beef | samak = fish
  beed / bed = eggs | kebda = liver | gambari = shrimp
  roz = rice | makarona / macarona = pasta | sha3reya = vermicelli
  aish = bread | shofan = oats | bleela = warm oatmeal porridge
  batates = potato | betingan = eggplant | kousa = zucchini
  felfel = pepper | tamatem / tomatem = tomato | bassal = onion
  mooz = banana | manga = mango | farawla = strawberry
  bortoan / bortoaan = orange | tofah / tofa7 = apple
  ananas / pinabl = pineapple | 3enab = grapes | teen = figs
  bate5 / bate7 = watermelon | shamam = cantaloupe | rumman = pomegranate
  laban = milk | zabadi = yogurt | gebna / gibna = cheese
  zebda = butter | samna = ghee | zeet = oil
  ful = fava beans | ads = lentils | ta3mya / taamya = falafel
  koshary = rice+lentils+pasta Egyptian dish
  mahshi = stuffed vegetables | ma7shy = stuffed
  mashwy / mashweya = grilled | maqli / maqliya = fried
  maslooq / maslooqa = boiled | mehamara = roasted | banee = breaded fried
  tarb = fat-wrapped kofta (350 cal, 18g P, 2g C, 30g F per 100g)
  mombar = Egyptian stuffed intestines with rice
  fesikh = fermented salted mullet (200 cal, 25g P, 0g C, 10g F per 100g)
  renga = smoked herring (210 cal, 22g P, 0g C, 13g F per 100g)
  kawaree = slow-cooked cow trotters
  bashamel = bechamel sauce | makarona bashamel = pasta with bechamel (220 cal/100g)
  sudani = peanuts | termis = lupini beans
  sahlab = hot milk drink | karkadeh = hibiscus drink | asab = sugarcane juice

TASK: Identify the food the user typed and return its nutritional values per 100g.

RULES:
1. Return ONLY a valid JSON object — no markdown, no explanation, no extra text.
2. Use EXACTLY these keys to match the database schema:
   {"name": "<English name>", "calories": <number>, "protein": <number>,
    "carbs": <number>, "fat": <number>, "ask_cooking": <true|false>,
    "arabic_names": ["<arabic script name>", "<franco-arabic name>"]}
3. The 'arabic_names' array MUST contain the Arabic script name and the Franco-Arabic
   transliteration. If the user searched in Arabic or Franco-Arabic, include their
   exact search term in this list.
4. ask_cooking must be:
   - true  → raw, uncooked ingredient where cooking method significantly changes macros
              (e.g. raw chicken, raw beef, raw fish, raw potato, raw eggs)
   - false → any complete/prepared dish, cured meat, dairy, fruit, vegetable, or
              anything already described with a cooking method (grilled, fried, boiled…)
5. All macro values must be plain numbers (no units, no strings).
6. If you cannot confidently identify the food or estimate macros, set calories to 0.
7. NEVER generalise: if the user says "كنافة نابلسية" / Nablus kunafa, return THAT exact
   regional dish — NOT plain "Kunafa" or generic kunafeh. The English 'name' must include
   the distinguishing detail (e.g. "Kunafa Nabulsia", "Kunafa with Pistachio").
8. Put the user's exact search phrase as the FIRST item in arabic_names.
"""


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def ensure_dirs():
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def today_str():
    return datetime.date.today().isoformat()


def load_today_log():
    path = DATA_DIR / f"{today_str()}.json"
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {"date": today_str(), "entries": [],
            "totals": {"calories": 0, "protein": 0, "carbs": 0, "fat": 0}}


def save_today_log(log):
    path = DATA_DIR / f"{today_str()}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)




def load_user_profile():
    p = Path("data/user_profile.json")
    return json.loads(p.read_text()) if p.exists() else None


def get_calorie_target(profile) -> int:
    return profile.get("daily_calories", 2000) if profile else 2000


def calc_nutrients(food: dict, grams: float,
                   extra_fat: float = 0, extra_cal: float = 0,
                   extra_carb: float = 0) -> dict:
    r = grams / 100.0
    return {
        "calories": round((float(food["calories"]) + extra_cal) * r, 1),
        "protein":  round(float(food["protein"]) * r, 1),
        "carbs":    round((float(food["carbs"]) + extra_carb) * r, 1),
        "fat":      round((float(food["fat"]) + extra_fat) * r, 1),
    }


def add_to_totals(log: dict, nutrients: dict):
    for k in ("calories", "protein", "carbs", "fat"):
        log["totals"][k] = round(log["totals"][k] + nutrients[k], 1)


# ─────────────────────────────────────────────
# FRANCO-ARABIC NORMALISER  (from V1)
# ─────────────────────────────────────────────

def normalize_query(query: str) -> str:
    words = query.lower().strip().split()
    return " ".join(FRANCO_MAP.get(w, w) for w in words)


# ─────────────────────────────────────────────
# SEARCH — 4 layers
#   Layer 1: Exact substring match against name + arabic_names
#   Layer 2: Franco normalisation → exact match
#   Layer 3: Fuzzy match (handles typos)
#   Layer 4: Groq AI fallback (unknown/unlisted foods) + JSON cache
# ─────────────────────────────────────────────

def _searchable(food: dict) -> str:
    """Build one flat searchable string for a DB entry."""
    parts = [food["name"].lower()] + [a.lower() for a in food.get("arabic_names", [])]
    return " | ".join(parts)


def _exact_search(query: str) -> list:
    q = query.lower().strip()
    return [f for f in FOOD_DB if q in _searchable(f)]


def _strict_match_food(query: str, food: dict) -> bool:
    """
    True only when the user's search clearly describes this food entry.
    Multi-word queries require every word in the food's names (avoids
    'كنافة نابلسية' → generic Konafa). Single-word requires an exact alias token.
    """
    q = query.lower().strip()
    if not q:
        return False
    tokens = [food["name"].lower()] + [a.lower() for a in food.get("arabic_names", [])]
    searchable = " | ".join(tokens)
    words = [w for w in q.split() if len(w) >= 2]

    if q in tokens:
        return True

    if len(words) >= 2:
        if q in searchable:
            return True
        return all(w in searchable for w in words)

    w = words[0] if words else q
    return any(w == t for t in tokens)


def _strict_search(query: str) -> list:
    return [f for f in FOOD_DB if _strict_match_food(query, f)]


# Generic parent foods — hide when user asked for a more specific dish (multi-word query)
_GENERIC_PARENT_IDS = {68}  # plain Konafa


def display_name_for_query(food: dict, query: str) -> str:
    """Show the alias the user actually searched for, not a vague English name."""
    q = query.strip().lower()
    words = [w for w in q.split() if len(w) >= 2]
    best = None
    for alias in food.get("arabic_names", []):
        al = alias.lower()
        if al == q:
            return alias
        if len(words) >= 2 and all(w in al for w in words):
            if best is None or len(al) > len(best):
                best = alias
    if best:
        return best
    return food["name"]


def _drop_generic_parents(results: list, query: str) -> list:
    words = [w for w in query.lower().split() if len(w) >= 2]
    if len(words) < 2:
        return results
    specific = [f for f in results if f["id"] not in _GENERIC_PARENT_IDS]
    return specific if specific else results


def find_food_strict(query: str):
    """
    Web/API search: exact + franco only (no fuzzy guesses).
    Returns (results_list, 'db' | 'franco' | 'none').
    """
    results = _strict_search(query)
    if results:
        return _drop_generic_parents(results, query), "db"

    norm = normalize_query(query)
    if norm != query.lower().strip():
        results = _strict_search(norm)
        if results:
            return _drop_generic_parents(results, query), "franco"

    return [], "none"


def _fuzzy_search(query: str) -> list:
    candidates = []
    for f in FOOD_DB:
        for token in [f["name"].lower()] + [a.lower() for a in f.get("arabic_names", [])]:
            candidates.append((token, f))
    close = set(get_close_matches(query.lower().strip(),
                                  [c[0] for c in candidates], n=5, cutoff=0.55))
    seen, results = set(), []
    for token, food in candidates:
        if token in close and food["id"] not in seen:
            seen.add(food["id"])
            results.append(food)
    return results


def _next_food_db_id() -> int:
    """Return the next available integer id for a new FOOD_DB entry."""
    int_ids = [f["id"] for f in FOOD_DB if isinstance(f["id"], int)]
    return max(int_ids, default=0) + 1


def _enrich_groq_aliases(entry: dict, user_query: str) -> dict:
    """Keep the user's search phrase so the next lookup hits the local DB."""
    names = list(entry.get("arabic_names") or [])
    q = user_query.strip()
    if q and q not in names:
        names.insert(0, q)
    for variant in (q.replace("نابولسية", "نابلسية"), q.replace("نابلسية", "نابولسية")):
        if variant != q and variant not in names:
            names.append(variant)
    entry["arabic_names"] = names
    return entry


def _find_existing_groq_food(user_query: str) -> dict | None:
    """If we already saved this search phrase, reuse it (no API call)."""
    hits, _ = find_food_strict(user_query)
    return hits[0] if hits else None


def append_to_food_db(entry: dict) -> bool:
    """
    Write a new entry into FOOD_DB inside this .py file itself.

    Inserts one formatted dict just before the closing ']' of FOOD_DB,
    under a '# ══ ADDED BY GROQ' section header (created once if absent).
    Also appends to the live in-memory FOOD_DB so the current session
    can find the food immediately without restarting.

    Returns True on success, False on any error.
    """
    try:
        file_src = FOOD_DB_PATH.read_text(encoding="utf-8")

        new_entry = dict(entry)
        q_lower = (new_entry.get("name") or "").lower()
        for f in FOOD_DB:
            if f.get("name", "").lower() == q_lower:
                print(f"  [DB] '{new_entry['name']}' already in FOOD_DB — skip duplicate")
                return True

        new_entry["id"] = _next_food_db_id()

        # Build arabic_names repr
        arabic = new_entry.get("arabic_names", [])
        arabic_repr = "[" + ", ".join('"' + a + '"' for a in arabic) + "]"

        ask    = "True"  if new_entry.get("ask_cooking") else "False"
        is_oil = ', "is_oil": True' if new_entry.get("is_oil") else ""

        # Two-line format that matches the rest of FOOD_DB
        new_line = (
            '    {"id": ' + str(new_entry["id"]) +
            ', "name": "' + new_entry["name"] + '",\n' +
            '     "arabic_names": ' + arabic_repr + ',\n' +
            '     "calories": ' + str(new_entry["calories"]) +
            ', "protein": ' + str(new_entry["protein"]) +
            ', "carbs": ' + str(new_entry["carbs"]) +
            ', "fat": ' + str(new_entry["fat"]) +
            ', "ask_cooking": ' + ask + is_oil + '},\n'
        )

        groq_header = "    # \u2550\u2550 ADDED BY GROQ \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\n"
        block = new_line
        if groq_header not in file_src:
            block = groq_header + new_line

        # Always insert before FOOD_DB closing bracket (works for 2nd, 3rd, … Groq food)
        anchor = "\n]\n\nOIL_OPTIONS"
        if anchor not in file_src:
            print("  [DB Write Error] Could not find FOOD_DB end marker")
            return False
        file_src = file_src.replace(anchor, "\n" + block + anchor, 1)

        FOOD_DB_PATH.write_text(file_src, encoding="utf-8")

        # Append to live in-memory list — current session sees it immediately
        new_entry["ask_cooking"] = bool(new_entry.get("ask_cooking"))
        FOOD_DB.append(new_entry)

        return True

    except Exception as e:
        print("  [DB Write Error] " + str(e))
        return False


def groq_lookup(food_name: str) -> dict | None:
    """
    Layer 4: call Groq Llama directly.
    On success, the result is written permanently into FOOD_DB inside this
    .py file via append_to_food_db(), and also appended to the live in-memory
    list so the current session can find it immediately.
    """
    cached = _find_existing_groq_food(food_name)
    if cached:
        print(f"  [DB] Using saved entry for '{food_name}' (no Groq call)")
        return cached

    try:
        from groq import Groq

        api_key = os.getenv("GROQ_API_KEY", "").strip()
        if not api_key:
            env_file = Path(__file__).resolve().parent / ".env"
            if env_file.exists() and env_file.stat().st_size > 0:
                raw = env_file.read_bytes()
                if raw.startswith(b"\xff\xfe"):
                    text = raw.decode("utf-16-le")
                else:
                    try:
                        text = raw.decode("utf-8-sig")
                    except UnicodeError:
                        text = raw.decode("utf-16-le", errors="replace")
                for line in text.splitlines():
                    line = line.strip().strip("\ufeff")
                    if line.startswith("GROQ_API_KEY="):
                        api_key = line.split("=", 1)[1].strip().strip('"').strip("'")
                        os.environ["GROQ_API_KEY"] = api_key
                        break
        if not api_key:
            print("  [Warning] GROQ_API_KEY not set. Add it to .env to enable AI fallback.")
            return None

        client = Groq(api_key=api_key)
        prompt = (
            f"The user searched for this EXACT dish (not a simpler/generic version):\n"
            f"'{food_name}'\n"
            f"Example: if they said كنافة نابلسية, return Nablus kunafa — NOT plain kunafa.\n"
            f"Return macros per 100g as JSON only."
        )

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": GROQ_SYSTEM_PROMPT},
                {"role": "user",   "content": prompt},
            ],
            temperature=0.0,
        )

        raw = response.choices[0].message.content.strip()
        raw = raw.strip("```json").strip("```").strip()
        print(f"  [Groq AI] Raw response: {raw}")

        result = json.loads(raw)

        # Validate required keys (now includes arabic_names from updated prompt)
        for k in ("name", "calories", "protein", "carbs", "fat", "ask_cooking"):
            if k not in result:
                raise ValueError(f"Missing key in Groq response: {k}")

        # Force numeric macro values
        for k in ("calories", "protein", "carbs", "fat"):
            result[k] = float(result[k])

        if result["calories"] == 0:
            print(f"  [Groq] Could not reliably estimate macros for '{food_name}'.")
            return None

        result = _enrich_groq_aliases(result, food_name)
        result["id"] = f"groq_{food_name.lower().strip()}"
        result.setdefault("arabic_names", [])

        print(f"  [Groq] '{food_name}' → '{result['name']}' ({result['calories']} kcal/100g)")

        # Write permanently into FOOD_DB in this .py file
        if append_to_food_db(result):
            print(f"  [DB] '{result['name']}' added to FOOD_DB permanently.")
        else:
            print(f"  [DB] Could not write to file — food usable this session only.")

        return result

    except ImportError:
        print("  [Warning] 'groq' package not installed. Run: pip install groq")
        return None
    except Exception as e:
        print(f"  [Groq Error] {e}")
        return None


def find_food(query: str):
    """
    Offline search only — Layers 1-3.  Groq is never called here.
    Returns (results_list, source_label).
    source_label: 'db' | 'franco' | 'fuzzy' | 'none'

    Groq (Layer 4) is invoked explicitly by log_food_item based on user choice.
    """
    # Layer 1 — exact match
    results = _exact_search(query)
    if results:
        return results, "db"

    # Layer 2 — franco normalisation → exact match
    norm = normalize_query(query)
    if norm != query.lower().strip():
        results = _exact_search(norm)
        if results:
            return results, "franco"

    # Layer 3 — fuzzy match
    results = _fuzzy_search(query)
    if results:
        return results, "fuzzy"

    return [], "none"


# ─────────────────────────────────────────────
# COOKING METHOD PROMPT  (from V1)
# ─────────────────────────────────────────────

def ask_cooking_method() -> dict | None:
    """
    Prompts the user to pick a cooking method.
    Returns the chosen method dict, or None if the user cancels (enters 0).
    """
    print("\n  اتعمل إزاي؟ (How was it cooked?)")
    print("    0. Cancel / إلغاء")
    for k, m in COOKING_METHODS.items():
        print(f"    {k}. {m['label']}")
    while True:
        choice = input("  اختار رقم (Enter number, 0 to cancel): ").strip()
        if choice == "0":
            print("  Cancelled.")
            return None
        if choice in COOKING_METHODS:
            return COOKING_METHODS[choice]
        print("  رقم غلط. حاول تاني. (Invalid — try again.)")


# ─────────────────────────────────────────────
# MAIN FLOW
# ─────────────────────────────────────────────

def log_food_item(log: dict):
    """
    Full food-logging flow with:
      • Outer search loop — user can search again without returning to main menu.
      • 0 = cancel / back at every single prompt.
      • Smart fallback sub-menu when results exist but user rejects them.
      • Groq is called ONLY when the user explicitly asks, or when local search
        returns 0 results and the user chooses to try AI.
    """

    while True:  # outer search loop — "2. Search for a different word" lands here

        # ── Step 1: get search query ───────────────────────────────────
        print("\nSearch for food (Enter to browse all, 0 to cancel): ", end="")
        query = input().strip()

        if query == "0":
            print("  Cancelled.")
            return

        # ── Step 2: run offline search layers 1-3 ─────────────────────
        if query == "":
            results = [f for f in FOOD_DB if not f.get("is_oil", False)]
            source  = "db"
        else:
            results, source = find_food(query)  # exact → franco → fuzzy (no Groq)

        # ── Step 3: handle zero local results ─────────────────────────
        if not results:
            print(f"  '{query}' — not found locally.")
            print("    1. Ask AI (Groq) about this")
            print("    2. Search for a different word")
            print("    0. Cancel")
            while True:
                sub = input("  Choose: ").strip()
                if sub == "1":
                    print(f"  Asking Groq about '{query}'...")
                    food = groq_lookup(query)
                    if food:
                        results = [food]
                        break          # fall through to food-selection below
                    else:
                        print("  Groq couldn't identify it either. Nothing logged.")
                        return
                elif sub == "2":
                    break              # restart outer search loop
                elif sub == "0":
                    print("  Cancelled.")
                    return
                else:
                    print("  Enter 1, 2, or 0.")
            if not results:
                continue              # user chose "search again" → top of while loop

        # ── Step 4: pick one food from results ────────────────────────
        food = None   # will be set when the user makes a valid selection

        if len(results) == 1:
            candidate = results[0]
            tag = "  *" if candidate.get("ask_cooking") else ""
            print(f"  Found: {candidate['name']} — {candidate['calories']} kcal/100g{tag}")
            if source == "fuzzy":
                print("  (Fuzzy / approximate match)")
            print("  Log this? (y / n / 0 to cancel): ", end="")
            while True:
                ans = input().strip().lower()
                if ans in ("y", "yes"):
                    food = candidate
                    break
                elif ans in ("n", "no"):
                    # treat "no" the same as picking "0 None of these"
                    break
                elif ans == "0":
                    print("  Cancelled.")
                    return
                else:
                    print("  Please enter y, n, or 0: ", end="")

        else:
            shown = results[:20]
            if source == "fuzzy":
                print("  [Fuzzy match] Did you mean one of these?")
            print()
            for i, f in enumerate(shown, 1):
                tag = "  *" if f.get("ask_cooking") else ""
                print(f"    {i:>2}. {f['name']} — {f['calories']} kcal/100g{tag}")
            print("     0. None of these")
            if any(f.get("ask_cooking") for f in shown):
                print("       (* will ask cooking method)")
            while True:
                raw = input("  Pick number: ").strip()
                if raw == "0":
                    food = None   # user rejects list — show sub-menu below
                    break
                try:
                    idx = int(raw)
                    if 1 <= idx <= len(shown):
                        food = shown[idx - 1]
                        break
                except ValueError:
                    pass
                print("  Invalid. Enter a number from the list, or 0: ")

        # ── Step 5: sub-menu when user picks "0 / None of these" ──────
        if food is None:
            print()
            print(f"  What would you like to do?")
            print(f"    1. Ask AI (Groq) about '{query}'")
            print( "    2. Search for a different word")
            print( "    3. Cancel and go back to main menu")
            while True:
                sub = input("  Choose: ").strip()
                if sub == "1":
                    print(f"  Asking Groq about '{query}'...")
                    food = groq_lookup(query)
                    if food:
                        break          # proceed with Groq result
                    else:
                        print("  Groq couldn't identify it. Nothing logged.")
                        return
                elif sub == "2":
                    break              # restart outer search loop (food stays None)
                elif sub in ("3", "0"):
                    print("  Cancelled.")
                    return
                else:
                    print("  Enter 1, 2, or 3.")
            if food is None:
                continue              # user chose "search again"

        # ── Step 6: cooking method (raw ingredients only) ──────────────
        extra_fat = extra_cal = extra_carb = 0
        method_label = ""
        if food.get("ask_cooking"):
            method = ask_cooking_method()   # returns None if user enters 0
            if method is None:
                return                      # user cancelled at cooking prompt
            extra_fat    = method.get("fat_add",  0)
            extra_cal    = method.get("cal_add",  0)
            extra_carb   = method.get("carb_add", 0)
            method_label = f" ({method['label'].strip()})"

        # ── Step 7: grams ──────────────────────────────────────────────
        print(f"  How many grams of {food['name']}{method_label}? (0 to cancel): ", end="")
        grams = None
        while True:
            raw = input().strip()
            if raw == "0":
                print("  Cancelled.")
                return
            try:
                val = float(raw)
                if val > 0:
                    grams = val
                    break
            except ValueError:
                pass
            print("  Enter a valid positive number (or 0 to cancel): ", end="")

        # ── Step 8: calculate, save, and confirm ───────────────────────
        nutrients   = calc_nutrients(food, grams, extra_fat, extra_cal, extra_carb)
        logged_name = food["name"] + method_label
        log["entries"].append({"food": logged_name, "grams": grams, "type": "food", **nutrients})
        add_to_totals(log, nutrients)

        print(f"\n  ✓ {grams}g {logged_name} → {nutrients['calories']} kcal | "
              f"P:{nutrients['protein']}g  C:{nutrients['carbs']}g  F:{nutrients['fat']}g")
        return   # done — exit the outer loop


def display_summary(log: dict, calorie_target: int):
    t = log["totals"]
    remaining = round(calorie_target - t["calories"], 1)
    status    = "✓ On track" if remaining >= 0 else f"⚠ Over by {abs(remaining)} kcal"
    print("\n" + "=" * 56)
    print(f"  TODAY'S NUTRITION — {log['date']}")
    print("=" * 56)
    print(f"  Calories  : {t['calories']} / {calorie_target} kcal  ({remaining} remaining)")
    print(f"  Status    : {status}")
    print(f"  Protein   : {t['protein']}g")
    print(f"  Carbs     : {t['carbs']}g")
    print(f"  Fat       : {t['fat']}g")
    print("-" * 56)
    if log["entries"]:
        for i, e in enumerate(log["entries"], 1):
            print(f"  {i:>2}. {e['food']}  {e['grams']}g → {e['calories']} kcal | "
                  f"P:{e['protein']}g  C:{e['carbs']}g  F:{e['fat']}g")
    else:
        print("  No items logged yet.")
    print("=" * 56)


def run():
    ensure_dirs()
    log            = load_today_log()
    profile        = load_user_profile()
    calorie_target = get_calorie_target(profile)
    name           = profile.get("name", "Athlete") if profile else "Athlete"

    print(f"\nWelcome, {name}! Daily target: {calorie_target} kcal")

    while True:
        print("\n" + "-" * 42)
        print("  1. Log a food item")
        print("  2. View today's summary")
        print("  3. Exit")
        print("-" * 42)
        choice = input("  Choose (1-3): ").strip()

        if choice == "1":
            log_food_item(log)
            save_today_log(log)
        elif choice == "2":
            display_summary(log, calorie_target)
        elif choice == "3":
            display_summary(log, calorie_target)
            print("  Saved. Goodbye! 💪")
            break
        else:
            print("  Invalid choice. Enter 1, 2, or 3.")


if __name__ == "__main__":
    run()