TRACTATE_MAX_DAF = {
    "Berakhot": 64,
    "Shabbat": 157,
    "Eruvin": 105,
    "Pesachim": 121,
    "Yoma": 88,
    "Sukkah": 56,
    "Beitzah": 40,
    "Rosh_Hashanah": 35,
    "Taanit": 31,
    "Megillah": 32,
    "Moed_Katan": 29,
    "Chagigah": 27,
    "Yevamot": 122,
    "Ketubot": 112,
    "Nedarim": 91,
    "Nazir": 66,
    "Sotah": 49,
    "Gittin": 90,
    "Kiddushin": 82,
    "Bava_Kamma": 119,
    "Bava_Metzia": 119,
    "Bava_Batra": 176,
    "Sanhedrin": 113,
    "Makkot": 24,
    "Shevuot": 49,
    "Avodah_Zarah": 76,
    "Horayot": 14,
    "Zevachim": 120,
    "Menachot": 110,
    "Chullin": 142,
    "Bekhorot": 61,
    "Arakhin": 34,
    "Temurah": 34,
    "Keritot": 28,
    "Meilah": 22,
    "Kinnim": 3,
    "Tamid": 10,
    "Middot": 4,
    "Niddah": 73,
}


def daf_range(max_daf: int):
    # Babylonian pagination starts at 2a
    for page in range(2, max_daf + 1):
        yield f"{page}a"
        yield f"{page}b"
