-- schema.sql
-- Star schema for the hospital readmission risk & capacity project.
-- Run this once against a fresh Postgres database before loading data.

CREATE TABLE IF NOT EXISTS dim_hospital (
    facility_id                                        VARCHAR(10) PRIMARY KEY,  -- CMS Certification Number
    facility_name                                      TEXT NOT NULL,
    address                                             TEXT,
    citytown                                            VARCHAR(100),
    countyparish                                        VARCHAR(100),
    state                                               CHAR(2),
    zip_code                                            VARCHAR(10),
    telephone_number                                    VARCHAR(20),
    hospital_type                                       VARCHAR(100),
    hospital_ownership                                  VARCHAR(100),
    emergency_services                                  BOOLEAN,
    hospital_overall_rating                             SMALLINT,   -- 1-5, nullable
    hospital_overall_rating_footnote                    TEXT,
    meets_criteria_for_birthing_friendly_designation    VARCHAR(10),
    loaded_at                                           TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS fact_measure_summary (
    facility_id               VARCHAR(10) REFERENCES dim_hospital(facility_id),
    measure_group              VARCHAR(20) NOT NULL,  -- mortality | readmission | safety | patient_experience | timely_effective
    facility_measure_count     SMALLINT,               -- measures in this group this facility reports
    group_measure_count        SMALLINT,               -- total measures possible in this group nationally
    count_better                SMALLINT,
    count_no_different           SMALLINT,
    count_worse                   SMALLINT,
    group_footnote                 TEXT,
    PRIMARY KEY (facility_id, measure_group)
);

-- HRRP data — condition-level excess readmission ratios per facility.
-- NOTE: CMS's payment_adjustment_factor (the literal dollar-penalty driver) is
-- NOT in this API dataset — it lives in a separate IPPS supplemental file CMS
-- publishes as a spreadsheet, not through this API. We use excess_readmission_ratio
-- as our risk signal instead, and are upfront about that in the write-up
-- (a ratio > 1.0 means worse-than-expected readmissions for that condition).
CREATE TABLE IF NOT EXISTS fact_readmission_detail (
    facility_id                  VARCHAR(10) REFERENCES dim_hospital(facility_id),
    measure_name                  VARCHAR(100),  -- e.g. 'READM-30-AMI-HRRP'
    state                          CHAR(2),
    excess_readmission_ratio       NUMERIC(6,4),  -- >1.0 = worse than expected
    predicted_readmission_rate      NUMERIC(6,4),
    expected_readmission_rate        NUMERIC(6,4),
    number_of_discharges              INTEGER,
    number_of_readmissions             INTEGER,
    start_date                          DATE,
    end_date                            DATE,
    footnote                             TEXT,
    PRIMARY KEY (facility_id, measure_name, start_date)
);

CREATE INDEX IF NOT EXISTS idx_dim_hospital_state ON dim_hospital(state);
CREATE INDEX IF NOT EXISTS idx_fact_measure_group ON fact_measure_summary(measure_group);