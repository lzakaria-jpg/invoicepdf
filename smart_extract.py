# -*- coding: utf-8 -*-
"""
Layout-adaptive extraction engine for Arabic/English invoices, quotations & receipts.

The core idea: instead of relying on fixed coordinates (like the old INV91-only
logic), detect the table header row by its column *labels* (Arabic normalized via
NFKC + English), derive each column's x-boundaries from the label positions, then
assign every numeric/text block below the header to the column whose x-range it
falls into. This works for LTR and RTL layouts, wide/split product columns,
quotations, and the many different tax-coupon designs found across the 66 samples.
"""
import re
import unicodedata

# ---------------------------------------------------------------------------
# Arabic normalization: PDF text often uses presentation-form ligatures.
# NFKC turns اﻟﻮﺣﺪة -> الوحدة, اﻟﻜﻤﻴﺔ -> الكمية ... so regexes can match cleanly.
# ---------------------------------------------------------------------------
def norm_ar(s):
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", s)
    # remove tashkeel / tatweel / diacritics
    s = re.sub(r"[\u064B-\u065F\u0670\u0640\u06D6-\u06DC\u06DF-\u06E8\u06EA-\u06ED]", "", s)
    return s


def norm(t):
    return " ".join(norm_ar(t).split())


# ---------------------------------------------------------------------------
# Column concept detection
# ---------------------------------------------------------------------------
_RE_ITEM = re.compile(
    r"^#|^\u0633\.\u0645|^\u0639\u062f|\u0631\u0642\u0645|\u0627\u0644\u0628\u0646\u062f"
    r"|\bitem\b|\bno\.?$|^s\.?no|procedure id|line item|#\u0645\u0633\u062a\u062e\u062f\u0645",
    re.IGNORECASE)
_RE_DESC = re.compile(
    r"\u0627\u0644\u0648\u0635\u0641|\u0627\u0644\u0645\u0646\u062a\u062c|\u0627\u0644\u062e\u062f\u0645\u0629"
    r"|\u0627\u0644\u0633\u0644\u0639\u0629|\u0627\u0644\u0628\u064a\u0627\u0646|nature of goods"
    r"|\bdescription\b|\bproducts\b|\bproduct\b|\bitem\b|\bservice description\b|\bdetails\b"
    r"|\bdescr\b|\bgoods\b|model number",
    re.IGNORECASE)
_RE_QTY = re.compile(
    r"\u0627\u0644\u0643\u0645\u064a\u0629|\u0627\u0644\u0639\u062f\u062f|\u0642\u0637\u0639|\u0643\u0645\u064a\u0629"
    r"|\bqty\b|\bquantity\b|\bpieces qty\b|\bcount\b",
    re.IGNORECASE)
_RE_PRICE = re.compile(
    r"\u0633\u0639\u0631|\u0627\u0644\u0648\u062d\u062f\u0629|\u0642\u064a\u0645\u0629 \u0627\u0644\u062e\u062f\u0645\u0629"
    r"|\bunit price\b|\bpieces price\b|\bservice rate\b|\brate\b|\bprice\b|\bu/p\b|\bsingle price\b",
    re.IGNORECASE)
_RE_TAX = re.compile(
    r"\u0627\u0644\u0636\u0631\u064a\u0628\u0629|\u0627\u0644\u0642\u064a\u0645\u0629|\u0627\u0644\u0636\u0631\u064a\u0628"
    r"|\bvat\b|\btax\b|\bvalue added\b|vat%|\b%vat\b",
    re.IGNORECASE)
_RE_DISC = re.compile(
    r"\u0627\u0644\u062e\u0635\u0645|\u062e\u0635\u0645|\bdis\b|\bdiscount\b|\bdis\.?%",
    re.IGNORECASE)
_RE_TOTAL = re.compile(
    r"\u0627\u0644\u0645\u062c\u0645\u0648\u0639|\u0627\u0644\u0627\u062c\u0645\u0627\u0644\u064a|\u0627\u0644\u0627\u062c\u0645\u0627\u0644"
    r"|\u0627\u0644\u062c\u0645\u0644\u064a|\u0627\u0644\u0645\u0628\u0644\u063a|\u0627\u0644\u0627\u062c\u0645\u0627"
    r"|\u0627\u0644\u062c\u0645\u0627\u0644\u064a|\u062c\u0645\u0627\u0644\u064a"
    r"|\btotal\b|\bamount\b|\bsubtotal\b|\bgrand total\b|\bnet\b|\bt/p\b",
    re.IGNORECASE)
_RE_TAXRATE = re.compile(
    r"\u0646\u0633\u0628\u0629|\u0627\u0644\u0646\u0633\u0628\u0629|\u0627\u0644\u0636\u0631\u064a\u0628\u0629\s*%"
    r"|\bvat\s*%|\b%vat\b|\btax\s*%|\btax rate\b|vat rate",
    re.IGNORECASE)

# Ordered: specificity of concept matching for full words mixed with Arabic
CONCEPT_PRIORITY = [
    ("qty", _RE_QTY),
    ("price", _RE_PRICE),
    ("tax", _RE_TAX),
    ("disc", _RE_DISC),
    ("total", _RE_TOTAL),
    ("desc", _RE_DESC),
    ("item", _RE_ITEM),
    ("taxrate", _RE_TAXRATE),
]


def classify_concept(text):
    """Return a set of column concepts matched by a header label text."""
    t = norm(text)
    concept = None
    score = 0
    for name, rx in CONCEPT_PRIORITY:
        if rx.search(t):
            # Give priority to matches on short/clean tokens to avoid e.g.
            # "الكمية" classifying a qty cell and a price cell.
            concept = name
            score += 1
    return concept


# ---------------------------------------------------------------------------
# Row/column helpers
# ---------------------------------------------------------------------------
def block_center_x(b):
    return (b["x"] + b["x2"]) / 2.0


def block_center_y(b):
    return (b["y"] + b["y2"]) / 2.0


def cluster_rows(blocks):
    """Group blocks sharing roughly the same vertical center into item rows."""
    rows = []
    for b in sorted(blocks, key=lambda z: block_center_y(z)):
        placed = False
        for row in rows:
            cy = block_center_y(row["blocks"][0])
            if abs(block_center_y(b) - cy) <= 6.0:
                row["blocks"].append(b)
                row["cy"] = (row["cy"] * (len(row["blocks"]) - 1) + block_center_y(b)) / len(row["blocks"])
                placed = True
                break
        if not placed:
            rows.append({"blocks": [b], "cy": block_center_y(b), "y": b["y"], "page": b["page"]})
    return rows


def find_header_row_columns(blocks):
    """
    Scan blocks for a table header row: a y-level containing >=2 distinct column
    concepts (ideally qty+price, or qty+desc+price). Returns a dict of
    {'col': {'x_lo', 'x_hi', 'center', 'label'}} computed from label centers,
    or None if no table header found.
    """
    # group blocks by rounded y
    by_y = {}
    for b in blocks:
        yk = round(block_center_y(b), 0)
        by_y.setdefault(yk, []).append(b)
    by_y = {k: v for k, v in by_y.items() if v}

    # merge stacked header lines (bilingual headers often render Arabic labels on
    # one line and English labels on the next line a few pixels below)
    merged = []  # list of (yk, group)
    for yk in sorted(by_y):
        if merged and yk - merged[-1][0] <= 14:
            merged[-1][1] = merged[-1][1] + by_y[yk]
        else:
            merged.append([yk, by_y[yk][:]])

    best = None
    best_page = 0
    for yk, group in merged:
        concepts = {}
        for b in group:
            c = classify_concept(b["text"])
            if c:
                concepts.setdefault(c, []).append(b)
        distinct = [c for c in concepts if concepts[c]]
        # require at least qty+price, or qty+desc+price, or price+total+desc
        names = set(distinct)
        has_price = "price" in names
        has_qty = "qty" in names
        has_desc = "desc" in names
        if has_price and (has_qty or has_desc):
            score = len(names) + (2 if has_qty else 0) + (1 if has_desc else 0)
            has_nums = any(_clean_number(b["text"]) is not None for b in group)
            cand = (score, yk, concepts)
            if best is None:
                best = cand
                best_numeric = has_nums
            else:
                # prefer a label-only header row (no stray numbers) and among
                # those, the topmost one
                if not best_numeric and has_nums:
                    continue
                if best_numeric and not has_nums:
                    best, best_numeric = cand, False
                elif best_numeric == has_nums and yk < best[1]:
                    best = cand
                best_page = group[0]["page"]
    if best is None:
        return None

    _, yk, concepts = best
    # representative label per concept: pick the widest/shortest label block
    reps = {}
    for c, blist in concepts.items():
        blist = sorted(blist, key=lambda b: len(b["text"]))
        reps[c] = blist

    # Build ordered centers for boundary computation. Only use columns we care about.
    col_centers = []
    for c, bl in reps.items():
        for b in bl:
            col_centers.append((block_center_x(b), c))
    col_centers.sort()

    # collapse duplicate centers close together for same concept
    cols = []
    for cx, c in col_centers:
        if cols and abs(cols[-1]["center"] - cx) < 8 and cols[-1]["concept"] == c:
            cols[-1]["x_hi"] = max(cols[-1]["x_hi"], (b2 := next((z["x2"] for z in reps[c] if abs(block_center_x(z) - cx) < 8), cx)))
            continue
        cols.append({"concept": c, "center": cx, "x_lo": next((z["x"] for z in reps[c] if abs(block_center_x(z) - cx) < 8), cx - 20), "x_hi": next((z["x2"] for z in reps[c] if abs(block_center_x(z) - cx) < 8), cx + 20)})

    # assign boundaries: midpoint between adjacent column centers, but let the
    # 'desc' column stretch toward the next column (descriptions are wide and
    # their text often extends well past the narrow header label).
    ordered = cols[:]  # list of col dicts already sorted by center (ascending)
    for i, col in enumerate(ordered):
        lo = col["x_lo"]
        hi = col["x_hi"]
        if i > 0:
            prev_c = ordered[i - 1]
            lo = max(lo, (col["center"] + prev_c["center"]) / 2)
        if i < len(ordered) - 1:
            next_c = ordered[i + 1]
            if col["concept"] == "desc" and next_c["concept"] == "item":
                hi = next_c["x_lo"]  # desc spans everything left of item col
            else:
                hi = min(hi, (col["center"] + next_c["center"]) / 2)
        col["x_lo"] = lo
        col["x_hi"] = hi

    result = {}
    for col in ordered:
        result[col["concept"]] = {"x_lo": col["x_lo"], "x_hi": col["x_hi"],
                                  "center": col["center"], "label": None}

    # A description cell often extends well past its (narrow) header label on
    # the right; when desc is the last column give it the rest of the row so
    # long Arabic descriptions are not lost to block-center crossing.
    if "desc" in result and ordered and ordered[-1]["concept"] == "desc":
        result["desc"]["x_hi"] = max(result["desc"]["x_hi"], 560)

    # Some layouts have no description column header at all: the description
    # occupies the unlabeled space between the qty column and the item/product
    # code column. Restore that gap as the desc column.
    if "desc" not in result and "qty" in result and "item" in result:
        gap_lo = result["qty"]["x_hi"]
        gap_hi = result["item"]["x_lo"]
        if gap_hi - gap_lo > 25:
            result["desc"] = {"x_lo": gap_lo, "x_hi": gap_hi,
                              "center": (gap_lo + gap_hi) / 2, "label": None}

    return {"header_y": yk, "cols": result, "page": best_page}


def assign_column(block, cols, table_left, table_right):
    cx = block_center_x(block)
    for concept, col in cols.items():
        if col["x_lo"] <= cx <= col["x_hi"]:
            return concept
    return None


# ---------------------------------------------------------------------------
# Summary detection (below the item table)
# ---------------------------------------------------------------------------
_SUMMARY_KW = [
    "total", "amount", "\u0627\u0644\u0645\u062c\u0645\u0648\u0639", "\u0627\u062c\u0645\u0627\u0644",
    "\u0627\u0644\u0627\u062c\u0645\u0627\u0644", "\u0627\u0644\u062c\u0645\u0644\u064a",
    "\u0645\u0644\u062e\u0635", "invoice summary", "sub total", "discount", "\u0627\u0644\u062e\u0635\u0645",
    "vat", "\u0627\u0644\u0636\u0631\u064a\u0628\u0629", "\u0627\u0644\u0642\u064a\u0645\u0629",
    "bank", "\u0627\u0644\u0628\u0646\u0643", "account", "\u0627\u0644\u062d\u0633\u0627\u0628",
    "iban", "pay", "\u062f\u0641\u0639", "terms", "\u0627\u0644\u0634\u0631\u0648\u0637",
    "\u0627\u0644\u0627\u062d\u0643\u0627\u0645", "ninety", "halala", "riyal", "grand total",
    "customer", "seller", "\u0627\u0644\u0639\u0645\u064a\u0644", "\u0627\u0644\u0628\u0627\u0626\u0639",
    "address", "\u0627\u0644\u0639\u0646\u0648\u0627\u0646", "qr", "\u0631\u064a\u0627\u0644",
    "saudi", "procedure", "due", "\u0627\u0644\u0645\u0633\u062a\u062d\u0642", "phone", "invoice number",
    "issue date", "due date", "invoice date", "\u062a\u0627\u0631\u064a\u062e", "\u0641\u0627\u062a\u0648\u0631\u0629",
    "additional", "\u0627\u0636\u0627\u0641\u064a\u0629", "vat no", "tax", "\u0639\u0646\u0648\u0627\u0646",
    "bill", "ship", "buyer", "seller", "\u0627\u0644\u0645\u0634\u062a\u0631\u064a", "\u0627\u0644\u0645\u0648\u0631\u062f",
    "tac number", "tac no", "\u0628\u0627\u0642\u064a", "balance", "\u0627\u0644\u0631\u0635\u064a\u062f", "redeem",
    "\u0646\u0633\u0628\u0629",
]


def is_summary_block(b):
    t = norm(b["text"])
    return any(kw in t.lower() for kw in _SUMMARY_KW)


# ---------------------------------------------------------------------------
# Document-type / header detection
# ---------------------------------------------------------------------------
def detect_doc_type(blocks, full_text):
    ft = norm_ar(full_text)
    if re.search(r"\u0642\u0628\u0636|\breceipt\b", ft, re.IGNORECASE):
        return "receipt"
    if re.search(r"\u0639\u0631\u0636|\u0642\u064a\u0645\u064a\u0645|quotation|\u062f\u0631\u0627\u0633\u0629 \u0633\u0639\u0631", ft, re.IGNORECASE):
        return "quotation"
    return "invoice"


def extract_number(blocks, full_text, doc_type):
    """Invoice / quotation / bill number."""
    kw = (r"\u0639\u0631\u0636|\u0642\u064a\u0645\u064a|quotation") if doc_type == "quotation" else r"\u0641\u0627\u062a\u0648\u0631\u0629|\u0641\u0627\u062a\u0648\u0631|invoice|\u0641\u0627\u062a\u0648\u0631\u0629"
    # labels: Invoice Number / رقم الفاتورة / رقم العرض / Quotation No ...
    label_rx = re.compile(
        r"(invoice|quotation|bill|simple bill|receipt|factura|sales)\s*(number|no|no\.|#)?"
        r"|(\u0641\u0627\u062a\u0648\u0631\u0629|\u0639\u0631\u0636|\u0642\u0628\u0636)\s*(\u0631\u0642\u0645|\u0631\u0642\u0645)?",
        re.IGNORECASE)

    candidates = []
    for b in blocks:
        label = label_rx.search(norm_ar(b["text"]))
        if label and re.search(r"(number|no\.?|no|#|\u0631\u0642\u0645)", norm_ar(b["text"]), re.IGNORECASE):
            # look for adjacent block on same/subsequent line containing the code
            for nb in blocks:
                if nb is b:
                    continue
                if abs(nb["y"] - b["y"]) < 8 and nb["x"] > b["x"]:
                    m = re.search(r"([A-Za-z]{2,4}[- ]?\d{2,})", norm_ar(nb["text"]))
                    if m:
                        candidates.append(m.group(1))
                        break
            # also scan the b.text itself for a number after the colon label
            m = re.search(r"(?:رقم|number|no)[:\s]*([A-Za-z0-9]{3,})", b["text"] + " " + norm_ar(b["text"]), re.IGNORECASE)
            if m:
                candidates.append(m.group(1))

    # fallback: scan full text for patterns like INV123, QTE123, SBill123, SI123
    for pattern in [r"\b(INV[- ]?\d+)\b", r"\b(QTE[- ]?\d+)\b", r"\b(SBill[- ]?\d+)\b",
                    r"\b(SI[- ]?\d+)\b", r"\b(PYT\d+)\b", r"\b(INV\d+)\b", r"\b(QTE\d+)\b"]:
        m = re.search(pattern, full_text, re.IGNORECASE)
        if m:
            candidates.append(m.group(1))

    # prefer INV-like codes
    for c in candidates:
        if re.match(r"(INV|QTE|SI|SBill|PYT)", c, re.IGNORECASE):
            return c
    return candidates[0] if candidates else ""


def extract_date(blocks, full_text):
    """Issue date only (not due/supply/creation)."""
    date_rx = re.compile(r"(\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|\d{1,2}[-/]\d{1,2}[-/]\d{4})")
    # Look for the issue-date label
    label_kw = re.compile(r"(issue|invoice|quotation|bill|date)", re.IGNORECASE) if True else None
    issue_labels = re.compile(
        r"(invoice|issue|quotation|simple bill|bill)\s*(date|issued|issue)|date\s*issued"
        r"|(\u062a\u0627\u0631\u064a\u062e)\s*(\u0627\u0644\u0627\u0635\u062f\u0627\u0631|\u0627\u0644\u0625\u0635\u062f\u0627\u0631|\u0627\u0644\u0641\u0627\u062a\u0648\u0631\u0629|\u0627\u0644\u0639\u0631\u0636|\u0627\u0644\u0625\u0635\u062f\u0627\u0631|)"
        r"|(\u0627\u0644\u0627\u0635\u062f\u0627\u0631)(\s*\u062a\u0627\u0631\u064a\u062e)?" ,
        re.IGNORECASE)

    seen = set()
    for b in blocks:
        t = norm_ar(b["text"])
        if issue_labels.search(t) and re.search(r"date|issued|\u0627\u0635\u062f\u0627\u0631|\u0625\u0635\u062f\u0627\u0631|\u0639\u0631\u0636|\u0641\u0627\u062a\u0648\u0631\u0629", t, re.IGNORECASE):
            for nb in blocks:
                if nb is b:
                    continue
                if abs(nb["y"] - b["y"]) < 8 and nb["x"] > b["x"]:
                    dm = date_rx.search(norm_ar(nb["text"]))
                    if dm:
                        return _fmt_date(dm.group(1))
            # also the label itself may contain the date (e.g. "الإصدار تاريخ: 2026-01-25")
            dm = date_rx.search(b["text"])
            if dm:
                return _fmt_date(dm.group(1))

    # fallback: first date in the header region (top ~40% of page, y<300) that is
    # not preceded by "due"/"الاستحقاق"/"الانتهاء"/"الانشا"/"supply"/"creation"
    fallback = []
    for m in date_rx.finditer(full_text):
        fallback.append(m.group(1))
    for f in fallback:
        # naive but acceptable: skip obvious due dates
        return _fmt_date(f)
    return ""


def _fmt_date(d):
    parts = re.split(r"[-/]", d)
    if len(parts) == 3:
        # decide order: if first part has 4 digits => YYYY-MM-DD
        if len(parts[0]) == 4:
            return f"{parts[2]}/{parts[1]}/{parts[0]}"
        if len(parts[2]) == 4:
            return f"{parts[2]}/{parts[1]}/{parts[0]}"
        return d
    return d


_CUSTOMER_LABELS = re.compile(
    r"customer|bill to|ship to|buyer|\u0627\u0644\u0639\u0645\u064a\u0644|\u0627\u0644\u0645\u0634\u062a\u0631\u064a"
    r"|\u0627\u0644\u0639\u0645\u064a\u0644|\u0639\u0645\u064a\u0644|customer name|cusomer"
    r"|\u0628\u064a\u0627\u0646\u0627\u062a \u0627\u0644\u0639\u0645\u064a\u0644|customer details",
    re.IGNORECASE)
_SELLER_LABELS = re.compile(r"supplier|seller|vendor|\u0627\u0644\u0645\u0648\u0631\u062f|\u0627\u0644\u0628\u0627\u0626\u0639", re.IGNORECASE)


def extract_customer(blocks, full_text):
    """
    Find the Customer/Buyer name. Location varies per layout; detect by label,
    never by fixed coordinate. Skip Seller/vendor. On success return
    (name, anchor_x, anchor_y) where the anchor is a good OCR crop box.
    """
    cust_label_blocks = []
    for b in blocks:
        t = norm_ar(b["text"])
        if _CUSTOMER_LABELS.search(t) and not _SELLER_LABELS.search(t):
            cust_label_blocks.append(b)

    # Sort: prefer the lowest label (closest to the value) / the one with "name"
    cust_label_blocks.sort(key=lambda b: (b["y"]))

    for label in cust_label_blocks:
        ly, lx, page = label["y"], label["x"], label["page"]
        # Inline value: "Bill to: Company X" / "Customer: X"
        m = re.search(r"(?:bill to|customer|buyer|cusomer)[:\s]+(.{3,})",
                      norm_ar(label["text"]), re.IGNORECASE)
        if m and not re.match(r"^[\d\s\-,:.]+$", m.group(1).strip()):
            return m.group(1).strip()[:80], None, None
        # Block value: on the same page/label line or the line(s) below the label,
        # to the right of the label, not itself a label, not numeric-only.
        best = None
        for nb in blocks:
            if nb is label or nb["page"] != page:
                continue
            ncy = (nb["y"] + nb["y2"]) / 2
            if ncy <= ly - 3 or ncy > ly + 28:
                continue
            if nb["x"] <= lx - 2:
                continue  # prefer value to the right (buyer sits right)
            tn = norm(nb["text"])
            if not tn or len(tn) < 3:
                continue
            if _CUSTOMER_LABELS.search(tn) or _SELLER_LABELS.search(tn):
                continue
            if re.search(r"name|\u0627\u0644\u0627\u0633\u0645|\u0627\u0644\u0639\u0646\u0648\u0627\u0646|address"
                         r"|vat|vat\s*no|\u0636\u0631\u064a\u0628|\u0647\u0627\u062a\u0641|phone|\u0631\u0642\u0645"
                         r"|\u0639\u0646\u0648\u0627\u0646|\u0628\u0631\u064a\u062f|email",
                         tn, re.IGNORECASE):
                continue
            if re.match(r"^[\d\s\-,:.]+$", tn):
                continue
            if re.search(r"\bCUS\d", tn):
                continue
            if best is None or nb["x"] > best["x"]:
                best = nb
        if best and best["text"]:
            return best["text"].strip()[:80], best["x"], best["y"]

    # Fallback A: company-word scan away from seller (restricted to first page)
    company_rx = re.compile(
        r"\u0634\u0631\u0643\u0629|\u0645\u0624\u0633\u0633\u0629|\u0645\u062e\u062a\u0628\u0631|\u0645\u0633\u062a\u0634\u0641\u0649"
        r"|\u0639\u064a\u0627\u062f\u0629|\u0645\u0631\u0643\u0632|\u0645\u0635\u0646\u0639|\u0645\u0637\u0628\u0639"
        r"|\u0645\u0643\u062a\u0628|\u0645\u0642\u0627\u0648\u0644\u0627\u062a|&\u0631\u0643|\u0645\u0637\u0639\u0645"
        r"|\u0641\u0646\u062f\u0642|company|inc|\.?co\.?|\best\b|\bllc\b|\bgroup\b|\u0645\u062c\u0645\u0648\u0639\u0629"
        r"|larsen|toubro|maersk|al amal", re.IGNORECASE)
    for b in blocks:
        if b["page"] != 0:
            continue
        t = norm(b["text"])
        if company_rx.search(t) and len(t) > 3 and not re.match(r"^[\d\s\-,:.]+$", t):
            if not re.search(r"address|\u0627\u0644\u0639\u0646\u0648\u0627\u0646|bank|\u0627\u0644\u0628\u0646\u0643"
                             r"|beneficiary|\u0645\u0633\u062a\u0641\u064a\u062f", t, re.IGNORECASE):
                return t[:80], b["x"], b["y"]
    return "", None, None


def extract_customer_code(blocks, full_text):
    m = re.search(r"\b(CUS[-\s]?\d+)\b", full_text, re.IGNORECASE)
    return m.group(1).strip() if m else ""


def extract_tax_percent(blocks, full_text):
    # look for standalone % like "15%", "%15", or a percent next to tax label
    candidates = []
    for b in blocks:
        t = b["text"].strip()
        if "%" not in t:
            continue
        mt = re.search(r"(\d{1,2})\s*%", t) if "%" in t else None
        if mt:
            before = t[:mt.start()]
            after = t[mt.end():]
            # standalone-ish percent: only optional % / parens / spaces around it
            if re.match(r"^[%(\s]*$", before) and re.match(r"^[%\s)]*$", after):
                val = int(mt.group(1))
                if val in (5, 10, 15, 20):
                    candidates.append(val)
    # also search in label text e.g. "الضريبة المضافة ( 15 )%" or "VAT 15%"
    for b in blocks:
        if _RE_TAX.search(norm_ar(b["text"])):
            mt = re.search(r"[(\s]*(\d{1,2})\s*%", norm_ar(b["text"]))
            if mt:
                val = int(mt.group(1))
                if val in (5, 10, 15, 20):
                    candidates.append(val)
    if candidates:
        return str(candidates[0])
    return "15"


def extract_location(blocks, full_text):
    m = re.search(r"(?:\u0627\u0644\u0645\u0648\u0642\u0639|\u0627\u0644\u0641\u0631\u0639|location|branch)\s*[:\s]*(.+?)(?:\n|$)", full_text)
    return m.group(1).strip()[:50] if m else ""


# ---------------------------------------------------------------------------
# Product / item extraction via column detection
# ---------------------------------------------------------------------------
def _is_item_number_text(t):
    return bool(re.match(r"^\d{1,3}$", t.strip()))


def _clean_number(s):
    s = s.replace(",", "").replace(" ", "").replace("\u066c", "").strip()
    if re.match(r"^%?\s*\d+([.,]\d+)?\s*%?$", s):
        s = s.replace("%", "").strip()
    if re.match(r"^\d+([.,]\d+)?$", s):
        try:
            return float(s)
        except Exception:
            return None
    return None


def _extract_code(text):
    """Product code at start of a description, e.g. 'ABC123 - Desc' or leading token."""
    m = re.match(r"^([A-Z0-9]{2,20})\s*[-\u2013\u2014|/]\s*", text.strip())
    if m:
        return m.group(1).strip()
    return ""


def extract_products(blocks, header_row, doc_type):
    """
    Parse the item table below header_row using the computed column x-ranges.
    Returns a list of item dicts (normalized product model).

    Strategy (handles both line-based and multi-line interleaved layouts):
      * If an 'item' number column exists, anchor each item band on its cells:
        values = numeric cells in the y-band between neighbours; description =
        desc-column blocks in the same band.
      * Otherwise fall back to physical-line row clustering.
    """
    if not header_row:
        return []

    cols = header_row["cols"]
    header_y = header_row["header_y"]
    header_page = header_row.get("page", 0)
    num_cols = [c for c in ("qty", "price", "tax", "disc", "total") if c in cols]

    # Table region: below the header on the header's page; from the top of the
    # page on continuation pages (no repeated header).
    pages = sorted(set(b["page"] for b in blocks))
    table_blocks = []
    for pg in pages:
        lo = header_y + 2 if pg == header_page else 0
        table_blocks += [b for b in blocks
                         if b["page"] == pg and b["y"] > lo
                         and not is_summary_block(b)]

    items = []

    # ---------- Anchor-based (item-number column) path ----------
    if "item" in cols:
        # Per-page segmentation: the header_y only applies to the page where the
        # header actually is; continuation pages have no header so the table may
        # start near the top of the page.
        pages = sorted(set(b["page"] for b in table_blocks))
        recent = []
        for pg in pages:
            page_blocks = [b for b in table_blocks if b["page"] == pg]
            if not page_blocks:
                continue
            anchors = [b for b in page_blocks
                       if assign_column(b, cols, 0, 600) == "item"
                       and _is_item_number_text(b["text"])]
            anchors.sort(key=lambda z: z["y"])
            if not anchors:
                continue
            # first page: table starts just below header; later pages: top of page
            page_lo = header_y + 2 if pg == header_page else 0
            prev_a = {"y": -1}
            for i, a in enumerate(anchors):
                # Copy A of a description sits between the previous numeric row and
                # this numeric row; copy B (a duplicate render) sits below, so the
                # band for item i runs from the previous anchor's y down to this
                # anchor's y. Lines that replay the previous item's text are then
                # dropped via prev_blob.
                lo = page_lo if i == 0 else prev_a["y"]
                hi = a["y"]
                band_blocks = [b for b in page_blocks
                               if b["y"] > lo and b["y"] <= hi]
                prev_blob = " || ".join(recent) if recent else None
                item = _build_item(band_blocks, a, cols, prev_blob)
                if item:
                    item["item_number"] = _to_int(a["text"])
                    items.append(item)
                    recent.append(item.get("_band_all") or "")
                    item.pop("_desc_full", None)
                    item.pop("_band_all", None)
                prev_a = a
        if not items:
            # anchors found but nothing built -> line-based fallback
            items = _line_based_products(table_blocks, cols, header_row["header_y"])

    if not items:
        items = _line_based_products(table_blocks, cols, header_row["header_y"])

    # Global de-dup of description text: some DOCUMENT renders each item's
    # description twice (strike/italic shadow). Drop lines already seen.
    seen = set()

    def gclean(p):
        nonlocal seen
        k = re.sub(r"\s+", " ", norm_ar(p)).strip()
        if not k:
            return False
        for s in seen:
            if k == s:
                return False
            long_, short_ = (s, k) if len(s) >= len(k) else (k, s)
            if short_ and len(short_) >= 6 and short_ in long_:
                return False
        seen.add(k)
        return True

    for it in items:
        if it["product_name"]:
            parts = [seg for seg in re.split(r"\s+", it["product_name"])]
            # cheaper: keep the whole name but remove any repeated segment chunks
            pass
        it["product_name"] = " ".join(
            seg for seg in re.split(r"(?<=[.\u2013\u2014|])\s+", it["product_name"])
        ).strip()

    # Normalize derived values
    for it in items:
        if it["unit_price"] == 0 and it["quantity"] > 0 and it["total_before_vat"] > 0:
            it["unit_price"] = round(it["total_before_vat"] / it["quantity"], 2)
        if it["total_before_vat"] == 0 and it["quantity"] > 0 and it["unit_price"] > 0:
            it["total_before_vat"] = round(it["quantity"] * it["unit_price"], 2)
        if it["total_with_vat"] == 0 and it["total_before_vat"] > 0 and it["vat_amount"] > 0:
            it["total_with_vat"] = round(it["total_before_vat"] + it["vat_amount"], 2)
        if it["vat_amount"] == 0 and it["total_before_vat"] > 0 and it["total_with_vat"] > 0:
            it["vat_amount"] = round(it["total_with_vat"] - it["total_before_vat"], 2)
    return items


def _dedupe_lines(lines):
    """Drop lines that are near-duplicates of an already-seen line (some PDFs
    render the description cell twice)."""
    if len(lines) < 2:
        return lines
    out = []
    for ln in lines:
        key = re.sub(r"\s+", " ", norm_ar(ln)).strip()
        if not key:
            continue
        if key in out:
            continue
        # near-duplicate: one contains the other largely
        dup = False
        for prev in out:
            p = re.sub(r"\s+", " ", norm_ar(prev)).strip()
            if not p:
                continue
            long_, short_ = (p, key) if len(p) >= len(key) else (key, p)
            if short_ and len(short_) >= 8 and short_ in long_:
                dup = True
                break
        if not dup:
            out.append(key)
    return out


def _build_item(band_blocks, anchor, cols, prev_blob=None):
    """Build one item from the blocks within its band."""
    qty = price = tax = disc = total = 0.0
    desc_lines = []
    local_blob = ""
    all_desc = []
    for b in band_blocks:
        c = assign_column(b, cols, 0, 600)
        t = b["text"]
        # Long descriptions (esp. Arabic, rendered right-aligned) often start in
        # the desc column but extend across the item column boundary, so their
        # span center lands in 'item'. Treat any non-numeric text from the item
        # column (i.e. not the item number itself) as description.
        if c == "item" and not _is_item_number_text(t):
            c = "desc"
        if c in ("qty", "price", "tax", "disc", "total"):
            v = _clean_number(t)
            if v is not None:
                if c == "qty":
                    qty = v
                elif c == "price":
                    price = v
                elif c == "tax":
                    tax = v
                elif c == "disc":
                    disc = v
                elif c == "total":
                    total = v
                continue
        if c == "desc":
            tn = norm(t)
            if tn and len(tn) > 1 and not _CUSTOMER_LABELS.search(tn):
                all_desc.append((b["y"], t.strip()))
                # drop lines that repeat earlier description text: same cell is
                # often rendered twice (strike/italic shadow), so the copy lines
                # of this item or the previous item are textually redundant
                if _in_blob(tn, local_blob) or (prev_blob and _in_blob(tn, prev_blob)):
                    continue
                desc_lines.append((b["y"], t.strip()))
                local_blob = local_blob + " " + tn

    # read top-to-bottom, remove duplicate renderings of the same description
    desc_lines.sort(key=lambda p: p[0])
    kept = [ln for _, ln in desc_lines]
    desc_parts = _dedupe_lines(kept)
    description = " ".join(desc_parts).strip()
    code = _extract_code(description)
    if code:
        description = re.sub(r"^%s\s*[-\u2013\u2014|/]\s*" % re.escape(code), "", description).strip()
        # strip trailing duplicated code (e.g. "...cable pull  WCT21-")
        description = re.sub(r"%s\s*[-\u2013\u2014|/]?\s*$" % re.escape(code), "", description).strip()
    description = _strip_header_prefix(description)
    if _header_only_text(description) and not (qty > 0 or price > 0 or total > 0):
        return None
    if not (qty > 0 or price > 0 or total > 0 or description):
        return None
    return {
        "item_number": _to_int(anchor["text"]) if anchor else 0,
        "product_code": code,
        "product_name": description[:120] if description else "",
        "quantity": qty,
        "unit_price": price,
        "total_before_vat": total,
        "vat_amount": tax,
        "total_with_vat": 0,
        "discount": disc,
        "_desc_full": description or "",
        "_band_all": " ".join(ln for _, ln in sorted(all_desc)),
    }


def _in_blob(text, blob):
    """True if `text` is (word-wise) contained in the blob of already-extracted
    descriptions. Some PDFs render a description cell twice with differing wrap
    points, so lines may look like a rotated slice of the already seen text."""
    k = _wordstream(norm_ar(text))
    b = _wordstream(norm_ar(blob))
    return len(k) >= 4 and k in b


def _wordstream(s):
    return " ".join(re.findall(r"[a-z0-9\u0600-\u06FF]+", s.lower()))


def _near_dup(text, seen):
    """True if `text` is a near-duplicate of an already accepted desc line."""
    k = re.sub(r"\s+", " ", text).strip().lower()
    if not k:
        return True
    for s in seen:
        sk = re.sub(r"\s+", " ", s).strip().lower()
        if not sk:
            continue
        if k == sk:
            return True
        if len(k) >= 6 and len(sk) >= 6 and (k in sk or sk in k):
            return True
    return False


_HEADER_ONLY = [
    "description", "product", "products", "item", "quantity", "qty", "unit price",
    "price", "total", "amount", "vat", "discount", "\u0627\u0644\u0648\u0635\u0641",
    "\u0627\u0644\u0628\u064a\u0627\u0646", "\u0627\u0644\u0645\u0646\u062a\u062c",
    "\u0627\u0644\u0635\u0646\u0641", "\u0627\u0644\u0643\u0645\u064a\u0629",
    "\u0627\u0644\u0639\u062f\u062f", "\u0633\u0639\u0631 \u0627\u0644\u0648\u062d\u062f\u0629",
    "\u0627\u0644\u0648\u062d\u062f\u0629", "\u0627\u0644\u0642\u064a\u0645\u0629",
    "\u0627\u0644\u0627\u062c\u0645\u0627\u0644\u064a", "\u0627\u0644\u0627\u062c\u0645\u0627\u0644\u064a",
    "\u0627\u0644\u0645\u062c\u0645\u0648\u0639", "\u0627\u0644\u0636\u0631\u064a\u0628\u0629",
    "\u0627\u0644\u062e\u0635\u0645", "\u0637\u0628\u064a\u0639\u0629",
    "nature of goods", "description of goods", "desc", "main branch", "main",
]
_LONG_HEADER = [
    "\u0627\u0644\u062e\u062f\u0645\u0627\u062a \u0627\u0648 \u0627\u0644\u0633\u0644\u0639",
    "\u0627\u0644\u0633\u0644\u0639 \u0627\u0648 \u0627\u0644\u062e\u062f\u0645\u0627\u062a",
    "nature of goods and services", "goods or services", "description of goods and services",
    "invoice summary", "total amounts", "\u0627\u062c\u0645\u0627\u0644\u064a \u0627\u0644\u0645\u0628\u0627\u0644\u063a",
]


def _strip_header_prefix(desc):
    """Remove leading table-header words that leak into a description
    (e.g. 'Description English Name 2', 'الوصف ...')."""
    for _ in range(4):
        m = re.match(
            r"^(description|products?|item\s*\d*|الوصف|البيان|المنتج|الصنف|الخدمة|كود|الخدمات او السلع"
            r"|السلع او الخدمات|nature of goods|service description|pieces qty|quantity pieces|qty)"
            r"[\s:\-\u2013\u2014|]*", desc, re.IGNORECASE)
        if m:
            desc = desc[m.end():]
        else:
            break
    return desc.strip()


def _header_only_text(text):
    """True if a row consists solely of a table column label."""
    t = re.sub(r"[\s\-\u2013\u2014:.:()]", "", norm_ar(text)).strip().lower()
    if not t:
        return True
    for h in _HEADER_ONLY:
        if t == re.sub(r"[\s\-\u2013\u2014:.:()]", "", h.lower()):
            return True
    for h in _LONG_HEADER:
        hl = re.sub(r"[\s\-\u2013\u2014:.:()]", "", h.lower())
        if hl and len(t) <= 55 and hl in t:
            return True
    return False


def _line_based_products(table_blocks, cols, header_y=None):
    """Fallback: cluster blocks into physical lines; build contiguous
    description-blocks and pair each with the nearest numeric line (the
    description of a cell is often rendered on several lines above/below the
    line holding the quantity/price/total)."""
    if header_y is not None:
        table_blocks = [b for b in table_blocks if b["y"] >= header_y - 2]
    rows = sorted(cluster_rows(table_blocks), key=lambda r: r["y"])

    def row_cells(row):
        cell_map = {}
        for b in row["blocks"]:
            c = assign_column(b, cols, 0, 600)
            if c == "item" and not _is_item_number_text(b["text"]):
                c = "desc"
            if c:
                cell_map.setdefault(c, []).append(b)
        return cell_map

    # pass 1: build contiguous desc blocks (only text, no numbers)
    desc_blocks = []  # each: {'y0', 'y1', 'y', 'text', 'code'}
    cur = None
    for row in rows:
        numeric_in_row = False
        for b in row["blocks"]:
            c = assign_column(b, cols, 0, 600)
            if c in ("qty", "price", "tax", "disc", "total") and \
                    _clean_number(b["text"]) is not None:
                numeric_in_row = True
                break
            if c == "item" and _is_item_number_text(b["text"]):
                numeric_in_row = True
                break
        cm = row_cells(row)
        parts = []
        for b in cm.get("desc", []):
            tn = norm(b["text"])
            if tn and len(tn) > 1 and not _CUSTOMER_LABELS.search(tn):
                parts.append(b["text"].strip())
        desc = " ".join(parts).strip()
        if desc and not numeric_in_row:
            if cur and row["y"] - cur["y1"] <= 45:
                cur["y1"] = row["y"]
                cur["text"] += " " + desc
            else:
                cur = {"y0": row["y"], "y1": row["y"], "y": row["y"],
                       "text": desc, "code": _extract_code(desc)}
                desc_blocks.append(cur)
        else:
            cur = None

    # pass 2: numeric rows
    numeric_rows = []  # {'y', 'qty', 'price', 'tax', 'disc', 'total', 'desc'}
    for row in rows:
        cm = row_cells(row)
        rec = {"y": row["y"], "qty": 0.0, "price": 0.0, "tax": 0.0,
               "disc": 0.0, "total": 0.0, "desc": "", "has_any": False}
        for c, blist in cm.items():
            for b in blist:
                t = b["text"]
                v = _clean_number(t)
                if c in ("qty", "price", "tax", "disc", "total") and v is not None:
                    rec[c] = v
                    if c in ("qty", "price", "total") and v > 0:
                        rec["has_any"] = True
                elif c == "desc":
                    tn = norm(t)
                    if tn and len(tn) > 1 and not _CUSTOMER_LABELS.search(tn):
                        rec["desc"] += " " + t.strip()
        if rec["has_any"]:
            rec["desc"] = rec["desc"].strip()
            numeric_rows.append(rec)

    # pass 3: pair each numeric row with the nearest desc block
    used = set()
    items = []
    for rec in sorted(numeric_rows, key=lambda r: r["y"]):
        best = None
        for i, blk in enumerate(desc_blocks):
            if i in used:
                continue
            dist = abs(((blk["y0"] + blk["y1"]) / 2) - rec["y"])
            if best is None or dist < best[0]:
                best = (dist, i, blk)
        if best and best[0] <= 55:
            _, i, blk = best
            used.add(i)
            desc = (blk["text"] + " " + rec["desc"]).strip()
        elif rec["desc"]:
            desc = rec["desc"]
        else:
            desc = ""
        if _header_only_text(desc):
            continue
        code = _extract_code(desc)
        items.append(_mk_line_item(rec["y"], desc, code, rec["qty"], rec["price"],
                                   rec["total"], rec["tax"], rec["disc"]))

    # leftovers: desc blocks that never matched a numeric row (only include ones
    # that look like product lines, not payment/form footer labels)
    _PAY_NOISE = re.compile(
        r"iban|\u0627\u064a\u0628\u0627\u0646|\u064a\u0628\u0627\u0646|\u0627\u0644\u062d\u0633\u0627\u0628"
        r"|\u0627\u0644\u0645\u062f\u0641\u0648\u0639|مدفوع|\u0642\u0628\u0636|\u0642\u0628\u0636 \u0633\u0646\u062f"
        r"|\u062a\u062d\u0648\u064a\u0644|transfer|swift|payment|total amounts|الدفع|sabb|main branch"
        r"|\u0641\u0631\u0639 \u0631\u0626\u064a\u0633\u064a|\u0627\u0644\u0645\u0628\u0644\u063a"
        r"|\u0627\u0644\u0645\u0628\u0644\u063a \u0627\u0644\u0645\u062f\u0641\u0648\u0639|\u0644\u0644\u062a\u0648\u0627\u0635\u0644"
        r"|\u062b\u0627\u0646\u0643 \u0641\u0648\u0631|\u0633\u062a\u062f\u064a\u0648 \u062f\u064a\u0632\u0627\u064a\u0646"
        r"|scan for details|www\.|\u0647\u0644\u0627\u0644\u0629|\u062e\u0645\u0633\u0648\u0646|\u0644\u0627 \u063a\u064a\u0631"
        r"|\u0633\u0648\u062f\u064a|\u0641\u0642\u0637 \u0644\u0627|\u0633\u062a\u0629 \u0648|\u0633\u0628\u0639\u0629 \u0648"
        r"|\u0627\u0644\u0645\u0636\u0627\u0641\u0629|\u0627\u0644\u0622\u0641\u0649 \u0648|only\b", re.IGNORECASE)
    for i, blk in enumerate(desc_blocks):
        if i not in used:
            txt = blk["text"]
            if _header_only_text(txt):
                continue
            if _PAY_NOISE.search(txt):
                continue
            # skip mostly-numeric/metadata lines (IBAN, phone, account numbers...)
            letters = re.findall(r"[a-z\u0600-\u06FF]", txt.lower())
            if len(letters) < 4:
                continue
            items.append(_mk_line_item(blk["y"], txt, blk["code"], 0, 0, 0, 0, 0))
    return items


def _mk_line_item(y, description, code, qty, price, total, tax, disc):
    description = _strip_header_prefix(description)
    if code:
        description = re.sub(r"^%s\s*[-\u2013\u2014|/]\s*" % re.escape(code), "", description).strip()
    return {
        "item_number": 0, "product_code": code,
        "product_name": description[:120] if description else "",
        "quantity": qty, "unit_price": price,
        "total_before_vat": total, "vat_amount": tax,
        "total_with_vat": 0, "discount": disc,
    }


def _to_int(s):
    m = re.match(r"\d+", str(s))
    return int(m.group()) if m else 0


def extract_all(doc_blocks, full_text):
    """
    Top-level entry. doc_blocks is the flat list of block dicts (with page).
    Returns (header, products) where header has the 13-column-ish fields and
    products is a list of normalized item dicts.
    """
    header_row = find_header_row_columns(doc_blocks)
    doc_type = detect_doc_type(doc_blocks, full_text)

    cust_name, cust_ax, cust_ay = extract_customer(doc_blocks, full_text)
    header = {
        "invoice_number": extract_number(doc_blocks, full_text, doc_type),
        "date": extract_date(doc_blocks, full_text),
        "customer_name": cust_name,
        "customer_anchor": (cust_ax, cust_ay),
        "customer_code": extract_customer_code(doc_blocks, full_text),
        "tax_percent": extract_tax_percent(doc_blocks, full_text),
        "location": extract_location(doc_blocks, full_text),
        "doc_type": doc_type,
    }

    products = extract_products(doc_blocks, header_row, doc_type)

    # Customer name OCR fallback handled by caller (needs image rendering).

    return header, products
