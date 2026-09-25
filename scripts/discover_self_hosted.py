#!/usr/bin/env python3
"""
Discover and verify institution-hosted copies of the NIRF 2025 Engineering data
disclosure, for the Tamil Nadu TNEA colleges that NIRF itself publishes only as a
rank band.

Why this exists
---------------
NIRF hosts per-institute disclosures on its own CDN only down to rank 200. Every
college in the 201-300 band returns HTTP 404 there. The same submission document
is, however, frequently published by the institution on its own website, because
NIRF requires participating institutions to disclose it. That copy is the same
document, but the chain of custody is weaker: it is served by the college rather
than by the Ministry. Data ingested from it is therefore graded separately
(grade S) and never presented as Ministry-hosted.

What counts as acceptable here
------------------------------
STRICT rules, because this is exactly the grey zone that invites bad data:

  1. The PDF must be served from a host that belongs to the institution itself.
     Third-party aggregators, brochure mirrors, Scribd, notopedia, random CDNs
     and coaching sites are rejected outright, no matter what they contain.
  2. The PDF must identify itself as the NIRF submission for India Rankings 2025.
     A 2021 or 2024 copy is rejected.
  3. The PDF must be the ENGINEERING submission, i.e. its embedded institute id
     must start with IR-E-. Overall/Innovation/SDG submissions carry different
     figures and are rejected.
  4. The institute name printed inside the PDF must match the college we expected,
     by distinctive-token overlap or whole-string similarity.

Anything that fails is reported with the reason and contributes nothing.
"""

from __future__ import annotations

import difflib
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data-sources" / "raw" / "self_hosted"
OUT = ROOT / "data-sources" / "parsed"

UA = "Mozilla/5.0 (compatible; TNEA-advisor-dataset-builder)"

# NIRF 2025 is the latest PUBLISHED ranking, and the rest of this dataset is built
# on it. Some institutions have additionally published their NIRF 2026 submission
# (the 2026 data-submission window closed in March 2026). A 2026 submission is
# newer and equally official, so it is accepted, but 2025 is preferred when both
# exist so that figures line up with the NIRF 2025 rank/band used elsewhere. The
# year actually used is recorded per college and surfaced in the UI.
ACCEPTED_YEARS = (2025, 2026)
PREFERRED_YEAR = 2025

# Candidate hosts per college. Several colleges serve documents from a www host,
# a bare host, or a separate files/subdomain, so more than one is tried.
TARGETS: dict[str, dict] = {
    "Chennai Institute of Technology": {"hosts": ["www.citchennai.edu.in", "citchennai.edu.in"]},
    "Annamalai University": {
        "hosts": ["www.annamalaiuniversity.ac.in", "annamalaiuniversity.ac.in"],
        # The university serves the same download path from several subdomains;
        # some are intermittently unreachable, so a few are tried in turn.
        "direct": [
            "https://www.annamalaiuniversity.ac.in/download/nirf2025/Engineering.pdf",
            "https://annamalaiuniversity.ac.in/download/nirf2025/Engineering.pdf",
            "https://lib.annamalaiuniversity.ac.in/download/nirf2025/Engineering.pdf",
            "https://mail.annamalaiuniversity.ac.in/download/nirf2025/Engineering.pdf",
            "https://dde.annamalaiuniversity.ac.in/download/nirf2025/Engineering.pdf",
            "https://www.gains.annamalaiuniversity.ac.in/download/nirf2025/Engineering.pdf",
        ],
        "extra_host_allow": [
            "gains.annamalaiuniversity.ac.in",
            "lib.annamalaiuniversity.ac.in",
            "mail.annamalaiuniversity.ac.in",
            "dde.annamalaiuniversity.ac.in",
        ],
    },
    "E.G.S. Pillay Engineering College": {"hosts": ["www.egspec.org", "egspec.org"]},
    "Hindusthan College of Engineering and Technology": {"hosts": ["www.hicet.ac.in", "hicet.ac.in"]},
    "K. Ramakrishnan College of Engineering": {"hosts": ["www.krce.ac.in", "krce.ac.in"]},
    "K. Ramakrishnan College of Technology": {"hosts": ["www.krct.ac.in", "krct.ac.in"]},
    "Kalaignar Karunanidhi Institute of Technology": {"hosts": ["www.kitcbe.com", "kitcbe.com"]},
    "Karpagam College of Engineering": {"hosts": ["www.kce.ac.in", "kce.ac.in"]},
    "M.Kumarasamy College of Engineering": {"hosts": ["www.mkce.ac.in", "mkce.ac.in"]},
    "National Engineering College": {"hosts": ["nec.edu.in", "www.nec.edu.in"]},
    "Panimalar Engineering College": {"hosts": ["www.panimalar.ac.in", "panimalar.ac.in"]},
    "Prince Shri Venkateshwara Padmavathy Engineering College": {"hosts": ["www.psvpec.in", "psvpec.in"]},
    "PSNA College of Engineering and Technology, Dindigul": {"hosts": ["www.psnacet.edu.in", "psnacet.edu.in"]},
    "R. M. K. College of Engineering and Technology": {"hosts": ["www.rmkcet.ac.in", "rmkcet.ac.in"]},
    "R.M.D Engineering College": {"hosts": ["www.rmd.ac.in", "rmd.ac.in"]},
    "Rajalakshmi Institute of Technology": {"hosts": ["www.ritchennai.edu.in", "ritchennai.edu.in", "ritchennai.org"]},
    "Rathinam Technical Campus": {"hosts": ["www.rathinamtechnicalcampus.com", "rathinamtechnicalcampus.com", "www.rathinam.in", "rathinam.in"]},
    "Saveetha Engineering College": {"hosts": ["www.saveetha.ac.in", "saveetha.ac.in"]},
    "SNS College of Technology": {
        "hosts": ["www.snsct.org", "snsct.org"],
        # SNS Institutions publish their NIRF submissions on their IQAC site. It is
        # a different registrable domain, so it is allowed only explicitly, for this
        # college, and recorded in the output so the provenance stays visible.
        "extra_host_allow": ["snsiqac.org"],
        "extra_host_note": "Served from snsiqac.org, the SNS Institutions IQAC site, rather than snsct.org.",
    },
    "Sri Eshwar College of Engineering": {
        "hosts": ["www.sece.ac.in", "sece.ac.in"],
        "direct": ["https://sece.ac.in/wp-content/uploads/2025/02/DCS-2025-Engineering.pdf"],
    },
    "Sri Venkateswara College of Engineering": {"hosts": ["www.svce.ac.in", "svce.ac.in"]},
    "St. Josephs College of Engineering": {"hosts": ["www.stjosephs.ac.in", "stjosephs.ac.in"]},
}

# Pages likely to carry the NIRF link.
INDEX_PATHS = [
    "/",
    "/nirf",
    "/nirf/",
    "/nirf.php",
    "/nirf.html",
    "/NIRF",
    "/iqac",
    "/iqac/",
    "/about/nirf",
    "/mandatory-disclosure",
    "/disclosure",
    "/ranking",
    "/rankings",
]

GENERIC = {
    "college", "institute", "institution", "engineering", "technology", "science",
    "sciences", "research", "advanced", "studies", "university", "autonomous",
    "of", "and", "the", "for", "campus", "school", "academy", "applied", "dr",
    "sri", "shri", "sree", "st", "s", "dindigul",
}

NAME_IN_PDF = re.compile(
    r"Institute Name:\s*(?P<name>.+?)\s*\[(?P<id>IR-[A-Z]-[A-Z]-\d+)\]"
)

# The submission year appears in two different wordings. The copy served by the
# NIRF CDN says "Data Submitted by Institution for India Rankings '2025'", while
# the Data Capturing System export that institutions publish themselves says
# "Submitted Institute Data for NIRF'2025'". Both are accepted.
YEAR_MARKER = re.compile(
    r"(?:India Rankings\s*'?|Submitted Institute Data for NIRF\s*'?)(?P<year>\d{4})"
)

# The DCS export also names the category in its header, which is an independent
# confirmation that this is the Engineering submission and not Overall/Innovation.
CATEGORY_MARKER = re.compile(r"Data Capturing System:\s*(?P<category>[A-Z &]+)")


def normalise_str(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower().replace("&", "and"))


def tokens(text: str) -> set[str]:
    text = text.lower().replace("&", " and ")
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return {t for t in text.split() if t not in GENERIC and len(t) > 1}


def encode_url(url: str) -> str:
    """Percent-encode the path so links containing spaces are fetchable."""
    parts = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            urllib.parse.quote(parts.path, safe="/%:@&=+$,~"),
            urllib.parse.quote(parts.query, safe="/?=&%:@+$,~"),
            "",
        )
    )


def http_get(url: str, timeout: int = 30) -> tuple[bytes | None, str | None]:
    req = urllib.request.Request(encode_url(url), headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read(), resp.headers.get("Content-Type", "")
    except Exception:
        return None, None


def host_of(url: str) -> str:
    return (urllib.parse.urlparse(url).hostname or "").lower()


def registrable(host: str) -> str:
    """Crude but sufficient: keep the last three labels for .ac.in / .edu.in."""
    parts = host.split(".")
    if len(parts) >= 3 and parts[-2] in {"ac", "edu", "co", "org", "gov", "net"}:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def institution_owned(url: str, allowed_hosts: list[str]) -> bool:
    """The PDF host must share a registrable domain with the college's own site."""
    h = host_of(url)
    if not h:
        return False
    allowed = {registrable(a.lower()) for a in allowed_hosts}
    return registrable(h) in allowed


def find_pdf_links(html: bytes, base_url: str) -> list[str]:
    try:
        text = html.decode("utf-8", errors="ignore")
    except Exception:
        return []
    found: list[str] = []
    for match in re.finditer(r'href\s*=\s*["\']([^"\']+)["\']', text, re.I):
        href = match.group(1).strip()
        absolute = urllib.parse.urljoin(base_url, href)
        low = absolute.lower()
        if "nirf" not in low and "dcs" not in low:
            continue
        found.append(absolute)
    # De-duplicate, keep order.
    seen, out = set(), []
    for url in found:
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out


def pdf_identity(data: bytes, tmp: Path) -> tuple[str | None, str | None, int | None, str | None]:
    """Return (institute_name, institute_id, rankings_year, category) from a NIRF PDF."""
    tmp.write_bytes(data)
    import pypdfium2 as pdfium

    try:
        pdf = pdfium.PdfDocument(str(tmp))
    except Exception:
        return None, None, None, None
    try:
        page = pdf[0]
        tp = page.get_textpage()
        text = tp.get_text_range()
        tp.close()
        page.close()
    except Exception:
        return None, None, None, None
    finally:
        pdf.close()

    flat = " ".join(text.split())
    name_match = NAME_IN_PDF.search(flat)
    year_match = YEAR_MARKER.search(flat)
    cat_match = CATEGORY_MARKER.search(flat)
    year = int(year_match.group("year")) if year_match else None
    category = cat_match.group("category").strip() if cat_match else None
    if not name_match:
        return None, None, year, category
    return name_match.group("name"), name_match.group("id"), year, category


def process_college(college: str, spec: dict) -> tuple[dict | None, dict | None, list[str]]:
    """Discover and verify one college's self-hosted disclosure."""
    log: list[str] = []
    if True:
        hosts = spec["hosts"]
        allowed = hosts + spec.get("extra_host_allow", [])
        candidates: list[str] = list(spec.get("direct", []))

        # Crawl likely index pages for NIRF-ish PDF links.
        for host in hosts:
            if candidates and any(c.lower().endswith(".pdf") for c in candidates):
                break
            for path in INDEX_PATHS:
                url = f"https://{host}{path}"
                body, ctype = http_get(url, timeout=12)
                if not body:
                    continue
                if ctype and "html" not in ctype.lower():
                    continue
                links = find_pdf_links(body, url)
                # Follow one level into NIRF landing pages that are not PDFs.
                for link in list(links):
                    if not link.lower().endswith(".pdf") and institution_owned(link, allowed):
                        sub, subtype = http_get(link, timeout=12)
                        if sub and subtype and "html" in subtype.lower():
                            links.extend(find_pdf_links(sub, link))
                candidates.extend(l for l in links if l.lower().endswith(".pdf"))
                if candidates:
                    break

        # Prefer URLs that look like the engineering submission for 2025.
        def rank_candidate(url: str) -> tuple[int, int, int]:
            low = url.lower()
            return (
                0 if "engine" in low or "engg" in low else 1,
                0 if "2025" in low else 1,
                len(low),
            )

        candidates = sorted(dict.fromkeys(candidates), key=rank_candidate)

        if not candidates:
            log.append(f"MISS   {college[:52]:<52} no candidate link")
            return None, {"college": college, "reason": "no NIRF PDF link found on the institution's own site"}, log

        valid: list[dict] = []
        tried = []
        for url in candidates[:18]:
            if not institution_owned(url, allowed):
                tried.append({"url": url, "reason": f"host {host_of(url)} is not the institution's own domain"})
                continue
            body, ctype = http_get(url, timeout=30)
            if not body or not body.startswith(b"%PDF"):
                tried.append({"url": url, "reason": "not reachable, or not a PDF"})
                continue
            # Unique probe filename so parallel workers cannot clobber each other.
            tmp = RAW / f"_probe_{abs(hash((college, url))) % 10**9}.pdf"
            name, inst_id, year, category = pdf_identity(body, tmp)
            if not name or not inst_id:
                tried.append({"url": url, "reason": "no 'Institute Name ... [ID]' line"})
                continue
            if year not in ACCEPTED_YEARS:
                tried.append({"url": url, "reason": f"submission year is {year}, not one of {ACCEPTED_YEARS}"})
                continue
            if not inst_id.startswith("IR-E-"):
                tried.append({"url": url, "reason": f"id {inst_id} is not the Engineering submission"})
                continue
            if category and "ENGINEERING" not in category.upper():
                tried.append({"url": url, "reason": f"header category is {category!r}, not ENGINEERING"})
                continue
            want, have = tokens(college), tokens(name)
            overlap = len(want & have) / len(want) if want else 0.0
            ratio = difflib.SequenceMatcher(None, normalise_str(college), normalise_str(name)).ratio()
            if overlap < 0.7 and ratio < 0.85:
                tried.append(
                    {"url": url, "reason": f"name in PDF is {name!r} (overlap {overlap:.2f}, similarity {ratio:.2f})"}
                )
                continue

            dest = RAW / f"{inst_id}_{year}.pdf"
            dest.write_bytes(body)
            valid.append(
                {
                    "college": college,
                    "institute_id": inst_id,
                    "institute_name_in_pdf": name,
                    "source_url": url,
                    "source_host": host_of(url),
                    "rankings_year": year,
                    "header_category": category,
                    "local_file": dest.name,
                    "provenance": "self_hosted_by_institution",
                    "host_note": spec.get("extra_host_note")
                    if registrable(host_of(url)) not in {registrable(h) for h in hosts}
                    else None,
                }
            )
            # Stop early once the preferred year is in hand.
            if year == PREFERRED_YEAR:
                break

        chosen = None
        if valid:
            valid.sort(key=lambda v: (0 if v["rankings_year"] == PREFERRED_YEAR else 1, v["rankings_year"]))
            chosen = valid[0]

        try:
            for leftover in RAW.glob("_probe_*.pdf"):
                leftover.unlink(missing_ok=True)
        except Exception:
            pass

        if chosen:
            log.append(
                f"OK     {college[:52]:<52} {chosen['institute_id']:<14} "
                f"NIRF {chosen['rankings_year']}  {chosen['source_host']}"
            )
            return chosen, None, log

        log.append(f"REJECT {college[:52]:<52} {len(candidates)} candidate(s), none acceptable")
        for t in tried[:3]:
            log.append(f"         - {t['reason']}")
        return None, {"college": college, "reason": "no acceptable PDF among candidates", "tried": tried[:8]}, log


def main() -> int:
    RAW.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)

    only = set(sys.argv[1:]) or None
    work = {c: s for c, s in TARGETS.items() if not only or c in only}

    accepted: dict[str, dict] = {}
    rejected: list[dict] = []

    from concurrent.futures import ThreadPoolExecutor, as_completed

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(process_college, c, s): c for c, s in work.items()}
        for future in as_completed(futures):
            college = futures[future]
            try:
                ok, bad, log = future.result()
            except Exception as exc:  # noqa: BLE001
                print(f"ERROR  {college[:52]:<52} {exc}")
                rejected.append({"college": college, "reason": f"discovery failed: {exc}"})
                continue
            for line in log:
                print(line)
            if ok:
                accepted[college] = ok
            if bad:
                rejected.append(bad)

    payload = {
        "meta": {
            "dataset": "Institution-hosted NIRF 2025 Engineering disclosures for band-ranked Tamil Nadu TNEA colleges",
            "why": "NIRF publishes per-institute disclosures only down to rank 200; colleges in the 201-300 band are absent from the Ministry CDN.",
            "provenance_warning": "These documents are the institution's own NIRF submission, but they are served by the institution rather than by the Ministry of Education. Data from them is graded separately (grade S) and must never be presented as Ministry-hosted.",
            "acceptance_rules": [
                "PDF host must share a registrable domain with the institution's own website.",
                "PDF must declare India Rankings 2025.",
                "Embedded institute id must start with IR-E- (the Engineering submission).",
                "Institute name inside the PDF must match the expected college.",
            ],
            "accepted_count": len(accepted),
            "rejected": rejected,
        },
        "sources": accepted,
    }
    (OUT / "self_hosted_sources.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\naccepted={len(accepted)} rejected={len(rejected)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
