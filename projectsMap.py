"""
EBP Projects Bioproject ID Mapping

This module contains a dictionary mapping EBP project names (lowercase) to their
corresponding NCBI Bioproject IDs. This mapping is used throughout the duplication
alert system to link project data with NCBI BioProject entries.

Dictionary Structure:
    Key: Project name (lowercase, e.g., "canbp", "dtol", "vgp")
    Value: NCBI Bioproject ID (e.g., "PRJNA813333") or empty string if not available

Usage:
    from projectsMap import projectsMap
    bioproject_id = projectsMap.get("canbp", "")  # Returns "PRJNA813333"

Note:
    Empty strings indicate projects without assigned Bioproject IDs.
    Project names must be lowercase for consistent lookups.

Author: Fang Chen
Date: October 2025
"""

projectsMap = {
    "ebp": "PRJNA533106",
    "10kp": "",
    "1000gch": "PRJNA1245457",
    "bat1k": "PRJNA489245",
    "i5k": "PRJNA163993",
    "africabp": "PRJNA811786",
    "ag100pest": "PRJNA555319",
    "agc": "",
    "asg": "PRJEB43743",
    "atlasea": "PRJEB64126",
    "ausarg": "PRJNA1075730",
    "beenome100": "PRJNA923301",
    "b10k": "PRJNA545868",
    "bridge-col": "",
    "bgp": "",
    "ccgp": "PRJNA720569",
    "canbp": "PRJNA813333",
    "canseq150": "PRJNA706690",
    "cfgp": "",
    "cbp": "PRJEB49670",
    "cgp": "PRJNA1020146",
    "crabgp": "",
    "dtol": "PRJEB40665",
    "dog": "",
    "disco": "",
    "dresdenhq": "",
    "ebpn": "PRJEB65317",
    "endemixit": "PRJNA712951",
    "edgp": "",
    "ein": "",
    "erga": "PRJEB43510",
    "fish10k": "",
    "g10k": "",
    "gbb": "PRJNA1180976",
    "gaga": "",
    "ggbn": "",
    "giga": "PRJNA649812",
    "ebphk": "",
    "ilebp": "PRJNA844590",
    "kazusa": "PRJDB20515",
    "lmgp": "PRJNA948806",
    "loewe-tbg": "PRJNA706923",
    "og": "PRJNA1046164",
    "ogg": "",
    "phyloalps": "PRJEB52290",
    "paftol": "",
    "plantgarden": "",
    "pgp": "",
    "prgp": "",
    "psyche": "PRJEB71705",
    "r2k": "",
    "metainvert": "PRJNA758215",
    "squalomix": "PRJNA707598",
    "tbp": "",
    "tsi": "PRJNA1075750",
    "ugp": "",
    "cal-ebp": "PRJNA707235",
    "vgp": "PRJNA489243",
    "wa": "PRJEB96280",
    "ygg": "PRJNA955268",
    "zoonomia": "PRJNA312960",
    "erga-bge": "PRJEB61747",
    "erga-ch": "PRJEB49197",
    "erga-pil": "PRJEB47820"
}