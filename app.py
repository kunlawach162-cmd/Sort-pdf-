import streamlit as st
from pypdf import PdfReader, PdfWriter
import pandas as pd
import re
import io

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
    if "tiktok" in text:
        return "TikTok 🖤"
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
    if not text:
        return ["ZZZZZZ"]

    matches = re.findall(r'1\s*-\s*GDS\s*-\s*[A-Z0-9\-]+', text, re.IGNORECASE)
    found_skus = []
    for m in matches:
        clean_sku = re.sub(r'\s+', '', m).upper()
        found_skus.append(clean_sku)

    seen = set()
    unique_skus = []
    for s in found_skus:
        if s not in seen:
            seen.add(s)
            unique_skus.append(s)

    return unique_skus if unique_skus else ["ZZZZZZ"]


def extract_grand_total_qty(text):
    if not text:
        return 1

    clean_text = text.replace('\xa0', ' ')

    # 1. ค้นหา "รวมทั้งสิ้น X"
    total_match = re.search(r'ร\s*ว\s*ม\s*ทั้\s*ง\s*สิ้\s*น\s*[:\=]?\s*(\d{1,3})', clean_text, re.IGNORECASE)
    if total_match:
        return int(total_match.group(1))

    # 2. ค้นหา "Total X"
    total_en_match = re.search(r'Total\s*[:\=]?\s*(\d{1,3})', clean_text, re.IGNORECASE)
    if total_en_match:
        return int(total_en_match.group(1))

    return 1


def extract_data_from_page(text):
    data = {
        "zone": "Unknown",
        "sku": "ZZZZZZ",
        "all_skus": [],
        "qty": 1,
        "source": "Unknown",
        "track_no": "Unknown",
        "courier": "Unknown",
        "order_id": "Unknown",
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

    # อ่านยอด "รวมทั้งสิ้น"
    total_qty = extract_grand_total_qty(text)
    data["qty"] = total_qty

    # ------------------ DECISION LOGIC ------------------
    if total_qty >= 2:
        data["need_split"] = True
        data["boxes"] = total_qty
        data["box_status"] = f"🚨 เพิ่มกล่อง ({total_qty} กล่อง)"
    else:
        data["need_split"] = False
        data["boxes"] = 1
        data["box_status"] = "✅ ปกติ (1 กล่อง)"

    return data


# ================= PDF PROCESS =================

def process_multiple_pdfs(uploaded_files, sort_mode):
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
            page_info = extract_data_from_page(text)
            page_info["file_index"] = file_index
            page_info["reader_page_ref"] = page

            all_pages_data.append(page_info)
            processed_pages += 1
            progress = processed_pages / total_pages
            progress_bar.progress(progress)

    # ================= 1. SPLIT INTO 2 GROUPS =================
    normal_bills = [p for p in all_pages_data if not p["need_split"]]
    split_bills = [p for p in all_pages_data if p["need_split"]]

    # ================= 2. SORT EACH GROUP =================
    if sort_mode == "🚚 เรียงตามขนส่ง -> SKU":
        normal_bills.sort(key=lambda x: (x["courier"], x["zone"], x["sku"]))
        split_bills.sort(key=lambda x: (x["courier"], x["zone"], x["sku"]))
    elif sort_mode == "📦 เรียงตามโซน -> SKU":
        normal_bills.sort(key=lambda x: (x["zone"], x["sku"]))
        split_bills.sort(key=lambda x: (x["zone"], x["sku"]))
    else:
        normal_bills.sort(key=lambda x: x["sku"])
        split_bills.sort(key=lambda x: x["sku"])

    # รวมกลุ่ม: บิลปกติไว้หน้า + บิลเพิ่มกล่องไว้หลัง
    final_pages_data = normal_bills + split_bills

    # ================= 3. WRITE PDF & MERGE WATERMARK =================
    watermark_page = None

    for page_info in final_pages_data:
        target_page = page_info["reader_page_ref"]

        if page_info["need_split"]:
            if watermark_page is None:
                page_w = float(target_page.mediabox.width)
                page_h = float(target_page.mediabox.height)
                watermark_page = create_watermark_page(page_w, page_h)
            
            # ปรับปรุงการ Merge ป้องกันปัญหา Object state ของ pypdf
            target_page.merge_page(watermark_page, expand=False)

        writer.add_page(target_page)

    output_pdf = io.BytesIO()
    writer.write(output_pdf)
    output_pdf.seek(0)

    return output_pdf, final_pages_data


# ================= HEADER =================

st.title("📦 Sharp Bill Sorter")
st.caption("ระบบจัดเรียงบิลอัจฉริยะ (แยกรายการสินค้า 'รวมทั้งสิ้น >= 2' ไว้ท้ายเล่มอัตโนมัติพร้อมตราปั๊ม EXTRA BOX)")

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
            with st.spinner("⏳ กำลังประมวลผล คัดแยกออเดอร์ และประทับตราลายน้ำ..."):
                sorted_pdf, details = process_multiple_pdfs(
                    uploaded_files,
                    sort_mode
                )

            df = pd.DataFrame(details)
            st.success("🎉 จัดบิลสำเร็จ!")

            # ================= DEBUG PANEL (ข้อ 3 & 4 ที่คุณแนะนำ) =================
            with st.expander("🛠️ DEBUG INFO: ตรวจสอบค่าที่อ่านได้จริงรายหน้า", expanded=True):
                st.write("ตารางแสดงค่าจากบิลที่จัดเรียงแล้ว (ลำดับบนลงล่างตามไฟล์ PDF ใหม่):")
                debug_df = df.copy()
                debug_df["หน้าใน PDF ใหม่"] = debug_df.index + 1
                st.dataframe(
                    debug_df[["หน้าใน PDF ใหม่", "order_id", "qty", "need_split", "boxes", "sku"]],
                    use_container_width=True,
                    hide_index=True
                )

            st.markdown("---")

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
                summary_df = df.groupby(["courier", "zone", "sku"]).agg(qty=("qty", "sum"), boxes=("boxes", "sum")).reset_index()
                summary_df.columns = ["ขนส่ง", "โซน", "SKU", "จำนวนสินค้า", "จำนวนกล่อง"]
                summary_df = summary_df.sort_values(by=["ขนส่ง", "โซน", "SKU"])
            elif sort_mode == "📦 เรียงตามโซน -> SKU":
                summary_df = df.groupby(["zone", "sku"]).agg(qty=("qty", "sum"), boxes=("boxes", "sum")).reset_index()
                summary_df.columns = ["โซน", "SKU", "จำนวนสินค้า", "จำนวนกล่อง"]
                summary_df = summary_df.sort_values(by=["โซน", "SKU"])
            else:
                summary_df = df.groupby(["sku"]).agg(qty=("qty", "sum"), boxes=("boxes", "sum")).reset_index()
                summary_df.columns = ["SKU", "จำนวนสินค้า", "จำนวนกล่อง"]
                summary_df = summary_df.sort_values(by=["SKU"])

            csv_data = summary_df.to_csv(index=False).encode("utf-8-sig")

            st.download_button(
                label="📊 ดาวน์โหลด Picking List (CSV)",
                data=csv_data,
                file_name="picking_summary.csv",
                mime="text/csv",
                use_container_width=True
            )

            st.dataframe(summary_df, use_container_width=True, hide_index=True)

        except Exception as e:
            st.error(f"❌ เกิดข้อผิดพลาด : {e}")

# ================= RESET =================

st.markdown("---")

col1, col2 = st.columns([3, 1])

with col2:
    if st.button("🔄 เริ่มรอบใหม่", use_container_width=True):
        st.session_state.uploader_key += 1
        st.rerun()

