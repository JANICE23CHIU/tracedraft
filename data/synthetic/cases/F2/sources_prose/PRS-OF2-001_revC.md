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

OF2-R-201 — Airflow output (Variable requirement). The fan shall deliver strong airflow at the highest speed. Specification limit: ≥ 1.8 m³/min at speed 3. DV acceptance criteria: Mean − 3σ ≥ 1.8 m³/min.

Requirement OF2-R-202 covers Noise level. Type: Variable. The fan shall run quietly at the lowest speed. The specification limit is ≤ 42 dB(A) at speed 1, 1 m, and the DV acceptance criteria are: All samples ≤ 42 dB(A).

For Oscillation angle (OF2-R-203, Variable): The head shall oscillate across a wide angle. Limit — 80° ± 5°. Acceptance — All samples within 75° to 85°.

OF2-R-204 — Tip-over switch (Attribute requirement). The motor shall stop within 2 s when the fan tilts beyond 15°. Specification limit: N/A. DV acceptance criteria: 0 failures in n samples.

Requirement OF2-R-205 covers Button actuation force. Type: Variable. The control buttons shall need a light press. The specification limit is 3 N to 6 N, and the DV acceptance criteria are: TBD.

For Remote control range (OF2-R-206, Attribute): The remote shall operate the fan at 6 m in line of sight. Limit — N/A. Acceptance — 0 failures in n samples.

OF2-R-207 — Guard finger probe (Attribute requirement). The test finger shall not touch moving parts through the guard. Specification limit: N/A. DV acceptance criteria: 0 failures in n samples.

<!-- page 3 -->
## Appendix B Previous model results (Orbit F1, informative)

Noise level: ≤ 48 dB(A). Airflow output: ≥ 1.5 m³/min. Button actuation force: 4 N to 8 N.
