<!-- page 1 -->
# Product Requirements Specification — Orbit F2 Desk Fan

- Document ID: PRS-OF2-001
- Revision: B
- Status: SUPERSEDED
- Owner: Lumen Labs (fictional)

> Fictional document created for the TraceDraft benchmark (CC BY 4.0).

## 1 Scope

This specification defines the design inputs of the Orbit F2 Desk Fan.

<!-- page 2 -->
## 4 Requirements

| Req ID | Test Name | Requirement | Type | Specification Limit | DV Acceptance Criteria |
|---|---|---|---|---|---|
| OF2-R-201 | Airflow output | The fan shall deliver strong airflow at the highest speed. | Variable | ≥ 1.8 m³/min at speed 3 | Mean − 3σ ≥ 1.8 m³/min |
| OF2-R-202 | Noise level | The fan shall run quietly at the lowest speed. | Variable | ≤ 42 dB(A) at speed 1, 1 m | All samples ≤ 42 dB(A) |
| OF2-R-203 | Oscillation angle | The head shall oscillate across a wide angle. | Variable | 80° ± 5° | All samples within 75° to 85° |
| OF2-R-204 | Tip-over switch | The motor shall stop within 2 s when the fan tilts beyond 15°. | Attribute | N/A | 0 failures in n samples |
| OF2-R-205 | Button actuation force | The control buttons shall need a light press. | Variable | 2 N to 5 N | All samples within 2 N to 5 N |
| OF2-R-206 | Remote control range | The remote shall operate the fan at 6 m in line of sight. | Attribute | N/A | 0 failures in n samples |
| OF2-R-207 | Guard finger probe | The test finger shall not touch moving parts through the guard. | Attribute | N/A | 0 failures in n samples |

Note: For Attribute requirements the Specification Limit is not numeric.

<!-- page 3 -->
## Appendix B Previous model results (Orbit F1, informative)

| Test Name | Previous Result |
|---|---|
| Noise level | ≤ 48 dB(A) |
| Airflow output | ≥ 1.5 m³/min |
| Button actuation force | 4 N to 8 N |
