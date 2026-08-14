
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import streamlit as st

from src.dashboard.tab_themes import inject_tab_theme


def _synthetic_events(days_ahead=7, n=40):
    now = datetime.now(timezone.utc)
    rows = []
    for i in range(n):
        event_date = now + timedelta(days=np.random.randint(0, days_ahead))
        time_utc = (datetime.min + timedelta(minutes=np.random.randint(0,1440))).time()
        rows.append({
            'date': event_date.strftime('%Y-%m-%d'),
            'time_utc': time_utc.strftime('%H:%M'),
            'country': np.random.choice(['US','EU','JP','UK','CN','AU']),
            'event': f"{np.random.choice(['GDP','CPI','Employment','PMI','Retail Sales'])} Release {i}",
            'importance': np.random.choice(['HIGH','MED','LOW'], p=[0.2,0.5,0.3]),
            'actual': round(np.random.uniform(0,5),2),
            'forecast': round(np.random.uniform(0,5),2),
            'previous': round(np.random.uniform(0,5),2),
            'surprise': 0,  # placeholder, will compute later
            'impact_on_market': np.random.choice(['Positive','Negative','Neutral']),
        })
    df = pd.DataFrame(rows)
    df['surprise'] = np.round(df['actual'] - df['forecast'],2)
    return df

def render_econ_calendar_tab() -> None:
    """Global Economic Calendar – sunset orange theme."""
    inject_tab_theme("📅 ECON CALENDAR")

    df = _synthetic_events()
    importance = st.selectbox('Filter by importance', options=['ALL','HIGH','MED','LOW'], index=0)
    if importance != 'ALL':
        df = df[df['importance']==importance]
    # color surprise cells
    def color_surprise(val):
        if val > 0:
            return 'color: #00ff00;'
        elif val < 0:
            return 'color: #ff0000;'
        return ''
    styled = df.style.applymap(lambda v: color_surprise(v), subset=['surprise'])
    st.dataframe(styled, use_container_width=True, hide_index=True)

    # Countdown for upcoming high impact events
    high_df = df[df['importance']=='HIGH']
    if not high_df.empty:
        now = datetime.now(timezone.utc)
        high_df['datetime'] = pd.to_datetime(high_df['date'] + ' ' + high_df['time_utc']).dt.tz_localize('UTC')
        high_df['minutes_to'] = (high_df['datetime'] - now).dt.total_seconds() // 60
        next_event = high_df.loc[high_df['minutes_to'].idxmin()]
        st.success(f"⏰ Next HIGH impact event in {int(next_event['minutes_to'])} minutes: {next_event['event']} ({next_event['country']})")
