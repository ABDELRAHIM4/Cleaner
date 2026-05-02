import streamlit as st
import pandas as pd
import stripe
from pymongo import MongoClient
import uuid, platform, hashlib

client = MongoClient(st.secrets['mongo_uri'])
db = client['csv_cleaner']
users_collection = db['users']

st.set_page_config(page_title="CSV Cleaner", page_icon=":smiley:")
st.title('CSV Cleaner :smiley:')
st.markdown('''
This app allows you to clean your CSV files by removing empty rows and columns, and filling missing values with a specified value.
''')
if 'user_email' not in st.session_state:
    st.subheader("login or sign up")
    email = st.text_input("enter your email")
    if email:
        if '@' not in email or '.' not in email:
            st.error("Enter valid email")
        else:
            user_data = users_collection.find_one({ "email": email.lower()})
            if not user_data:
                users_collection.insert_one({
                    "email": email.lower(),
                    "free_uses_left": 3,
                    "paid_uses": 0,
                    "created_at": pd.Timestamp.now()
                })
                st.session_state['user_email'] = email.lower()
                st.session_state["free_uses_left"] = 3
                st.session_state["paid_uses"] = 0
                st.success("welcome")
                st.rerun()
            else:
                st.session_state['user_email'] = email.lower()
                st.session_state["free_uses_left"] = user_data["free_uses_left"]
                st.session_state["paid_uses"] = user_data["paid_uses"]
                st.success("welcome back")
                st.rerun()
    else:
        st.info("Enter email")
        st.stop()
user_data =  users_collection.find_one({ "email": st.session_state['user_email']})
if user_data:
    st.session_state["free_uses_left"] = user_data["free_uses_left"]
    st.session_state["paid_uses"] = user_data["paid_uses"]

STRIPE_READY = False
PAYMENT_LINK = "https://buy.stripe.com/test_eVq5kFakObqqaMDafOdfG01"
PRICE = 0.50


try:
    stripe.api_key = st.secrets["stripe_api_key"]
    published_key = st.secrets["stripe_publishable_key"]
    STRIPE_READY = True
except:
    STRIPE_READY = False

if 'processing_completed' not in st.session_state:
    st.session_state['processing_completed'] = False

    
    
PRICE_PER_USE = 0.50
PRICE_IN_CENTS = 50
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("free uses left", st.session_state['free_uses_left'])
with col2:
    st.metric("paid uses", st.session_state['paid_uses'])
with col3:
    if STRIPE_READY:
        st.metric("price per use", f"{PRICE_PER_USE}")
    else:
        if st.session_state['free_uses_left'] > 0:
            st.metric("status", "freedemo")
        elif st.session_state['paid_uses'] > 0:
            st.metric("status", "has credits")
        else:
            st.metric("status", "need to pay")
with col4:
    total_uses= st.session_state['free_uses_left'] + st.session_state['paid_uses']
    st.metric("total uses", total_uses)

st.markdown("---")
def create_checkout_session():
    if not STRIPE_READY:
        st.error("not ready")
        return None
    try:
        current_free = st.session_state['free_uses_left']
        current_paid = st.session_state['paid_uses']
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data':
                {
                    'currency': 'usd',
                    'product_data': {
                        'name': 'CSV Cleaner Usage',
                    },
                    'unit_amount': PRICE_IN_CENTS,
                },
                'quantity': 1,
                
            }],
            mode='payment',
            success_url = st.secrets.get('app_url', "https://filecleanercsv.streamlit.app/")
            + f"?free={current_free}&paid={current_paid}&payment=success",
            cancel_url = st.secrets.get('app_url', "https://filecleanercsv.streamlit.app/")
            + f"?free={current_free}&paid={current_paid}&payment=cancel",
        )
        return session.url
    except Exception as e:
        st.error("Error creating checkout session")
        return None
def check_payment_status():
    query_params = st.query_params
    if query_params.get("payment") == 'success':
        users_collection.update_one(
            {"email": st.session_state['user_email']}
            ,{"$inc": {"paid_uses": 1}}
        )
        st.session_state['paid_uses'] += 1
        st.success("payment successful you have 1 paid use now")
        st.query_params.clear()
        st.rerun()
    elif query_params.get("payment") == 'cancel':
        st.info("payment cancelled")
        st.query_params.clear()
check_payment_status()
uploaded_file = st.file_uploader("Upload your CSV file", type=["csv", "xlsx"])
if uploaded_file is not None:
    if uploaded_file.name.endswith('.csv'):
        df = pd.read_csv(uploaded_file)
    elif uploaded_file.name.endswith('.xlsx'):
        df = pd.read_excel(uploaded_file)
    st.subheader('Original Data')
    st.dataframe(df)
    col1, col2, col3 = st.columns(3)
    col1.metric("Empty Rows", df.isnull().all(axis=1).sum())
    col2.metric("Empty Columns", df.isnull().all(axis=0).sum())
    col3.metric("Total Missing Values", df.isnull().sum().sum())
    clean_missing = st.radio("Handle Missing Values", ("Fill with Mean", "Drop Rows/Columns", "Fill with Unknown"))
    if clean_missing == "Fill with Mean":
        df = df.fillna(df.mean(numeric_only=True))
    elif clean_missing == "Fill with Unknown":
        df = df.fillna("Unknown")
    elif clean_missing == "Drop Rows/Columns":
        df = df.dropna(how='all')
        df = df.dropna(how='all', axis=1)
    else:
        st.warning("Please select a method to handle missing values.")

    st.subheader('Cleaned Data')
    st.dataframe(df)
    free_use = st.session_state['free_uses_left'] > 0
    paid_use = st.session_state['paid_uses'] > 0
    if free_use or paid_use:
        csv = df.to_csv(index=False).encode('utf-8')
        download_csv = st.download_button(
            label="Download Cleaned CSV",
            data=csv,
            file_name='cleaned_data.csv',
            mime='text/csv',
        )
        import io
        excel_buffer = io.BytesIO()

        df.to_excel(excel_buffer, index=False)
        download_excel = st.download_button(
            label="Download Cleaned Excel",
            data=excel_buffer.getvalue(),
            file_name='cleaned_data.xlsx',
            mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        if download_csv or download_excel:
            if st.session_state['free_uses_left'] > 0:
               users_collection.update_one(
            {"email": st.session_state['user_email']}
            ,{"$inc": {"free_uses_left": -1}}
        )
               st.session_state['free_uses_left'] -= 1
               st.success(f"{st.session_state['free_uses_left']} free uses left")
            elif st.session_state['paid_uses'] > 0:
                users_collection.update_one(
            {"email": st.session_state['user_email']}
            ,{"$inc": {"paid_uses": -1}}
                )
                st.session_state['paid_uses'] -= 1
                st.success(f"{st.session_state['paid_uses']} paid uses left")
                st.balloons()
            st.rerun()
            
    else:
        st.error(f"no uses left pay ${PRICE_PER_USE} FOR 1 USE")
        checkout_url = create_checkout_session()
        if checkout_url:
            st.link_button(
                f"pay ${PRICE_PER_USE}",
                checkout_url
            )
        st.info(""" click the button above to purchase""")
                        
else:
    st.info('Please upload a CSV or Excel file to get started.')
