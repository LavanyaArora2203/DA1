-- analysis_queries.sql
-- Phase 2 exploratory queries — usable now with dim_hospital + fact_measure_summary.
-- (fact_readmission_detail queries will be added once HRRP data is loaded.)

-- 1. Which states have the most hospitals performing WORSE than average on readmissions?
SELECT
    h.state,
    COUNT(DISTINCT h.facility_id)              AS hospitals_with_worse_readmissions,
    SUM(f.count_worse)                          AS total_worse_measures
FROM dim_hospital h
JOIN fact_measure_summary f ON h.facility_id = f.facility_id
WHERE f.measure_group = 'readmission'
  AND f.count_worse > 0
GROUP BY h.state
ORDER BY hospitals_with_worse_readmissions DESC
LIMIT 15;

-- 2. Does hospital ownership type correlate with readmission performance?
SELECT
    h.hospital_ownership,
    COUNT(DISTINCT h.facility_id)                              AS num_hospitals,
    ROUND(AVG(f.count_worse)::numeric, 2)                       AS avg_worse_measures,
    ROUND(AVG(f.count_better)::numeric, 2)                      AS avg_better_measures
FROM dim_hospital h
JOIN fact_measure_summary f ON h.facility_id = f.facility_id
WHERE f.measure_group = 'readmission'
GROUP BY h.hospital_ownership
ORDER BY avg_worse_measures DESC;

-- 3. Overall star rating vs. readmission performance — do low-rated hospitals
--    actually perform worse on readmissions specifically?
SELECT
    h.hospital_overall_rating,
    COUNT(DISTINCT h.facility_id)          AS num_hospitals,
    ROUND(AVG(f.count_worse)::numeric, 2)  AS avg_worse_readmission_measures
FROM dim_hospital h
JOIN fact_measure_summary f ON h.facility_id = f.facility_id
WHERE f.measure_group = 'readmission'
  AND h.hospital_overall_rating IS NOT NULL
GROUP BY h.hospital_overall_rating
ORDER BY h.hospital_overall_rating;

-- 4. "Watch list": specific hospitals with worse-than-average readmissions
--    AND no emergency services AND a low star rating — a plausible
--    ops-intervention target list.
SELECT
    h.facility_name,
    h.state,
    h.hospital_type,
    h.hospital_overall_rating,
    f.count_worse AS worse_readmission_measures
FROM dim_hospital h
JOIN fact_measure_summary f ON h.facility_id = f.facility_id
WHERE f.measure_group = 'readmission'
  AND f.count_worse >= 1
  AND h.emergency_services = false
ORDER BY f.count_worse DESC, h.hospital_overall_rating ASC
LIMIT 25;

-- 5. Data quality check: how many hospitals report NO readmission measures at all?
--    (Useful to flag in your write-up as a limitation — small/critical-access
--    hospitals often don't report enough volume to be measured.)
SELECT
    COUNT(DISTINCT h.facility_id) AS hospitals_with_no_readmission_data
FROM dim_hospital h
LEFT JOIN fact_measure_summary f
    ON h.facility_id = f.facility_id AND f.measure_group = 'readmission'
WHERE f.facility_id IS NULL OR f.facility_measure_count = 0;


-- ============================================================
-- HRRP-based queries (fact_readmission_detail) — the real risk signal
-- ============================================================

-- 6. Top 25 highest-risk hospitals: worst average excess readmission ratio
--    across all their reported conditions, weighted toward high-volume facilities.
SELECT
    h.facility_name,
    h.state,
    h.hospital_ownership,
    COUNT(r.measure_name)                              AS conditions_reported,
    ROUND(AVG(r.excess_readmission_ratio)::numeric, 3)  AS avg_excess_readmission_ratio,
    SUM(r.number_of_discharges)                         AS total_discharges
FROM fact_readmission_detail r
JOIN dim_hospital h ON r.facility_id = h.facility_id
WHERE r.excess_readmission_ratio IS NOT NULL
GROUP BY h.facility_id, h.facility_name, h.state, h.hospital_ownership
HAVING SUM(r.number_of_discharges) > 100   -- filter out low-volume noise
ORDER BY avg_excess_readmission_ratio DESC
LIMIT 25;

-- 7. Which specific conditions (AMI, HF, pneumonia, COPD, hip/knee, CABG) drive
--    the most excess-readmission risk nationally?
SELECT
    measure_name,
    COUNT(*)                                             AS hospitals_reporting,
    ROUND(AVG(excess_readmission_ratio)::numeric, 3)     AS avg_ratio,
    COUNT(*) FILTER (WHERE excess_readmission_ratio > 1) AS hospitals_worse_than_expected
FROM fact_readmission_detail
WHERE excess_readmission_ratio IS NOT NULL
GROUP BY measure_name
ORDER BY avg_ratio DESC;

-- 8. State-level risk exposure: which states have the highest share of hospitals
--    with excess_readmission_ratio > 1.0 (i.e. worse than expected)?
SELECT
    r.state,
    COUNT(DISTINCT r.facility_id)                                        AS hospitals_reporting,
    COUNT(DISTINCT r.facility_id) FILTER (WHERE r.excess_readmission_ratio > 1) AS hospitals_at_risk,
    ROUND(
        100.0 * COUNT(DISTINCT r.facility_id) FILTER (WHERE r.excess_readmission_ratio > 1)
        / NULLIF(COUNT(DISTINCT r.facility_id), 0)
    , 1) AS pct_hospitals_at_risk
FROM fact_readmission_detail r
WHERE r.excess_readmission_ratio IS NOT NULL
GROUP BY r.state
ORDER BY pct_hospitals_at_risk DESC
LIMIT 15;

-- 9. Simple risk tier per hospital (this is what your Streamlit dashboard/model
--    will build on) — counts how many of a hospital's reported conditions have
--    excess_readmission_ratio > 1.0
SELECT
    h.facility_id,
    h.facility_name,
    h.state,
    COUNT(r.measure_name) FILTER (WHERE r.excess_readmission_ratio > 1)   AS conditions_over_expected,
    COUNT(r.measure_name)                                                  AS conditions_reported,
    CASE
        WHEN COUNT(r.measure_name) FILTER (WHERE r.excess_readmission_ratio > 1) >= 4 THEN 'High'
        WHEN COUNT(r.measure_name) FILTER (WHERE r.excess_readmission_ratio > 1) >= 2 THEN 'Medium'
        ELSE 'Low'
    END AS risk_tier
FROM dim_hospital h
JOIN fact_readmission_detail r ON h.facility_id = r.facility_id
GROUP BY h.facility_id, h.facility_name, h.state
ORDER BY conditions_over_expected DESC;