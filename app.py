import streamlit as st
from pypdf import PdfReader, PdfWriter
import re
import io
import pandas as pd

# 1. ตั้งค่าหน้าเว็บให้คลีนและกว้างเต็มจอ
st.set_page_config(page_title="Sharp Bill Sorter", page_icon="📦", layout="wide")

# ================= 🎨 CSS ปรับแต่งดีไซน์แบนเนอร์พนักงานคลังสินค้ามินิมอล =================
st.markdown("""
    <style>
    /* ตั้งค่าฟอนต์และพื้นหลังหลักให้เป็นโทนคลีน-โมเดิร์น */
    html, body, [data-testid="stAppViewContainer"] {
        background-color: #faf9f6 !important;
        color: #1e293b;
    }
    
    /* โครงสร้างแบนเนอร์ Sharp Bill Sorter */
    .hero-banner {
        background-color: #f4efe6;
        border-radius: 20px;
        padding: 40px;
        margin-bottom: 30px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        border: 1px solid #e5dec9;
        box-shadow: 0 4px 20px rgba(0,0,0,0.03);
    }
    
    .hero-left {
        flex: 1;
        padding-right: 20px;
    }
    
    .hero-title {
        font-size: 3.8rem;
        font-weight: 900;
        line-height: 1.1;
        color: #1a1a1a;
        margin: 0 0 15px 0;
    }
    
    .hero-title span {
        display: block;
    }
    
    .hero-subtitle {
        font-size: 1.2rem;
        color: #4a4a4a;
        line-height: 1.6;
        margin-bottom: 5px;
    }
    
    .hero-right {
        flex: 1;
        display: flex;
        justify-content: flex-end;
        align-items: center;
    }
    
    .hero-img {
        max-width: 260px;
        width: 100%;
        height: auto;
        border-radius: 12px;
    }
    
    /* ตกแต่งตารางสรุปแบบแดชบอร์ด */
    div[data-testid="stMetric"] {
        background-color: #ffffff;
        padding: 16px 20px;
        border-radius: 12px;
        border: 1px solid #e5dec9;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.02);
    }
    div[data-testid="stMetricLabel"] { font-size: 13px !important; color: #64748b !important; font-weight: bold !important; }
    div[data-testid="stMetricValue"] { font-size: 24px !important; font-weight: bold !important; color: #1e293b !important; }
    
    /* ตกแต่งปุ่มดำเนินการสีเขียว */
    div.stButton > button:first-child {
        background-color: #10b981 !important;
        color: white !important;
        font-size: 16px !important;
        font-weight: bold !important;
        border-radius: 8px !important;
        border: none !important;
        padding: 0.75rem 2.5rem !important;
        box-shadow: 0 4px 10px rgba(16, 185, 129, 0.2);
    }
    div.stButton > button:first-child:hover {
        background-color: #059669 !important;
    }
    
    /* ปรับแต่งกล่อง File Uploader */
    div[data-testid="stFileUploader"] {
        background-color: #ffffff;
        border: 2px dashed #e5dec9;
        border-radius: 12px;
        padding: 20px;
    }
    
    /* 📱 รองรับมือถือแบบ Responsive */
    @media (max-width: 768px) {
        .hero-banner {
            flex-direction: column-reverse;
            padding: 24px;
            gap: 20px;
            text-align: center;
        }
        .hero-left {
            padding-right: 0;
        }
        .hero-title {
            font-size: 2.5rem;
        }
        .hero-subtitle {
            font-size: 1rem;
        }
        .hero-right {
            justify-content: center;
            width: 100%;
        }
        .hero-img {
            max-width: 200px;
        }
        div[data-testid="stMetric"] { margin-bottom: 8px !important; width: 100% !important; }
        div[data-testid="column"] { width: 100% !important; flex: 1 1 100% !important; }
    }
    </style>
""", unsafe_allow_html=True)

# --- ฟังก์ชันเบื้องหลังดึงข้อมูล (Core Logic) ---
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
    elif sort_mode == "🔤 เรียงตามรหัสสินค้าอย่างเดียว (ITEM CODE)":
        all_pages_data.sort(key=lambda x: x['sku'])
    elif sort_mode == "📍 เรียงตามโซนคลังสินค้า (PICK-CODE -> รหัสสินค้า)":
        all_pages_data.sort(key=lambda x: (x['zone'], x['sku']))
        
    for page_info in all_pages_data:
        writer.add_page(page_info['reader_page_ref'])
        
    output_pdf = io.BytesIO()
    writer.write(output_pdf)
    output_pdf.seek(0)
    
    return output_pdf, all_pages_data

# ================= 🚀 หน้าการแสดงผลเว็บไซต์ (UI Layout) =================

# ฝังรูปภาพพนักงานยกกล่องมินิมอลที่คุณเลือกไว้ที่ฝั่งขวาของแบนเนอร์เรียบร้อย
st.markdown("""
    <div class="hero-banner">
        <div class="hero-left">
            <h1 class="hero-title">
                <span>Sharp Bill</span>
                <span>Sorter</span>
            </h1>
            <p class="hero-subtitle">
                ระบบจัดเรียงบิล เลือกโหมดการคัดจัดเรียงบิลหน้างานได้ตามต้องการ
            </p>
        </div>
        <div class="hero-right">
            <img class="hero-img" src="https://i.ibb.co/6R0gGf9M/1000004375.jpg" alt="Sharp Warehouse Worker">
        </div>
    </div>
""", unsafe_allow_html=True)

# ส่วนช่องกรอกและปุ่มทำงานหลัก
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
uploaded_files = st.file_uploader(
    "ลากไฟล์ PDF มาวางตรงนี้ (สามารถลากวางพร้อมกันหลายๆ ไฟล์เพื่อรวมยอดรอบเดียวกันได้)", 
    type=["pdf"], 
    accept_multiple_files=True
)

if uploaded_files:
    st.info(f"🗂️ ตรวจพบไฟล์ใบงานทั้งหมด: {len(uploaded_files)} ไฟล์ พร้อมสำหรับจัดเรียงข้อมูล")
    
    if st.button("⚡ เริ่มจัดบิลและสรุปยอดรวม", use_container_width=True):
        with st.spinner("⏳ ระบบกำลังผสานไฟล์ คัดแยกประเภทขนส่ง และสรุปยอดหยิบรวม... กรุณารอสักครู่"):
            try:
                sorted_pdf, details = process_multiple_pdfs(uploaded_files, sort_mode)
                st.balloons()
                
                df = pd.DataFrame(details)
                st.success("🎉 ทำรายการสำเร็จเรียบร้อย!")
                
                st.download_button(
                    label="📥 ดาวน์โหลดไฟล์บิล PDF ที่มัดรวมและจัดเรียงใหม่ทั้งหมด",
                    data=sorted_pdf,
                    file_name="sharp_sorted_bills.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )
                
                st.markdown("---")
                
                # ================= แดชบอร์ดสรุปยอด =================
                st.subheader("📊 ขั้นตอนที่ 3: สรุปยอดรวมสินค้าจากทุกไฟล์")
                shopee_count = len(df[df['source'] == "Shopee 🟠"])
                laz_count = len(df[df['source'] == "Lazada 🔵"])
                
                col1, col2, col3 = st.columns(3)
                with col1: st.metric("📋 ใบออเดอร์รวม", f"{len(df)} บิล")
                with col2: st.metric("🧺 ยอดสินค้าที่ต้องเดินหยิบ", f"{df['qty'].sum()} ชิ้น")
                with col3: st.metric("🚚 แยกค่ายยอดออเดอร์", f"Shopee: {shopee_count} | Lazada: {laz_count}")
                
                st.markdown("##")
                
                # ================= ตารางสรุปยอดหยิบรวม (Picking Summary) =================
                st.write("**📝 ใบสรุปยอดสินค้าที่ต้องหยิบประจำรอบ (Picking List)**")
                if sort_mode == "🚚 เรียงตามขนส่ง -> แล้วเรียงรหัสสินค้า (ITEM CODE)":
                    summary_df = df.groupby(['courier', 'sku'])['qty'].sum().reset_index()
                    summary_df.columns = ['บริษัทขนส่ง', 'รหัสสินค้า (ITEM CODE)', 'จำนวน (ชิ้น)']
                    summary_df = summary_df.sort_values(by=['บริษัทขนส่ง', 'รหัสสินค้า (ITEM CODE)'])
                elif sort_mode == "📍 เรียงตามโซนคลังสินค้า (PICK-CODE -> รหัสสินค้า)":
                    summary_df = df.groupby(['zone', 'sku'])['qty'].sum().reset_index()
                    summary_df.columns = ['โซน (PICK-CODE)', 'รหัสสินค้า (ITEM CODE)', 'จำนวน (ชิ้น)']
                    summary_df = summary_df.sort_values(by=['โซน (PICK-CODE)', 'รหัสสินค้า (ITEM CODE)'])
                else:
                    summary_df = df.groupby('sku')['qty'].sum().reset_index()
                    summary_df.columns = ['รหัสสินค้า (ITEM CODE)', 'จำนวน (ชิ้น)']
                    summary_df = summary_df.sort_values(by='รหัสสินค้า (ITEM CODE)')
                    
                st.dataframe(summary_df, use_container_width=True, hide_index=True)
                
                st.markdown("---")
                
                # ================= ช่องค้นหาตำแหน่งหน้าบิล =================
                st.write("**🔍 ค้นหาออเดอร์ด่วนและตรวจสอบหน้าเอกสาร**")
                display_df = df.copy()
                display_df['หน้าใหม่'] = display_df.index + 1
                display_df = display_df[['หน้าใหม่', 'courier', 'zone', 'sku', 'qty', 'order_id']]
                display_df.columns = ['บิลใบที่ (หน้าใหม่)', 'บริษัทขนส่ง', 'โซนคลัง', 'รหัสสินค้า', 'จำนวน', 'Order ID']
                
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
