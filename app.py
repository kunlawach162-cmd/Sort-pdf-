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

# ================= SESSION =================
if "uploader_key" not in st.session_state:
    st.session_state.uploader_key = 0

# ================= CSS =================
st.markdown("""
<style>

html, body, [data-testid="stAppViewContainer"] {
    background-color: #faf9f6 !important;
    color: #1e293b;
}

.block-container {
    padding-top: 1rem;
}

h1, h2, h3 {
    color: #111827;
}

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

# ================= BULKY SKUS LOADER =================

@st.cache_data
def load_bulky_skus(file_path="bulky_skus.txt"):
    """โหลด รายการ SKU สินค้าชิ้นใหญ่จากไฟล์ bulky_skus.txt"""
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            # เก็บรายการรหัสสินค้าชิ้นใหญ่ ตัดช่องว่าง/ขีด เพื่อเตรียมไว้ค้นหาแบบยืดหยุ่น
            skus = []
            for line in f:
                clean = line.strip()
                if clean:
                    skus.append(clean)
            return skus
    return []


# ================= WATERMARK CREATOR (ตำแหน่งตรงกลางล่าง) =================

def create_watermark_page(width=595, height=842):
    """
    สร้างตราปั๊ม 'EXTRA BOX' วางไว้ตรงกลางด้านล่างของหน้ากระดาษ
    """
    packet = io.BytesIO()
    c = canvas.Canvas(packet, pagesize=(width, height))
    
    c.saveState()
    
    stamp_w, stamp_h = 160, 42
    x_pos = width / 2
    y_pos = 50
    
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
    
    return PdfReader(packet).pages[0]


# ================= FUNCTIONS =================

def detect_platform(text):
    text = text.lower()
    if "shopee" in text:
        return "Shopee 🟠"
    if "lazada" in text or "lada" in text:
        return "Lazada 🔵"
    return "Unknown"


def detect_courier(track_no, source):
    if not track_no:
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
    elif t.startswith("JT"):
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
    if match:
        return match.group(1)
    return "Unknown"


def extract_order_id(text):
    pa_match = re.search(r'(PA[A-Z0-9]+)', text, re.IGNORECASE)
    if pa_match:
        result = pa_match.group(1)
        if result.lower().endswith("order"):
            result = result[:-5]
        return result

    match = re.search(
        r'Order\s*ID\s*:\s*([A-Z0-9\-]+)',
        text,
        re.IGNORECASE
    )
    if match:
        return match.group(1).strip()

    return "Unknown"


def extract_all_skus(text):
    """
    ดึง SKU ทุกตัวที่มีในบิล
    """
    if not text:
        return ["ZZZZZZ"]

    clean_text = text.replace('\xa0', ' ')
    found_skus = []

    matches = re.findall(r'1\s*-\s*GDS\s*-\s*[A-Z0-9\s\-]+', clean_text, re.IGNORECASE)
    for m in matches:
        raw_sku = m.split()[0] if ' ' in m else m
        clean_sku = re.sub(r'\s+', '', raw_sku).upper()
        clean_sku = re.sub(r'(885\d+).*$', '', clean_sku)
        clean_sku = clean_sku.rstrip('-')
        
        if len(clean_sku) >= 10:
            found_skus.append(clean_sku)

    if not found_skus:
        alt_matches = re.findall(r'1-GDS-[A-Z0-9\-]+', clean_text.replace(" ", "").upper())
        found_skus.extend(alt_matches)

    seen = set()
    unique_skus = []
    for s in found_skus:
        if s not in seen:
            seen.add(s)
            unique_skus.append(s)

    return unique_skus if unique_skus else ["ZZZZZZ"]


def extract_grand_total_qty(text):
    """
    อ่านยอด 'รวมทั้งสิ้น' ล่างสุดของบิลเป็นหลัก 100%
    """
    if not text:
        return 1
        
    clean_text = text.replace('\xa0', ' ')

    # 1. ค้นหา "รวมทั้งสิ้น X"
    total_match = re.search(r'ร\s*ว\s*ม\s*ทั้\s*ง\s*สิ้\s*น\s*[:\=]?\s*(\d{1,3})', clean_text, re.IGNORECASE)
    if total_match:
        return int(total_match.group(1))

    # 2. ค้นหา Total
    total_en_match = re.search(r'Total\s*[:\=]?\s*(\d{1,3})', clean_text, re.IGNORECASE)
    if total_en_match:
        return int(total_en_match.group(1))

    # 3. ค้นหาจากตาราง QTY
    line_qtys = re.findall(r'\b[A-Z]\s*-\s*(\d{1,2})\b', clean_text)
    if line_qtys:
        return sum(int(q) for q in line_qtys)

    return 1


def check_is_bulky(text, bulky_skus_list):
    """
    ตรวจสอบว่ามีสินค้า Bulky ในบิลหรือไม่ โดยค้นแบบ Substring (ไม่สนช่องว่าง/ขีด)
    """
    if not text or not bulky_skus_list:
        return False

    # ทำความสะอาดข้อความทั้งหน้าบิล (ลบช่องว่างและขีดออก)
    cleaned_page_text = re.sub(r'[\s\-]+', '', text).upper()

    for bulky_sku in bulky_skus_list:
        cleaned_bulky = re.sub(r'[\s\-]+', '', bulky_sku).upper()
        if len(cleaned_bulky) >= 3 and cleaned_bulky in cleaned_page_text:
            return True

    return False


def extract_data_from_page(text, bulky_skus_list):
    data = {
        "zone": "Unknown",
        "sku": "ZZZZZZ",
        "all_skus": [],
        "qty": 1,
        "source": "Unknown",
        "track_no": "Unknown",
        "courier": "Unknown",
        "order_id": "Unknown",
        "is_bulky": False,
        "boxes": 1,
        "need_split": False,
        "box_status": "ปกติ (1 กล่อง)"
    }

    if not text:
        return data

    data["source"] = detect_platform(text)
    data["track_no"] = extract_track(text)
    data["courier"] = detect_courier(
        data["track_no"],
        data["source"]
    )
    data["zone"] = extract_zone(text)
    
    extracted_skus = extract_all_skus(text)
    data["all_skus"] = extracted_skus
    data["sku"] = ", ".join(extracted_skus)
    data["order_id"] = extract_order_id(text)

    # 1. ยอด "รวมทั้งสิ้น"
    total_qty = extract_grand_total_qty(text)
    data["qty"] = total_qty

    # 2. ตรวจจับสินค้า Bulky แบบยืดหยุ่น (ทนต่อชื่อรุ่น/รหัสย่อ)
    is_bulky = check_is_bulky(text, bulky_skus_list)
    data["is_bulky"] = is_bulky

    # 3. เงื่อนไขตัดสินใจการปั๊มลายน้ำ และแยกไปท้ายสุด:
    # - ยอดรวม 1 ชิ้น -> ปกติ (ไม่แยก, ไม่ปั๊มลายน้ำ)
    # - ยอดรวม >= 2 ชิ้น AND เป็นสินค้าใหญ่ -> 🚨 เพิ่มกล่อง (ย้ายไปท้ายสุด + ปั๊มลายน้ำ)
    if total_qty == 1:
        data["need_split"] = False
        data["boxes"] = 1
        data["box_status"] = "✅ ปกติ (1 กล่อง)"
    elif is_bulky and total_qty >= 2:
        data["need_split"] = True
        data["boxes"] = total_qty
        data["box_status"] = f"🚨 เพิ่มกล่อง ({total_qty} กล่อง)"
    else:
        data["need_split"] = False
        data["boxes"] = 1
        data["box_status"] = "✅ ปกติ (1 กล่อง)"

    return data


# ================= PDF PROCESS =================

def process_multiple_pdfs(uploaded_files, sort_mode, bulky_skus):
    all_pages_data = []
    writer = PdfWriter()
    total_pages = 0
    
    pdf_streams = []
    readers = []

    for file_index, uploaded_file in enumerate(uploaded_files):
        file_bytes = uploaded_file.getvalue()
        stream = io.BytesIO(file_bytes)
        pdf_streams.append(stream)

        reader = PdfReader(stream)
        readers.append((file_index, reader))
        total_pages += len(reader.pages)

    progress_bar = st.progress(0)
    processed_pages = 0

    for file_index, reader in readers:
        for page in reader.pages:
            text = page.extract_text() or ""
            page_info = extract_data_from_page(text, bulky_skus)
            page_info["file_index"] = file_index
            page_info["reader_page_ref"] = page

            all_pages_data.append(page_info)
            processed_pages += 1
            progress = processed_pages / total_pages
            progress_bar.progress(progress)

    # ================= SORTING LOGIC =================
    # x["need_split"] -> False (0) อยู่หน้าสุด, True (1) ถูกย้ายไปท้ายสุด
    if sort_mode == "🚚 เรียงตามขนส่ง -> SKU":
        all_pages_data.sort(
            key=lambda x: (
                x["need_split"],
                x["courier"],
                x["zone"],
                x["sku"]
            )
        )
    elif sort_mode == "📦 เรียงตามโซน -> SKU":
        all_pages_data.sort(
            key=lambda x: (
                x["need_split"],
                x["zone"],
                x["sku"]
            )
        )
    else:
        all_pages_data.sort(
            key=lambda x: (
                x["need_split"],
                x["sku"]
            )
        )

    # ================= WRITE PDF & ADD WATERMARK =================
    watermark_page = None

    for page_info in all_pages_data:
        page = page_info["reader_page_ref"]

        if page_info["need_split"]:
            if watermark_page is None:
                page_w = float(page.mediabox.width)
                page_h = float(page.mediabox.height)
                watermark_page = create_watermark_page(page_w, page_h)
            
            page.merge_page(watermark_page)

        writer.add_page(page)

    output_pdf = io.BytesIO()
    writer.write(output_pdf)
    output_pdf.seek(0)

    return output_pdf, all_pages_data


# ================= HEADER =================

st.title("📦 Sharp Bill Sorter")
st.caption("ระบบจัดเรียงบิลอัจฉริยะ (รองรับหลาย SKU ในบิลเดียว + ปั๊มตรา EXTRA BOX ตรงกลางล่าง)")

# โหลดรายการ Bulky SKUs
bulky_skus = load_bulky_skus("bulky_skus.txt")
st.sidebar.info(f"📋 รายการ Bulky SKUs ในระบบ: **{len(bulky_skus)}** รายการ")

st.markdown("---")

# ================= SORT MODE =================

st.subheader("⚙️ ขั้นตอนที่ 1 : เลือกโหมดจัดเรียง")

sort_mode = st.radio(
    "เลือกรูปแบบการจัดบิล",
    [
        "🚚 เรียงตามขนส่ง -> SKU",
        "📦 เรียงตามโซน -> SKU",
        "🔤 เรียงตาม SKU อย่างเดียว"
    ],
    horizontal=True
)

st.markdown("---")

# ================= UPLOAD =================

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

    if st.button(
        "⚡ เริ่มจัดบิล",
        type="primary",
        use_container_width=True
    ):

        try:
            with st.spinner("⏳ กำลังประมวลผลและประทับตราลายน้ำ..."):
                sorted_pdf, details = process_multiple_pdfs(
                    uploaded_files,
                    sort_mode,
                    bulky_skus
                )

            df = pd.DataFrame(details)
            st.success("🎉 จัดบิลสำเร็จ! (ย้ายรายการเพิ่มกล่องไปไว้ท้ายสุดเรียบร้อยแล้ว)")

            # ================= METRICS =================

            total_orders = len(df)
            total_qty = df["qty"].sum()
            total_boxes = df["boxes"].sum()
            split_orders = len(df[df["need_split"] == True])

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

            # ================= DOWNLOAD PDF =================

            st.download_button(
                label="📥 ดาวน์โหลด PDF ที่จัดเรียงแล้ว (มีตราปั๊ม)",
                data=sorted_pdf,
                file_name="sharp_sorted_bills_with_watermark.pdf",
                mime="application/pdf",
                use_container_width=True,
                type="primary"
            )

            # ================= SUMMARY =================

            st.subheader("📊 Picking Summary")

            if sort_mode == "🚚 เรียงตามขนส่ง -> SKU":
                summary_df = df.groupby(
                    ["courier", "zone", "sku"]
                ).agg(
                    qty=("qty", "sum"),
                    boxes=("boxes", "sum")
                ).reset_index()

                summary_df.columns = ["ขนส่ง", "โซน", "SKU", "จำนวนสินค้า", "จำนวนกล่อง"]
                summary_df = summary_df.sort_values(by=["ขนส่ง", "โซน", "SKU"])

            elif sort_mode == "📦 เรียงตามโซน -> SKU":
                summary_df = df.groupby(
                    ["zone", "sku"]
                ).agg(
                    qty=("qty", "sum"),
                    boxes=("boxes", "sum")
                ).reset_index()

                summary_df.columns = ["โซน", "SKU", "จำนวนสินค้า", "จำนวนกล่อง"]
                summary_df = summary_df.sort_values(by=["โซน", "SKU"])

            else:
                summary_df = df.groupby(
                    ["sku"]
                ).agg(
                    qty=("qty", "sum"),
                    boxes=("boxes", "sum")
                ).reset_index()

                summary_df.columns = ["SKU", "จำนวนสินค้า", "จำนวนกล่อง"]
                summary_df = summary_df.sort_values(by=["SKU"])

            # DOWNLOAD CSV
            csv_data = summary_df.to_csv(index=False).encode("utf-8-sig")

            st.download_button(
                label="📊 ดาวน์โหลด Picking List (CSV)",
                data=csv_data,
                file_name="picking_summary.csv",
                mime="text/csv",
                use_container_width=True
            )

            st.dataframe(
                summary_df,
                use_container_width=True,
                hide_index=True
            )

            st.markdown("---")

            # ================= SEARCH =================

            st.subheader("🔍 ค้นหาออเดอร์")

            display_df = df.copy()
            display_df["หน้าใหม่"] = display_df.index + 1

            display_df = display_df[
                [
                    "หน้าใหม่",
                    "track_no", 
                    "courier",
                    "zone",
                    "sku",
                    "qty",
                    "boxes",
                    "box_status",
                    "order_id"
                ]
            ]

            display_df.columns = [
                "หน้า",
                "Tracking",
                "ขนส่ง",
                "โซน",
                "SKU",
                "จำนวน",
                "จำนวนกล่อง",
                "สถานะแพ็ก",
                "Order ID"
            ]

            search = st.text_input("ค้นหา SKU / Order ID / Tracking / ขนส่ง / สถานะแพ็ก")

            if search:
                filtered = display_df[
                    display_df["SKU"].astype(str).str.contains(search, case=False, na=False)
                    | display_df["Order ID"].astype(str).str.contains(search, case=False, na=False)
                    | display_df["ขนส่ง"].astype(str).str.contains(search, case=False, na=False)
                    | display_df["Tracking"].astype(str).str.contains(search, case=False, na=False)
                    | display_df["สถานะแพ็ก"].astype(str).str.contains(search, case=False, na=False)
                ]

                st.dataframe(filtered, use_container_width=True, hide_index=True)
            else:
                st.dataframe(display_df, use_container_width=True, hide_index=True)

        except Exception as e:
            st.error(f"❌ เกิดข้อผิดพลาด : {e}")

# ================= RESET =================

st.markdown("---")

col1, col2 = st.columns([3, 1])

with col2:
    if st.button("🔄 เริ่มรอบใหม่", use_container_width=True):
        st.session_state.uploader_key += 1
        st.rerun()
