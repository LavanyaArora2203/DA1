"""
load_data_for_modeling.py
-------------------------

Loads hospital and HRRP readmission data from MySQL,
creates a modeling-ready dataset, assigns a risk tier,
and optionally saves it as a CSV.

Usage:

python scripts/load_data_for_modeling.py

or

python scripts/load_data_for_modeling.py \
    --out data/modeling_dataset.csv

or inside Jupyter:

from load_data_for_modeling import load_modeling_dataset

df = load_modeling_dataset()
"""

from pathlib import Path
import argparse

import pandas as pd
from sqlalchemy import create_engine


# ==========================================================
# DATABASE CONNECTION
# ==========================================================

DB_URL = "mysql+pymysql://root:Lavi%40220307@localhost/hospital_readmissions"

# If your password contains @, #, :, / etc.,
# URL encode it or use sqlalchemy.engine.URL.create()


# ==========================================================
# LOAD DATA
# ==========================================================

def load_modeling_dataset(db_url: str = DB_URL) -> pd.DataFrame:
    """
    Returns a modeling-ready dataframe.
    """

    engine = create_engine(db_url)

    try:

        hospitals = pd.read_sql(
            "SELECT * FROM dim_hospital",
            engine,
        )

        readmissions = pd.read_sql(
            """
            SELECT
                facility_id,
                measure_name,
                excess_readmission_ratio,
                number_of_discharges,
                number_of_readmissions
            FROM fact_readmission_detail
            WHERE excess_readmission_ratio IS NOT NULL
            """,
            engine,
        )

    finally:
        engine.dispose()

    # ------------------------------------------------------

    agg = (
        readmissions.groupby("facility_id")
        .agg(
            conditions_reported=("measure_name", "count"),
            conditions_over_expected=(
                "excess_readmission_ratio",
                lambda s: (s > 1).sum(),
            ),
            avg_excess_readmission_ratio=(
                "excess_readmission_ratio",
                "mean",
            ),
            total_discharges=(
                "number_of_discharges",
                "sum",
            ),
            total_readmissions=(
                "number_of_readmissions",
                "sum",
            ),
        )
        .reset_index()
    )

    # ------------------------------------------------------

    def risk_tier(x):

        if pd.isna(x):
            return None

        if x >= 4:
            return "High"

        elif x >= 2:
            return "Medium"

        else:
            return "Low"

    agg["risk_tier"] = agg["conditions_over_expected"].apply(risk_tier)

    # ------------------------------------------------------

    df = hospitals.merge(
        agg,
        on="facility_id",
        how="inner",
    )

    return df


# ==========================================================
# MAIN
# ==========================================================

def main():

    project_root = Path(__file__).resolve().parent.parent

    default_output = project_root / "data" / "modeling_dataset.csv"

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--db-url",
        default=DB_URL,
        help="SQLAlchemy database URL",
    )

    parser.add_argument(
        "--out",
        default=str(default_output),
        help="Output CSV location",
    )

    args = parser.parse_args()

    print("=" * 60)
    print("Loading data...")
    print("=" * 60)

    df = load_modeling_dataset(args.db_url)

    print(f"\nRows : {len(df)}")
    print(f"Cols : {len(df.columns)}")

    if df.empty:
        print("\nWARNING: DataFrame is empty.")
        return

    print("\nRisk Tier Distribution\n")

    print(df["risk_tier"].value_counts(dropna=False))

    output_path = Path(args.out)

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    df.to_csv(
        output_path,
        index=False,
    )

    print("\nDataset Preview\n")

    print(df.head())

    print("\nSaved Successfully")

    print(output_path.resolve())


if __name__ == "__main__":
    main()