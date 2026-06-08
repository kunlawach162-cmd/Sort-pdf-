import streamlit as st
import pdfplumber
from pypdf import PdfReader, PdfWriter
import re
import io
import pandas as pd

# ตั้งค่าหน้าตาของเว็บให้ดูโปรและ Scannable
st.set_page_config(page_title="Smart Picking Sorter PRO", page_icon="📦", layout="wide")

# --- ฟังก์ชันแกะข้อมูลจาก PDF ---
def extract_data_from_page(text):
    data = {
        'sku': 'ZZZZZZ',
        'qty': 1,
        'source': 'Unknown',
        'track_no': 'Unknown',
        'order_id': 'Unknown'
    }
    if not text:
        return data
        
    # 1. หา ITEM CODE (เช่น 1-GDS-SHARP-000000565)
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

    # 2. หาจำนวน QTY (อยู่แถวๆ บรรทัดที่มีรหัสสินค้า หรือมองหาตัวเลขรวม)
    qty_match = re.search(r'รวมทั้งสิ้น\s*(\d+)', text)
    if qty_match:
        data['qty'] = int(qty_match.group(1))

    # 3. หา Source (Shopee / Lazada)
    if "Shopee" in text:
        data['source'] = "Shopee 🟠"
    elif "Lada" in text or "Lazada" in text:
        data['source'] = "Lazada 🔵"

    # 4. หา Order ID และ Tracking Number
    order_match = re.search(r'Order ID\s*:\s*([\w-]+)', text, re.IGNORECASE)
    if order_match:
        data['order_id'] = order_match.group(1)
        
    track_match = re.search(r'Track No\s*:\s*([\w-]+)', text, re.IGNORECASE)
    if track_match:
        data['track_no'] = track_match.group(1)

    return data

# --- ฟังก์ชันประมวลผลหลัก ---
def process_pdf_pro(uploaded_file):
    pages_data = []
    
    with pdfplumber.open(uploaded_file) as pdf:
        for index, page in enumerate(pdf.pages):
            text = page.extract_text()
            page_info = extract_data_from_page(text)
            page_info['page_index'] = index
            pages_data.append(page_info)
            
    # เรียงลำดับตาม SKU จากน้อยไปมาก
    pages_data.sort(key=lambda x: x['sku'])
    
    # สร้าง PDF ใหม่
    reader = PdfReader(uploaded_file)
    writer = PdfWriter()
    for page_info in pages_data:
        writer.add_page(reader.pages[page_info['page_index']])
        
    output_pdf = io.BytesIO()
    writer.write(output_pdf)
    output_pdf.seek(0)
    
    return output_pdf, pages_data

# --- ส่วนแสดงผลหน้าเว็บ (UI) ---
st.title("📦 ระบบจัดเรียงใบจัดสินค้าเวอร์ชันคลังโปร (Smart Picking PRO)")
st.caption("เวอร์ชันอัปเกรด: เรียงรหัสสินค้าอัตโนมัติ + สรุปยอดหยิบรวมเพื่อความรวดเร็วหน้างาน")
st.markdown("---")

uploaded_file = st.file_uploader("📂 ลากไฟล์ PDF ใบจัดสินค้ารวมมาวางที่นี่", type=["pdf"])

if uploaded_file is not None:
    st.success(f"🗂️ โหลดไฟล์ '{uploaded_file.name}' เรียบร้อย!")
    
    if st.button("⚡ เริ่มประมวลผลและจัดเรียงเอกสาร", type="primary", use_container_width=True):
        with st.spinner("🧠 ระบบกำลังอ่านข้อมูลแยกแยะรหัสสินค้าและสรุปออเดอร์..."):
            try:
                sorted_pdf, details = process_pdf_pro(uploaded_file)
                st.balloons()
                
                # สร้าง DataFrame เพื่อจัดการข้อมูลสถิติ
                df = pd.DataFrame(details)
                
                # ================= ส่วนดาวน์โหลดไฟล์ =================
                st.success("🎉 จัดเรียงเสร็จเรียบร้อยแล้ว!")
                st.download_button(
                    label="📥 ดาวน์โหลด PDF ที่จัดเรียงรหัสสินค้าแล้ว (พร้อมพิมพ์)",
                    data=sorted_pdf,
                    file_name=f"sorted_{uploaded_file.name}",
                    mime="application/pdf",
                    use_container_width=True
                )
                
                st.markdown("---")
                
                # ================= ส่วนแดชบอร์ดสรุปงานคลัง =================
                st.subheader("📊 สรุปภาพรวมใบงาน (Dashboard)")
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("จำนวนใบงานทั้งหมด", f"{len(df)} ใบ")
                with col2:
                    total_items = df['qty'].sum()
                    st.metric("จำนวนสินค้าที่ต้องหยิบทวน", f"{total_items} ชิ้น")
                with col3:
                    shopee_count = len(df[df['source'] == "Shopee 🟠"])
                    laz_count = len(df[df['source'] == "Lazada 🔵"])
                    st.metric("แยกช่องทาง", f"Shopee: {shopee_count} | Laz: {laz_count}")
                
                st.markdown("---")
                
                # ================= ส่วนใบบิลรวมสินค้า (Picking List) =================
                st.subheader("📝 ใบสรุปยอดหยิบรวม (Picking Summary)")
                st.write("💡 แนะนำให้พนักงานดูตรงนี้แล้วไปหยิบของมากองรวมกันทีเดียวตามจำนวน ก่อนจะแยกแพ็กตามใบออเดอร์")
                
                # ยุบรวมจำนวนชิ้นตาม SKU
                summary_df = df.groupby('sku')['qty'].sum().reset_index()
                summary_df.columns = ['รหัสสินค้า (ITEM CODE)', 'จำนวนที่ต้องหยิบทั้งหมด (ชิ้น)']
                summary_df = summary_df.sort_values(by='รหัสสินค้า (ITEM CODE)')
                
                st.table(summary_df)
                
                st.markdown("---")
                
                # ================= ส่วนตารางเช็กตำแหน่งหน้า =================
                st.subheader("🔍 ตารางตรวจเช็กตำแหน่งออเดอร์")
                st.write("พิมพ์ค้นหารหัสสินค้า หรือเลขที่คำสั่งซื้อ เพื่อดูว่าอยู่หน้าไหนในบิล PDF ใหม่")
                
                # ปรับแต่งการแสดงผลตารางให้เข้าใจง่าย
                display_df = df.copy()
                display_df['ลำดับหน้าใหม่'] = display_df.index + 1
                display_df['หน้าเดิมในไฟล์เก่า'] = display_df['page_index'] + 1
                display_df = display_df[['ลำดับหน้าใหม่', 'sku', 'qty', 'source', 'order_id', 'หน้าเดิมในไฟล์เก่า']]
                display_df.columns = ['ลำดับหน้าใน PDF ใหม่', 'รหัสสินค้า (ITEM CODE)', 'จำนวน', 'ช่องทาง', 'Order ID', 'ตำแหน่งหน้าในไฟล์เดิม']
                
                # ช่องเซิร์ชข้อมูล
                search_query = st.text_input("ค้นหาในตาราง (ใส่ ITEM CODE หรือ Order ID):")
                if search_query:
                    filtered_df = display_df[
                        display_df['รหัสสินค้า (ITEM CODE)'].str.contains(search_query, case=False, na=False) |
                        display_df['Order ID'].str.contains(search_query, case=False, na=False)
                    ]
                    st.dataframe(filtered_df, use_container_width=True)
                else:
                    st.dataframe(display_df, use_container_width=True)
                    
            except Exception as e:
                st.error(f"เกิดข้อผิดพลาดในการประมวลผล: {e}")

