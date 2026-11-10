"""Small language helpers: guess the script of a question and short fixed phrases for spoken confirmations."""
from __future__ import annotations

SCRIPTS = [("ঀ", "৿", "bn"), ("ऀ", "ॿ", "hi"), ("஀", "௿", "ta"),
           ("ఀ", "౿", "te"), ("઀", "૿", "gu"), ("ಀ", "೿", "kn"),
           ("ഀ", "ൿ", "ml"), ("଀", "୿", "or"), ("਀", "੿", "pa")]
NAMES = {"bn": "Bengali", "hi": "Hindi", "en": "English", "hinglish": "Hinglish (Hindi in Latin letters)",
         "banglish": "Banglish (Bengali in Latin letters)", "ta": "Tamil", "te": "Telugu", "mr": "Marathi",
         "gu": "Gujarati", "kn": "Kannada", "ml": "Malayalam", "or": "Odia", "pa": "Punjabi"}


HINGLISH = set("hai hain kya nahi nahin raha rahi rahe karo kar karna bana banao do dijiye mein se ka ki ko kaise "
               "kyun aur bhi abhi wala wali par pe chal gaya gayi hota hoti".split())
BANGLISH = set("ache achhe korbo koro korte ki na hocche hochhe theke amar amader koyta koto keno dekhache "
               "dekhachhe kothay ekhon hoye gele bolo din".split())


def guess_language(text: str) -> str:
    """Script first (বাংলা -> bn, देवनागरी -> hi ...); for Latin text, spot Hinglish / Banglish by common words."""
    counts = {code: sum(1 for ch in text if lo <= ch <= hi) for lo, hi, code in SCRIPTS}
    code, n = max(counts.items(), key=lambda kv: kv[1])
    if n >= 3:
        return code
    words = text.lower().replace("?", " ").replace(",", " ").split()
    hi_hits, bn_hits = sum(w in HINGLISH for w in words), sum(w in BANGLISH for w in words)
    if max(hi_hits, bn_hits) >= 2:
        return "hinglish" if hi_hits >= bn_hits else "banglish"
    return "en"


CONFIRM_ASK = {
    "en": "Shall I do this? Press Yes or say yes.",
    "hi": "क्या मैं यह कर दूँ? हाँ दबाइए।",
    "bn": "আমি কি এটা করে দেব? হ্যাঁ টিপুন।",
}
DONE = {
    "ticket": {"en": "Done. Fault ticket {id} is raised for {machine}. Maintenance has been told.",
               "hi": "हो गया। {machine} के लिए फ़ॉल्ट टिकट {id} बन गया है। मेंटेनेंस को बता दिया गया है।",
               "bn": "হয়ে গেছে। {machine}-এর জন্য ফল্ট টিকিট {id} তৈরি হয়েছে। মেইনটেন্যান্সকে জানানো হয়েছে।"},
    "work_order": {"en": "Done. Work order {id} is created for {machine}.",
                   "hi": "हो गया। {machine} के लिए वर्क ऑर्डर {id} बन गया है।",
                   "bn": "হয়ে গেছে। {machine}-এর জন্য ওয়ার্ক অর্ডার {id} তৈরি হয়েছে।"},
    "cancel": {"en": "Okay, nothing was created.", "hi": "ठीक है, कुछ नहीं बनाया गया।",
               "bn": "ঠিক আছে, কিছু তৈরি করা হয়নি।"},
}


def phrase(table: dict, language: str, **kw) -> str:
    return table.get(language, table["en"]).format(**kw)
