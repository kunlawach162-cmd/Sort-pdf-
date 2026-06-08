import streamlit as st
import pdfplumber
from pypdf import PdfReader, PdfWriter
import re
import io
import pandas as pd

# ตั้งค่าหน้าตาของเว็บ (เริ่มแรกให้เป็นแบบยืดหยุ่นกว้าง)
st.set_page_config(page_title="Smart Picking PRO", page_icon="📦", layout="wide")

# ================= 🆕 ส่วนบนสุด: เลือกอุปกรณ์ที่กำลังใช้งาน =================
st.sidebar.subheader("📱⚙️ ตั้งค่าขนาดหน้าจอ")
device_mode = st.sidebar.radio(
    "คุณกำลังเปิดใช้งานผ่านอุปกรณ์อะไร?",
    ["คอมพิวเตอร์ (PC / Laptop) 💻", "โทรศัพท์มือถือ (Mobile) 📱"],
    index=0
)

# ปรับสไตล์ CSS ตามอุปกรณ์ที่เลือก
if device_mode == "โทรศัพท์มือถือ (Mobile) 📱":
    st.markdown("""
        <style>
        .block-container { padding-top: 1rem; padding-bottom: 1rem; max-width: 100% !important; }
        div[data-testid="stMetric"] {
            background-color: #1e293b;
            padding: 10px 14px;
            border-radius: 10px;
            margin-bottom: 6px;
            border-left: 5px solid #3b82f6;
        }
        div[data-testid="stMetricLabel"] { font-size: 13px !important; color: #94a3b8 !important; }
        div[data-testid="stMetricValue"] { font-size: 20px !important; font-weight: bold !important; color: #f8fafc !important; }
        </style>
    """, unsafe_context=True)
else:
    st.markdown("""
        <style>
        div[data-testid="stMetric"] {
            background-color: #0f172a;
            padding: 20px;
            border-radius: 12px;
            border-top: 4px solid #3b82f6;
        }
        </style>
    """, unsafe_context=True)

# --- ฟังก์ชันแกะข้อมูลจาก PDF ---
def extract_data_from_page(text):
    data = {
        'zone': 'Unknown',
        'sku': 'ZZZZZZ',
        'qty': 1,
        'source': 'Unknown',
        'track_no': 'Unknown',
        'order_id': 'Unknown'
    }
    if not text:
        return data
        
    # 1. หา PICK-CODE / โซน
    zone_match = re.search(r'\b(G\d+)\b', text)
    if zone_match:
        data['zone'] = zone_match.group(1)
    else:
        for line in text.split('\n'):
            if line.strip().startswith('G0'):
                data['zone'] = line.strip().split()[0]
                break
        
    # 2. หา ITEM CODE
    sku_match = re.search(r'\b\d+-[A-Z]+-[A-Z]+-\d+\b', text)
    if sku_match:
        data['sku'] = sku_match.group(0)
    else:
        for line in text.split('\n'):
            if "1-GDS-" in line:
                m = re.search(r'(1-GDS-[\w-]+)', line)
                if m:
                    data['sku'] = m.group(1)
                    break

    # 3. หาจำนวน QTY
    qty_match = re.search(r'รวมทั้งสิ้น\s*(\d+)', text)
    if qty_match:
        data['qty'] = int(qty_match.group(1))

    # 4. หา Source (Shopee / Lazada)
    if "Shopee" in text:
        data['source'] = "Shopee 🟠"
    elif "Lada" in text or "Lazada" in text:
        data['source'] = "Lazada 🔵"

    # 5. หา Order ID
    order_match = re.search(r'Order ID\s*:\s*([\w-]+)', text, re.IGNORECASE)
    if order_match:
        data['order_id'] = order_match.group(1)

    return data

# --- ฟังก์ชันประมวลผลหลัก ---
def process_pdf_pro(uploaded_file, sort_mode):
    pages_data = []
    with pdfplumber.open(uploaded_file) as pdf:
        for index, page in enumerate(pdf.pages):
            text = page.extract_text()
            page_info = extract_data_from_page(text)
            page_info['page_index'] = index
            pages_data.append(page_info)
            
    if sort_mode == "🔤 เรียงตามรหัสสินค้า (ITEM CODE)":
        pages_data.sort(key=lambda x: x['sku'])
    elif sort_mode == "📍 เรียงตามโซนคลังสินค้า (PICK-CODE -> รหัสสินค้า)":
        pages_data.sort(key=lambda x: (x['zone'], x['sku']))
    
    reader = PdfReader(uploaded_file)
    writer = PdfWriter()
    for page_info in pages_data:
        writer.add_page(reader.pages[page_info['page_index']])
        
    output_pdf = io.BytesIO()
    writer.write(output_pdf)
    output_pdf.seek(0)
    
    return output_pdf, pages_data

# --- ส่วนแสดงผลหน้าเว็บ (UI) ---
st.title("📦 Smart Picking PRO")
st.caption("ระบบจัดเรียงบิลอัจฉริยะ รองรับการแสดงผลทั้งบน PC และ มือถือ")
st.markdown("---")

# เลือกโหมดการเรียงลำดับ
st.subheader("⚙️ เลือกรูปแบบการเรียงลำดับเอกสาร")
sort_mode = st.radio(
    "ต้องการให้ระบบเรียงลำดับหน้าบิลตามอะไร?",
    [
        "🔤 เรียงตามรหัสสินค้า (ITEM CODE)",
        "📍 เรียงตามโซนคลังสินค้า (PICK-CODE -> รหัสสินค้า)"
    ],
    index=0
)

st.markdown("---")

uploaded_file = st.file_uploader("📂 เลือกไฟล์ PDF ใบจัดสินค้า", type=["pdf"])

if uploaded_file is not None:
    st.info(f"🗂️ ไฟล์: {uploaded_file.name}")
    
    if st.button("⚡ เริ่มจัดเรียงและสรุปยอดหยิบ", type="primary", use_container_width=True):
        with st.spinner("⏳ กำลังคำนวณข้อมูล..."):
            try:
                sorted_pdf, details = process_pdf_pro(uploaded_file, sort_mode)
                st.balloons()
                
                df = pd.DataFrame(details)
                st.success("🎉 จัดเรียงสำเร็จ!")
                
                # ปุ่มดาวน์โหลด
                st.download_button(
                    label="📥 ดาวน์โหลด PDF ที่จัดเรียงใหม่แล้ว",
                    data=sorted_pdf,
                    file_name=f"sorted_{uploaded_file.name}",
                    mime="application/pdf",
                    use_container_width=True
                )
                
                st.markdown("---")
                
                # ================= ส่วนแดชบอร์ดสรุปงานคลัง (ปรับตามประเภทอุปกรณ์) =================
                st.subheader("📊 สรุปภาพรวม")
                shopee_count = len(df[df['source'] == "Shopee 🟠"])
                laz_count = len(df[df['source'] == "Lazada 🔵"])
                
                if device_mode == "โทรศัพท์มือถือ (Mobile) 📱":
                    # แสดงผลแนวตั้งสำหรับมือถือ ไม่ให้ตกขอบ
                    st.metric("📋 จำนวนใบงานทั้งหมด", f"{len(df)} ใบ")
                    st.metric("🧺 สินค้าที่ต้องหยิบรวม", f"{df['qty'].sum()} ชิ้น")
                    st.metric("🚚 แยกค่ายออเดอร์", f"Shopee: {shopee_count} | Lazada: {laz_count}")
                else:
                    # แสดงผลแนวนอน 3 คอลัมน์สวยๆ เต็มจอสำหรับ PC
                    col1, col2, col3 = st.columns(3)
                    with col1: st.metric("📋 จำนวนใบงานทั้งหมด", f"{len(df)} ใบ")
                    with col2: st.metric("🧺 สินค้าที่ต้องหยิบรวม", f"{df['qty'].sum()} ชิ้น")
                    with col3: st.metric("🚚 แยกค่ายออเดอร์", f"Shopee: {shopee_count} | Lazada: {laz_count}")
                
                st.markdown("---")
                
                # ================= ส่วนใบบิลรวมสินค้า (Picking Summary) =================
                st.subheader("📝 ยอดหยิบรวมสินค้า")
                
                summary_df = df.groupby(['zone', 'sku'])['qty'].sum().reset_index()
                summary_df.columns = ['โซน (PICK-CODE)', 'รหัสสินค้า (ITEM CODE)', 'จำนวน (ชิ้น)']
                
                if sort_mode == "🔤 เรียงตามรหัสสินค้า (ITEM CODE)":
                    summary_df = summary_df.sort_values(by='รหัสสินค้า (ITEM CODE)')
                else:
                    summary_df = summary_df.sort_values(by=['โซน (PICK-CODE)', 'รหัสสินค้า (ITEM CODE)'])
                    
                st.dataframe(summary_df, use_container_width=True, hide_index=True)
                
                st.markdown("---")
                
                # ================= ส่วนค้นหาออเดอร์ =================
                st.subheader("🔍 ตรวจสอบตำแหน่งหน้าบิล")
                
                display_df = df.copy()
                display_df['หน้าใหม่'] = display_df.index + 1
                display_df['หน้าเดิม'] = display_df['page_index'] + 1
                display_df = display_df[['หน้าใหม่', 'zone', 'sku', 'qty', 'order_id', 'หน้าเดิม']]
                display_df.columns = ['บิลใบที่', 'โซน', 'รหัสสินค้า', 'จำนวน', 'Order ID', 'หน้าเดิมในไฟล์เก่า']
                
                search_query = st.text_input("พิมพ์รหัสสินค้า, โซน หรือ Order ID เพื่อค้นหาหน้า:")
                if search_query:
                    filtered_df = display_df[
                        display_df['รหัสสินค้า'].str.contains(search_query, case=False, na=False) |
                        display_df['โซน'].str.contains(search_query, case=False, na=False) |
                        display_df['Order ID'].str.contains(search_query, case=False, na=False)
                    ]
                    st.dataframe(filtered_df, use_container_width=True, hide_index=True)
                else:
                    st.dataframe(display_df, use_container_width=True, hide_index=True)
                    
            except Exception as e:
                st.error(f"เกิดข้อผิดพลาด: {e}")
import streamlit as st
import pdfplumber
from pypdf import PdfReader, PdfWriter
import re
import io
import pandas as pd

# ตั้งค่าหน้าตาของเว็บ (เริ่มแรกให้เป็นแบบยืดหยุ่นกว้าง)
st.set_page_config(page_title="Smart Picking PRO", page_icon="📦", layout="wide")

# ================= 🆕 ส่วนบนสุด: เลือกอุปกรณ์ที่กำลังใช้งาน =================
st.sidebar.subheader("📱⚙️ ตั้งค่าขนาดหน้าจอ")
device_mode = st.sidebar.radio(
    "คุณกำลังเปิดใช้งานผ่านอุปกรณ์อะไร?",
    ["คอมพิวเตอร์ (PC / Laptop) 💻", "โทรศัพท์มือถือ (Mobile) 📱"],
    index=0
)

# ปรับสไตล์ CSS ตามอุปกรณ์ที่เลือก
if device_mode == "โทรศัพท์มือถือ (Mobile) 📱":
    st.markdown("""
        <style>
        .block-container { padding-top: 1rem; padding-bottom: 1rem; max-width: 100% !important; }
        div[data-testid="stMetric"] {
            background-color: #1e293b;
            padding: 10px 14px;
            border-radius: 10px;
            margin-bottom: 6px;
            border-left: 5px solid #3b82f6;
        }
        div[data-testid="stMetricLabel"] { font-size: 13px !important; color: #94a3b8 !important; }
        div[data-testid="stMetricValue"] { font-size: 20px !important; font-weight: bold !important; color: #f8fafc !important; }
        </style>
    """, unsafe_context=True)
else:
    st.markdown("""
        <style>
        div[data-testid="stMetric"] {
            background-color: #0f172a;
            padding: 20px;
            border-radius: 12px;
            border-top: 4px solid #3b82f6;
        }
        </style>
    """, unsafe_context=True)

# --- ฟังก์ชันแกะข้อมูลจาก PDF ---
def extract_data_from_page(text):
    data = {
        'zone': 'Unknown',
        'sku': 'ZZZZZZ',
        'qty': 1,
        'source': 'Unknown',
        'track_no': 'Unknown',
        'order_id': 'Unknown'
    }
    if not text:
        return data
        
    # 1. หา PICK-CODE / โซน
    zone_match = re.search(r'\b(G\d+)\b', text)
    if zone_match:
        data['zone'] = zone_match.group(1)
    else:
        for line in text.split('\n'):
            if line.strip().startswith('G0'):
                data['zone'] = line.strip().split()[0]
                break
        
    # 2. หา ITEM CODE
    sku_match = re.search(r'\b\d+-[A-Z]+-[A-Z]+-\d+\b', text)
    if sku_match:
        data['sku'] = sku_match.group(0)
    else:
        for line in text.split('\n'):
            if "1-GDS-" in line:
                m = re.search(r'(1-GDS-[\w-]+)', line)
                if m:
                    data['sku'] = m.group(1)
                    break

    # 3. หาจำนวน QTY
    qty_match = re.search(r'รวมทั้งสิ้น\s*(\d+)', text)
    if qty_match:
        data['qty'] = int(qty_match.group(1))

    # 4. หา Source (Shopee / Lazada)
    if "Shopee" in text:
        data['source'] = "Shopee 🟠"
    elif "Lada" in text or "Lazada" in text:
        data['source'] = "Lazada 🔵"

    # 5. หา Order ID
    order_match = re.search(r'Order ID\s*:\s*([\w-]+)', text, re.IGNORECASE)
    if order_match:
        data['order_id'] = order_match.group(1)

    return data

# --- ฟังก์ชันประมวลผลหลัก ---
def process_pdf_pro(uploaded_file, sort_mode):
    pages_data = []
    with pdfplumber.open(uploaded_file) as pdf:
        for index, page in enumerate(pdf.pages):
            text = page.extract_text()
            page_info = extract_data_from_page(text)
            page_info['page_index'] = index
            pages_data.append(page_info)
            
    if sort_mode == "🔤 เรียงตามรหัสสินค้า (ITEM CODE)":
        pages_data.sort(key=lambda x: x['sku'])
    elif sort_mode == "📍 เรียงตามโซนคลังสินค้า (PICK-CODE -> รหัสสินค้า)":
        pages_data.sort(key=lambda x: (x['zone'], x['sku']))
    
    reader = PdfReader(uploaded_file)
    writer = PdfWriter()
    for page_info in pages_data:
        writer.add_page(reader.pages[page_info['page_index']])
        
    output_pdf = io.BytesIO()
    writer.write(output_pdf)
    output_pdf.seek(0)
    
    return output_pdf, pages_data

# --- ส่วนแสดงผลหน้าเว็บ (UI) ---
st.title("📦 Smart Picking PRO")
st.caption("ระบบจัดเรียงบิลอัจฉริยะ รองรับการแสดงผลทั้งบน PC และ มือถือ")
st.markdown("---")

# เลือกโหมดการเรียงลำดับ
st.subheader("⚙️ เลือกรูปแบบการเรียงลำดับเอกสาร")
sort_mode = st.radio(
    "ต้องการให้ระบบเรียงลำดับหน้าบิลตามอะไร?",
    [
        "🔤 เรียงตามรหัสสินค้า (ITEM CODE)",
        "📍 เรียงตามโซนคลังสินค้า (PICK-CODE -> รหัสสินค้า)"
    ],
    index=0
)

st.markdown("---")

uploaded_file = st.file_uploader("📂 เลือกไฟล์ PDF ใบจัดสินค้า", type=["pdf"])

if uploaded_file is not None:
    st.info(f"🗂️ ไฟล์: {uploaded_file.name}")
    
    if st.button("⚡ เริ่มจัดเรียงและสรุปยอดหยิบ", type="primary", use_container_width=True):
        with st.spinner("⏳ กำลังคำนวณข้อมูล..."):
            try:
                sorted_pdf, details = process_pdf_pro(uploaded_file, sort_mode)
                st.balloons()
                
                df = pd.DataFrame(details)
                st.success("🎉 จัดเรียงสำเร็จ!")
                
                # ปุ่มดาวน์โหลด
                st.download_button(
                    label="📥 ดาวน์โหลด PDF ที่จัดเรียงใหม่แล้ว",
                    data=sorted_pdf,
                    file_name=f"sorted_{uploaded_file.name}",
                    mime="application/pdf",
                    use_container_width=True
                )
                
                st.markdown("---")
                
                # ================= ส่วนแดชบอร์ดสรุปงานคลัง (ปรับตามประเภทอุปกรณ์) =================
                st.subheader("📊 สรุปภาพรวม")
                shopee_count = len(df[df['source'] == "Shopee 🟠"])
                laz_count = len(df[df['source'] == "Lazada 🔵"])
                
                if device_mode == "โทรศัพท์มือถือ (Mobile) 📱":
                    # แสดงผลแนวตั้งสำหรับมือถือ ไม่ให้ตกขอบ
                    st.metric("📋 จำนวนใบงานทั้งหมด", f"{len(df)} ใบ")
                    st.metric("🧺 สินค้าที่ต้องหยิบรวม", f"{df['qty'].sum()} ชิ้น")
                    st.metric("🚚 แยกค่ายออเดอร์", f"Shopee: {shopee_count} | Lazada: {laz_count}")
                else:
                    # แสดงผลแนวนอน 3 คอลัมน์สวยๆ เต็มจอสำหรับ PC
                    col1, col2, col3 = st.columns(3)
                    with col1: st.metric("📋 จำนวนใบงานทั้งหมด", f"{len(df)} ใบ")
                    with col2: st.metric("🧺 สินค้าที่ต้องหยิบรวม", f"{df['qty'].sum()} ชิ้น")
                    with col3: st.metric("🚚 แยกค่ายออเดอร์", f"Shopee: {shopee_count} | Lazada: {laz_count}")
                
                st.markdown("---")
                
                # ================= ส่วนใบบิลรวมสินค้า (Picking Summary) =================
                st.subheader("📝 ยอดหยิบรวมสินค้า")
                
                summary_df = df.groupby(['zone', 'sku'])['qty'].sum().reset_index()
                summary_df.columns = ['โซน (PICK-CODE)', 'รหัสสินค้า (ITEM CODE)', 'จำนวน (ชิ้น)']
                
                if sort_mode == "🔤 เรียงตามรหัสสินค้า (ITEM CODE)":
                    summary_df = summary_df.sort_values(by='รหัสสินค้า (ITEM CODE)')
                else:
                    summary_df = summary_df.sort_values(by=['โซน (PICK-CODE)', 'รหัสสินค้า (ITEM CODE)'])
                    
                st.dataframe(summary_df, use_container_width=True, hide_index=True)
                
                st.markdown("---")
                
                # ================= ส่วนค้นหาออเดอร์ =================
                st.subheader("🔍 ตรวจสอบตำแหน่งหน้าบิล")
                
                display_df = df.copy()
                display_df['หน้าใหม่'] = display_df.index + 1
                display_df['หน้าเดิม'] = display_df['page_index'] + 1
                display_df = display_df[['หน้าใหม่', 'zone', 'sku', 'qty', 'order_id', 'หน้าเดิม']]
                display_df.columns = ['บิลใบที่', 'โซน', 'รหัสสินค้า', 'จำนวน', 'Order ID', 'หน้าเดิมในไฟล์เก่า']
                
                search_query = st.text_input("พิมพ์รหัสสินค้า, โซน หรือ Order ID เพื่อค้นหาหน้า:")
                if search_query:
                    filtered_df = display_df[
                        display_df['รหัสสินค้า'].str.contains(search_query, case=False, na=False) |
                        display_df['โซน'].str.contains(search_query, case=False, na=False) |
                        display_df['Order ID'].str.contains(search_query, case=False, na=False)
                    ]
                    st.dataframe(filtered_df, use_container_width=True, hide_index=True)
                else:
                    st.dataframe(display_df, use_container_width=True, hide_index=True)
                    
            except Exception as e:
                st.error(f"เกิดข้อผิดพลาด: {e}")
