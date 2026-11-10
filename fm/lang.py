"""Small language helpers: guess the script of a question and short fixed phrases for spoken confirmations."""
from __future__ import annotations

SCRIPTS = [("ঀ", "৿", "bn"), ("ऀ", "ॿ", "hi"), ("஀", "௿", "ta"),
           ("ఀ", "౿", "te"), ("઀", "૿", "gu"), ("ಀ", "೿", "kn"),
           ("ഀ", "ൿ", "ml"), ("଀", "୿", "or"), ("਀", "੿", "pa")]
NAMES = {"bn": "Bengali", "hi": "Hindi", "en": "English", "hinglish": "Hinglish (Hindi in Latin letters)",
         "banglish": "Banglish (Bengali in Latin letters)", "ta": "Tamil", "te": "Telugu", "mr": "Marathi",
         "gu": "Gujarati", "kn": "Kannada", "ml": "Malayalam", "or": "Odia", "pa": "Punjabi"}


def guess_language(text: str) -> str:
    counts = {code: sum(1 for ch in text if lo <= ch <= hi) for lo, hi, code in SCRIPTS}
    code, n = max(counts.items(), key=lambda kv: kv[1])
    return code if n >= 3 else "en"


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
