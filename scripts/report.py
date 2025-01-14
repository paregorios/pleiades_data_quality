#
# This file is part of pleiades_data_quality
# by Tom Elliott for the Institute for the Study of the Ancient World
# (c) Copyright 2023 by New York University
# Licensed under the AGPL-3.0; see LICENSE.txt file.
#

"""
Report on problems in Pleiades data
"""

from airtight.cli import configure_commandline
from datetime import date
import json
import logging
import os
from place import PleiadesPlace
from pathlib import Path
from pprint import pprint

logger = logging.getLogger(__name__)

DEFAULT_LOG_LEVEL = logging.WARNING
OPTIONAL_ARGUMENTS = [
    [
        "-l",
        "--loglevel",
        "NOTSET",
        "desired logging level ("
        + "case-insensitive string: DEBUG, INFO, WARNING, or ERROR",
        False,
    ],
    ["-v", "--verbose", False, "verbose output (logging level == INFO)", False],
    [
        "-w",
        "--veryverbose",
        False,
        "very verbose output (logging level == DEBUG)",
        False,
    ],
]
POSITIONAL_ARGUMENTS = [
    # each row is a list with 3 elements: name, type, help
    ["srcdir", str, "directory tree to crawl for Pleiades JSON data"],
    ["destdir", str, "directory where report data are to be written"],
]

ACCURACY_THRESHOLD = 1000.0
issues = {
    "rough_not_unlocated": set(),
    "poor_accuracy": set(),
    "missing_accuracy": set(),
    "bad_osm_way": set(),
    "bad_place_type": set(),
    "question_mark_titles": set(),
    "names_romanized_only": set(),
    "missing_modern_name": set(),
}
accuracy_details = dict()
bad_osm_way_details = dict()
DEPRECATED_PLACE_TYPES = {
    "church",
    "fort",
    "labeled-feature",
    "mine",
    "numbered feature",
    "plaza",
    "province",
    "temple",
    "unknown",
    "wall",
}  # these are term IDs, not the full terms (e.g. "church" here meant "church or monastery" on BAtlas map)
names_details = dict()
place_type_details = dict()
problems = dict()
summary = {"place_count": 0, "problem_count": 0}
for k in issues.keys():
    summary[k] = 0


def set_default(obj):
    if isinstance(obj, set):
        return sorted(list(obj))
    raise TypeError


def evaluate(p):
    global issues
    global accuracy_details
    global place_type_details
    global problems
    global summary

    pid = p.id
    problem = False
    if "?" in p.title:
        issues["question_mark_titles"].add(pid)
        problem = True
    if p.rough and not p.unlocated:
        place_type_details[pid] = sorted(list(p.place_types))
        issues["rough_not_unlocated"].add(pid)
        problem = True
    if p.precise:
        try:
            if p.accuracy_min >= ACCURACY_THRESHOLD:
                issues["poor_accuracy"].add(pid)
                accuracy_details[pid] = {
                    "accuracy_min": p.accuracy_min,
                    "accuracy_max": p.accuracy_max,
                }
                problem = True
        except TypeError:
            issues["missing_accuracy"].add(pid)
            problem = True
        if p.bad_osm_ways:
            issues["bad_osm_way"].add(pid)
            bad_osm_way_details[pid] = p.get_bad_osm_way_ids()
            problem = True
    bad_place_types = DEPRECATED_PLACE_TYPES.intersection(p.place_types)
    if bad_place_types:
        issues["bad_place_type"].add(pid)
        place_type_details[pid] = sorted(list(p.place_types))
        problem = True
    names_romanized_only = p.names_romanized_only
    if names_romanized_only:
        issues["names_romanized_only"].add(pid)
        names_details[pid] = [
            (
                n["attested"],
                n["language"],
                [r.strip() for r in n["romanized"].split(",")],
            )
            for n in p.names
        ]
        problem = True
    if p.name_count > 0 and not p.names_modern:
        issues["missing_modern_name"].add(pid)
        problem = True

    if problem:
        problems[pid] = p
    else:
        del p


def main(**kwargs):
    """
    main function
    """
    global summary

    # logger = logging.getLogger(sys._getframe().f_code.co_name)
    src_path = Path(kwargs["srcdir"]).expanduser().resolve()
    logger.info(f"Crawling for Pleiades JSON: {src_path}")
    for root, dirs, files in os.walk(src_path):
        for f in files:
            if f.endswith(".json"):
                p = PleiadesPlace(Path(root) / f)
                summary["place_count"] += 1
                evaluate(p)
    for k, v in issues.items():
        logger.info(f"{k}: {len(v)}")
        summary[k] = len(v)
    dest_path = Path(kwargs["destdir"]).expanduser().resolve()
    dest_path.mkdir(parents=True, exist_ok=True)
    issues["places"] = {pid: {"title": p.title} for pid, p in problems.items()}
    for pid, d in accuracy_details.items():
        issues["places"][pid] = issues["places"][pid] | d
    for pid, v in place_type_details.items():
        issues["places"][pid]["place_types"] = v
    for pid, v in names_details.items():
        issues["places"][pid]["names"] = v
    for pid, v in bad_osm_way_details.items():
        issues["places"][pid]["osm_way_ids"] = v
    logger.info(f"Total problem place count: {len(problems)}")
    summary["problem_count"] = len(problems)
    issues["summary"] = summary
    with open(dest_path / "issues.json", "w", encoding="utf-8") as fp:
        json.dump(issues, fp, default=set_default, indent=4, ensure_ascii=False)
    del fp
    logger.info(f"Wrote report data to {dest_path}.")
    msg = [
        f"Pleiades Data Quality Report {date.today().isoformat()}\n",
        f"{len(issues['rough_not_unlocated']):,} places with 'rough' precision (i.e., no specific geometry), but not marked 'unlocated'.",
        f"{len(issues['poor_accuracy']):,} places whose locations have no horizontal accuracy smaller than {ACCURACY_THRESHOLD:,.0f} meters.",
        f"{len(issues['missing_accuracy']):,} places whose locations have no associated accuracy value.",
        f"{len(issues['bad_osm_way']):,} places whose locations include an OSM Way that has been incompletely imported as a Node.",
        f"{len(issues['bad_place_type']):,} places that make use of a deprecated place type.",
        f"{len(issues['question_mark_titles']):,} place titles that include a question mark.",
        f"{len(issues['names_romanized_only']):,} names that only have values in the 'romanized' field (no 'attested' field value in original language and script).",
        f"{len(issues['missing_modern_name']):,} places that have no assigned 'modern name'.",
    ]
    print(" ".join(msg[1:]))
    print("\n")
    print("-" * 78)
    print("\n")
    print("\n".join([(s, f"- {s}")[i > 0] for i, s in enumerate(msg)]))


if __name__ == "__main__":
    main(
        **configure_commandline(
            OPTIONAL_ARGUMENTS, POSITIONAL_ARGUMENTS, DEFAULT_LOG_LEVEL
        )
    )
