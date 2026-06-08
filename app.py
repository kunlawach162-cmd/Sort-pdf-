import streamlit as st
from pypdf import PdfReader, PdfWriter
import re
import io
import pandas as pd

# 1. ตั้งค่าหน้าเว็บให้คลีนและกว้างเต็มจอ
st.set_page_config(page_title="Sharp Bill Sorter", page_icon="📦", layout="wide")

# 2. ปรับแต่งดีไซน์ด้วย CSS ขยับรูปภาพการ์ตูนให้อยู่ตรงกลาง และปรับสไตล์ตาราง
st.markdown("""
    <style>
    html, body, [data-testid="stAppViewContainer"] {
        background-color: #ffffff;
        color: #1e293b;
    }
    
    /* จัดรูปภาพให้อยู่ตรงกลางจอ และทำมุมมนสวยงาม */
    [data-testid="stImage"] {
        display: flex;
        justify-content: center;
        margin: 0 auto;
    }
    [data-testid="stImage"] img {
        border-radius: 16px !important;
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.05);
    }
    
    /* ดีไซน์กล่องสถิติภาพรวม (Metrics) */
    div[data-testid="stMetric"] {
        background-color: #f8fafc;
        padding: 18px 24px;
        border-radius: 12px;
        border: 1px solid #e2e8f0;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
    }
    div[data-testid="stMetricLabel"] { font-size: 14px !important; color: #475569 !important; font-weight: 600 !important; }
    div[data-testid="stMetricValue"] { font-size: 26px !important; font-weight: bold !important; color: #0f172a !important; }
    
    /* ดีไซน์ปุ่มหลักสีเขียวสดเด่นสะดุดตา */
    div.stButton > button:first-child {
        background-color: #059669 !important;
        color: white !important;
        font-size: 16px !important;
        font-weight: bold !important;
        border-radius: 8px !important;
        border: none !important;
        padding: 0.75rem 2.5rem !important;
        box-shadow: 0 4px 6px -1px rgba(5, 150, 105, 0.2);
    }
    div.stButton > button:first-child:hover {
        background-color: #047857 !important;
    }
    
    @media (max-width: 768px) {
        .block-container { padding: 1rem 0.5rem !important; }
        div[data-testid="stMetric"] { margin-bottom: 10px !important; width: 100% !important; }
        div[data-testid="column"] { width: 100% !important; flex: 1 1 100% !important; }
    }
    </style>
""", unsafe_allow_html=True)

# --- ฟังก์ชันจัดการข้อมูลเบื้องหลัง (Core Logic) ---
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
    
    track_match = re.search(r'Track\s*No\s*:\s*([\w-]+)', text, re.IGNORECASE)
    if track_match: data['track_no'] = track_match.group(1).strip()
    
    if "Shopee" in text: data['source'] = "Shopee 🟠"
    elif "Lada" in text or "Lazada" in text: data['source'] = "Lazada 🔵"
    
    data['courier'] = detect_courier(data['track_no'], data['source'])
    
    zone_match = re.search(r'\b(G\d+)\b', text)
    if zone_match: data['zone'] = zone_match.group(1)
    
    sku_match = re.search(r'\b\d+-[A-Z]+-[A-Z]+-\d+\b', text)
    if sku_match: 
        data['sku'] = sku_match.group(0)
    else:
        for line in text.split('\n'):
            if "1-GDS-" in line:
                m = re.search(r'(1-GDS-[\w-]+)', line)
                if m: data['sku'] = m.group(1); break
                
    qty_match = re.search(r'รวมทั้งสิ้น\s*(\d+)', text)
    if qty_match: data['qty'] = int(qty_match.group(1))
    
    order_match = re.search(r'Order ID\s*:\s*([\w-]+)', text, re.IGNORECASE)
    if order_match: data['order_id'] = order_match.group(1)
    
    return data

# --- ฟังก์ชันประมวลผลรองรับหลายไฟล์พร้อมกัน ---
def process_multiple_pdfs(uploaded_files, sort_mode):
    all_pages_data = []
    writer = PdfWriter()
    global_page_index = 0
    
    # วนลูปอ่านทีละไฟล์เพื่อประหยัด RAM (เปิดเสร็จเคลียร์ทิ้งทันที)
    for file_index, uploaded_file in enumerate(uploaded_files):
        file_bytes = uploaded_file.read()
        reader = PdfReader(io.BytesIO(file_bytes))
        
        for page in reader.pages:
            text = page.extract_text() or ""
            page_info = extract_data_from_page(text)
            
            # เก็บข้อมูลตำแหน่งหน้าและตัวระบุไฟล์ไว้เชื่อมโยงตอนมัดรวมไฟล์
            page_info['file_index'] = file_index
            page_info['reader_page_ref'] = page
            all_pages_data.append(page_info)
            
    # จัดเรียงข้อมูลทั้งหมดตามโหมดที่เลือก
    if sort_mode == "🚚 เรียงตามขนส่ง -> แล้วเรียงรหัสสินค้า (ITEM CODE)":
        all_pages_data.sort(key=lambda x: (x['courier'], x['sku']))
    elif sort_mode == "🔤 เรียงตามรหัสสินค้าอย่างเดียว (ITEM CODE)":
        all_pages_data.sort(key=lambda x: x['sku'])
    elif sort_mode == "📍 เรียงตามโซนคลังสินค้า (PICK-CODE -> รหัสสินค้า)":
        all_pages_data.sort(key=lambda x: (x['zone'], x['sku']))
        
    # สร้างไฟล์ PDF มัดรวมเล่มใหม่
    for page_info in all_pages_data:
        writer.add_page(page_info['reader_page_ref'])
        
    output_pdf = io.BytesIO()
    writer.write(output_pdf)
    output_pdf.seek(0)
    
    return output_pdf, all_pages_data

# --- ส่วนแสดงผลหน้าเว็บ (UI Layout) ---

# 🖼️ เปลี่ยนเป็นรูปการ์ตูนคลังสินค้า 3D สีสันสดใส ลิงก์ตรงจากเว็บบล็อกภาพกราฟิกคลีนๆ
st.image("https://img.freepik.com/free-vector/isometric-warehouse-horizontal-illustration_1284-57223.jpg", width=380)

st.title("🏢 Sharp Bill Sorter")
st.caption("ระบบจัดการบิลใบจัดสินค้าและสรุปยอดหยิบรวมอัจฉริยะ (เวอร์ชันการ์ตูนคลีน & รองรับไฟล์ใหญ่)")
st.markdown("---")

st.subheader("⚙️ ขั้นตอนที่ 1: เลือกโหมดการคัดแยกเอกสาร")
sort_mode = st.radio(
    "ระบบจะเรียงบิลตามเงื่อนไขที่คุณเลือกทันที:",
    [
        "🚚 เรียงตามขนส่ง -> แล้วเรียงรหัสสินค้า (ITEM CODE)",
        "🔤 เรียงตามรหัสสินค้าอย่างเดียว (ITEM CODE)",
        "📍 เรียงตามโซนคลังสินค้า (PICK-CODE -> รหัสสินค้า)"
    ],
    index=0,
    horizontal=True
)

st.markdown("---")

st.subheader("📂 ขั้นตอนที่ 2: อัปโหลดไฟล์บิลใบจัดสินค้า (PDF)")
# เปลี่ยนเป็น accept_multiple_files=True เพื่อให้ลากวางหลายไฟล์พร้อมกันได้ปลดล็อกหมื่นหน้า
uploaded_files = st.file_uploader(
    "ลากไฟล์ PDF มาวางตรงนี้ (เลือกอัปโหลดพร้อมกันได้ทีละหลายไฟล์)", 
    type=["pdf"], 
    accept_multiple_files=True
)

if uploaded_files:
    st.info(f"🗂️ ตรวจพบไฟล์ทั้งหมด: {len(uploaded_files)} ไฟล์ พร้อมทำการรวมและจัดเรียงข้อมูล")
    
    if st.button("⚡ เริ่มประมวลผลข้อมูลและจัดบิลใหม่", use_container_width=True):
        with st.spinner("⏳ ระบบกำลังผสานไฟล์และคัดแยกยอดหยิบรวม... กรุณารอสักครู่"):
            try:
                sorted_pdf, details = process_multiple_pdfs(uploaded_files, sort_mode)
                st.balloons()
                
                df = pd.DataFrame(details)
                st.success("🎉 ทำรายการสำเร็จ! ระบบทำการรวมไฟล์และจัดเรียงบิลเรียบร้อยแล้ว")
                
                st.download_button(
                    label="📥 ดาวน์โหลดไฟล์บิล PDF ที่มัดรวมและจัดเรียงใหม่ทั้งหมด",
                    data=sorted_pdf,
                    file_name="sharp_sorted_bills.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )
                
                st.markdown("---")
                
                # แดชบอร์ดสรุปยอดรวมของทุกไฟล์
                st.subheader("📊 ขั้นตอนที่ 3: ยอดสรุปการหยิบสินค้าทั้งหมด (จากทุกไฟล์รวมกัน)")
                shopee_count = len(df[df['source'] == "Shopee 🟠"])
                laz_count = len(df[df['source'] == "Lazada 🔵"])
                
                col1, col2, col3 = st.columns(3)
                with col1: st.metric("📋 ใบออเดอร์รวมทั้งหมด", f"{len(df)} บิล")
                with col2: st.metric("🧺 ยอดสินค้าที่ต้องเดินหยิบ", f"{df['qty'].sum()} ชิ้น")
                with col3: st.metric("🚚 แยกช่องทาง Shopee/Lazada", f"Shopee: {shopee_count} | Lazada: {laz_count}")
                
                st.markdown("##")
                
                # ตารางใบสรุปยอดหยิบรวม (Picking Summary)
                st.write("**📝 ตารางใบสรุปยอดหยิบสินค้ารวมประจำรอบ (Picking List)**")
                if sort_mode == "🚚 เรียงตามขนส่ง -> แล้วเรียงรหัสสินค้า (ITEM CODE)":
                    summary_df = df.groupby(['courier', 'sku'])['qty'].sum().reset_index()
                    summary_df.columns = ['บริษัทขนส่ง', 'รหัสสินค้า (ITEM CODE)', 'จำนวนที่ต้องหยิบ (ชิ้น)']
                    summary_df = summary_df.sort_values(by=['บริษัทขนส่ง', 'รหัสสินค้า (ITEM CODE)'])
                elif sort_mode == "📍 เรียงตามโซนคลังสินค้า (PICK-CODE -> รหัสสินค้า)":
                    summary_df = df.groupby(['zone', 'sku'])['qty'].sum().reset_index()
                    summary_df.columns = ['โซน (PICK-CODE)', 'รหัสสินค้า (ITEM CODE)', 'จำนวนที่ต้องหยิบ (ชิ้น)']
                    summary_df = summary_df.sort_values(by=['โซน (PICK-CODE)', 'รหัสสินค้า (ITEM CODE)'])
                else:
                    summary_df = df.groupby('sku')['qty'].sum().reset_index()
                    summary_df.columns = ['รหัสสินค้า (ITEM CODE)', 'จำนวนที่ต้องหยิบ (ชิ้น)']
                    summary_df = summary_df.sort_values(by='รหัสสินค้า (ITEM CODE)')
                    
                st.dataframe(summary_df, use_container_width=True, hide_index=True)
                
                st.markdown("---")
                
                # ช่องค้นหาตำแหน่งหน้าบิลใหม่
                st.write("**🔍 ช่องค้นหาออเดอร์ด่วนและตรวจสอบตำแหน่งหน้าบิล**")
                display_df = df.copy()
                display_df['หน้าใหม่'] = display_df.index + 1
                display_df = display_df[['หน้าใหม่', 'courier', 'zone', 'sku', 'qty', 'order_id']]
                display_df.columns = ['บิลใบที่ (หน้าใหม่ในเล่มรวม)', 'บริษัทขนส่ง', 'โซนคลัง', 'รหัสสินค้า', 'จำนวน', 'Order ID']
                
                search_query = st.text_input("พิมพ์รหัสสินค้า, ชื่อขนส่ง หรือ Order ID เพื่อส่องตำแหน่งหน้าบิลในเล่มรวมทันที:")
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
                st.error(f"เกิดข้อผิดพลาดในการประมวลผลระบบ: {e}")
