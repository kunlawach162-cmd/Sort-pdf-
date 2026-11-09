import streamlit as st
from pypdf import PdfReader, PdfWriter
import pandas as pd
import re
import io
import os

# นำเข้า ReportLab สำหรับสร้างลายน้ำ
from reportlab.pdfgen import canvas
from reportlab.lib import colors

# ================= PAGE CONFIG =================
st.set_page_config(
    page_title="Sharp Bill Sorter",
    page_icon="📦",
    layout="wide"
)

# ================= SESSION STATE =================
if "uploader_key" not in st.session_state:
    st.session_state.uploader_key = 0
if "editor_version" not in st.session_state:
    st.session_state.editor_version = 0
if "file_store" not in st.session_state:
    st.session_state.file_store = []
if "result" not in st.session_state:
    st.session_state.result = None

# ================= CUSTOM CSS =================
st.markdown("""
<style>
html, body, [data-testid="stAppViewContainer"] {
    background-color: #faf9f6 !important;
    color: #1e293b;
}
.block-container { padding-top: 1rem; }
h1, h2, h3 { color: #111827; }
div[data-testid="stMetric"] {
    background-color: white;
    padding: 18px;
    border-radius: 14px;
    border: 1px solid #e5e7eb;
    box-shadow: 0 2px 8px rgba(0,0,0,0.03);
}
button[kind="primary"] {
    background-color: #10b981 !important;
    border-color: #10b981 !important;
    color: white !important;
    font-weight: bold !important;
    border-radius: 10px !important;
    height: 3rem;
}
button[kind="primary"]:hover {
    background-color: #059669 !important;
    border-color: #059669 !important;
}
div[data-testid="stFileUploader"] {
    background-color: white;
    border: 2px dashed #d1d5db;
    border-radius: 14px;
    padding: 20px;
}
</style>
""", unsafe_allow_html=True)

# ================= WATER CONFIG =================
WATER_MODE = "💧 น้ำแร่ : ขนส่ง -> ขนาด -> Order ID"
WATER_CODES = {
    "726281987631": 1500,
    "726281987648": 1000,
    "726281987655": 500,
}
SIZE_RANK = {1500: 0, 1000: 1, 500: 2}
UNKNOWN_SIZE_RANK = 99
MIXED_KEY = "__MIXED__"
INCOMPLETE_KEY = "__INCOMPLETE__"
WATER_COURIER_MAP = {"PX": "SCG Express 🚚"}
NUMERIC_COURIER = "Nim Express 🚚"


def size_rank(size):
    return SIZE_RANK.get(size, UNKNOWN_SIZE_RANK)


def size_label(size):
    return f"{size:,} ml" if size else "ไม่ระบุขนาด"


# ================= BULKY SKU FILE LOADER =================
def load_bulky_skus_from_file(filename="bulky_skus.txt"):
    if os.path.exists(filename):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                lines = f.readlines()
            return [s.strip() for s in lines if s.strip()], True
        except Exception as e:
            st.error(f"⚠️ ไม่สามารถอ่านไฟล์ {filename} ได้: {e}")
            return [], False
    return [], False


# ================= WATERMARK CREATOR =================
def create_watermark_reader(width=595, height=842):
    """สร้างหน้าลายน้ำ EXTRA BOX และคืน PdfReader เพื่อรักษาอายุของ stream"""
    packet = io.BytesIO()
    c = canvas.Canvas(packet, pagesize=(width, height))

    c.saveState()
    stamp_w, stamp_h = 160, 42
    x_pos, y_pos = width / 2, 50
    c.translate(x_pos, y_pos)
    c.rotate(-5)
    c.setStrokeColor(colors.HexColor("#DC2626"))
    c.setFillColor(colors.HexColor("#FEF2F2"))
    c.setLineWidth(2.5)
    c.roundRect(-stamp_w / 2, -stamp_h / 2, stamp_w, stamp_h, 8, stroke=1, fill=1)
    c.setFont("Helvetica-Bold", 16)
    c.setFillColor(colors.HexColor("#DC2626"))
    c.drawCentredString(0, -5, "EXTRA BOX")
    c.restoreState()
    c.save()
    packet.seek(0)
    return PdfReader(packet)


# ================= EXTRACTION FUNCTIONS =================
def detect_platform(text):
    t = text.lower()
    if "shopee" in t:
        return "Shopee 🟠"
    if "lazada" in t or "lada" in t:
        return "Lazada 🔵"
    if "tiktok" in t:
        return "TikTok 🖤"
    return "Unknown"


def detect_courier(track_no, source):
    if not track_no or track_no == "Unknown":
        return "Unknown"
    t = track_no.upper()
    if t.startswith("LEX"):
        return "Lazada Express (LEX) 🔵"
    elif t.startswith("SPX") or t.startswith("TH"):
        return "SPX Express 🟠"
    elif t.startswith("KEX") or t.startswith("KER"):
        return "Kerry Express 🟡"
    elif t.startswith("FLA"):
        return "Flash Express ⚡"
    elif t.startswith("JT") or t.startswith("JTTH"):
        return "J&T Express 🟣"
    return f"ขนส่งอื่นๆ ({source.split()[0]}) 🚚"


def extract_track(text):
    patterns = [
        r'Track\s*No\s*:\s*([A-Z0-9\-]+)',
        r'Tracking\s*No\s*:\s*([A-Z0-9\-]+)'
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return "Unknown"


def extract_zone(text):
    match = re.search(r'\b(G\d+)\b', text)
    return match.group(1) if match else "Unknown"


def extract_order_id(text):
    pa_match = re.search(r'PA\d{6,}', text)
    if pa_match:
        return pa_match.group(0)
    match = re.search(r'(?i:Order\s*ID)\s*:[ \t]*([A-Z0-9\-]{5,})', text)
    if match:
        return match.group(1).strip()
    return "Unknown"


def extract_order_parts(text):
    if not text:
        return "Unknown", "Unknown", 0
    match = re.search(r'PA\d{6,}(?:-\d+)?', text)
    if not match:
        fallback = extract_order_id(text)
        return fallback, fallback, 0
    full = match.group(0)
    base, _, seq = full.partition("-")
    return full, base, int(seq) if seq.isdigit() else 0


def extract_channel(text):
    if not text:
        return "ไม่ระบุช่องทาง"
    match = re.search(r'Source\s*by\s*:\s*(.+?)\s+\d{1,2}/\d{1,2}/\d{4}', text)
    if match:
        return match.group(1).strip()
    match = re.search(r'Source\s*by\s*:\s*([A-Za-z][A-Za-z&.\- ]{1,29})', text)
    if match:
        return match.group(1).strip()
    return "ไม่ระบุช่องทาง"


def water_courier_key(track_no):
    t = (track_no or "").upper().strip()
    if not t or t == "UNKNOWN":
        return "ไม่ระบุขนส่ง"
    prefix = re.match(r'[A-Z]+', t)
    if prefix:
        code = prefix.group(0)
        return WATER_COURIER_MAP.get(code, f"ขนส่งอื่นๆ ({code}) 🚚")
    if t.isdigit():
        return NUMERIC_COURIER
    return "ไม่ระบุขนส่ง"


def extract_water_size(text):
    if not text:
        return None
    compact = re.sub(r'\s+', '', text)
    for code, size in WATER_CODES.items():
        if code in compact:
            return size
    match = re.search(r'ขนาด\s*([\d,\.]+)\s*ml', text, re.IGNORECASE)
    if match:
        raw = match.group(1).replace(",", "")
        try:
            return int(float(raw))
        except ValueError:
            return None
    return None


def extract_all_skus(text):
    if not text:
        return ["ZZZZZZ"]
    matches = re.findall(r'1\s*-\s*GDS\s*-\s*[A-Z0-9\-]+', text, re.IGNORECASE)
    found_skus = [re.sub(r'\s+', '', m).upper() for m in matches]
    seen = set()
    unique_skus = [s for s in found_skus if not (s in seen or seen.add(s))]
    return unique_skus if unique_skus else ["ZZZZZZ"]


def extract_grand_total_qty(text):
    if not text:
        return 1
    lines = text.splitlines()
    for line in lines:
        line_str = line.strip()
        if "รวม" in line_str:
            nums = re.findall(r"\d+", line_str)
            if nums:
                return int(nums[-1])
    for line in lines:
        line_str = line.strip().lower()
        if "total" in line_str:
            nums = re.findall(r"\d+", line_str)
            if nums:
                return int(nums[-1])
    return 1


def is_bulky_sku(skus, bulky_list):
    if not bulky_list:
        return True
    for sku in skus:
        norm_sku = re.sub(r'[\-\s]', '', sku).upper()
        for b_sku in bulky_list:
            norm_b = re.sub(r'[\-\s]', '', b_sku).upper()
            if norm_b and norm_b in norm_sku:
                return True
    return False


def extract_data_from_page(text, bulky_list):
    data = {
        "zone": "Unknown", "sku": "ZZZZZZ", "qty": 1,
        "source": "Unknown", "track_no": "Unknown", "courier": "Unknown",
        "order_id": "Unknown", "order_full": "Unknown", "order_base": "Unknown",
        "order_seq": 0, "channel": "ไม่ระบุช่องทาง",
        "water_courier": "ไม่ระบุขนส่ง", "size": None,
        "size_label": "ไม่ระบุขนาด", "boxes": 1, "need_split": False,
        "box_status": "ปกติ (1 กล่อง)"
    }
    if not text:
        return data

    data["source"] = detect_platform(text)
    data["track_no"] = extract_track(text)
    data["courier"] = detect_courier(data["track_no"], data["source"])
    data["zone"] = extract_zone(text)
    extracted_skus = extract_all_skus(text)
    data["sku"] = ", ".join(extracted_skus)
    data["order_id"] = extract_order_id(text)
    data["order_full"], data["order_base"], data["order_seq"] = extract_order_parts(text)
    data["channel"] = extract_channel(text)
    data["water_courier"] = water_courier_key(data["track_no"])
    data["size"] = extract_water_size(text)
    data["size_label"] = size_label(data["size"])

    total_qty = extract_grand_total_qty(text)
    data["qty"] = total_qty
    if total_qty == 1:
        data["need_split"] = False
        data["boxes"] = 1
        data["box_status"] = "✅ ปกติ (1 กล่อง)"
    elif is_bulky_sku(extracted_skus, bulky_list):
        data["need_split"] = True
        data["boxes"] = total_qty
        data["box_status"] = f"🚨 เพิ่มกล่อง ({total_qty} กล่อง)"
    else:
        data["need_split"] = False
        data["boxes"] = 1
        data["box_status"] = "✅ ปกติ (1 กล่อง)"
    return data


# ================= WATER MODE =================
def group_by_order(pages_data):
    groups = {}
    for p in pages_data:
        groups.setdefault(p["order_base"], []).append(p)
    return groups


def sort_water_pages(pages_data):
    normal_pages, mixed_pages, incomplete_pages, _, _ = split_water_groups(pages_data)
    normal_pages.sort(key=lambda r: (r["water_courier"], size_rank(r["size"]), r["order_base"], r["order_seq"]))
    mixed_pages.sort(key=lambda r: (r["water_courier"], r["order_base"], size_rank(r["size"]), r["order_seq"]))
    incomplete_pages.sort(key=lambda r: (r["water_courier"], r["order_base"], size_rank(r["size"]), r["order_seq"]))
    return normal_pages + mixed_pages + incomplete_pages


def split_water_groups(pages_data):
    incomplete_bases = {prob["base"] for prob in find_incomplete_orders(pages_data)}
    mixed_bases = {
        base for base, items in group_by_order(pages_data).items()
        if base not in incomplete_bases and len({i["size"] for i in items}) > 1
    }
    normal, mixed, incomplete = [], [], []
    for p in pages_data:
        if p["order_base"] in incomplete_bases:
            incomplete.append(p)
        elif p["order_base"] in mixed_bases:
            mixed.append(p)
        else:
            normal.append(p)
    return normal, mixed, incomplete, mixed_bases, incomplete_bases


def mixed_order_detail(pages_data):
    _, mixed_pages, _, _, _ = split_water_groups(pages_data)
    detail = []
    for base, items in group_by_order(mixed_pages).items():
        sizes = sorted({i["size"] for i in items}, key=size_rank)
        detail.append((base, sizes, len(items)))
    return sorted(detail)


def find_incomplete_orders(pages_data):
    problems = []
    for base, items in group_by_order(pages_data).items():
        seqs = sorted(i["order_seq"] for i in items)
        uniq = sorted(set(seqs))
        if uniq == [0]:
            continue
        notes = []
        if 0 in uniq:
            notes.append("มีใบที่ไม่มีเลขท้ายปนอยู่")
            uniq = [s for s in uniq if s != 0]
        dup = sorted({s for s in seqs if s != 0 and seqs.count(s) > 1})
        if dup:
            notes.append("เลขท้ายซ้ำ " + ", ".join(f"-{d}" for d in dup))
        missing = []
        if uniq:
            have = set(uniq)
            missing = [n for n in range(1, max(uniq) + 1) if n not in have]
        if missing or notes:
            problems.append({
                "base": base, "present": uniq, "missing": missing,
                "notes": " / ".join(notes), "items": items
            })
    return sorted(problems, key=lambda r: r["base"])


def filter_water_pages(pages_data, selected_sizes, include_mixed, include_incomplete=False):
    _, _, _, mixed_bases, incomplete_bases = split_water_groups(pages_data)
    selected = set(selected_sizes)
    kept = []
    for p in pages_data:
        if p["order_base"] in incomplete_bases:
            if include_incomplete:
                kept.append(p)
        elif p["order_base"] in mixed_bases:
            if include_mixed:
                kept.append(p)
        elif p["size"] in selected:
            kept.append(p)
    return kept


# ================= CORE STEPS =================
def analyze_pdfs(uploaded_files, bulky_list):
    file_store, readers, total_pages = [], [], 0
    for uploaded_file in uploaded_files:
        file_bytes = uploaded_file.getvalue()
        file_store.append(file_bytes)
        reader = PdfReader(io.BytesIO(file_bytes))
        readers.append(reader)
        total_pages += len(reader.pages)

    pages_data = []
    progress_bar = st.progress(0)
    processed = 0
    for file_index, reader in enumerate(readers):
        for page_index, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            page_info = extract_data_from_page(text, bulky_list)
            page_info["file_index"] = file_index
            page_info["page_index"] = page_index
            pages_data.append(page_info)
            processed += 1
            progress_bar.progress(processed / total_pages)
    progress_bar.empty()
    return pages_data, file_store


def apply_manual_split(pages_data, manual_flags):
    updated = []
    for p, flag in zip(pages_data, manual_flags):
        q = dict(p)
        q["need_split"] = bool(flag)
        if q["need_split"]:
            q["boxes"] = max(int(q["qty"]), 1)
            q["box_status"] = f"🚨 เพิ่มกล่อง ({q['boxes']} กล่อง)"
        else:
            q["boxes"] = 1
            q["box_status"] = "✅ ปกติ (1 กล่อง)"
        updated.append(q)
    return updated


def render_pdf(pages_data, file_store):
    """
    สร้าง PDF ตามลำดับที่ส่งเข้ามา + ปั๊มตราเฉพาะหน้าที่ need_split
    แก้ pypdf 7.x: เพิ่มหน้าลง PdfWriter ก่อนเรียก merge_page
    """
    readers = [PdfReader(io.BytesIO(b)) for b in file_store]
    writer = PdfWriter()
    wm_cache = {}

    for page_info in pages_data:
        source_page = readers[page_info["file_index"]].pages[page_info["page_index"]]

        # เพิ่มหน้าลง Writer ก่อน เพื่อให้หน้าเป็นส่วนหนึ่งของ writer
        writer.add_page(source_page)
        target_page = writer.pages[-1]

        if page_info["need_split"]:
            page_w = float(target_page.mediabox.width)
            page_h = float(target_page.mediabox.height)
            key = (round(page_w), round(page_h))
            if key not in wm_cache:
                wm_cache[key] = create_watermark_reader(page_w, page_h)

            target_page.merge_page(wm_cache[key].pages[0], expand=False)

    output_pdf = io.BytesIO()
    writer.write(output_pdf)
    output_pdf.seek(0)
    return output_pdf.getvalue()


def build_sorted_pdf(pages_data, sort_mode, file_store):
    normal_bills = [p for p in pages_data if not p["need_split"]]
    split_bills = [p for p in pages_data if p["need_split"]]

    if sort_mode == WATER_MODE:
        normal_bills = sort_water_pages(normal_bills)
        split_bills = sort_water_pages(split_bills)
    else:
        if sort_mode == "🚚 เรียงตามขนส่ง -> SKU":
            sort_key = lambda x: (x["courier"], x["zone"], x["sku"])
        elif sort_mode == "📦 เรียงตามโซน -> SKU":
            sort_key = lambda x: (x["zone"], x["sku"])
        else:
            sort_key = lambda x: (x["sku"],)
        normal_bills.sort(key=sort_key)
        split_bills.sort(key=sort_key)

    final_pages_data = normal_bills + split_bills
    return render_pdf(final_pages_data, file_store), final_pages_data


# ================= HEADER =================
st.title("📦 Sharp Bill Sorter")
st.caption("ระบบจัดเรียงบิลอัจฉริยะ (เช็คยอดรวม -> ตรวจหา Bulky SKU -> แยกไว้ท้ายเล่ม + ปั๊มตรา EXTRA BOX | ติ๊กปรับเองได้ใน DEBUG INFO)")
st.markdown("---")

# ================= BULKY SKU AUTO-LOAD =================
default_bulky_skus, file_found = load_bulky_skus_from_file("bulky_skus.txt")
if file_found:
    st.success(f"✅ โหลดไฟล์ `bulky_skus.txt` สำเร็จ! พบรายการ Bulky SKU ทั้งหมด {len(default_bulky_skus)} รายการ")
else:
    st.info("ℹ️ ไม่พบไฟล์ `bulky_skus.txt` ในระบบ สามารถพิมพ์ระบุรายการด้านล่างได้ครับ")

with st.expander("⚙️ ดู/แก้ไข รายการ Bulky SKU (สินค้าใหญ่ที่ต้องเพิ่มกล่อง)", expanded=not file_found):
    bulky_text_default = "\n".join(default_bulky_skus)
    bulky_input = st.text_area("รายชื่อ Bulky SKU (บรรทัดละ 1 SKU)", value=bulky_text_default, height=150)
    bulky_list = [s.strip() for s in bulky_input.replace(",", "\n").splitlines() if s.strip()]

st.markdown("---")

# ================= STEP 1: SORT MODE =================
st.subheader("⚙️ ขั้นตอนที่ 1 : เลือกโหมดจัดเรียง")
sort_mode = st.radio(
    "เลือกรูปแบบการจัดบิล",
    ["🚚 เรียงตามขนส่ง -> SKU", "📦 เรียงตามโซน -> SKU", "🔤 เรียงตาม SKU อย่างเดียว", WATER_MODE],
    horizontal=True
)
if sort_mode == WATER_MODE:
    st.caption("💧 โหมดน้ำแร่ : แยกตามขนส่งก่อน → เรียง 1500 → 1000 → 500 ml → ตาม Order ID; ออเดอร์หลายขนาดอยู่ท้ายเล่มและกรองแยกได้")
st.markdown("---")

# ================= STEP 2: UPLOAD =================
st.subheader("📂 ขั้นตอนที่ 2 : อัปโหลด PDF")
uploaded_files = st.file_uploader(
    "ลากไฟล์ PDF มาวางตรงนี้",
    type=["pdf"],
    accept_multiple_files=True,
    key=f"uploader_{st.session_state.uploader_key}"
)

# ================= PROCESS =================
if uploaded_files:
    st.info(f"🗂️ พบไฟล์ทั้งหมด {len(uploaded_files)} ไฟล์")
    if st.button("⚡ เริ่มจัดบิล", type="primary", use_container_width=True):
        try:
            with st.spinner("⏳ กำลังประมวลผล คัดแยกออเดอร์ตามเงื่อนไข และประทับตราลายน้ำ..."):
                pages_data, file_store = analyze_pdfs(uploaded_files, bulky_list)
                pdf_bytes, final_pages = build_sorted_pdf(pages_data, sort_mode, file_store)
            st.session_state.file_store = file_store
            st.session_state.result = {"pdf": pdf_bytes, "pages": final_pages, "sort_mode": sort_mode}
            st.session_state.editor_version += 1
            st.rerun()
        except Exception as e:
            st.error(f"❌ เกิดข้อผิดพลาด : {e}")

# ================= RESULT =================
if st.session_state.result:
    res = st.session_state.result
    df = pd.DataFrame(res["pages"])
    is_water = res["sort_mode"] == WATER_MODE
    st.markdown("---")
    st.success("🎉 จัดบิลเรียบร้อย! ตรวจสอบ/ติ๊กปรับได้ใน DEBUG INFO ด้านล่าง")

    incomplete_orders = find_incomplete_orders(res["pages"])
    all_orders_count = len(group_by_order(res["pages"]))
    if incomplete_orders:
        st.error(f"🚨 พบ {len(incomplete_orders)} ออเดอร์ที่เลขท้าย PA ไม่ครบ — เช็คก่อนแพ็ก")
        missing_rows = []
        for prob in incomplete_orders:
            first = prob["items"][0]
            missing_rows.append({
                "Order ID": prob["base"],
                "ใบที่หาย": ", ".join(f"-{n}" for n in prob["missing"]) or "-",
                "ใบที่มี": ", ".join(f"-{n}" for n in prob["present"]) or "-",
                "จำนวนใบที่มี": len(prob["items"]),
                "ขนส่ง": first.get("water_courier", "-"),
                "หมายเหตุ": prob["notes"] or "-"
            })
        missing_df = pd.DataFrame(missing_rows)
        st.dataframe(missing_df, use_container_width=True, hide_index=True)
        st.download_button(
            label="📥 ดาวน์โหลดรายการออเดอร์ที่ไม่ครบ (CSV)",
            data=missing_df.to_csv(index=False).encode("utf-8-sig"),
            file_name="incomplete_orders.csv", mime="text/csv", use_container_width=True
        )
        st.caption("⚠️ ตรวจจากช่องว่างระหว่างเลขท้ายที่มีอยู่เท่านั้น — หากใบท้ายสุดหายไปจะตรวจไม่เจอ")
    else:
        st.success(f"✅ เลขท้าย PA ครบทุกออเดอร์ ({all_orders_count} ออเดอร์)")

    if is_water:
        courier_counts = {}
        for p in res["pages"]:
            courier_counts[p["water_courier"]] = courier_counts.get(p["water_courier"], 0) + 1
        st.info("🚚 แยกขนส่งจากเลขพัสดุได้ " + " | ".join(f"{c} {n} หน้า" for c, n in sorted(courier_counts.items())))
        _, banner_mixed_pages, _, banner_mixed_bases, _ = split_water_groups(res["pages"])
        if banner_mixed_bases:
            st.info(f"💧 พบออเดอร์ที่มีหลายขนาด {len(banner_mixed_bases)} ออเดอร์ ({len(banner_mixed_pages)} หน้า) — ย้ายไปไว้ท้ายเล่มแล้ว")

    # ================= DEBUG PANEL =================
    with st.expander("🛠️ DEBUG INFO: ตรวจสอบค่าที่อ่านได้จริงรายหน้า (ติ๊ก need_split ปรับเองได้)", expanded=False):
        st.write("ตารางแสดงค่าจากบิลที่จัดเรียงแล้ว (เรียงจากบนลงล่างตามไฟล์ PDF ใหม่):")
        st.caption("✏️ ติ๊ก/เอาติ๊กออกในช่อง need_split แล้วกดอัปเดต — บิลที่ติ๊กจะโดนปั๊มตรา EXTRA BOX และย้ายไปท้ายเล่ม")
        if is_water:
            debug_df = pd.DataFrame({
                "หน้าใน PDF ใหม่": range(1, len(df) + 1),
                "ขนส่ง": df["water_courier"], "Order ID": df["order_full"],
                "ขนาด": df["size_label"], "qty": df["qty"],
                "need_split": df["need_split"].astype(bool), "boxes": df["boxes"]
            })
            locked_cols = ["หน้าใน PDF ใหม่", "ขนส่ง", "Order ID", "ขนาด", "qty", "boxes"]
        else:
            debug_df = pd.DataFrame({
                "หน้าใน PDF ใหม่": range(1, len(df) + 1),
                "order_id": df["order_id"], "qty": df["qty"],
                "need_split": df["need_split"].astype(bool), "boxes": df["boxes"], "sku": df["sku"]
            })
            locked_cols = ["หน้าใน PDF ใหม่", "order_id", "qty", "boxes", "sku"]

        edited_df = st.data_editor(
            debug_df,
            column_config={"need_split": st.column_config.CheckboxColumn(
                "need_split", help="ติ๊ก = ปั๊มตรา EXTRA BOX + ย้ายไปท้ายเล่ม"
            )},
            disabled=locked_cols, hide_index=True, use_container_width=True,
            key=f"debug_editor_{st.session_state.editor_version}"
        )
        new_flags = [bool(x) for x in edited_df["need_split"].tolist()]
        old_flags = [bool(x) for x in df["need_split"].tolist()]
        has_changes = new_flags != old_flags
        if has_changes:
            diff_count = sum(1 for a, b in zip(old_flags, new_flags) if a != b)
            st.warning(f"⚠️ มีการติ๊กเปลี่ยน {diff_count} บิลที่ยังไม่ได้อัปเดต — กดปุ่มอัปเดตก่อนดาวน์โหลด")
        if st.button("🔄 อัปเดตตามติ๊กใหม่ (จัดเรียง + ปั๊มตราใหม่)", use_container_width=True):
            if has_changes:
                try:
                    with st.spinner("⏳ กำลังจัดเรียงและประทับตราใหม่ตามติ๊ก..."):
                        updated_pages = apply_manual_split(res["pages"], new_flags)
                        pdf_bytes, final_pages = build_sorted_pdf(updated_pages, res["sort_mode"], st.session_state.file_store)
                    st.session_state.result = {"pdf": pdf_bytes, "pages": final_pages, "sort_mode": res["sort_mode"]}
                    st.session_state.editor_version += 1
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ เกิดข้อผิดพลาด : {e}")
            else:
                st.info("ยังไม่มีการติ๊กเปลี่ยนแปลงครับ")

    st.markdown("---")

    # ================= METRICS =================
    total_orders = len(df)
    total_qty = int(df["qty"].sum())
    total_boxes = int(df["boxes"].sum())
    split_orders = int(df["need_split"].sum())
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("📋 จำนวนออเดอร์", f"{total_orders} บิล")
    with col2:
        st.metric("📦 จำนวนสินค้ารวม", f"{total_qty} ชิ้น")
    with col3:
        st.metric("📫 รวมกล่องที่ต้องใช้", f"{total_boxes} กล่อง")
    with col4:
        st.metric("🚨 ออเดอร์ที่ต้องเพิ่มกล่อง", f"{split_orders} บิล (อยู่ท้ายสุด)")

    st.markdown("---")
    st.download_button(
        label="📥 ดาวน์โหลด PDF ที่จัดเรียงแล้ว (มีตราปั๊ม)",
        data=res["pdf"], file_name="sharp_sorted_bills_with_watermark.pdf",
        mime="application/pdf", use_container_width=True, type="primary"
    )

    # ================= WATER FILTER =================
    if is_water:
        st.markdown("---")
        st.subheader("💧 เลือกกลุ่มที่จะปริ้น")
        st.caption("อัปโหลดครั้งเดียว แล้วสลับติ๊กเพื่อดาวน์โหลดแยกรอบได้ | ออเดอร์เลขท้ายไม่ครบจะไม่เลือกมาให้ตั้งแต่แรก")
        single_pages, mixed_pages, incomplete_pages, mixed_bases, incomplete_bases = split_water_groups(res["pages"])
        size_counts = {}
        for p in single_pages:
            size_counts[p["size"]] = size_counts.get(p["size"], 0) + 1
        sizes_present = sorted(size_counts.keys(), key=size_rank)
        label_to_key = {f"{size_label(s)} ({size_counts[s]} หน้า)": s for s in sizes_present}
        if mixed_pages:
            mixed_label = f"🔀 ออเดอร์ผสมหลายขนาด ({len(mixed_pages)} หน้า / {len(mixed_bases)} ออเดอร์)"
            label_to_key[mixed_label] = MIXED_KEY
        incomplete_label = None
        if incomplete_pages:
            incomplete_label = f"⚠️ ออเดอร์เลขท้ายไม่ครบ ({len(incomplete_pages)} หน้า / {len(incomplete_bases)} ออเดอร์)"
            label_to_key[incomplete_label] = INCOMPLETE_KEY
        options = list(label_to_key.keys())
        default_labels = [l for l in options if l != incomplete_label]
        picked_labels = st.multiselect("เลือกขนาด / กลุ่มที่จะปริ้น", options, default=default_labels)
        picked_keys = [label_to_key[l] for l in picked_labels]
        selected_sizes = [k for k in picked_keys if k not in (MIXED_KEY, INCOMPLETE_KEY)]
        include_mixed = MIXED_KEY in picked_keys
        include_incomplete = INCOMPLETE_KEY in picked_keys

        if incomplete_pages:
            if include_incomplete:
                st.warning(f"⚠️ กำลังรวมออเดอร์เลขท้ายไม่ครบ {len(incomplete_bases)} ออเดอร์เข้าไฟล์ด้วย")
            else:
                st.info(f"⏸️ กันออเดอร์เลขท้ายไม่ครบไว้ {len(incomplete_bases)} ออเดอร์ ({len(incomplete_pages)} หน้า)")
        if mixed_pages:
            with st.expander(f"🔀 ดูรายละเอียดออเดอร์ผสม {len(mixed_bases)} ออเดอร์", expanded=False):
                st.caption("ออเดอร์กลุ่มนี้จะออกมาครบทั้งชุดเสมอ")
                st.dataframe(pd.DataFrame([
                    {"Order ID": base, "ขนาดที่มี": " + ".join(size_label(s) for s in sizes), "จำนวนหน้า": n}
                    for base, sizes, n in mixed_order_detail(res["pages"])
                ]), use_container_width=True, hide_index=True)

        if not picked_keys:
            st.warning("⚠️ ยังไม่ได้เลือกอะไรเลย")
        else:
            kept_pages = filter_water_pages(res["pages"], selected_sizes, include_mixed, include_incomplete)
            if not kept_pages:
                st.error("❌ ไม่มีบิลที่ตรงเงื่อนไข")
            else:
                kept_df = pd.DataFrame(kept_pages)
                c1, c2, c3 = st.columns(3)
                with c1:
                    st.metric("📄 จำนวนหน้าที่จะปริ้น", f"{len(kept_pages)} หน้า")
                with c2:
                    st.metric("📋 จำนวนออเดอร์", f"{kept_df['order_base'].nunique()} ออเดอร์")
                with c3:
                    st.metric("📫 รวมกล่อง", f"{int(kept_df['boxes'].sum())} กล่อง")
                try:
                    filtered_pdf = render_pdf(kept_pages, st.session_state.file_store)
                    parts = [str(s) if s else "unknown" for s in selected_sizes]
                    if include_mixed:
                        parts.append("mix")
                    if include_incomplete:
                        parts.append("incomplete")
                    tag = "-".join(parts) if parts else "all"
                    st.download_button(
                        label=f"📥 ดาวน์โหลดเฉพาะขนาดที่เลือก ({len(kept_pages)} หน้า)",
                        data=filtered_pdf, file_name=f"sharp_water_{tag}ml.pdf",
                        mime="application/pdf", use_container_width=True, type="primary"
                    )
                except Exception as e:
                    st.error(f"❌ สร้างไฟล์ที่กรองไม่สำเร็จ : {e}")

    # ================= SUMMARY =================
    st.markdown("---")
    st.subheader("📊 Picking Summary")
    result_sort_mode = res["sort_mode"]
    if result_sort_mode == WATER_MODE:
        summary_df = df.groupby(["water_courier", "size_label"]).agg(
            bills=("order_full", "count"), orders=("order_base", "nunique"), boxes=("boxes", "sum")
        ).reset_index()
        summary_df["_rank"] = summary_df["size_label"].map(
            lambda l: size_rank(int(l.replace(",", "").replace(" ml", "")) if "ml" in l else None)
        )
        summary_df = summary_df.sort_values(by=["water_courier", "_rank"]).drop(columns=["_rank"])
        summary_df.columns = ["ขนส่ง", "ขนาด", "จำนวนใบ (ลัง)", "จำนวนออเดอร์", "จำนวนกล่อง"]
    elif result_sort_mode == "🚚 เรียงตามขนส่ง -> SKU":
        summary_df = df.groupby(["courier", "zone", "sku"]).agg(qty=("qty", "sum"), boxes=("boxes", "sum")).reset_index()
        summary_df.columns = ["ขนส่ง", "โซน", "SKU", "จำนวนสินค้า", "จำนวนกล่อง"]
        summary_df = summary_df.sort_values(by=["ขนส่ง", "โซน", "SKU"])
    elif result_sort_mode == "📦 เรียงตามโซน -> SKU":
        summary_df = df.groupby(["zone", "sku"]).agg(qty=("qty", "sum"), boxes=("boxes", "sum")).reset_index()
        summary_df.columns = ["โซน", "SKU", "จำนวนสินค้า", "จำนวนกล่อง"]
        summary_df = summary_df.sort_values(by=["โซน", "SKU"])
    else:
        summary_df = df.groupby(["sku"]).agg(qty=("qty", "sum"), boxes=("boxes", "sum")).reset_index()
        summary_df.columns = ["SKU", "จำนวนสินค้า", "จำนวนกล่อง"]
        summary_df = summary_df.sort_values(by=["SKU"])
    csv_data = summary_df.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        label="📊 ดาวน์โหลด Picking List (CSV)", data=csv_data,
        file_name="picking_summary.csv", mime="text/csv", use_container_width=True
    )
    st.dataframe(summary_df, use_container_width=True, hide_index=True)
    st.markdown("---")

    # ================= SEARCH =================
    st.subheader("🔍 ค้นหาออเดอร์")
    display_df = df.copy()
    display_df["หน้าใหม่"] = display_df.index + 1
    if is_water:
        display_df = display_df[["หน้าใหม่", "water_courier", "order_full", "size_label", "track_no", "channel", "boxes", "box_status"]]
        display_df.columns = ["หน้า", "ขนส่ง", "Order ID", "ขนาด", "Tracking", "ช่องทาง", "จำนวนกล่อง", "สถานะแพ็ก"]
        search_cols = ["ขนส่ง", "Order ID", "ขนาด", "Tracking", "ช่องทาง", "สถานะแพ็ก"]
        search_hint = "ค้นหา ขนส่ง / Order ID / ขนาด / Tracking / ช่องทาง"
    else:
        display_df = display_df[["หน้าใหม่", "track_no", "courier", "zone", "sku", "qty", "boxes", "box_status", "order_id"]]
        display_df.columns = ["หน้า", "Tracking", "ขนส่ง", "โซน", "SKU", "จำนวน", "จำนวนกล่อง", "สถานะแพ็ก", "Order ID"]
        search_cols = ["SKU", "Order ID", "ขนส่ง", "Tracking", "สถานะแพ็ก"]
        search_hint = "ค้นหา SKU / Order ID / Tracking / ขนส่ง / สถานะแพ็ก"
    search = st.text_input(search_hint)
    if search:
        mask = False
        for col in search_cols:
            hit = display_df[col].astype(str).str.contains(search, case=False, na=False, regex=False)
            mask = hit if mask is False else (mask | hit)
        st.dataframe(display_df[mask], use_container_width=True, hide_index=True)
    else:
        st.dataframe(display_df, use_container_width=True, hide_index=True)

# ================= RESET =================
st.markdown("---")
col1, col2 = st.columns([3, 1])
with col2:
    if st.button("🔄 เริ่มรอบใหม่", use_container_width=True):
        st.session_state.uploader_key += 1
        st.session_state.file_store = []
        st.session_state.result = None
        st.rerun()
