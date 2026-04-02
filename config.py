from calibre.utils.config import JSONConfig

plugin_prefs = JSONConfig("metadata_sources/BiblioMeta")
plugin_prefs.defaults.update({
    "language_mode":    "all",
    "use_openlibrary":  True,
    "use_google_books": True,
    "replace_tags":     False,
    "cdu_tags":         True,
    "genre_tags":       True,
    "lcc_tags":         True,
    "stats": {
        "total": 0, "found": 0, "not_found": 0,
        "bne": 0, "loc": 0, "ol": 0,
        "last_run": "",
    },
})
