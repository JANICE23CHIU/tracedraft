<!-- page 1 -->
# Product Requirements Specification — Nimbus K1 Smart Kettle

- Document ID: PRS-NK1-001
- Revision: A
- Status: SUPERSEDED
- Owner: Lumen Labs (fictional)

> Fictional document created for the TraceDraft benchmark (CC BY 4.0).

## 1 Scope

This specification defines the design inputs of the Nimbus K1 Smart Kettle.

<!-- page 2 -->
## 4 Requirements

NK1-R-101 — Boil time (Variable requirement). The kettle shall boil 1.0 L of water starting from 20 °C quickly. Specification limit: ≤ 240 s for 1.0 L from 20 °C. DV acceptance criteria: Mean + 3σ ≤ 240 s.

Requirement NK1-R-102 covers Temperature hold accuracy. Type: Variable. The keep-warm function shall hold the selected temperature. The specification limit is 70 °C ± 3 °C for 30 min, and the DV acceptance criteria are: All readings within 67 °C to 73 °C.

For Lid opening force (NK1-R-103, Variable): The lid shall open with a moderate push on the release button. Limit — 10 N to 30 N. Acceptance — All samples within 10 N to 30 N.

NK1-R-104 — Auto shut-off (Attribute requirement). The kettle shall switch off within 10 s after the water boils. Specification limit: N/A. DV acceptance criteria: 0 failures in n samples.

Requirement NK1-R-105 covers Dry-boil protection. Type: Attribute. The heater shall cut power when the kettle is switched on empty. The specification limit is N/A, and the DV acceptance criteria are: 0 failures in n samples.

For Handle surface temperature (NK1-R-106, Variable): The handle shall stay comfortable to hold during use. Limit — ≤ 45 °C after 3 consecutive boils. Acceptance — TBD.

NK1-R-107 — Water level readability (Attribute requirement). The level marks shall be readable at 0.5 m under 300 lx. Specification limit: N/A. DV acceptance criteria: 0 failures in n samples.

Requirement NK1-R-108 covers Cord retraction endurance. Type: Variable. The cord base shall withstand repeated cord retraction. The specification limit is ≥ 5,000 cycles without damage, and the DV acceptance criteria are: All samples complete 5,000 cycles.

<!-- page 3 -->
## Appendix B Previous model results (Nimbus K0, informative)

Boil time: ≤ 270 s. Lid opening force: 20 N to 40 N. Handle surface temperature: ≤ 50 °C.
