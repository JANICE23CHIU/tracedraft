<!-- page 1 -->
# Product Requirements Specification — Orbit F2 Desk Fan

- Document ID: PRS-OF2-001
- Revision: C
- Status: APPROVED
- Owner: Lumen Labs (fictional)

> Fictional document created for the TraceDraft benchmark (CC BY 4.0).

## 1 Scope

This specification defines the design inputs of the Orbit F2 Desk Fan.

<!-- page 2 -->
## 4 Requirements

Under OF2-R-201 (Airflow output, Variable) the requirement reads: The fan shall deliver strong airflow at the highest speed. Its specification is ≥ 1.8 m³/min at speed 3. To pass, every sample must meet: Mean − 3σ ≥ 1.8 m³/min.

OF2-R-202 | Noise level | Variable. The fan shall run quietly at the lowest speed. Required limit: ≤ 42 dB(A) at speed 1, 1 m. Acceptance: All samples ≤ 42 dB(A).

Oscillation angle [OF2-R-203] is a variable requirement: The head shall oscillate across a wide angle. Spec limit = 80° ± 5°; pass criteria = All samples within 75° to 85°.

Under OF2-R-204 (Tip-over switch, Attribute) the requirement reads: The motor shall stop within 2 s when the fan tilts beyond 15°. Its specification is N/A. To pass, every sample must meet: 0 failures in n samples.

OF2-R-205 | Button actuation force | Variable. The control buttons shall need a light press. Required limit: 3 N to 6 N. Acceptance: TBD.

Remote control range [OF2-R-206] is an attribute requirement: The remote shall operate the fan at 6 m in line of sight. Spec limit = N/A; pass criteria = 0 failures in n samples.

Under OF2-R-207 (Guard finger probe, Attribute) the requirement reads: The test finger shall not touch moving parts through the guard. Its specification is N/A. To pass, every sample must meet: 0 failures in n samples.

<!-- page 3 -->
## Appendix B Previous model results (Orbit F1, informative)

Noise level: ≤ 48 dB(A). Airflow output: ≥ 1.5 m³/min. Button actuation force: 4 N to 8 N.
