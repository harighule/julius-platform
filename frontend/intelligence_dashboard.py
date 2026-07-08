import streamlit as st
import pandas as pd
import plotly.express as px
import requests
from datetime import datetime

st.set_page_config(page_title="JULIUS Intelligence", page_icon="🧠", layout="wide")

st.markdown("""
<style>
    .main-header { font-size: 2.5rem; font-weight: 700; color: #00ff88; }
    .metric-card { background: #1a1a2e; padding: 20px; border-radius: 10px; border: 1px solid #2a2a4e; }
    .score-high { color: #00ff88; font-weight: 700; }
    .score-medium { color: #ffaa00; font-weight: 700; }
    .score-low { color: #ff4444; font-weight: 700; }
</style>
""", unsafe_allow_html=True)

API_BASE = "http://127.0.0.1:8000/api/intelligence"

st.title("🧠 JULIUS Intelligence Engine")
st.caption("Real-time business intelligence from open-source data · 0 API keys")

with st.sidebar:
    st.header("🎯 Controls")
    company_input = st.text_input("Company Symbol", "AAPL")
    if st.button("🚀 Generate Report", type="primary"):
        st.session_state['run_analysis'] = True
    st.divider()
    st.markdown("### 📊 Available Signals")
    signals = ["Purchase Intent", "Revenue Momentum", "Supply Chain Risk", 
               "Corporate Expansion", "AI Adoption", "Sector Rotation"]
    for s in signals:
        st.markdown(f"- {s}")

if st.session_state.get('run_analysis', False):
    with st.spinner("🧠 Analyzing data..."):
        try:
            response = requests.get(f"{API_BASE}/report?symbol={company_input}", timeout=30)
            if response.status_code == 200:
                data = response.json()
                if data['reports']:
                    report = data['reports'][0]
                    st.markdown(f"## {report['company']} ({report['symbol']})")
                    st.caption(f"Sector: {report['sector']} | Updated: {report['timestamp']}")
                    
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        pi = report['purchase_intent']
                        st.metric("🛒 Purchase Intent", f"{pi['score']:.0%}", delta=pi['confidence'])
                    with col2:
                        rm = report['revenue_momentum']
                        st.metric("📈 Revenue Momentum", rm['direction'], delta=rm['confidence'])
                    with col3:
                        sc = report['supply_chain']
                        st.metric("🔗 Supply Chain Risk", f"{sc['risk_score']:.0%}", delta=sc['status'])
                    with col4:
                        ai = report['ai_adoption']
                        st.metric("🤖 AI Adoption", f"{ai['adoption_score']:.0%}", delta=ai['gpu_demand'])
                    
                    st.divider()
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown("### 📊 Detailed Signals")
                        details = pd.DataFrame({
                            'Signal': ['Purchase Intent', 'Revenue Momentum', 'Supply Chain', 'AI Adoption', 'Expansion'],
                            'Score': [
                                report['purchase_intent']['score'],
                                report['revenue_momentum']['score'],
                                1 - report['supply_chain']['risk_score'],
                                report['ai_adoption']['adoption_score'],
                                report['corporate_expansion']['expansion_score']
                            ]
                        })
                        fig = px.bar(details, x='Signal', y='Score', color='Score', 
                                     color_continuous_scale='Viridis', title="Signal Scores")
                        st.plotly_chart(fig, use_container_width=True)
                    with col2:
                        st.markdown("### 🎯 Expansion Insights")
                        exp = report['corporate_expansion']
                        st.metric("Expansion Score", f"{exp['expansion_score']:.0%}")
                        st.write("**Likely Actions:**")
                        for action in exp['likely_actions']:
                            st.write(f"- {action.replace('_', ' ').title()}")
                    
                    st.divider()
                    st.markdown("### 🔄 Sector Rotation Signals")
                    sector_data = data.get('sector_rotation', {})
                    if sector_data:
                        sector_df = pd.DataFrame([
                            {'Sector': k, 'Score': v['score'], 'Signal': v['signal']}
                            for k, v in sector_data.items()
                        ])
                        fig = px.bar(sector_df, x='Sector', y='Score', color='Signal',
                                     color_discrete_map={'overweight':'#00ff88','neutral':'#ffaa00','underweight':'#ff4444'},
                                     title="Sector Rotation")
                        st.plotly_chart(fig, use_container_width=True)
                else:
                    st.error("No data found for that symbol.")
            else:
                st.error(f"API error: {response.status_code}. Is the backend running?")
        except Exception as e:
            st.error(f"Error: {str(e)}")
    st.session_state['run_analysis'] = False
else:
    st.info("Enter a company symbol and click 'Generate Report' to start analysis.")

st.divider()
st.caption("🧠 JULIUS Intelligence Engine v1.0 | Powered by Open-Source ML | No API Keys Required")
