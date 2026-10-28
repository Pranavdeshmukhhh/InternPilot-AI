"""Source configurations, never listings. Verification is a dated snapshot."""
from .regional_search import configured


def catalog():
    return [
        {"key":"sarvam-ai","label":"Sarvam AI","coverage":"Official India AI startup board; location and eligibility remain listing-specific.","verified_at":"2026-10-23","requires_key":False,
         "source":{"kind":"ashby","slug":"sarvam","company":"Sarvam AI","permitted":True,"enabled":True,"interval_seconds":1800}},
        {"key":"india-research","label":"University & research internships","coverage":"Authorized search of IISc and IIT public announcements; publisher verification is bounded.","verified_at":None,"requires_key":not configured(),
         "source":{"kind":"search","slug":"(internship OR undergraduate research fellowship) (site:iisc.ac.in OR site:iitb.ac.in OR site:iitm.ac.in)","company":"India university research search","permitted":True,"enabled":True,"interval_seconds":21600}},
        {"key":"india-programs","label":"Government & student programs","coverage":"Authorized search of AICTE and government announcements; program availability and eligibility require verification.","verified_at":None,"requires_key":not configured(),
         "source":{"kind":"search","slug":"student internship India (site:gov.in OR site:aicte-india.org) undergraduate","company":"India government program search","permitted":True,"enabled":True,"interval_seconds":21600}},
    ]
