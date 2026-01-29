import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from sklearn.preprocessing import MinMaxScaler
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense, Dropout
import datetime as dt

# Cache to avoid re-training every time
@st.cache_resource(show_spinner=False)
def get_data_and_model(ticker):
    end = dt.date.today()
    start = end - dt.timedelta(days=2000)
    df = yf.download(ticker, start=start, end=end, progress=False)
    if df.empty or len(df) < 100:
        return None, None, None
    
    close_prices = df['Close'].values.reshape(-1, 1)
    scaler = MinMaxScaler(feature_range=(0, 1))
    scaled_data = scaler.fit_transform(close_prices)
    
    look_back = 60
    X, y = [], []
    for i in range(look_back, len(scaled_data)):
        X.append(scaled_data[i-look_back:i, 0])
        y.append(scaled_data[i, 0])
    
    X = np.array(X).reshape((len(X), look_back, 1))
    y = np.array(y)
    
    split = int(0.8 * len(X))
    X_train, y_train = X[:split], y[:split]
    
    model = Sequential()
    model.add(LSTM(50, return_sequences=True, input_shape=(look_back, 1)))
    model.add(Dropout(0.2))
    model.add(LSTM(50))
    model.add(Dropout(0.2))
    model.add(Dense(1))
    model.compile(optimizer='adam', loss='mean_squared_error')
    model.fit(X_train, y_train, epochs=10, batch_size=32, verbose=0)
    
    return df, scaler, model

st.set_page_config(page_title="NSE Stock Predictor", layout="wide")
st.title("Indian Stock Market Price Prediction (NSE) - LSTM Demo")
st.caption("Educational only • Not financial advice")

stocks_dict = {
    "Reliance Industries": "RELIANCE.NS",
    "TCS": "TCS.NS",
    "HDFC Bank": "HDFCBANK.NS",
    "Infosys": "INFY.NS",
    "Nifty 50 Index": "^NSEI"
}

selected = st.selectbox("Select Stock", list(stocks_dict.keys()))
ticker = stocks_dict[selected]

future_days = st.slider("Predict next days?", 1, 30, 10)

if st.button("Generate Prediction"):
    with st.spinner("Loading data + training model..."):
        df, scaler, model = get_data_and_model(ticker)
        if df is None:
            st.error("Data issue — try another stock.")
        else:
            # Historical chart
            fig_hist = go.Figure(go.Scatter(x=df.index[-400:], y=df['Close'][-400:], mode='lines', name='Historical'))
            fig_hist.update_layout(title=f"{selected} Historical", height=400)
            st.plotly_chart(fig_hist, use_container_width=True)
            
            # Predict future
            last_seq = scaler.transform(df['Close'][-60:].values.reshape(-1, 1))
            batch = last_seq.reshape(1, 60, 1)
            preds_scaled = []
            for _ in range(future_days):
                p = model.predict(batch, verbose=0)
                preds_scaled.append(p[0, 0])
                batch = np.roll(batch, -1, axis=1)
                batch[0, -1, 0] = p[0, 0]
            
            preds = scaler.inverse_transform(np.array(preds_scaled).reshape(-1, 1))
            
            future_dates = pd.date_range(df.index[-1] + pd.Timedelta(1, 'D'), periods=future_days)
            pred_df = pd.DataFrame({'Date': future_dates.strftime('%Y-%m-%d'), 'Predicted ₹': preds.flatten().round(2)})
            st.subheader(f"Next {future_days} Days Predictions")
            st.dataframe(pred_df)
            
            fig_pred = go.Figure()
            fig_pred.add_trace(go.Scatter(x=df.index[-200:], y=df['Close'][-200:], mode='lines', name='Historical'))
            fig_pred.add_trace(go.Scatter(x=future_dates, y=preds.flatten(), mode='lines', name='Predicted', line=dict(dash='dash')))
            fig_pred.update_layout(title="Forecast", height=400)
            st.plotly_chart(fig_pred, use_container_width=True)
