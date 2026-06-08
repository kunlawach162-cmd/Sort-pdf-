import streamlit as st
import pdfplumber
from pypdf import PdfReader, PdfWriter
import re
import io

# ตั้งค่าหน้าตาของเว็บ
st.set_page_config(page_title="PDF SKU Sorter", page_icon="📄", layout="centered")

# --- ฟังก์ชันแกะรหัสสินค้าเจาะจงรูปแบบไฟล์คลังสินค้าจริง ---
def extract_sku_from_text(text):
    if not text:
        return "ZZZZZZ"
        
    # 1. ค้นหารหัสรูปแบบเฉพาะของคลังคุณ (เช่น 1-GDS-SHARP-000000565)
    # ค้นหาคำที่ขึ้นต้นด้วยตัวเลข-ตามด้วยตัวหนังสือและมีขีดกลางเชื่อม
    specific_pattern = re.search(r'\b\d+-[A-Z]+-[A-Z]+-\d+\b', text)
    if specific_pattern:
        return specific_pattern.group(0)
        
    # 2. ถ้าไม่เจอแบบแรก ให้หาคำสำคัญรอบๆ ITEM CODE
    lines = text.split('\n')
    for line in lines:
        if "1-GDS-" in line:
            # ดึงคำที่ขึ้นต้นด้วย 1-GDS ออกมา
            match = re.search(r'(1-GDS-[\w-]+)', line)
            if match:
                return match.group(1)
                
    return "ZZZZZZ" # ถ้าหน้าไหนหาไม่เจอจริงๆ ให้ไปอยู่ท้ายสุด

# --- ฟังก์ชันจัดเรียงและสร้าง PDF ใหม่ ---
def process_pdf(uploaded_file):
    pages_data = []
    
    # อ่านไฟล์ PDF จากหน่วยความจำ
    with pdfplumber.open(uploaded_file) as pdf:
        for index, page in enumerate(pdf.pages):
            text = page.extract_text()
            sku = extract_sku_from_text(text)
            pages_data.append({
                'page_index': index,
                'sku': sku
            })
            
    # เรียงลำดับตามรหัสสินค้า (SKU) จากน้อยไปมาก
    pages_data.sort(key=lambda x: x['sku'])
    
    # สร้าง PDF ใหม่ในหน่วยความจำ (BytesIO)
    reader = PdfReader(uploaded_file)
    writer = PdfWriter()
    
    for page_info in pages_data:
        writer.add_page(reader.pages[page_info['page_index']])
        
    output_pdf = io.BytesIO()
    writer.write(output_pdf)
    output_pdf.seek(0)
    
    return output_pdf, pages_data

# --- ส่วนแสดงผลบนหน้าเว็บ (UI) ---
st.title("📄 ระบบจัดเรียงใบจัดสินค้าอัตโนมัติ")
st.subheader("เรียงลำดับหน้า PDF ตามรหัสสินค้า (ITEM CODE)")
st.write("เวอร์ชันอัปเดต: รองรับรหัสสินค้ารูปแบบคลังสินค้า Sharp")

st.markdown("---")

uploaded_file = st.file_uploader("📂 ลากไฟล์ PDF ใบจัดสินค้ามาวางตรงนี้ หรือคลิกเพื่อเลือกไฟล์", type=["pdf"])

if uploaded_file is not None:
    st.success(f"โหลดไฟล์ '{uploaded_file.name}' สำเร็จแล้ว!")
    
    if st.button("⚡ เริ่มจัดเรียงเอกสารใหม่", type="primary"):
        with st.spinner("กำลังอ่านข้อมูลและจัดเรียงหน้า PDF... กรุณารอสักครู่"):
            try:
                sorted_pdf, details = process_pdf(uploaded_file)
                
                st.balloons() 
                st.success("🎉 จัดเรียงตาม ITEM CODE เสร็จเรียบร้อยแล้ว!")
                
                # แสดงตารางพรีวิวรายละเอียดที่ระบบเจอ
                with st.expander("🔍 ดูรายละเอียดการจัดเรียงรหัสสินค้าแต่ละหน้า"):
                    for idx, item in enumerate(details):
                        st.write(f"• ลำดับที่ {idx+1} (หน้าเดิมที่ {item['page_index']+1}) ➡️ ITEM CODE: **{item['sku']}**")
                
                # ปุ่มสำหรับดาวน์โหลดไฟล์ที่เรียงแล้ว
                st.download_button(
                    label="📥 ดาวน์โหลดไฟล์ PDF ที่เรียงลำดับแล้ว",
                    data=sorted_pdf,
                    file_name=f"sorted_{uploaded_file.name}",
                    mime="application/pdf"
                )
                
            except Exception as e:
                st.error(f"เกิดข้อผิดพลาดในการประมวลผล: {e}")
