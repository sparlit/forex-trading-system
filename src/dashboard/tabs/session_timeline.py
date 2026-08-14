
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st


# Simulated session data – normally imported from src.strategy.sessions.all_sessions
def _load_sessions():
    sessions = [
        {'name':'Forex','market_type':'FX','start_utc':'00:00','end_utc':'24:00','is_active':True},
        {'name':'Equity US','market_type':'Equity','start_utc':'13:30','end_utc':'20:00','is_active':False},
        {'name':'Futures','market_type':'Futures','start_utc':'20:00','end_utc':'04:00','is_active':False},
    ]
    return pd.DataFrame(sessions)

def render_session_timeline_tab() -> None:
    """GMT session timelines with countdown – teal / cyan theme."""
    st.markdown(f"""{header_template.format(colors='#008080, #00ffff', title='Session Timelines & Overlaps')}""", unsafe_allow_html=True)

    df = _load_sessions()
    now = datetime.utcnow()
    # Compute countdown in minutes
    def countdown(row):
        start = datetime.strptime(row['start_utc'], '%H:%M').replace(year=now.year, month=now.month, day=now.day)
        end = datetime.strptime(row['end_utc'], '%H:%M').replace(year=now.year, month=now.month, day=now.day)
        # handle overnight sessions where end < start
        if end <= start:
            end += timedelta(days=1)
        if start <= now <= end:
            remaining = (end - now).total_seconds() / 60
            return f"🟢 Open – {int(remaining)} min left"
        else:
            # time until next open
            if now < start:
                minutes = (start - now).total_seconds() / 60
            else:
                # next day's start
                minutes = ((start + timedelta(days=1)) - now).total_seconds() / 60
            return f"🔴 Closed – opens in {int(minutes)} min"
    df['status'] = df.apply(countdown, axis=1)
    st.dataframe(df[['name','market_type','start_utc','end_utc','status']])

    st.subheader('Session Overlap Directory')
    # Simple overlap calculation for demo purposes
    overlaps = []
    for i, row_i in df.iterrows():
        for j, row_j in df.iterrows():
            if i >= j:
                continue
            # compute overlap minutes (naïve)
            s1 = datetime.strptime(row_i['start_utc'], '%H:%M')
            e1 = datetime.strptime(row_i['end_utc'], '%H:%M')
            s2 = datetime.strptime(row_j['start_utc'], '%H:%M')
            e2 = datetime.strptime(row_j['end_utc'], '%H:%M')
            # normalize to minutes of day
            def mins(t):
                return t.hour*60 + t.minute
            s1m, e1m = mins(s1), mins(e1)
            s2m, e2m = mins(s2), mins(e2)
            # handle overnight by adding 1440 where needed
            if e1m <= s1m: e1m += 1440
            if e2m <= s2m: e2m += 1440
            overlap = max(0, min(e1m, e2m) - max(s1m, s2m))
            if overlap > 0:
                overlaps.append({
                    'Session A': row_i['name'],
                    'Session B': row_j['name'],
                    'Overlap (min)': overlap,
                })
    if overlaps:
        st.table(pd.DataFrame(overlaps))
    else:
        st.info('No overlaps detected in the demo data.')
