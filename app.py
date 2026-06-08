import streamlit as st
import pdfplumber
from pypdf import PdfReader, PdfWriter
import re
import io

# ตั้งค่าหน้าตาของเว็บ
st.set_page_config(page_title="PDF SKU Sorter", page_icon="📄", layout="centered")

# --- ฟังก์ชันหลักในการค้นหา SKU ---
def extract_sku_from_text(text):
    if not text:
        return "999999"
    # ค้นหาคำสำคัญ เช่น ITEM, SKU, รหัสสินค้า
    match = re.search(r'(?:ITEM|SKU|รหัสสินค้า)\s*:\s*(\w+)', text, re.IGNORECASE)
    if match:
        return match.group(1)
    # ถ้าไม่เจอคำสำคัญ ให้หาตัวเลขล้วนที่มีความยาว 5-10 หลัก
    numbers = re.findall(r'\b\d{5,10}\b', text)
    if numbers:
        return numbers[0]
    return "999999"

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
            
    # เรียงลำดับตาม SKU
    pages_data.sort(key=lambda x: x['sku'])
    
    # สร้าง PDF ใหม่ในหน่วยความจำ (BytesIO) เพื่อเตรียมให้ดาวน์โหลด
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
st.subheader("เรียงลำดับหน้า PDF ตามรหัสสินค้า (SKU)")
st.write("ช่วยจัดเรียงหน้าเอกสารใหม่อัตโนมัติ เพื่อให้เดินหยิบสินค้าในคลังได้ง่ายและเร็วที่สุด")

st.markdown("---")

# กล่องสำหรับลากและวางไฟล์ PDF
uploaded_file = st.file_uploader("📂 ลากไฟล์ PDF ใบจัดสินค้ามาวางตรงนี้ หรือคลิกเพื่อเลือกไฟล์", type=["pdf"])

if uploaded_file is not None:
    st.success(f"โหลดไฟล์ '{uploaded_file.name}' สำเร็จแล้ว!")
    
    # ปุ่มกดเริ่มทำงาน
    if st.button("⚡ เริ่มจัดเรียงเอกสารใหม่", type="primary"):
        with st.spinner("กำลังอ่านข้อมูลและจัดเรียงหน้า PDF... กรุณารอสักครู่"):
            try:
                # ประมวลผลไฟล์
                sorted_pdf, details = process_pdf(uploaded_file)
                
                st.balloons() # แสดงเอฟเฟกต์ลูกโป่งแสดงความยินดีเมื่อเสร็จ
                st.success("🎉 จัดเรียงเสร็จเรียบร้อยแล้ว!")
                
                # แสดงพรีวิวรายละเอียดที่ระบบเจอ
                with st.expander("🔍 ดูรายละเอียดรหัสสินค้าที่ระบบตรวจพบในแต่ละหน้า"):
                    for idx, item in enumerate(details):
                        st.write(f"• หน้าที่เรียงใหม่ตำแหน่งที่ {idx+1} (หน้าเดิมที่ {item['page_index']+1}) -> เจอ SKU: **{item['sku']}**")
                
                # ปุ่มสำหรับดาวน์โหลดไฟล์ที่เรียงแล้ว
                st.download_button(
                    label="📥 ดาวน์โหลดไฟล์ PDF ที่เรียงลำดับแล้ว",
                    data=sorted_pdf,
                    file_name=f"sorted_{uploaded_file.name}",
                    mime="application/pdf"
                )
                
            except Exception as e:
                st.error(f"เกิดข้อผิดพลาดในการประมวลผล: {e}")
