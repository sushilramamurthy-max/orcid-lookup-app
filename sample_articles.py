"""
sample_articles.py
-------------------
Seed data for the demo sidebar: a handful of sample articles with real
manuscript-style author bylines. Deliberately mixes:
  - a well-known ORCID-diligent author (Egon Willighagen) for a clean
    "Confirmed" demo
  - a very common name (Wei Zhang) to show ambiguous/weak matches
  - a real person whose ORCID isn't attached in CrossRef (Susil Kumar
    Ramamurthy) to demonstrate the manual "Not me" flagging flow
  - a couple of fictional authors as filler/contrast

These are illustrative only -- swap in your own article/author data for
real use.
"""

ARTICLES = [
    {
        "id": "art-1",
        "doi": "10.1038/s41586-023-06541-7",
        "title": "Mapping Regulatory Networks in Cell Differentiation",
        "journal": "Nature",
        "authors": [
            {"given_name": "Egon", "family_name": "Willighagen",
             "affiliation": "Maastricht University", "email": ""},
            {"given_name": "Priya", "family_name": "Sharma",
             "affiliation": "Indian Institute of Science", "email": ""},
        ],
    },
    {
        "id": "art-2",
        "doi": "10.1016/j.joi.2022.101234",
        "title": "Disambiguating Common Author Names in Large-Scale Bibliometric Databases",
        "journal": "Journal of Informetrics",
        "authors": [
            {"given_name": "Wei", "family_name": "Zhang",
             "affiliation": "", "email": ""},
            {"given_name": "Susil Kumar", "family_name": "Ramamurthy",
             "affiliation": "Madras University", "email": "sushil.chennai@gmail.com"},
        ],
    },
    {
        "id": "art-3",
        "doi": "10.1002/anie.202301234",
        "title": "Structural Basis of Ligand Recognition in Membrane Receptors",
        "journal": "Angewandte Chemie",
        "authors": [
            {"given_name": "Hiroshi", "family_name": "Tanaka",
             "affiliation": "University of Tokyo", "email": ""},
            {"given_name": "Maria", "family_name": "Gonzalez",
             "affiliation": "Universidad de Barcelona", "email": ""},
        ],
    },
]
