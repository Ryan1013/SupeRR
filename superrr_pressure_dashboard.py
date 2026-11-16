# ------------------------------------------------------------
# SupeRR Selector Season 2 | Pressure Scale Dashboard
# Reads batter_pressure_ratings.csv and bowler_pressure_ratings.csv directly from the runtime
# ------------------------------------------------------------
import streamlit as st
import pandas as pd
import numpy as np
import re
from pathlib import Path
import warnings

st.set_page_config(page_title="SupeRR | Pressure Scale", page_icon="🏏", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Space+Grotesk:wght@500;600;700&display=swap');
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
.stApp { background: radial-gradient(circle at 10% 0%, #14243b 0%, #0b1220 42%, #080d16 100%); color: #e8eef8; }
.block-container { padding-top: 2rem; max-width: 1500px; }
.hero { padding: 26px 30px; border: 1px solid #263952; border-radius: 22px; background: linear-gradient(115deg, rgba(24,42,67,.95), rgba(13,23,39,.92)); box-shadow: 0 18px 50px rgba(0,0,0,.22); }
.hero-kicker { color: #6ee7c5; font-size: 12px; font-weight: 700; letter-spacing: 2.5px; text-transform: uppercase; }
.hero-title { font-family: 'Space Grotesk'; font-size: 38px; font-weight: 700; letter-spacing: -1.4px; color: #f4f8ff; margin: 5px 0 2px; }
.hero-sub { color: #a8b8ce; font-size: 15px; }
.panel { background: rgba(17,29,47,.82); border: 1px solid #26364d; border-radius: 18px; padding: 20px 22px; }
.metric-card { background: linear-gradient(145deg,#17263b,#101a2b); border: 1px solid #2a3b55; border-radius: 16px; padding: 17px 19px; min-height: 105px; }
.metric-label { color: #91a5bf; font-size: 12px; letter-spacing: 1px; text-transform: uppercase; font-weight: 700; }
.metric-value { color: #f4f8ff; font-family: 'Space Grotesk'; font-size: 29px; font-weight: 700; margin-top: 7px; }
.metric-note { color: #7d91ad; font-size: 12px; margin-top: 2px; }
.section-title { font-family: 'Space Grotesk'; font-size: 20px; font-weight: 700; color: #eaf2ff; margin: 2px 0 12px; }
.small-note { color: #8297b4; font-size: 12px; }
div[data-testid="stSelectbox"] label, div[data-testid="stMultiSelect"] label { color: #c8d6e8 !important; font-weight: 600; }
[data-testid="stMetric"] { background: #142137; border: 1px solid #2b3d57; padding: 15px; border-radius: 14px; }
[data-testid="stMetricLabel"] { color: #9cb0ca !important; }
[data-testid="stMetricValue"] { color: #f1f6ff !important; font-family: 'Space Grotesk'; }
hr { border-color: #26364d; }
</style>
""", unsafe_allow_html=True)

CATS = ["Elite", "Good", "Satisfactory", "Unsatisfactory"]
CAT_COLORS = {"Elite":"#65e6bd", "Good":"#79b8ff", "Satisfactory":"#ffc96b", "Unsatisfactory":"#ff8293"}

def category_from_pct(x):
    if pd.isna(x):
        return "Unrated"
    if x > 90:
        return "Elite"
    if x > 80:
        return "Good"
    if x > 70:
        return "Satisfactory"
    return "Unsatisfactory"

def clean_rating_file(file_path, role):
    df = pd.read_csv(file_path)
    # Allow the canonical evaluator outputs, plus common naming variations.
    name_col = next((c for c in ["player_name", "name", "Player", "player"] if c in df.columns), None)
    id_col = "batter_id" if role == "Batting" else "bowler_id"
    if name_col is None:
        name_col = id_col if id_col in df.columns else None
    if name_col is None or "pressure_rating" not in df.columns:
        raise ValueError(f"{role} file needs a player_name (or {id_col}) column and pressure_rating.")
    df["Player"] = df[name_col].astype(str).str.strip()
    df["Pressure Percentile"] = pd.to_numeric(df["pressure_rating"], errors="coerce")

    # Minimum sample-size eligibility: fewer than 100 balls is unrated.
    sample_col = "balls_faced" if role == "Batting" else "legal_balls"
    if sample_col in df.columns:
        df[sample_col] = pd.to_numeric(df[sample_col], errors="coerce")
        low_sample = df[sample_col] < 100
        df.loc[low_sample, "Pressure Percentile"] = np.nan
    else:
        low_sample = pd.Series(False, index=df.index)

    df["Category"] = df["Pressure Percentile"].apply(category_from_pct)
    df.loc[low_sample, "Category"] = "Unsatisfactory"
    metric_map = ({"Batting Average":"batting_average", "Strike Rate":"strike_rate"} if role == "Batting"
                  else {"Bowling Average":"bowling_average", "Economy Rate":"economy_rate"})
    for display, source in metric_map.items():
        if source in df.columns:
            df[display] = pd.to_numeric(df[source], errors="coerce")
        else:
            df[display] = np.nan
    df["Role"] = role
    return df

st.markdown("""
<div class="hero">
  <div class="hero-kicker">SupeRR Selector · Season 2</div>
  <div class="hero-title">PRESSURE SCALE <span style="color:#6ee7c5">//</span> PLAYER LAB</div>
  <div class="hero-sub">Explore player pressure percentiles, raw performance metrics and category tiers.</div>
</div>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("### 🎛️ Filters")
    category_selection = st.multiselect("Player Category", CATS, default=[], help="Leave empty to include every category.")
    logic = st.radio("", ["OR", "AND"], horizontal=True,
                     help="When 'All' option is selected in Player Pool then OR: player qualifies in either role, AND: player must qualify in both batting and bowling.")
    role_view = st.radio("Player Pool", ["All", "Batters", "Bowlers"], index=0)

# Read both rating CSVs directly from the same runtime/environment as this app.
BAT_CSV = Path(__file__).resolve().parent / "batter_pressure_ratings.csv"
BOWL_CSV = Path(__file__).resolve().parent / "bowler_pressure_ratings.csv"

try:
    if not BAT_CSV.exists():
        raise FileNotFoundError(f"Missing file: {BAT_CSV}")
    if not BOWL_CSV.exists():
        raise FileNotFoundError(f"Missing file: {BOWL_CSV}")
    batting = clean_rating_file(BAT_CSV, "Batting")
    bowling = clean_rating_file(BOWL_CSV, "Bowling")
except Exception as e:
    st.error(f"Could not load rating CSVs: {e}")
    st.info("Place both CSV files in the same directory as superrr_pressure_dashboard.py.")
    st.stop()

all_data = pd.concat([batting, bowling], ignore_index=True, sort=False)
all_data = all_data[all_data["Player"].notna() & all_data["Player"].ne("")]

# Build player eligibility from selected categories and role pool.
players = sorted(all_data["Player"].unique().tolist(), key=str.casefold)
if role_view == "Batters": players = sorted(batting["Player"].dropna().unique().tolist(), key=str.casefold)
if role_view == "Bowlers": players = sorted(bowling["Player"].dropna().unique().tolist(), key=str.casefold)

if category_selection:
    eligible = []
    for player in players:
        pbat = batting[batting.Player == player]
        pbowl = bowling[bowling.Player == player]
        bat_match = bool(len(pbat) and pbat.iloc[0]["Category"] in category_selection)
        bowl_match = bool(len(pbowl) and pbowl.iloc[0]["Category"] in category_selection)
        if role_view == "Batters": ok = bat_match
        elif role_view == "Bowlers": ok = bowl_match
        elif logic == "OR": ok = bat_match or bowl_match
        else:
            # AND means a player must have both role records and both must be in selected category set.
            ok = bool(len(pbat) and len(pbowl) and bat_match and bowl_match)
        if ok: eligible.append(player)
    players = eligible

# Sort filtered player list by the highest relevant pressure rating.
def player_sort_score(player):
    vals=[]
    if role_view != "Bowlers":
        x=batting.loc[batting.Player==player,"Pressure Percentile"]
        if len(x): vals.extend(x.dropna().tolist())
    if role_view != "Batters":
        x=bowling.loc[bowling.Player==player,"Pressure Percentile"]
        if len(x): vals.extend(x.dropna().tolist())
    return max(vals) if vals else -1
players = sorted(players, key=lambda p: (-player_sort_score(p), p.casefold()))

col1, col2, col3 = st.columns([1.15, 1, 1])
with col1:
    st.markdown(
    '<div class="section-title">🔎 Player Selector '
    '<span style="font-size:10px; font-weight:400;">(descending order of pressure ratings)</span>'
    '</div>',
    unsafe_allow_html=True
    )
    selected_player = st.selectbox("Player (filtered & pressure-ranked)", players, index=0 if players else None,
                                   placeholder="Choose a player…", label_visibility="collapsed")
with col2:
    st.markdown('<div class="section-title">🏷️ Tier Key</div>', unsafe_allow_html=True)
    st.markdown(
    "<span style='color:#65e6bd'>● Elite >90</span> &nbsp; "
    "<span style='color:#79b8ff'>● 90≥Good>80</span><br>"
    "<span style='color:#ffc96b'>● 80≥Satisfactory>70</span> &nbsp; "
    "<span style='color:#ff8293'>● Unsatisfactory ≤70</span>",
    unsafe_allow_html=True
    )
with col3:
    st.markdown('<div class="section-title">📌 Current View</div>', unsafe_allow_html=True)
    st.markdown(f"<div class='small-note'>{len(players):,} players available · {len(category_selection) if category_selection else 'All'} category filter(s)</div>", unsafe_allow_html=True)

if not players:
    st.warning("No players match these filters. Try changing the category selection, OR/AND logic, or player pool.")
    st.stop()

st.markdown("---")
if selected_player:
    b_row = batting[batting.Player == selected_player]
    w_row = bowling[bowling.Player == selected_player]
    bat_exists, bowl_exists = bool(len(b_row)), bool(len(w_row))
    bat_row = b_row.iloc[0] if bat_exists else None
    bowl_row = w_row.iloc[0] if bowl_exists else None

    st.markdown(f"<div class='section-title'>PLAYER PROFILE <span style='color:#6ee7c5'>/</span> {selected_player}</div>", unsafe_allow_html=True)
    left, right = st.columns(2, gap="large")
    with left:
        st.markdown("<div class='panel'>", unsafe_allow_html=True)
        st.markdown("### 🏏 Batting Pressure Rating")
        if bat_exists:
            pct=bat_row["Pressure Percentile"]
            cat=bat_row["Category"]
            if pd.isna(pct):
                st.markdown(f"<div style='font-size:42px;font-family:Space Grotesk;font-weight:700;color:{CAT_COLORS.get(cat,'#eaf2ff')}'>—<span style='font-size:18px;color:#8ea3bd'> / 100</span></div><div style='font-weight:700;color:{CAT_COLORS.get(cat,'#eaf2ff')};font-size:16px'>{cat}</div>", unsafe_allow_html=True)
                st.caption("Pressure percentile undefined · fewer than 100 balls faced")
            else:
                pct=float(pct)
                st.markdown(f"<div style='font-size:42px;font-family:Space Grotesk;font-weight:700;color:{CAT_COLORS.get(cat,'#eaf2ff')}'>{pct:.2f}<span style='font-size:18px;color:#8ea3bd'> / 100</span></div><div style='font-weight:700;color:{CAT_COLORS.get(cat,'#eaf2ff')};font-size:16px'>{cat}</div>", unsafe_allow_html=True)
                st.progress(max(0,min(100,int(round(pct))))/100)
            m1,m2=st.columns(2)
            m1.metric("Batting Average", "—" if pd.isna(bat_row["Batting Average"]) else f"{bat_row['Batting Average']:.2f}", help="Raw, un-pressure-adjusted batting average")
            m2.metric("Strike Rate", "—" if pd.isna(bat_row["Strike Rate"]) else f"{bat_row['Strike Rate']:.2f}", help="Raw, un-pressure-adjusted strike rate")
        else: st.info("No batting pressure rating available for this player.")
        st.markdown("</div>", unsafe_allow_html=True)
    with right:
        st.markdown("<div class='panel'>", unsafe_allow_html=True)
        st.markdown("### 🎯 Bowling Pressure Rating")
        if bowl_exists:
            pct=bowl_row["Pressure Percentile"]
            cat=bowl_row["Category"]
            if pd.isna(pct):
                st.markdown(f"<div style='font-size:42px;font-family:Space Grotesk;font-weight:700;color:{CAT_COLORS.get(cat,'#eaf2ff')}'>—<span style='font-size:18px;color:#8ea3bd'> / 100</span></div><div style='font-weight:700;color:{CAT_COLORS.get(cat,'#eaf2ff')};font-size:16px'>{cat}</div>", unsafe_allow_html=True)
                st.caption("Pressure percentile undefined · fewer than 100 legal balls")
            else:
                pct=float(pct)
                st.markdown(f"<div style='font-size:42px;font-family:Space Grotesk;font-weight:700;color:{CAT_COLORS.get(cat,'#eaf2ff')}'>{pct:.2f}<span style='font-size:18px;color:#8ea3bd'> / 100</span></div><div style='font-weight:700;color:{CAT_COLORS.get(cat,'#eaf2ff')};font-size:16px'>{cat}</div>", unsafe_allow_html=True)
                st.progress(max(0,min(100,int(round(pct))))/100)
            m1,m2=st.columns(2)
            m1.metric("Bowling Average", "—" if pd.isna(bowl_row["Bowling Average"]) else f"{bowl_row['Bowling Average']:.2f}", help="Raw, un-pressure-adjusted bowling average; lower is better")
            m2.metric("Economy Rate", "—" if pd.isna(bowl_row["Economy Rate"]) else f"{bowl_row['Economy Rate']:.2f}", help="Raw, un-pressure-adjusted economy rate; lower is better")
        else: st.info("No bowling rating available for this player.")
        st.markdown("</div>", unsafe_allow_html=True)

    with st.expander("View the player's underlying rating row"):
        tabs=st.tabs(["Batting row", "Bowling row"])
        with tabs[0]:
            if bat_exists: st.dataframe(b_row, use_container_width=True, hide_index=True)
            else: st.write("No batting row.")
        with tabs[1]:
            if bowl_exists: st.dataframe(w_row, use_container_width=True, hide_index=True)
            else: st.write("No bowling row.")

st.markdown("---")
st.markdown('<div class="section-title">📋 Category Leaderboard</div>', unsafe_allow_html=True)

# Build leaderboard from the current filtered player pool. The sort score must
# use the pressure rating for the selected category/role—not the player's other
# role rating, which could otherwise incorrectly move them up the table.
leader_rows = []
for player in players:
    br = batting[batting["Player"] == player]
    wr = bowling[bowling["Player"] == player]
    bat = br.iloc[0] if not br.empty else None
    bowl = wr.iloc[0] if not wr.empty else None

    bat_pct = float(bat["Pressure Percentile"]) if bat is not None and pd.notna(bat["Pressure Percentile"]) else np.nan
    bowl_pct = float(bowl["Pressure Percentile"]) if bowl is not None and pd.notna(bowl["Pressure Percentile"]) else np.nan

    # Score only the role(s) relevant to Player Pool and selected category.
    sort_candidates = []
    if role_view != "Bowlers" and bat is not None:
        if not category_selection or bat["Category"] in category_selection:
            sort_candidates.append(bat_pct)
    if role_view != "Batters" and bowl is not None:
        if not category_selection or bowl["Category"] in category_selection:
            sort_candidates.append(bowl_pct)
    sort_pressure = max((v for v in sort_candidates if pd.notna(v)), default=np.nan)

    leader_rows.append({
        "Player": player,
        "Batting Category": bat["Category"] if bat is not None else "—",
        "Batting Pressure %ile": bat_pct,
        "Batting Average": bat["Batting Average"] if bat is not None else np.nan,
        "Strike Rate": bat["Strike Rate"] if bat is not None else np.nan,
        "Bowling Category": bowl["Category"] if bowl is not None else "—",
        "Bowling Pressure %ile": bowl_pct,
        "Bowling Average": bowl["Bowling Average"] if bowl is not None else np.nan,
        "Economy Rate": bowl["Economy Rate"] if bowl is not None else np.nan,
        "_Sort Pressure": sort_pressure,
    })

if leader_rows:
    leader = pd.DataFrame(leader_rows)
    leader["_Sort Pressure"] = pd.to_numeric(leader["_Sort Pressure"], errors="coerce")
    leader = leader.sort_values("_Sort Pressure", ascending=False, na_position="last", kind="stable")
    leader = leader.drop(columns="_Sort Pressure")
    st.dataframe(
        leader,
        use_container_width=True,
        hide_index=True,
        height=440,
        column_config={
            "Batting Pressure %ile": st.column_config.ProgressColumn(
                "Batting Pressure %ile", min_value=0, max_value=100, format="%.2f"
            ),
            "Bowling Pressure %ile": st.column_config.ProgressColumn(
                "Bowling Pressure %ile", min_value=0, max_value=100, format="%.2f"
            ),
        },
    )
else:
    st.info("The leaderboard is empty because no players remain after the current filters.")
