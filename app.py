import streamlit as st
from pypdf import PdfReader, PdfWriter
import pandas as pd
import re
import io
from collections import Counter

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
    padding-top: 1.5rem;
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

.stDataFrame {
    border-radius: 12px;
}

@media (max-width: 768px) {
    .block-container {
        padding-left: 0.6rem !important;
        padding-right: 0.6rem !important;
    }
}

</style>
""", unsafe_allow_html=True)

# ================= FUNCTIONS =================

def clean_text(text):
    if not text:
        return ""
    return text.replace("\n", " ").replace("\r", " ").strip()


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

    elif t.startswith("KER"):
        return "Kerry Express 🟡"

    elif t.startswith("FLA"):
        return "Flash Express ⚡"

    elif t.startswith("JT"):
        return "J&T Express 🟣"

    return f"ขนส่งอื่นๆ ({source.split()[0]}) 🚚"


def extract_track(text):
    patterns = [
        r'Track\s*No\s*[:\-]?\s*([A-Z0-9\-]+)',
        r'Tracking\s*No\s*[:\-]?\s*([A-Z0-9\-]+)'
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
    patterns = [
        r'Order\s*ID\s*[:\-]?\s*([A-Z0-9\-]+)',
        r'เลขคำสั่งซื้อ\s*[:\-]?\s*([A-Z0-9\-]+)'
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)

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

    patterns = [
        r'รวมทั้งสิ้น\s*(\d{1,3})',
        r'จำนวน\s*[:=]?\s*(\d{1,3})',
        r'Qty\s*[:=]?\s*(\d{1,3})',
        r'Quantity\s*[:=]?\s*(\d{1,3})'
    ]

    # หาแบบรายบรรทัดก่อน
    for line in lines:

        for pattern in patterns:

            match = re.search(pattern, line, re.IGNORECASE)

            if match:
                qty = int(match.group(1))

                if 1 <= qty <= 200:
                    return qty

    # fallback แบบรวมข้อความ
    full_text = clean_text(text)

    for pattern in patterns:

        match = re.search(pattern, full_text, re.IGNORECASE)

        if match:
            qty = int(match.group(1))

            if 1 <= qty <= 200:
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

    # นับหน้าทั้งหมดก่อน
    for uploaded_file in uploaded_files:
        file_bytes = uploaded_file.getvalue()
        reader = PdfReader(io.BytesIO(file_bytes))
        total_pages += len(reader.pages)

    progress_bar = st.progress(0)

    processed_pages = 0

    for file_index, uploaded_file in enumerate(uploaded_files):

        file_bytes = uploaded_file.getvalue()

        reader = PdfReader(io.BytesIO(file_bytes))

        for page in reader.pages:

            text = page.extract_text() or ""

            page_info = extract_data_from_page(text)

            page_info["file_index"] = file_index
            page_info["reader_page_ref"] = page

            all_pages_data.append(page_info)

            processed_pages += 1

            progress = processed_pages / total_pages

            progress_bar.progress(progress)

    # SORT
    if sort_mode == "🚚 เรียงตามขนส่ง -> แล้วเรียง SKU":

        all_pages_data.sort(
            key=lambda x: (
                x["courier"],
                x["zone"],
                x["sku"]
            )
        )

    elif sort_mode == "📦 เรียงตามโซน -> SKU":

        all_pages_data.sort(
            key=lambda x: (
                x["zone"],
                x["sku"]
            )
        )

    else:

        all_pages_data.sort(
            key=lambda x: x["sku"]
        )

    # WRITE PDF
    for page_info in all_pages_data:
        writer.add_page(page_info["reader_page_ref"])

    output_pdf = io.BytesIO()

    writer.write(output_pdf)

    output_pdf.seek(0)

    return output_pdf, all_pages_data


# ================= HEADER =================

st.markdown("""
<h1 style='font-size:3rem;font-weight:900;margin-bottom:0;'>
Sharp Bill Sorter
</h1>
""", unsafe_allow_html=True)

st.markdown("""
ระบบจัดเรียงบิลอัจฉริยะสำหรับงานคลังสินค้า
""")

st.markdown("---")

# ================= SORT MODE =================

st.subheader("⚙️ ขั้นตอนที่ 1 : เลือกโหมดจัดเรียง")

sort_mode = st.radio(
    "เลือกรูปแบบการจัดบิล",
    [
        "🚚 เรียงตามขนส่ง -> แล้วเรียง SKU",
        "📦 เรียงตามโซน -> SKU",
        "🔤 เรียงตาม SKU อย่างเดียว"
    ],
    horizontal=True
)

st.markdown("---")

# ================= FILE UPLOAD =================

st.subheader("📂 ขั้นตอนที่ 2 : อัปโหลดไฟล์ PDF")

uploaded_files = st.file_uploader(
    "ลากไฟล์ PDF มาวางตรงนี้",
    type=["pdf"],
    accept_multiple_files=True,
    key=f"uploader_{st.session_state.uploader_key}"
)

# ================= PROCESS =================

if uploaded_files:

    st.info(f"🗂️ ตรวจพบ {len(uploaded_files)} ไฟล์")

    if st.button(
        "⚡ เริ่มจัดบิล",
        type="primary",
        use_container_width=True
    ):

        try:

            with st.spinner("⏳ กำลังประมวลผลไฟล์..."):

                sorted_pdf, details = process_multiple_pdfs(
                    uploaded_files,
                    sort_mode
                )

            st.success("🎉 จัดบิลสำเร็จ")

            df = pd.DataFrame(details)

            # ================= METRICS =================

            total_orders = len(df)

            total_qty = df["qty"].sum()

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
                data=sorted_pdf,
                file_name="sharp_sorted_bills.pdf",
                mime="application/pdf",
                use_container_width=True,
                type="primary"
            )

            # ================= SUMMARY =================

            st.subheader("📊 Picking Summary")

            if sort_mode == "🚚 เรียงตามขนส่ง -> แล้วเรียง SKU":

                summary_df = df.groupby(
                    ["courier", "zone", "sku"]
                )["qty"].sum().reset_index()

                summary_df.columns = [
                    "ขนส่ง",
                    "โซน",
                    "SKU",
                    "จำนวน"
                ]

                summary_df = summary_df.sort_values(
                    by=["ขนส่ง", "โซน", "SKU"]
                )

            elif sort_mode == "📦 เรียงตามโซน -> SKU":

                summary_df = df.groupby(
                    ["zone", "sku"]
                )["qty"].sum().reset_index()

                summary_df.columns = [
                    "โซน",
                    "SKU",
                    "จำนวน"
                ]

                summary_df = summary_df.sort_values(
                    by=["โซน", "SKU"]
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

            # HOT ITEMS
            if "จำนวน" in summary_df.columns:

                summary_df["🔥HOT"] = summary_df["จำนวน"].apply(
                    lambda x: "🔥" if x >= 10 else ""
                )

            # CSV
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

            display_df = df.copy()

            display_df["หน้าใหม่"] = display_df.index + 1

            display_df = display_df[
                [
                    "หน้าใหม่",
                    "courier",
                    "zone",
                    "sku",
                    "qty",
                    "order_id"
                ]
            ]

            display_df.columns = [
                "หน้า",
                "ขนส่ง",
                "โซน",
                "SKU",
                "จำนวน",
                "Order ID"
            ]

            search = st.text_input(
                "ค้นหา SKU / Order ID / ขนส่ง"
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

        except Exception as e:

            st.error(f"❌ เกิดข้อผิดพลาด : {e}")

# ================= RESET =================

st.markdown("---")

col1, col2 = st.columns([3, 1])

with col2:

    if st.button(
        "🔄 เริ่มรอบใหม่",
        use_container_width=True
    ):

        st.session_state.uploader_key += 1

        st.rerun()import streamlit as st
from pypdf import PdfReader, PdfWriter
import pandas as pd
import re
import io
from collections import Counter

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
    padding-top: 1.5rem;
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

.stDataFrame {
    border-radius: 12px;
}

@media (max-width: 768px) {
    .block-container {
        padding-left: 0.6rem !important;
        padding-right: 0.6rem !important;
    }
}

</style>
""", unsafe_allow_html=True)

# ================= FUNCTIONS =================

def clean_text(text):
    if not text:
        return ""
    return text.replace("\n", " ").replace("\r", " ").strip()


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

    elif t.startswith("KER"):
        return "Kerry Express 🟡"

    elif t.startswith("FLA"):
        return "Flash Express ⚡"

    elif t.startswith("JT"):
        return "J&T Express 🟣"

    return f"ขนส่งอื่นๆ ({source.split()[0]}) 🚚"


def extract_track(text):
    patterns = [
        r'Track\s*No\s*[:\-]?\s*([A-Z0-9\-]+)',
        r'Tracking\s*No\s*[:\-]?\s*([A-Z0-9\-]+)'
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
    patterns = [
        r'Order\s*ID\s*[:\-]?\s*([A-Z0-9\-]+)',
        r'เลขคำสั่งซื้อ\s*[:\-]?\s*([A-Z0-9\-]+)'
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)

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

    patterns = [
        r'รวมทั้งสิ้น\s*(\d{1,3})',
        r'จำนวน\s*[:=]?\s*(\d{1,3})',
        r'Qty\s*[:=]?\s*(\d{1,3})',
        r'Quantity\s*[:=]?\s*(\d{1,3})'
    ]

    # หาแบบรายบรรทัดก่อน
    for line in lines:

        for pattern in patterns:

            match = re.search(pattern, line, re.IGNORECASE)

            if match:
                qty = int(match.group(1))

                if 1 <= qty <= 200:
                    return qty

    # fallback แบบรวมข้อความ
    full_text = clean_text(text)

    for pattern in patterns:

        match = re.search(pattern, full_text, re.IGNORECASE)

        if match:
            qty = int(match.group(1))

            if 1 <= qty <= 200:
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

    # นับหน้าทั้งหมดก่อน
    for uploaded_file in uploaded_files:
        file_bytes = uploaded_file.getvalue()
        reader = PdfReader(io.BytesIO(file_bytes))
        total_pages += len(reader.pages)

    progress_bar = st.progress(0)

    processed_pages = 0

    for file_index, uploaded_file in enumerate(uploaded_files):

        file_bytes = uploaded_file.getvalue()

        reader = PdfReader(io.BytesIO(file_bytes))

        for page in reader.pages:

            text = page.extract_text() or ""

            page_info = extract_data_from_page(text)

            page_info["file_index"] = file_index
            page_info["reader_page_ref"] = page

            all_pages_data.append(page_info)

            processed_pages += 1

            progress = processed_pages / total_pages

            progress_bar.progress(progress)

    # SORT
    if sort_mode == "🚚 เรียงตามขนส่ง -> แล้วเรียง SKU":

        all_pages_data.sort(
            key=lambda x: (
                x["courier"],
                x["zone"],
                x["sku"]
            )
        )

    elif sort_mode == "📦 เรียงตามโซน -> SKU":

        all_pages_data.sort(
            key=lambda x: (
                x["zone"],
                x["sku"]
            )
        )

    else:

        all_pages_data.sort(
            key=lambda x: x["sku"]
        )

    # WRITE PDF
    for page_info in all_pages_data:
        writer.add_page(page_info["reader_page_ref"])

    output_pdf = io.BytesIO()

    writer.write(output_pdf)

    output_pdf.seek(0)

    return output_pdf, all_pages_data


# ================= HEADER =================

st.markdown("""
<h1 style='font-size:3rem;font-weight:900;margin-bottom:0;'>
Sharp Bill Sorter
</h1>
""", unsafe_allow_html=True)

st.markdown("""
ระบบจัดเรียงบิลอัจฉริยะสำหรับงานคลังสินค้า
""")

st.markdown("---")

# ================= SORT MODE =================

st.subheader("⚙️ ขั้นตอนที่ 1 : เลือกโหมดจัดเรียง")

sort_mode = st.radio(
    "เลือกรูปแบบการจัดบิล",
    [
        "🚚 เรียงตามขนส่ง -> แล้วเรียง SKU",
        "📦 เรียงตามโซน -> SKU",
        "🔤 เรียงตาม SKU อย่างเดียว"
    ],
    horizontal=True
)

st.markdown("---")

# ================= FILE UPLOAD =================

st.subheader("📂 ขั้นตอนที่ 2 : อัปโหลดไฟล์ PDF")

uploaded_files = st.file_uploader(
    "ลากไฟล์ PDF มาวางตรงนี้",
    type=["pdf"],
    accept_multiple_files=True,
    key=f"uploader_{st.session_state.uploader_key}"
)

# ================= PROCESS =================

if uploaded_files:

    st.info(f"🗂️ ตรวจพบ {len(uploaded_files)} ไฟล์")

    if st.button(
        "⚡ เริ่มจัดบิล",
        type="primary",
        use_container_width=True
    ):

        try:

            with st.spinner("⏳ กำลังประมวลผลไฟล์..."):

                sorted_pdf, details = process_multiple_pdfs(
                    uploaded_files,
                    sort_mode
                )

            st.success("🎉 จัดบิลสำเร็จ")

            df = pd.DataFrame(details)

            # ================= METRICS =================

            total_orders = len(df)

            total_qty = df["qty"].sum()

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
                data=sorted_pdf,
                file_name="sharp_sorted_bills.pdf",
                mime="application/pdf",
                use_container_width=True,
                type="primary"
            )

            # ================= SUMMARY =================

            st.subheader("📊 Picking Summary")

            if sort_mode == "🚚 เรียงตามขนส่ง -> แล้วเรียง SKU":

                summary_df = df.groupby(
                    ["courier", "zone", "sku"]
                )["qty"].sum().reset_index()

                summary_df.columns = [
                    "ขนส่ง",
                    "โซน",
                    "SKU",
                    "จำนวน"
                ]

                summary_df = summary_df.sort_values(
                    by=["ขนส่ง", "โซน", "SKU"]
                )

            elif sort_mode == "📦 เรียงตามโซน -> SKU":

                summary_df = df.groupby(
                    ["zone", "sku"]
                )["qty"].sum().reset_index()

                summary_df.columns = [
                    "โซน",
                    "SKU",
                    "จำนวน"
                ]

                summary_df = summary_df.sort_values(
                    by=["โซน", "SKU"]
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

            # HOT ITEMS
            if "จำนวน" in summary_df.columns:

                summary_df["🔥HOT"] = summary_df["จำนวน"].apply(
                    lambda x: "🔥" if x >= 10 else ""
                )

            # CSV
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

            display_df = df.copy()

            display_df["หน้าใหม่"] = display_df.index + 1

            display_df = display_df[
                [
                    "หน้าใหม่",
                    "courier",
                    "zone",
                    "sku",
                    "qty",
                    "order_id"
                ]
            ]

            display_df.columns = [
                "หน้า",
                "ขนส่ง",
                "โซน",
                "SKU",
                "จำนวน",
                "Order ID"
            ]

            search = st.text_input(
                "ค้นหา SKU / Order ID / ขนส่ง"
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

        except Exception as e:

            st.error(f"❌ เกิดข้อผิดพลาด : {e}")

# ================= RESET =================

st.markdown("---")

col1, col2 = st.columns([3, 1])

with col2:

    if st.button(
        "🔄 เริ่มรอบใหม่",
        use_container_width=True
    ):

        st.session_state.uploader_key += 1

        st.rerun()
