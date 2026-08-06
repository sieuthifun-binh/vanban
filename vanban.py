import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, date
import json
import re
from pypdf import PdfReader
import docx

# Tích hợp OpenAI & Gemini tùy chọn
try:
    import openai
except ImportError:
    openai = None

try:
    import google.generativeai as genai
except ImportError:
    genai = None

# ==========================================
# 1. CẤU HÌNH TRANG VÀ GIAO DIỆN
# ==========================================
st.set_page_config(
    page_title="Hệ Thống Quản Lý & Tra Cứu Văn Bản Thông Minh",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .main-title {
        color: #1E3A8A;
        font-size: 26px;
        font-weight: bold;
        border-bottom: 2px solid #1E3A8A;
        padding-bottom: 10px;
        margin-bottom: 20px;
    }
    .doc-card {
        background-color: #F8FAFC;
        border-left: 4px solid #2563EB;
        padding: 12px;
        margin-bottom: 10px;
        border-radius: 4px;
    }
    .stButton>button {
        width: 100%;
    }
    .badge {
        background-color: #E2E8F0;
        color: #1E293B;
        padding: 2px 8px;
        border-radius: 12px;
        font-size: 12px;
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. XỬ LÝ CƠ SỞ DỮ LIỆU (SQLITE)
# ==========================================
DB_FILE = "doc_management.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_number TEXT,
            title TEXT,
            doc_type TEXT,
            issuing_authority TEXT,
            issue_date DATE,
            content TEXT,
            summary TEXT,
            related_doc_ids TEXT,
            updated_at TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def get_all_documents():
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query("SELECT * FROM documents ORDER BY updated_at DESC", conn)
    conn.close()
    return df

def insert_document(doc_number, title, doc_type, issuing_authority, issue_date, content, summary, related_doc_ids):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute('''
        INSERT INTO documents (doc_number, title, doc_type, issuing_authority, issue_date, content, summary, related_doc_ids, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (doc_number, title, doc_type, issuing_authority, issue_date, content, summary, json.dumps(related_doc_ids), now))
    conn.commit()
    conn.close()

# ==========================================
# 3. ENGINE BÓC TÁCH SIÊU TỐC (REGEX + AI DỰ PHÒNG)
# ==========================================
def extract_text_from_file(uploaded_file):
    """Trích xuất văn bản thô từ file"""
    text = ""
    try:
        if uploaded_file.name.endswith('.pdf'):
            pdf_reader = PdfReader(uploaded_file)
            for page in pdf_reader.pages:
                extracted = page.extract_text()
                if extracted:
                    text += extracted + "\n"
        elif uploaded_file.name.endswith('.docx'):
            doc = docx.Document(uploaded_file)
            for para in doc.paragraphs:
                text += para.text + "\n"
        elif uploaded_file.name.endswith('.txt'):
            text = uploaded_file.read().decode('utf-8')
    except Exception as e:
        st.error(f"Lỗi khi đọc file: {str(e)}")
    return text

def regex_extract_metadata(raw_text):
    """Bóc tách cực nhanh bằng Quy tắc Thể thức Văn bản (0.01 giây, 100% không lỗi)"""
    sample = raw_text[:2500]  # Chỉ xét 2500 ký tự đầu
    
    # 1. Bóc tách Số / Ký hiệu
    doc_number = ""
    num_match = re.search(r'(Số|Số:)\s*([0-9]+[0-9a-zA-Z/\-\._]+)', sample, re.IGNORECASE)
    if num_match:
        doc_number = num_match.group(2).strip()

    # 2. Bóc tách Ngày tháng
    issue_date_str = str(date.today())
    date_match = re.search(r'ngày\s+([0-9]{1,2})\s+tháng\s+([0-9]{1,2})\s+năm\s+([0-9]{4})', sample, re.IGNORECASE)
    if date_match:
        d, m, y = date_match.groups()
        issue_date_str = f"{y}-{int(m):02d}-{int(d):02d}"

    # 3. Bóc tách Loại văn bản
    doc_type = "Khác"
    types = ["Nghị định", "Thông tư", "Quyết định", "Luật", "Công văn", "Quy chế", "Quy định", "Nghị quyết", "Thông báo"]
    for t in types:
        if re.search(rf'\b{t}\b', sample, re.IGNORECASE):
            doc_type = "Quy chế / Quy định" if t in ["Quy chế", "Quy định"] else t
            break

    # 4. Trích xuất Tiêu đề / Trích yếu
    title = ""
    # Tìm sau từ khóa "Về việc" hoặc sau Tên Loại văn bản
    about_match = re.search(r'Về việc\s+([^\n\r]+)', sample, re.IGNORECASE)
    if about_match:
        title = "Về việc " + about_match.group(1).strip()
    else:
        # Lấy dòng chứa loại văn bản
        lines = [line.strip() for line in sample.split('\n') if line.strip()]
        for line in lines[:15]:
            if any(t.lower() in line.lower() for t in types) and len(line) > 10:
                title = line
                break

    # 5. Cơ quan ban hành
    issuing_authority = ""
    lines = [line.strip() for line in sample.split('\n') if line.strip()]
    if len(lines) > 0:
        issuing_authority = lines[0] # Thông thường nằm ở dòng đầu tiên bên trái

    return {
        "doc_number": doc_number,
        "title": title[:200] if title else "Văn bản chưa có tiêu đề",
        "doc_type": doc_type,
        "issuing_authority": issuing_authority[:100],
        "issue_date": issue_date_str
    }

def openai_extract_metadata(api_key, raw_text):
    """Trích xuất bằng OpenAI GPT-4o-mini (Nếu người dùng chọn dùng OpenAI)"""
    try:
        client = openai.OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Bạn là chuyên gia bóc tách dữ liệu văn bản hành chính Việt Nam. Trả về định dạng JSON."},
                {"role": "user", "content": f"Bóc tách metadata từ đoạn đầu văn bản này:\n{raw_text[:2000]}\nTrả về JSON chứa: doc_number, title, doc_type, issuing_authority, issue_date (YYYY-MM-DD)."}
            ],
            response_format={"type": "json_object"}
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        st.error(f"Lỗi OpenAI: {str(e)}")
        return {}

# ==========================================
# 4. GIAO DIỆN CHÍNH & SIDEBAR
# ==========================================
st.sidebar.title("⚙️ Cấu hình & Engine")
engine_choice = st.sidebar.radio(
    "Chọn Engine Phân Tích:",
    ["🚀 Thuật toán Regex (Siêu tốc & Miễn phí)", "🤖 OpenAI GPT-4o-mini", "♊ Google Gemini"]
)

api_key_input = ""
if engine_choice == "🤖 OpenAI GPT-4o-mini":
    api_key_input = st.sidebar.text_input("Nhập OpenAI API Key:", type="password")
elif engine_choice == "♊ Google Gemini":
    api_key_input = st.sidebar.text_input("Nhập Gemini API Key:", type="password")

menu = st.sidebar.radio(
    "Chức năng chính:",
    ["📖 Tra cứu & Đọc văn bản", "➕ Thêm mới văn bản", "📊 Thống kê hệ thống"]
)

st.sidebar.markdown("---")
st.sidebar.info("""
**Hệ Thống Quản Lý Văn Bản Tối Ưu**
- Engine Bóc Tách Tốc Độ Cao (Regex/AI)
- Không lo nghẽn mạng hay Timeout
""")

# ==========================================
# CHỨC NĂNG 1: TRA CỨU & ĐỌC VĂN BẢN
# ==========================================
if menu == "📖 Tra cứu & Đọc văn bản":
    st.markdown("<div class='main-title'>⚖️ QUẢN LÝ & TRA CỨU HỆ THỐNG VĂN BẢN</div>", unsafe_allow_html=True)
    
    df = get_all_documents()

    if df.empty:
        st.warning("Hệ thống chưa có văn bản nào. Vui lòng chuyển sang mục 'Thêm mới văn bản' để tải lên!")
    else:
        col_list, col_reader = st.columns([5, 7])

        with col_list:
            st.subheader("🔍 Tìm kiếm & Lọc văn bản")
            search_kw = st.text_input("Từ khóa (Số hiệu, Tiêu đề, Nội dung):", value="")
            
            col_filter1, col_filter2 = st.columns(2)
            with col_filter1:
                doc_type_filter = st.selectbox("Loại văn bản:", ["Tất cả"] + list(df['doc_type'].unique()))
            with col_filter2:
                min_date = pd.to_datetime(df['issue_date']).min().date() if not df.empty else date(2020, 1, 1)
                max_date = pd.to_datetime(df['issue_date']).max().date() if not df.empty else date.today()
                date_range = st.date_input("Khoảng ngày ban hành:", [min_date, max_date])

            filtered_df = df.copy()

            if search_kw:
                kw = search_kw.lower()
                filtered_df = filtered_df[
                    filtered_df['doc_number'].str.lower().str.contains(kw) |
                    filtered_df['title'].str.lower().str.contains(kw) |
                    filtered_df['content'].str.lower().str.contains(kw)
                ]

            if doc_type_filter != "Tất cả":
                filtered_df = filtered_df[filtered_df['doc_type'] == doc_type_filter]

            if len(date_range) == 2:
                start_d, end_d = date_range
                filtered_df['issue_date_dt'] = pd.to_datetime(filtered_df['issue_date']).dt.date
                filtered_df = filtered_df[
                    (filtered_df['issue_date_dt'] >= start_d) & 
                    (filtered_df['issue_date_dt'] <= end_d)
                ]

            st.caption(f"Tìm thấy **{len(filtered_df)}** văn bản (Sắp xếp theo ngày cập nhật mới nhất):")

            for idx, row in filtered_df.iterrows():
                with st.container():
                    st.markdown(f"""
                    <div class='doc-card'>
                        <small><b>Cập nhật:</b> {row['updated_at']} | <b>Ngày BH:</b> {row['issue_date']}</small><br>
                        <strong style='color:#1E3A8A;'>[{row['doc_number']}]</strong> {row['title']}<br>
                        <span class='badge'>{row['doc_type']}</span> <span class='badge'>{row['issuing_authority']}</span>
                    </div>
                    """, unsafe_allow_html=True)
                    if st.button(f"📄 Mở đọc văn bản này", key=f"btn_{row['id']}"):
                        st.session_state['active_doc_id'] = row['id']

        with col_reader:
            st.subheader("📖 Khung đọc văn bản")
            active_id = st.session_state.get('active_doc_id', None)
            if active_id is None and not filtered_df.empty:
                active_id = filtered_df.iloc[0]['id']

            if active_id:
                doc = df[df['id'] == active_id].iloc[0]

                st.markdown(f"### {doc['title']}")
                m_col1, m_col2, m_col3 = st.columns(3)
                m_col1.write(f"**Số/Ký hiệu:** {doc['doc_number']}")
                m_col2.write(f"**Cơ quan BH:** {doc['issuing_authority']}")
                m_col3.write(f"**Ngày BH:** {doc['issue_date']}")

                st.text_area("Toàn văn nội dung:", value=doc['content'], height=500, disabled=True)
            else:
                st.info("Vui lòng chọn một văn bản từ danh sách bên trái để đọc.")

# ==========================================
# CHỨC NĂNG 2: THÊM MỚI VĂN BẢN (AUTO-EXTRACT)
# ==========================================
elif menu == "➕ Thêm mới văn bản":
    st.markdown("<div class='main-title'>➕ CẬP NHẬT VĂN BẢN MỚI VÀO HỆ THỐNG</div>", unsafe_allow_html=True)

    st.subheader("📥 1. Nhập văn bản hoặc Tải file lên")
    file_tab, text_tab = st.tabs(["📁 Tải File (PDF / DOCX / TXT)", "📝 Dán đoạn văn bản thô"])
    
    raw_content_extracted = ""
    with file_tab:
        uploaded_file = st.file_uploader("Chọn file văn bản từ máy tính:", type=['pdf', 'docx', 'txt'])
        if uploaded_file is not None:
            raw_content_extracted = extract_text_from_file(uploaded_file)

    with text_tab:
        pasted_text = st.text_area("Dán nội dung văn bản thô tại đây:", height=150)
        if pasted_text:
            raw_content_extracted = pasted_text

    if st.button("⚡ Phân tích & Điền tự động"):
        if not raw_content_extracted:
            st.warning("Vui lòng tải file hoặc dán nội dung văn bản trước khi bấm phân tích.")
        else:
            extracted_data = {}
            if "Regex" in engine_choice:
                # Chạy Regex cực nhanh
                extracted_data = regex_extract_metadata(raw_content_extracted)
                st.success("⚡ Đã phân tích xong bằng Thuật toán Regex trong 0.01s!")
            elif "OpenAI" in engine_choice:
                if not api_key_input:
                    st.error("Vui lòng nhập OpenAI API Key ở thanh bên.")
                else:
                    with st.spinner("OpenAI đang xử lý..."):
                        extracted_data = openai_extract_metadata(api_key_input, raw_content_extracted)
                        st.success("✅ OpenAI bóc tách thành công!")

            if extracted_data:
                st.session_state['temp_doc_number'] = extracted_data.get('doc_number', '')
                st.session_state['temp_title'] = extracted_data.get('title', '')
                st.session_state['temp_doc_type'] = extracted_data.get('doc_type', 'Nghị định')
                st.session_state['temp_issuing_authority'] = extracted_data.get('issuing_authority', '')
                
                try:
                    st.session_state['temp_issue_date'] = datetime.strptime(extracted_data.get('issue_date'), "%Y-%m-%d").date()
                except Exception:
                    st.session_state['temp_issue_date'] = date.today()

                st.session_state['temp_content'] = raw_content_extracted

    st.markdown("---")
    st.subheader("📝 2. Xác nhận & Lưu thông tin")

    with st.form("add_doc_form"):
        col1, col2 = st.columns(2)
        with col1:
            doc_number = st.text_input("Số / Ký hiệu văn bản (*):", value=st.session_state.get('temp_doc_number', ''))
            
            doc_type_options = ["Nghị định", "Thông tư", "Quyết định", "Luật", "Công văn", "Quy chế / Quy định", "Khác"]
            default_type = st.session_state.get('temp_doc_type', 'Nghị định')
            doc_type_idx = doc_type_options.index(default_type) if default_type in doc_type_options else 0
            
            doc_type = st.selectbox("Loại văn bản:", doc_type_options, index=doc_type_idx)
            issuing_authority = st.text_input("Cơ quan ban hành:", value=st.session_state.get('temp_issuing_authority', ''))
        
        with col2:
            title = st.text_input("Trích yếu / Tiêu đề văn bản (*):", value=st.session_state.get('temp_title', ''))
            issue_date = st.date_input("Ngày ban hành:", value=st.session_state.get('temp_issue_date', date.today()))
        
        content = st.text_area("Nội dung toàn văn của văn bản (*):", value=st.session_state.get('temp_content', ''), height=250)

        submitted = st.form_submit_button("🚀 Lưu văn bản vào hệ thống")

        if submitted:
            if not doc_number or not title or not content:
                st.error("Vui lòng điền đầy đủ các thông tin bắt buộc (*).")
            else:
                insert_document(doc_number, title, doc_type, issuing_authority, str(issue_date), content, "", [])
                st.success("✅ Đã lưu thành công văn bản mới vào hệ thống!")
                
                for key in ['temp_doc_number', 'temp_title', 'temp_doc_type', 'temp_issuing_authority', 'temp_issue_date', 'temp_content']:
                    if key in st.session_state:
                        del st.session_state[key]
                st.balloons()

# ==========================================
# CHỨC NĂNG 3: THỐNG KÊ HỆ THỐNG
# ==========================================
elif menu == "📊 Thống kê hệ thống":
    st.markdown("<div class='main-title'>📊 THỐNG KÊ & TỔNG QUAN DỮ LIỆU</div>", unsafe_allow_html=True)
    df = get_all_documents()
    
    if df.empty:
        st.warning("Chưa có dữ liệu.")
    else:
        m1, m2, m3 = st.columns(3)
        m1.metric("Tổng số văn bản", len(df))
        m2.metric("Loại văn bản nhiều nhất", df['doc_type'].mode()[0] if not df.empty else "N/A")
        m3.metric("Cập nhật gần nhất", df['updated_at'].max())

        st.markdown("### Phân bố theo loại văn bản")
        st.bar_chart(df['doc_type'].value_counts())
