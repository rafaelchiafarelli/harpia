"""Jurisdiction registry for the `ComplianceReport/` doc-template selection
(process-artifacts task 3).

`jurisdiction[]` never forks generated code (master plan Section 0a) -- it only
picks which paperwork shell the *same* SBOM + traceability evidence is
stamped into. This module holds the header-block values that differ per
jurisdiction; everything below the header is rendered identically.

The header text here is a credible scaffold, NOT authoritative regulatory
content -- see the disclaimer every rendered report carries
(`harpia_sensitive_data_design_rules.md` Section 6 / Section 9).
"""

#: baseline every regime shares (design-rules Section 6): used for the generic
#: `compliance_report.md` and for any unrecognized jurisdiction token.
GENERIC = {
    "regime": "jurisdiction-neutral baseline",
    "doc_package": "harmonized medical-device software compliance evidence package",
    "framework": "harmonized medical-device software standards",
    "standards": "IEC 62304 (software life cycle), ISO 14971 (risk management)",
    "review_body": "the target jurisdiction's regulator / conformity-assessment body",
    "postmarket": "per the target jurisdiction",
    "extra_note": "",
}

JURISDICTIONS = {
    "FDA": {
        "regime": "U.S. FDA",
        "doc_package": "Design History File (DHF) / premarket submission (510(k) or PMA)",
        "framework": "21 CFR Part 820 (Quality System Regulation); FDA premarket cybersecurity guidance",
        "standards": "IEC 62304, ISO 14971, ANSI/AAMI SW96",
        "review_body": "FDA (CDRH)",
        "postmarket": "Medical Device Reporting (MDR) under 21 CFR Part 803",
        "extra_note": "",
    },
    "EU_MDR": {
        "regime": "EU MDR",
        "doc_package": "Technical Documentation (Regulation (EU) 2017/745, Annex II & III)",
        "framework": "Regulation (EU) 2017/745 (MDR); IEC 81001-5-1 (health-software security)",
        "standards": "EN IEC 62304, EN ISO 14971, IEC 81001-5-1",
        "review_body": "Notified Body",
        "postmarket": "Vigilance reporting under MDR Articles 87-90; PSUR",
        "extra_note": (
            "> **EU MDR / IEC 81001-5-1:** tamper-evident audit-log integrity is "
            "required. Harpia treats append-only / tamper-evident audit storage as "
            "the universal default (design-rules Section 6), so no jurisdiction-specific "
            "code branch is needed to satisfy this."
        ),
    },
    "ANVISA": {
        "regime": "ANVISA (Brazil)",
        "doc_package": "Documentacao Tecnica / dossie tecnico",
        "framework": "RDC 751/2022; RDC 657/2022 (software as a medical device); Boas Praticas de Fabricacao",
        "standards": "ABNT NBR IEC 62304, ISO 14971",
        "review_body": "ANVISA",
        "postmarket": "Tecnovigilancia",
        "extra_note": "",
    },
}


def resolve(token):
    """(canonical_key, entry_or_None). `None` entry => no specific template;
    the caller falls back to GENERIC and adds a note."""
    key = str(token).strip().upper().replace(" ", "_").replace("-", "_")
    return key, JURISDICTIONS.get(key)
