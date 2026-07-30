"""
app.py — Hospital Readmission Risk Dashboard
----------------------------------------------
Run with:
    streamlit run dashboard/app.py

Reads data/modeling_dataset.csv (produced by src/load_data_for_modeling.py),
trains the same risk-tier classifier used in the notebook (cached so it only
trains once), and presents:
  - Headline KPIs
  - A state-level choropleth of % High-risk hospitals
  - Filterable hospital table
  - A hospital drill-down with the model's predicted risk tier + probability
"""

import os
import pandas as pd
import numpy as np
import streamlit as st
import plotly.express as px

from sklearn.model_selection import train_test_split
from sklearn.preprocessing import OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "modeling_dataset.csv")

FEATURES_CATEGORICAL = ["hospital_ownership", "hospital_type", "emergency_services"]
FEATURES_NUMERIC = ["hospital_overall_rating", "total_discharges", "conditions_reported"]
TARGET = "risk_tier"

st.set_page_config(page_title="Hospital Readmission Risk Dashboard", layout="wide")


# --------------------------------------------------------------------------
@st.cache_data
def load_data() -> pd.DataFrame:
    if not os.path.exists(DATA_PATH):
        st.error(
            f"Couldn't find {DATA_PATH}. Run "
            "`python src/load_data_for_modeling.py` first to generate it."
        )
        st.stop()
    return pd.read_csv(DATA_PATH)


@st.cache_resource
def train_model(df: pd.DataFrame):
    model_df = df.dropna(subset=FEATURES_CATEGORICAL + FEATURES_NUMERIC + [TARGET]).copy()

    X = model_df[FEATURES_CATEGORICAL + FEATURES_NUMERIC]
    y = model_df[TARGET]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=42, stratify=y
    )

    preprocessor = ColumnTransformer(
        transformers=[("cat", OneHotEncoder(handle_unknown="ignore"), FEATURES_CATEGORICAL)],
        remainder="passthrough",
    )
    pipeline = Pipeline([
        ("preprocess", preprocessor),
        ("model", LogisticRegression(max_iter=1000, class_weight="balanced")),
    ])
    pipeline.fit(X_train, y_train)

    report = classification_report(y_test, pipeline.predict(X_test), output_dict=True)
    return pipeline, report


# --------------------------------------------------------------------------
df = load_data()
model, report = train_model(df)

st.title("🏥 Hospital Readmission Risk Dashboard")
st.caption(
    "Built from CMS public data (Hospital General Information + Hospital "
    "Readmissions Reduction Program). Risk tier reflects how many tracked "
    "conditions a hospital exceeds expected readmission rates on."
)

# --------------------------------------------------------------------------
# Sidebar filters
# --------------------------------------------------------------------------
st.sidebar.header("Filters")

states = st.sidebar.multiselect(
    "State", options=sorted(df["state"].dropna().unique()), default=[]
)
ownerships = st.sidebar.multiselect(
    "Ownership type", options=sorted(df["hospital_ownership"].dropna().unique()), default=[]
)
tiers = st.sidebar.multiselect(
    "Risk tier", options=["High", "Medium", "Low"], default=["High", "Medium", "Low"]
)

filtered = df.copy()
if states:
    filtered = filtered[filtered["state"].isin(states)]
if ownerships:
    filtered = filtered[filtered["hospital_ownership"].isin(ownerships)]
if tiers:
    filtered = filtered[filtered["risk_tier"].isin(tiers)]

# --------------------------------------------------------------------------
# KPIs
# --------------------------------------------------------------------------
col1, col2, col3, col4 = st.columns(4)
col1.metric("Hospitals shown", f"{len(filtered):,}")
col2.metric("High risk", f"{(filtered['risk_tier'] == 'High').sum():,}")
col3.metric(
    "% High risk",
    f"{100 * (filtered['risk_tier'] == 'High').mean():.1f}%" if len(filtered) else "—",
)
col4.metric("States covered", filtered["state"].nunique())

st.divider()

# --------------------------------------------------------------------------
# State choropleth
# --------------------------------------------------------------------------
st.subheader("Share of High-risk hospitals by state")

state_summary = (
    df.groupby("state")
    .agg(
        total_hospitals=("facility_id", "count"),
        high_risk_hospitals=("risk_tier", lambda s: (s == "High").sum()),
    )
    .reset_index()
)
state_summary["pct_high_risk"] = (
    100 * state_summary["high_risk_hospitals"] / state_summary["total_hospitals"]
)

fig = px.choropleth(
    state_summary,
    locations="state",
    locationmode="USA-states",
    color="pct_high_risk",
    scope="usa",
    color_continuous_scale="Reds",
    hover_data={"total_hospitals": True, "high_risk_hospitals": True, "state": True},
    labels={"pct_high_risk": "% High risk"},
)
fig.update_layout(margin=dict(l=0, r=0, t=0, b=0), height=450)
st.plotly_chart(fig, use_container_width=True)

st.divider()

# --------------------------------------------------------------------------
# Hospital table
# --------------------------------------------------------------------------
st.subheader(f"Hospitals ({len(filtered):,} matching filters)")

display_cols = [
    "facility_name", "state", "hospital_ownership", "hospital_type",
    "hospital_overall_rating", "conditions_reported", "conditions_over_expected",
    "risk_tier",
]
st.dataframe(
    filtered[display_cols].sort_values("conditions_over_expected", ascending=False),
    use_container_width=True,
    hide_index=True,
)

st.divider()

# --------------------------------------------------------------------------
# Hospital drill-down / what-if
# --------------------------------------------------------------------------
st.subheader("Look up a hospital")

hospital_names = sorted(filtered["facility_name"].dropna().unique())
if hospital_names:
    selected_name = st.selectbox("Select a hospital", hospital_names)
    row = filtered[filtered["facility_name"] == selected_name].iloc[0]

    c1, c2 = st.columns([1, 1])
    with c1:
        st.markdown(f"**{row['facility_name']}**")
        st.write(f"State: {row['state']}")
        st.write(f"Ownership: {row['hospital_ownership']}")
        st.write(f"Type: {row['hospital_type']}")
        st.write(f"Overall star rating: {row['hospital_overall_rating']}")
        st.write(f"Conditions reported: {row['conditions_reported']}")
        st.write(f"Conditions over expected: {row['conditions_over_expected']}")

    with c2:
        input_row = pd.DataFrame([{
            "hospital_ownership": row["hospital_ownership"],
            "hospital_type": row["hospital_type"],
            "emergency_services": row["emergency_services"],
            "hospital_overall_rating": row["hospital_overall_rating"],
            "total_discharges": row["total_discharges"],
            "conditions_reported": row["conditions_reported"],
        }])
        pred = model.predict(input_row)[0]
        proba = model.predict_proba(input_row)[0]
        classes = model.classes_

        st.markdown("**Model prediction**")
        st.write(f"Predicted risk tier: **{pred}**")
        proba_df = pd.DataFrame({"risk_tier": classes, "probability": proba}) \
            .sort_values("probability", ascending=False)
        st.bar_chart(proba_df.set_index("risk_tier"))

        st.caption(
            "Note: this prediction uses only hospital characteristics "
            "(ownership, type, rating, size) — not the actual readmission "
            "outcomes — so it reflects what the model expects *before* "
            "seeing a hospital's real performance."
        )
else:
    st.info("No hospitals match the current filters.")

st.divider()

# --------------------------------------------------------------------------
# Model performance (collapsed by default so it doesn't clutter the main view)
# --------------------------------------------------------------------------
with st.expander("About the model / performance metrics"):
    st.write(
        "Logistic Regression trained on hospital characteristics only "
        "(ownership, type, star rating, discharge volume, conditions "
        "reported) to predict risk tier. Evaluated on a held-out 25% test set."
    )
    report_df = pd.DataFrame(report).transpose().round(2)
    st.dataframe(report_df, use_container_width=True)
    st.caption(
        "This dataset does not include CMS's official penalty dollar amounts "
        "(published in a separate supplemental file) — risk tier is used as "
        "a proxy for financial exposure."
    )