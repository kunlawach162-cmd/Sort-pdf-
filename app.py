import streamlit as st
from pypdf import PdfReader, PdfWriter
import pandas as pd
import re
import io

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

    # ★ หมายเหตุ: เลขที่ขึ้นต้น TH อาจเป็น Flash ได้ด้วย
    # ถ้าพบว่าจัดผิดบ่อย ให้เทียบ prefix กับบิลจริงแล้วปรับเงื่อนไขตรงนี้
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


# ★ FIX 2: แปลงโซนเป็นตัวเลข เพื่อเรียงแบบธรรมชาติ (G2 มาก่อน G10)
def zone_sort_key(zone):

    match = re.match(r'G(\d+)$', str(zone))

    if match:
        return int(match.group(1))

    return 999999  # Unknown / อื่นๆ ไปอยู่ท้ายสุด


def extract_order_id(text):

    # ดึงหมายเลขที่ขึ้นต้นด้วย PA ก่อน
    pa_match = re.search(r'(PA[A-Z0-9]+)', text, re.IGNORECASE)
    if pa_match:
        result = pa_match.group(1)
        # ตัดคำว่า Order ที่บังเอิญติดมาด้วยออกไป
        if result.lower().endswith("order"):
            result = result[:-5]
        return result

    # ถ้าไม่มี PA ค่อย fallback กลับไปหา Order ID ปกติ
    match = re.search(
        r'Order\s*ID\s*:\s*([A-Z0-9\-]+)',
        text,
        re.IGNORECASE
    )

    if match:
        return match.group(1).strip()

    return "Unknown"


def extract_sku(text):

    patterns = [
        r'(1-GDS-[A-Z0-9\-]+)',
        r'(\d+-[A-Z]+-[A-Z0-9\-]+)'
    ]

    for pattern in patterns:

        match = re.search(pattern, text)

        if match:
            return match.group(1)

    return "ZZZZZZ"


def extract_qty(text):

    lines = text.splitlines()

    for line in lines:

        line = line.strip()

        match = re.match(
            r'^[A-Z]{1,3}\s+(\d{1,3})$',
            line
        )

        if match:

            qty = int(match.group(1))

            if 1 <= qty <= 50:
                return qty

    # fallback
    full_text = text.replace("\n", " ")

    total_match = re.search(
        r'รวมทั้งสิ้น\s*(\d{1,3})',
        full_text
    )

    if total_match:

        qty = int(total_match.group(1))

        if 1 <= qty <= 50:
            return qty

    return 1


def extract_data_from_page(text):

    data = {
        "zone": "Unknown",
        "sku": "ZZZZZZ",
        "qty": 1,
        "source": "Unknown",
        "track_no": "Unknown",
        "courier": "Unknown",
        "order_id": "Unknown"
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

    data["sku"] = extract_sku(text)

    data["qty"] = extract_qty(text)

    data["order_id"] = extract_order_id(text)

    return data


# ================= PDF PROCESS =================

def process_multiple_pdfs(uploaded_files, sort_mode):

    all_pages_data = []

    writer = PdfWriter()

    total_pages = 0

    # ★ FIX 3: นับหน้าที่อ่านข้อความไม่ได้ (เช่น ภาพสแกน)
    unreadable_pages = 0

    # สำคัญมาก: เก็บ Stream ไว้ไม่ให้โดนระบบเคลียร์แรมทิ้ง
    # ป้องกันปัญหารูปภาพ บาร์โค้ด หายตอนเซฟเป็น PDF ใหม่
    pdf_streams = []
    readers = []

    # โหลดไฟล์และอ่านหน้าทั้งหมด
    for file_index, uploaded_file in enumerate(uploaded_files):

        file_bytes = uploaded_file.getvalue()

        stream = io.BytesIO(file_bytes)
        pdf_streams.append(stream)

        reader = PdfReader(stream)
        readers.append((file_index, reader))

        total_pages += len(reader.pages)

    progress_bar = st.progress(0)

    processed_pages = 0

    # ดึงข้อมูลจากแต่ละหน้า
    for file_index, reader in readers:

        for page in reader.pages:

            text = page.extract_text() or ""

            if not text.strip():
                unreadable_pages += 1

            page_info = extract_data_from_page(text)

            page_info["file_index"] = file_index

            page_info["reader_page_ref"] = page

            all_pages_data.append(page_info)

            processed_pages += 1

            progress = processed_pages / max(total_pages, 1)

            progress_bar.progress(progress)

    # SORT (★ FIX 2: โซนเรียงตามตัวเลขจริง ไม่ใช่ตามตัวอักษร)
    if sort_mode == "🚚 เรียงตามขนส่ง -> SKU":

        all_pages_data.sort(
            key=lambda x: (
                x["courier"],
                zone_sort_key(x["zone"]),
                x["sku"]
            )
        )

    elif sort_mode == "📦 เรียงตามโซน -> SKU":

        all_pages_data.sort(
            key=lambda x: (
                zone_sort_key(x["zone"]),
                x["sku"]
            )
        )

    else:

        all_pages_data.sort(
            key=lambda x: x["sku"]
        )

    # WRITE PDF
    for page_info in all_pages_data:

        writer.add_page(
            page_info["reader_page_ref"]
        )

    output_pdf = io.BytesIO()

    writer.write(output_pdf)

    output_pdf.seek(0)

    # เอา page ref ออกก่อนเก็บลง session_state
    # (object หนักและผูกอยู่กับ reader ที่จะถูกเคลียร์ทิ้ง)
    for page_info in all_pages_data:
        page_info.pop("reader_page_ref", None)

    # ★ FIX จุดย่อย: เคลียร์แถบ progress ไม่ให้ค้างที่ 100%
    progress_bar.empty()

    return output_pdf, all_pages_data, unreadable_pages


# ================= HEADER =================

st.title("📦 Sharp Bill Sorter")

st.caption(
    "ระบบจัดเรียงบิลอัจฉริยะสำหรับคลังสินค้า"
)

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

            with st.spinner("⏳ กำลังประมวลผล..."):

                sorted_pdf, details, unreadable = process_multiple_pdfs(
                    uploaded_files,
                    sort_mode
                )

            # ★ FIX 1: เก็บผลลัพธ์ลง session_state
            # จะได้ไม่หายตอนกดดาวน์โหลด / พิมพ์ค้นหา (Streamlit rerun)
            st.session_state.result = {
                "pdf_bytes": sorted_pdf.getvalue(),
                "df": pd.DataFrame(details),
                "sort_mode": sort_mode,
                "unreadable": unreadable
            }

        except Exception as e:

            st.session_state.pop("result", None)

            st.error(f"❌ เกิดข้อผิดพลาด : {e}")

# ================= RESULTS =================
# ★ FIX 1: ส่วนแสดงผลอยู่นอกปุ่ม อ่านจาก session_state
# ทำให้ตาราง / ปุ่มดาวน์โหลด / ช่องค้นหา อยู่ครบทุกครั้งที่หน้า rerun

if "result" in st.session_state:

    result = st.session_state.result

    df = result["df"]

    # ใช้โหมด ณ ตอนที่กดจัดบิล (ไม่ใช่ค่าปัจจุบันของ radio)
    result_mode = result["sort_mode"]

    st.success("🎉 จัดบิลสำเร็จ")

    # ★ FIX 3: เตือนหน้าที่อ่านข้อความไม่ได้
    if result["unreadable"] > 0:

        st.warning(
            f"⚠️ มี {result['unreadable']} หน้า ที่อ่านข้อความไม่ได้ "
            f"(อาจเป็นภาพสแกน) ข้อมูลจะขึ้นเป็น Unknown "
            f"— ลองค้นหาคำว่า Unknown ในตารางด้านล่าง แล้วเช็คด้วยมืออีกที"
        )

    # ★ FIX จุดย่อย: เตือน Tracking ซ้ำ (กันบิลพิมพ์ซ้ำ / แพ็คซ้ำ)
    dup_mask = (
        (df["track_no"] != "Unknown")
        & df["track_no"].duplicated(keep=False)
    )

    dup_tracks = df.loc[dup_mask, "track_no"].unique()

    if len(dup_tracks) > 0:

        show = ", ".join(dup_tracks[:5])

        more = (
            f" และอีก {len(dup_tracks) - 5} เลข"
            if len(dup_tracks) > 5
            else ""
        )

        st.warning(
            f"⚠️ พบเลข Tracking ซ้ำ: {show}{more} "
            f"— อาจเป็นบิลพิมพ์ซ้ำ ระวังแพ็คซ้ำ"
        )

    # ================= METRICS =================

    total_orders = len(df)

    total_qty = int(df["qty"].sum())

    shopee_count = len(
        df[df["source"] == "Shopee 🟠"]
    )

    lazada_count = len(
        df[df["source"] == "Lazada 🔵"]
    )

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            "📋 จำนวนออเดอร์",
            f"{total_orders} บิล"
        )

    with col2:
        st.metric(
            "📦 จำนวนสินค้ารวม",
            f"{total_qty} ชิ้น"
        )

    with col3:
        st.metric(
            "🛒 Marketplace",
            f"Shopee {shopee_count} | Lazada {lazada_count}"
        )

    st.markdown("---")

    # ================= DOWNLOAD PDF =================

    st.download_button(
        label="📥 ดาวน์โหลด PDF ที่จัดเรียงแล้ว",
        data=result["pdf_bytes"],
        file_name="sharp_sorted_bills.pdf",
        mime="application/pdf",
        use_container_width=True,
        type="primary"
    )

    # ================= SUMMARY =================

    st.subheader("📊 Picking Summary")

    if result_mode == "🚚 เรียงตามขนส่ง -> SKU":

        summary_df = df.groupby(
            ["courier", "zone", "sku"]
        )["qty"].sum().reset_index()

        summary_df.columns = [
            "ขนส่ง",
            "โซน",
            "SKU",
            "จำนวน"
        ]

        # ★ FIX 2: เรียงโซนตามตัวเลขจริงใน summary ด้วย
        summary_df = summary_df.sort_values(
            by=["ขนส่ง", "โซน", "SKU"],
            key=lambda s: s.map(zone_sort_key) if s.name == "โซน" else s
        )

    elif result_mode == "📦 เรียงตามโซน -> SKU":

        summary_df = df.groupby(
            ["zone", "sku"]
        )["qty"].sum().reset_index()

        summary_df.columns = [
            "โซน",
            "SKU",
            "จำนวน"
        ]

        summary_df = summary_df.sort_values(
            by=["โซน", "SKU"],
            key=lambda s: s.map(zone_sort_key) if s.name == "โซน" else s
        )

    else:

        summary_df = df.groupby(
            ["sku"]
        )["qty"].sum().reset_index()

        summary_df.columns = [
            "SKU",
            "จำนวน"
        ]

        summary_df = summary_df.sort_values(
            by=["SKU"]
        )

    # DOWNLOAD CSV
    csv_data = summary_df.to_csv(
        index=False
    ).encode("utf-8-sig")

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

    display_df = df.copy().reset_index(drop=True)

    display_df["หน้าใหม่"] = display_df.index + 1

    display_df = display_df[
        [
            "หน้าใหม่",
            "track_no",
            "courier",
            "zone",
            "sku",
            "qty",
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
        "Order ID"
    ]

    search = st.text_input(
        "ค้นหา SKU / Order ID / Tracking / ขนส่ง",
        key="search_box"
    )

    if search:

        filtered = display_df[
            display_df["SKU"].astype(str).str.contains(
                search,
                case=False,
                na=False
            )
            |
            display_df["Order ID"].astype(str).str.contains(
                search,
                case=False,
                na=False
            )
            |
            display_df["ขนส่ง"].astype(str).str.contains(
                search,
                case=False,
                na=False
            )
            |
            display_df["Tracking"].astype(str).str.contains(
                search,
                case=False,
                na=False
            )
        ]

        st.dataframe(
            filtered,
            use_container_width=True,
            hide_index=True
        )

    else:

        st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True
        )

# ================= RESET =================

st.markdown("---")

col1, col2 = st.columns([3, 1])

with col2:

    if st.button(
        "🔄 เริ่มรอบใหม่",
        use_container_width=True
    ):

        st.session_state.uploader_key += 1

        # ★ FIX 1: เคลียร์ผลลัพธ์เก่าด้วย
        st.session_state.pop("result", None)

        st.rerun()

