"""Tags name one genre many ways ("Rap", "Hip Hop", "Rap/Hip Hop"). Tracks keep
what their files say; plays are grouped here, when shown, so changing a group
needs no new import."""
from core.stats_db import fold, usable_genre

_GROUPS = {
    "Rap & Hip-Hop": (
        "rap", "hip hop", "hip-hop", "hiphop", "rap/hip hop", "hip-hop & rap", "hip hop & rap", "hip-hop/rap",
        "french rap", "rap francais", "trap", "gangsta rap",
    ),
    "Film & Game Music": ("films/jeux video", "musiques de films", "films/games", "film scores", "films", "games", "soundtrack", "film score", "video game music"),
    "Electronic": ("electro", "electronic", "electronica", "edm", "dance", "house", "techno"),
    "R&B & Soul": ("r&b", "rnb", "contemporary r&b", "contemporary soul", "soul", "soul & funk"),
    "Latin": ("latino", "musique bresilienne", "brazilian music", "latin music", "latin", "brazilian music", "reggaeton"),
    "Asian": ("musique asiatique", "asian music", "j-pop", "k-pop", "jpop", "kpop"),
}
_LOOKUP = {name: group for group, names in _GROUPS.items() for name in names}
_MEANINGLESS = {"music", "other", "various", "misc"}


def genre_group(raw):
    if not usable_genre(raw):
        return None
    name = str(raw).strip()
    folded = fold(name)
    if folded in _MEANINGLESS:
        return None
    return _LOOKUP.get(folded, name)
