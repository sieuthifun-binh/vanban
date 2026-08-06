import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, date
import json
import google.generativeai as genai
from pypdf import PdfReader
import docx

# ==========================================
# 1. CẤU HÌNH TRANG VÀ GIAO DIỆN CHÍNH
# ==========================================
st.set_page_config(
    page_title="Hệ Thống Quản Lý & Tra Cứu Văn Bản Thông Minh",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS cho giao diện chuyên nghiệp
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
# 3. TIỆN ÍCH TRÍ TUỆ NHÂN TẠO (AI) & ĐỌC FILE
# ==========================================
def extract_text_from_file(uploaded_file):
    """Trích xuất văn bản thô từ file PDF, DOCX hoặc TXT"""
    text = ""
    try:
        if uploaded_file.name.endswith('.pdf'):
            pdf_reader = PdfReader(uploaded_file)
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"
        elif uploaded_file.name.endswith('.docx'):
            doc = docx.Document(uploaded_file)
            for para in doc.paragraphs:
                text += para.text + "\n"
        elif uploaded_file.name.endswith('.txt'):
            text = uploaded_file.read().decode('utf-8')
    except Exception as e:
        st.error(f"Lỗi khi đọc file: {str(e)}")
    return text

def ai_extract_metadata(api_key, raw_text):
    """BỔ SUNG MỚI: AI Phân tích văn bản và tự động bóc tách các trường Metadata pháp lý"""
    if not api_key:
        st.warning("⚠️ Vui lòng nhập Gemini API Key ở thanh bên để dùng tính năng bóc tách tự động.")
        return {}
    
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = f"""
        Bạn là một chuyên gia quản lý văn bản hành chính và pháp lý. 
        Hãy đọc đoạn văn bản sau và bóc tách chính xác các thông tin metadata.

        Nội dung văn bản:
        {raw_text[:3000]}

        Yêu cầu trả về duy nhất một chuỗi JSON hợp lệ (không kèm theo văn bản giải thích nào khác) chứa các khóa (keys) sau:
        - "doc_number": Số / Ký hiệu văn bản (Ví dụ: "15/2023/NĐ-CP" hoặc "123/QĐ-UBND"). Nếu không thấy ghi "".
        - "title": Trích yếu hoặc Tiêu đề văn bản (Ví dụ: "Về việc quy định chi tiết..."). Nếu không thấy ghi "".
        - "doc_type": Loại văn bản, chọn 1 trong các giá trị sau ["Nghị định", "Thông tư", "Quyết định", "Luật", "Công văn", "Quy chế / Quy định", "Khác"].
        - "issuing_authority": Cơ quan ban hành (Ví dụ: "Chính phủ", "Bộ Tài chính"). Nếu không thấy ghi "".
        - "issue_date": Ngày ban hành định dạng YYYY-MM-DD (Ví dụ: "2023-05-15"). Nếu không xác định được ghi đúng ngày hôm nay dạng YYYY-MM-DD.

        Định dạng trả về mẫu:
        {{
            "doc_number": "123/QĐ-UBND",
            "title": "Về việc ban hành quy chế...",
            "doc_type": "Quyết định",
            "issuing_authority": "Ủy ban nhân dân tỉnh X",
            "issue_date": "2023-10-25"
        }}
        """
        response = model.generate_content(prompt)
        clean_json = response.text.strip().replace("```json", "").replace("```", "")
        return json.loads(clean_json)
    except Exception as e:
        st.error(f"Lỗi AI trích xuất thông tin: {str(e)}")
        return {}

def ai_summarize_content(api_key, doc_title, content):
    """Tóm tắt nội dung chính của văn bản bằng AI"""
    if not api_key:
        return "⚠️ Vui lòng cấu hình API Key ở thanh bên để sử dụng tính năng tóm tắt AI."
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = f"""
        Bạn là một chuyên gia pháp lý và quản lý văn bản chuyên nghiệp.
        Hãy tóm tắt ngắn gọn, chính xác các điểm quan trọng nhất của văn bản sau:
        Tên văn bản: {doc_title}
        Nội dung:
        {content}

        Yêu cầu:
        1. Tóm tắt theo các ý chính (dấu gạch đầu dòng).
        2. Nêu rõ quyền hạn, nghĩa vụ hoặc quy định cốt lõi nếu có.
        3. Ngôn ngữ súc tích, chuẩn phong cách hành chính - pháp lý.
        """
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Lỗi khi gọi AI: {str(e)}"

def ai_find_related_docs(api_key, current_title, current_content, existing_docs_df):
    """Tự động phân tích và gợi ý các văn bản liên quan trong hệ thống"""
    if existing_docs_df.empty or not api_key:
        return []
    
    docs_summary_list = []
    for idx, row in existing_docs_df.iterrows():
        docs_summary_list.append({
            "id": int(row['id']),
            "doc_number": row['doc_number'],
            "title": row['title']
        })

    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = f"""
        Dưới đây là một văn bản mới:
        Tiêu đề: {current_title}
        Nội dung: {current_content[:1500]}

        Danh sách các văn bản hiện có trong cơ sở dữ liệu:
        {json.dumps(docs_summary_list, ensure_ascii=False)}

        Hãy phân tích nội dung và chọn ra tối đa 3 ID văn bản trong danh sách trên có nội dung, chủ đề hoặc căn cứ liên quan nhất đến văn bản mới này.
        Chỉ trả về danh sách JSON chứa các ID số, ví dụ: [1, 4, 12]. Nếu không có văn bản liên quan, trả về [].
        """
        response = model.generate_content(prompt)
        cleaned_response = response.text.strip().replace("```json", "").replace("```", "")
        related_ids = json.loads(cleaned_response)
        return related_ids if isinstance(related_ids, list) else []
    except Exception:
        return []

# ==========================================
# 4. GIAO DIỆN CHÍNH & SIDEBAR
# ==========================================
st.sidebar.title("⚙️ Cấu hình & Điều hướng")
gemini_api_key = st.sidebar.text_input("Nhập Google Gemini API Key:", type="password")

menu = st.sidebar.radio(
    "Chức năng chính:",
    ["📖 Tra cứu & Đọc văn bản", "➕ Thêm mới văn bản", "📊 Thống kê hệ thống"]
)

st.sidebar.markdown("---")
st.sidebar.info("""
**Hệ Thống Quản Lý Văn Bản AI**
- Hỗ trợ lưu trữ & tra cứu nhanh
- Đọc nội dung trực quan
- Tóm tắt & Phân tích liên kết bằng AI
- Auto-extract Metadata từ File/Văn bản thô
""")

# ==========================================
# CHỨC NĂNG 1: TRA CỨU & ĐỌC VĂN BẢN (SPLIT VIEW)
# ==========================================
if menu == "📖 Tra cứu & Đọc văn bản":
    st.markdown("<div class='main-title'>⚖️ QUẢN LÝ & TRA CỨU HỆ THỐNG VĂN BẢN</div>", unsafe_allow_html=True)
    
    df = get_all_documents()

    if df.empty:
        st.warning("Hệ thống chưa có văn bản nào. Vui lòng chuyển sang mục 'Thêm mới văn bản' để tải lên!")
    else:
        # Bố cục 2 khung kế bên nhau
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
            st.subheader("📖 Khung đọc & Tóm tắt văn bản")
            
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

                tab_reader, tab_ai, tab_related = st.tabs(["📄 Nội dung văn bản", "🤖 Tóm tắt AI", "🔗 Văn bản liên quan"])

                with tab_reader:
                    st.text_area("Toàn văn nội dung:", value=doc['content'], height=450, disabled=True)

                with tab_ai:
                    st.info("🤖 **Tóm tắt nội dung chính tự động bởi AI:**")
                    st.write(doc['summary'] if doc['summary'] else "Chưa có bản tóm tắt cho văn bản này.")

                with tab_related:
                    st.write("🔗 **Các văn bản có nội dung/căn cứ liên quan:**")
                    try:
                        related_ids = json.loads(doc['related_doc_ids']) if doc['related_doc_ids'] else []
                        if related_ids:
                            related_docs = df[df['id'].isin(related_ids)]
                            for _, r_row in related_docs.iterrows():
                                st.markdown(f"- **[{r_row['doc_number']}]** {r_row['title']} *(Ban hành: {r_row['issue_date']})*")
                        else:
                            st.write("Chưa ghi nhận văn bản liên quan trực tiếp trong hệ thống.")
                    except Exception:
                        st.write("Không thể tải danh sách liên kết.")
            else:
                st.info("Vui lòng chọn một văn bản từ danh sách bên trái để đọc.")

# ==========================================
# CHỨC NĂNG 2: THÊM MỚI VĂN BẢN (CÓ AUTO-EXTRACT AI)
# ==========================================
elif menu == "➕ Thêm mới văn bản":
    st.markdown("<div class='main-title'>➕ CẬP NHẬT VĂN BẢN MỚI VÀO HỆ THỐNG</div>", unsafe_allow_html=True)

    # -------------------------------------------------------------
    # BỔ SUNG MỚI: MODULE NHẬP FILE HOẶC VĂN BẢN ĐỂ AI TỰ BÓC TÁCH
    # -------------------------------------------------------------
    st.subheader("📥 1. Nhập văn bản hoặc Tải file lên (Để AI tự bóc tách thông tin)")
    
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

    if st.button("🤖 Phân tích & Điền tự động bằng AI"):
        if not raw_content_extracted:
            st.warning("Vui lòng tải file hoặc dán nội dung văn bản trước khi bấm phân tích.")
        else:
            with st.spinner("AI đang đọc văn bản và bóc tách dữ liệu..."):
                extracted_data = ai_extract_metadata(gemini_api_key, raw_content_extracted)
                
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
                    st.success("✅ AI đã bóc tách xong! Hãy kiểm tra thông tin ở Form bên dưới.")

    st.markdown("---")
    st.subheader("📝 2. Xác nhận thông tin văn bản")

    # Form nhập liệu (Lấy giá trị mặc định từ Session State do AI điền)
    with st.form("add_doc_form"):
        col1, col2 = st.columns(2)
        with col1:
            doc_number = st.text_input(
                "Số / Ký hiệu văn bản (*):", 
                value=st.session_state.get('temp_doc_number', ''),
                placeholder="VD: 15/2023/NĐ-CP"
            )
            
            doc_type_options = ["Nghị định", "Thông tư", "Quyết định", "Luật", "Công văn", "Quy chế / Quy định", "Khác"]
            default_type = st.session_state.get('temp_doc_type', 'Nghị định')
            doc_type_idx = doc_type_options.index(default_type) if default_type in doc_type_options else 0
            
            doc_type = st.selectbox("Loại văn bản:", doc_type_options, index=doc_type_idx)
            
            issuing_authority = st.text_input(
                "Cơ quan ban hành:", 
                value=st.session_state.get('temp_issuing_authority', ''),
                placeholder="VD: Chính phủ / Bộ Tài chính"
            )
        
        with col2:
            title = st.text_input(
                "Trích yếu / Tiêu đề văn bản (*):", 
                value=st.session_state.get('temp_title', ''),
                placeholder="VD: Quy định chi tiết một số điều..."
            )
            issue_date = st.date_input(
                "Ngày ban hành:", 
                value=st.session_state.get('temp_issue_date', date.today())
            )
        
        content = st.text_area(
            "Nội dung toàn văn của văn bản (*):", 
            value=st.session_state.get('temp_content', ''),
            height=250, 
            placeholder="Nội dung sẽ được tự động điền nếu tải file..."
        )

        st.markdown("---")
        auto_ai = st.checkbox("Tự động Tóm tắt nội dung & Tìm văn bản liên quan bằng AI khi lưu", value=True)

        submitted = st.form_submit_button("🚀 Lưu văn bản vào hệ thống")

        if submitted:
            if not doc_number or not title or not content:
                st.error("Vui lòng điền đầy đủ các thông tin bắt buộc (*).")
            else:
                existing_df = get_all_documents()
                
                ai_summary = ""
                related_ids = []

                if auto_ai:
                    with st.spinner("AI đang tóm tắt nội dung và phân tích văn bản liên quan..."):
                        ai_summary = ai_summarize_content(gemini_api_key, title, content)
                        related_ids = ai_find_related_docs(gemini_api_key, title, content, existing_df)

                insert_document(doc_number, title, doc_type, issuing_authority, str(issue_date), content, ai_summary, related_ids)
                st.success("✅ Đã lưu thành công văn bản mới vào hệ thống!")
                
                # Reset bộ nhớ tạm sau khi lưu
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
