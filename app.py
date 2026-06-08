import streamlit as st
from pypdf import PdfReader, PdfWriter
import re
import io
import pandas as pd

# 1. ตั้งค่าหน้าเว็บให้คลีนและกว้างเต็มจอ
st.set_page_config(page_title="Sharp Bill Sorter", page_icon="📦", layout="wide")

# ================= 🚀 ระบบจัดการ Session State =================
if "uploader_key" not in st.session_state:
    st.session_state.uploader_key = 0

# ================= 🎨 CSS ปรับแต่งดีไซน์ =================
st.markdown("""
    <style>
    html, body, [data-testid="stAppViewContainer"] {
        background-color: #faf9f6 !important;
        color: #1e293b;
    }
    div[data-testid="stMetric"] {
        background-color: #ffffff;
        padding: 16px 20px;
        border-radius: 12px;
        border: 1px solid #e5dec9;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.02);
    }
    div[data-testid="stMetricLabel"] { font-size: 13px !important; color: #64748b !important; font-weight: bold !important; }
    div[data-testid="stMetricValue"] { font-size: 24px !important; font-weight: bold !important; color: #1e293b !important; }
    
    /* บังคับปุ่ม Primary ให้เป็นสีเขียวสดใส */
    button[kind="primary"] {
        background-color: #10b981 !important;
        border-color: #10b981 !important;
        color: white !important;
        font-size: 16px !important;
        font-weight: bold !important;
        border-radius: 8px !important;
        padding: 0.75rem 2.5rem !important;
        box-shadow: 0 4px 10px rgba(16, 185, 129, 0.2);
    }
    button[kind="primary"]:hover {
        background-color: #059669 !important;
        border-color: #059669 !important;
    }
    
    div[data-testid="stFileUploader"] {
        background-color: #ffffff;
        border: 2px dashed #e5dec9;
        border-radius: 12px;
        padding: 20px;
    }
    @media (max-width: 768px) {
        .block-container { padding: 1rem 0.5rem !important; }
        div[data-testid="stMetric"] { margin-bottom: 8px !important; width: 100% !important; }
        div[data-testid="column"] { width: 100% !important; flex: 1 1 100% !important; }
    }
    </style>
""", unsafe_allow_html=True)

# --- ฟังก์ชันหลักดึงและคัดแยกข้อมูลบิล ---
def detect_courier(track_no, source):
    if not track_no or track_no == "Unknown": return source
    t = track_no.upper()
    if t.startswith("LEX"): return "Lazada Express (LEX) 🔵"
    elif t.startswith("TH") or t.startswith("SPX"): return "SPX Express 🟠"
    elif t.startswith("KER") or t.startswith("SHP") or t.startswith("FLA"): return "Kerry / Flash 🟡"
    return f"ขนส่งอื่นๆ ({source.split()[0]}) 🚚"

def extract_data_from_page(text):
    data = {'zone': 'Unknown', 'sku': 'ZZZZZZ', 'qty': 1, 'source': 'Unknown', 'track_no': 'Unknown', 'courier': 'Unknown', 'order_id': 'Unknown'}
    if not text: return data
    
    # 🌟 [อัปเกรด] แปลงข้อความทั้งหมดในหน้าให้เป็นบรรทัดเดียว (ลบการเว้นบรรทัดออก) 
    # เพื่อแก้ปัญหาคำว่า "รวมทั้งสิ้น" อยู่คนละบรรทัดกับตัวเลข
    clean_text = re.sub(r'\s+', ' ', text)
    
    # 1. ดึง Track No
    track_match = re.search(r'Track\s*No\s*:\s*([\w-]+)', clean_text, re.IGNORECASE)
    if track_match: data['track_no'] = track_match.group(1).strip()
    
    # 2. ดึง Platform
    if "Shopee" in clean_text: data['source'] = "Shopee 🟠"
    elif "Lada" in clean_text or "Lazada" in clean_text: data['source'] = "Lazada 🔵"
    
    data['courier'] = detect_courier(data['track_no'], data['source'])
    
    # 3. ดึง Zone (หาตัวแรกที่เจอ)
    zone_matches = re.findall(r'\b(G\d+)\b', clean_text)
    if zone_matches: data['zone'] = zone_matches[0]
    
    # 4. ดึง Order ID
    order_match = re.search(r'Order ID\s*:\s*([\w-]+)', clean_text, re.IGNORECASE)
    if order_match: data['order_id'] = order_match.group(1)

    # 🌟 5. ดึง SKU (ดักจับกรณี 1 ใบมีหลายรหัสสินค้า)
    # ค้นหาทุกรหัสในหน้านั้น แล้วเลือกเอาเฉพาะ "ตัวแรกสุด [0]" ตามที่กำหนด
    sku_matches = re.findall(r'(1-GDS-[\w-]+)', clean_text)
    if sku_matches:
        data['sku'] = sku_matches[0]
    else:
        sku_alt_matches = re.findall(r'\b\d+-[A-Z]+-[A-Z]+-\d+\b', clean_text)
        if sku_alt_matches:
            data['sku'] = sku_alt_matches[0]

    # 🌟 6. ดึงยอดชิ้นจากคำว่า "รวมทั้งสิ้น" เป็นหลัก
    qty_match = re.search(r'รวมทั้งสิ้น\s*(\d+)', clean_text)
    if qty_match:
        data['qty'] = int(qty_match.group(1))
    else:
        # คำค้นหาสำรอง เผื่อบางใบไม่มีคำว่ารวมทั้งสิ้น
        qty_fallback = re.search(r'(?:จำนวน|Qty|Quantity)\s*[:=]?\s*(\d+)', clean_text, re.IGNORECASE)
        if qty_fallback:
            data['qty'] = int(qty_fallback.group(1))

    return data

def process_multiple_pdfs(uploaded_files, sort_mode):
    all_pages_data = []
    writer = PdfWriter()
    
    for file_index, uploaded_file in enumerate(uploaded_files):
        file_bytes = uploaded_file.read()
        reader = PdfReader(io.BytesIO(file_bytes))
        
        for page in reader.pages:
            text = page.extract_text() or ""
            page_info = extract_data_from_page(text)
            page_info['file_index'] = file_index
            page_info['reader_page_ref'] = page
            all_pages_data.append(page_info)
            
    if sort_mode == "🚚 เรียงตามขนส่ง -> แล้วเรียงรหัสสินค้า (ITEM CODE)":
        all_pages_data.sort(key=lambda x: (x['courier'], x['sku']))
    else:
        all_pages_data.sort(key=lambda x: x['sku'])
        
    for page_info in all_pages_data:
        writer.add_page(page_info['reader_page_ref'])
        
    output_pdf = io.BytesIO()
    writer.write(output_pdf)
    output_pdf.seek(0)
    
    return output_pdf, all_pages_data

# ================= 🚀 หน้าการแสดงผลเว็บไซต์ =================

st.markdown("<br>", unsafe_allow_html=True) 

col_left, col_right = st.columns([2, 1])

with col_left:
    st.markdown("<h1 style='font-size: 3.5rem; font-weight: 900; margin-bottom: 5px; color: #1a1a1a;'>Sharp Bill Sorter</h1>", unsafe_allow_html=True)
    st.markdown("<p style='font-size: 1.1rem; color: #4a4a4a;'>ระบบจัดเรียงบิลใบจัดสินค้าและผสานไฟล์อัจฉริยะ เลือกโหมดการคัดจัดเรียงบิลหน้างานได้ตามต้องการ</p>", unsafe_allow_html=True)

with col_right:
    try:
        st.image("logo.jpg", use_container_width=True)
    except:
        try:
            st.image("stock-availability-restocking-2d-vector-600nw-2682190953.jpg", use_container_width=True)
        except:
            st.image("https://img.freepik.com/free-vector/isometric-warehouse-horizontal-illustration_1284-57223.jpg", use_container_width=True)

st.markdown("---")

st.subheader("⚙️ ขั้นตอนที่ 1: เลือกโหมดการคัดแยกเอกสาร")
sort_mode = st.radio(
    "ระบบจะเรียงบิลตามเงื่อนไขที่คุณเลือกทันที:",
    [
        "🚚 เรียงตามขนส่ง -> แล้วเรียงรหัสสินค้า (ITEM CODE)",
        "🔤 เรียงตามรหัสสินค้าอย่างเดียว (ITEM CODE)"
    ],
    index=0,
    horizontal=True
)

st.markdown("---")

st.subheader("📂 ขั้นตอนที่ 2: อัปโหลดไฟล์บิลใบจัดสินค้า (PDF)")
uploaded_files = st.file_uploader(
    "ลากไฟล์ PDF มาวางตรงนี้ (สามารถลากวางพร้อมกันหลายๆ ไฟล์เพื่อรวมยอดรอบเดียวกันได้)", 
    type=["pdf"], 
    accept_multiple_files=True,
    key=f"uploader_{st.session_state.uploader_key}"
)

if uploaded_files:
    st.info(f"🗂️ ตรวจพบไฟล์ใบงานทั้งหมด: {len(uploaded_files)} ไฟล์ พร้อมสำหรับจัดเรียงข้อมูล")
    
    if st.button("⚡ เริ่มจัดบิลและสรุปยอดรวม", type="primary", use_container_width=True):
        with st.spinner("⏳ ระบบกำลังผสานไฟล์ คัดแยกประเภทขนส่ง และสรุปยอดหยิบรวม... กรุณารอสักครู่"):
            try:
                sorted_pdf, details = process_multiple_pdfs(uploaded_files, sort_mode)
                st.balloons()
                
                df = pd.DataFrame(details)
                st.success("🎉 ทำรายการสำเร็จเรียบร้อย! เตรียมไฟล์ดาวน์โหลดพร้อมแล้ว")
                
                st.download_button(
                    label="📥 1. ดาวน์โหลดไฟล์บิล PDF ที่มัดรวมและจัดเรียงใหม่ทั้งหมด (สำหรับปรินต์)",
                    data=sorted_pdf,
                    file_name="sharp_sorted_bills.pdf",
                    mime="application/pdf",
                    type="primary",
                    use_container_width=True
                )
                
                st.markdown("---")
                
                st.subheader("📊 ขั้นตอนที่ 3: สรุปยอดรวมสินค้าจากทุกไฟล์")
                shopee_count = len(df[df['source'] == "Shopee 🟠"])
                laz_count = len(df[df['source'] == "Lazada 🔵"])
                total_qty = df['qty'].sum()
                
                col1, col2, col3 = st.columns(3)
                with col1: st.metric("📋 ใบออเดอร์รวม", f"{len(df)} บิล")
                with col2: st.metric("🧺 ยอดสินค้าที่ต้องเดินหยิบ", f"{total_qty} ชิ้น")
                with col3: st.metric("🚚 แยกค่ายยอดออเดอร์", f"Shopee: {shopee_count} | Lazada: {laz_count}")
                
                st.markdown("##")
                
                st.write("**📝 ใบสรุปยอดสินค้าที่ต้องหยิบประจำรอบ (Picking List)**")
                if sort_mode == "🚚 เรียงตามขนส่ง -> แล้วเรียงรหัสสินค้า (ITEM CODE)":
                    summary_df = df.groupby(['courier', 'sku'])['qty'].sum().reset_index()
                    summary_df.columns = ['บริษัทขนส่ง', 'รหัสสินค้า (ITEM CODE)', 'จำนวน (ชิ้น)']
                else:
                    summary_df = df.groupby('sku')['qty'].sum().reset_index()
                    summary_df.columns = ['รหัสสินค้า (ITEM CODE)', 'จำนวน (ชิ้น)']
                    summary_df = summary_df.sort_values(by='รหัสสินค้า (ITEM CODE)')
                
                csv_data = summary_df.to_csv(index=False).encode('utf-8-sig')
                st.download_button(
                    label="📊 2. ดาวน์โหลดใบสรุปยอดหยิบเป็นไฟล์ Excel (CSV)",
                    data=csv_data,
                    file_name="picking_list_summary.csv",
                    mime="text/csv",
                    use_container_width=True
                )
                    
                st.dataframe(summary_df, use_container_width=True, hide_index=True)
                
                st.markdown("---")
                
                st.write("**🔍 ค้นหาออเดอร์ด่วนและตรวจสอบหน้าเอกสาร**")
                display_df = df.copy()
                display_df['หน้าใหม่'] = display_df.index + 1
                display_df = display_df[['หน้าใหม่', 'courier', 'zone', 'sku', 'qty', 'order_id']]
                display_df.columns = ['บิลใบที่ (หน้าใหม่)', 'บริษัทขนส่ง', 'โซนคลัง', 'รหัสสินค้า', 'จำนวนชิ้น', 'Order ID']
                
                search_query = st.text_input("พิมพ์รหัสสินค้า, ชื่อขนส่ง หรือ Order ID เพื่อส่องตำแหน่งหน้าทันที:")
                if search_query:
                    filtered_df = display_df[
                        display_df['รหัสสินค้า'].str.contains(search_query, case=False, na=False) |
                        display_df['บริษัทขนส่ง'].str.contains(search_query, case=False, na=False) |
                        display_df['Order ID'].str.contains(search_query, case=False, na=False)
                    ]
                    st.dataframe(filtered_df, use_container_width=True, hide_index=True)
                else:
                    st.dataframe(display_df, use_container_width=True, hide_index=True)
                    
            except Exception as e:
                st.error(f"เกิดข้อผิดพลาดในการคำนวณข้อมูล: {e}")

st.markdown("---")
col_space, col_reset = st.columns([2, 1])
with col_reset:
    if st.button("🔄 เคลียร์ข้อมูล / เริ่มจัดบิลรอบใหม่", use_container_width=True):
        st.session_state.uploader_key += 1
        st.rerun()
