import streamlit as st
import pdfplumber
from pypdf import PdfReader, PdfWriter
import re
import io
import pandas as pd

# 1. ตั้งค่าหน้าเว็บให้คลีนและกว้างเต็มจอ (สไตล์แดชบอร์ดสากล)
st.set_page_config(page_title="Sharp Bill Sorter", page_icon="📦", layout="wide")

# 2. ปรับแต่งดีไซน์ด้วย CSS ขั้นสูง เพื่อหน้าตาที่สวยงามและใช้งานง่ายที่สุด
st.markdown("""
    <style>
    /* ตั้งค่าฟอนต์และพื้นหลังสีคลีน */
    html, body, [data-testid="stAppViewContainer"] {
        background-color: #ffffff;
        color: #1e293b;
    }
    
    /* ดีไซน์กล่องสถิติภาพรวม (Metrics) ให้เด่นชัด */
    div[data-testid="stMetric"] {
        background-color: #f8fafc;
        padding: 18px 24px;
        border-radius: 12px;
        border: 1px solid #e2e8f0;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
    }
    div[data-testid="stMetricLabel"] { font-size: 14px !important; color: #475569 !important; font-weight: 600 !important; }
    div[data-testid="stMetricValue"] { font-size: 26px !important; font-weight: bold !important; color: #0f172a !important; }
    
    /* ดีไซน์ปุ่มหลัก (ดาวน์โหลด/เริ่มคำนวณ) ให้สีเขียวสดเด่นสะดุดตา */
    div.stButton > button:first-child {
        background-color: #059669 !important;
        color: white !important;
        font-size: 16px !important;
        font-weight: bold !important;
        border-radius: 8px !important;
        border: none !important;
        padding: 0.75rem 2.5rem !important;
        box-shadow: 0 4px 6px -1px rgba(5, 150, 105, 0.2);
        transition: all 0.2s;
    }
    div.stButton > button:first-child:hover {
        background-color: #047857 !important;
        transform: translateY(-1px);
    }
    
    /* สำหรับปรับจอมือถืออัตโนมัติ */
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
    elif t.startswith("TH"): return "SPX Express 🟠"
    elif t.startswith("KERRY") or t.startswith("SHP"): return "Kerry / Flash 🟡"
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
    if sku_match: data['sku'] = sku_match.group(0)
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

def process_pdf_pro(uploaded_file, sort_mode):
    pages_data = []
    file_bytes = uploaded_file.read()
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for index, page in enumerate(pdf.pages):
            text = page.extract_text()
            page_info = extract_data_from_page(text)
            page_info['page_index'] = index
            pages_data.append(page_info)
    if sort_mode == "🚚 เรียงตามขนส่ง -> แล้วเรียงรหัสสินค้า (ITEM CODE)":
        pages_data.sort(key=lambda x: (x['courier'], x['sku']))
    elif sort_mode == "🔤 เรียงตามรหัสสินค้าอย่างเดียว (ITEM CODE)":
        pages_data.sort(key=lambda x: x['sku'])
    elif sort_mode == "📍 เรียงตามโซนคลังสินค้า (PICK-CODE -> รหัสสินค้า)":
        pages_data.sort(key=lambda x: (x['zone'], x['sku']))
    reader = PdfReader(io.BytesIO(file_bytes))
    writer = PdfWriter()
    for page_info in pages_data: writer.add_page(reader.pages[page_info['page_index']])
    output_pdf = io.BytesIO()
    writer.write(output_pdf)
    output_pdf.seek(0)
    return output_pdf, pages_data

# --- ส่วนจัดวางโครงสร้างเว็บ (UI Layout) ---

# 🖼️ [ส่วนติดตั้งรูปภาพ/โลโก้] 
# คุณสามารถเปลี่ยนลิงก์ภาพด้านล่างเป็นโลโก้ของคลังสินค้าตัวเองได้เลยครับ
st.image("https://images.unsplash.com/photo-1586528116311-ad8dd3c8310d?q=80&w=600&auto=format&fit=crop", width=250)

st.title("🏢 Sharp Bill Sorter")
st.caption("ระบบจัดการใบจัดสินค้าและสรุปยอดหยิบรวมอัจฉริยะ (Ultimate Edition)")
st.markdown("---")

# การจัดลำดับขั้นตอนการใช้งานให้พนักงานหน้างานเข้าใจง่าย
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
uploaded_file = st.file_uploader("ลากไฟล์ PDF มาวางตรงนี้ หรือคลิกเพื่อเปิดกล่องเลือกไฟล์", type=["pdf"])

if uploaded_file is not None:
    st.info(f"🗂️ ตรวจพบไฟล์เรียบร้อย: {uploaded_file.name}")
    
    if st.button("⚡ เริ่มประมวลผลข้อมูลและจัดบิลใหม่", use_container_width=True):
        with st.spinner("⏳ กำลังอ่านเนื้อหาบิลและวิเคราะห์ข้อมูลคลังสินค้า..."):
            try:
                sorted_pdf, details = process_pdf_pro(uploaded_file, sort_mode)
                st.balloons()
                
                df = pd.DataFrame(details)
                st.success("🎉 ระบบได้จัดระเบียบบิลตามเงื่อนไขของคุณเสร็จสิ้น!")
                
                # ปุ่มดาวน์โหลดเวอร์ชันโดดเด่นสะดุดตาพนักงาน
                st.download_button(
                    label="📥 ดาวน์โหลดไฟล์บิล PDF ที่จัดเรียงใหม่ (พิมพ์ออกมาแพ็กของได้เลย)",
                    data=sorted_pdf,
                    file_name=f"sorted_{uploaded_file.name}",
                    mime="application/pdf",
                    use_container_width=True
                )
                
                st.markdown("---")
                
                # ================= ส่วนกล่องแดชบอร์ดสรุปผลยอดหยิบ =================
                st.subheader("📊 ขั้นตอนที่ 3: สรุปยอดรวมสำหรับเดินหยิบสินค้า")
                shopee_count = len(df[df['source'] == "Shopee 🟠"])
                laz_count = len(df[df['source'] == "Lazada 🔵"])
                
                col1, col2, col3 = st.columns(3)
                with col1: st.metric("📋 ใบออเดอร์ทั้งหมดในรอบนี้", f"{len(df)} บิล")
                with col2: st.metric("🧺 สินค้ารวมที่ต้องหยิบทวน", f"{df['qty'].sum()} ชิ้น")
                with col3: st.metric("🚚 ยอดแยกตามค่าย", f"Shopee: {shopee_count} | Lazada: {laz_count}")
                
                st.markdown("##")
                
                # ================= ตารางใบบิลรวมสินค้า (Picking Summary) =================
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
                
                # ================= ตารางเช็กตำแหน่งหน้าพร้อมกล่องเซิร์ชหาข้อมูล =================
                st.write("**🔍 ช่องค้นหาออเดอร์ด่วนและตรวจสอบตำแหน่งหน้าบิล**")
                display_df = df.copy()
                display_df['หน้าใหม่'] = display_df.index + 1
                display_df['หน้าเดิม'] = display_df['page_index'] + 1
                display_df = display_df[['หน้าใหม่', 'courier', 'zone', 'sku', 'qty', 'order_id', 'หน้าเดิม']]
                display_df.columns = ['บิลใบที่ (หน้าใหม่)', 'บริษัทขนส่ง', 'โซนคลัง', 'รหัสสินค้า', 'จำนวน', 'Order ID', 'หน้าเดิมในไฟล์เก่า']
                
                search_query = st.text_input("พิมพ์รหัสสินค้า, ชื่อขนส่ง หรือ Order ID เพื่อส่องตำแหน่งหน้าบิลทันที:")
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
