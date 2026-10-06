<!-- page 1 -->
# Product Requirements Specification — Nimbus K1 Smart Kettle

- Document ID: PRS-NK1-001
- Revision: B
- Status: APPROVED
- Owner: Lumen Labs (fictional)

> Fictional document created for the TraceDraft benchmark (CC BY 4.0).

## 1 Scope

This specification defines the design inputs of the Nimbus K1 Smart Kettle.

<!-- page 2 -->
## 4 Requirements

Under NK1-R-101 (Boil time, Variable) the requirement reads: The kettle shall boil 1.0 L of water starting from 20 °C quickly. Its specification is ≤ 240 s for 1.0 L from 20 °C. To pass, every sample must meet: Mean + 3σ ≤ 240 s.

NK1-R-102 | Temperature hold accuracy | Variable. The keep-warm function shall hold the selected temperature. Required limit: 70 °C ± 3 °C for 30 min. Acceptance: All readings within 67 °C to 73 °C.

Lid opening force [NK1-R-103] is a variable requirement: The lid shall open with a moderate push on the release button. Spec limit = 15 N to 35 N; pass criteria = All samples within 15 N to 35 N.

Under NK1-R-104 (Auto shut-off, Attribute) the requirement reads: The kettle shall switch off within 10 s after the water boils. Its specification is N/A. To pass, every sample must meet: 0 failures in n samples.

NK1-R-105 | Dry-boil protection | Attribute. The heater shall cut power when the kettle is switched on empty. Required limit: N/A. Acceptance: 0 failures in n samples.

Handle surface temperature [NK1-R-106] is a variable requirement: The handle shall stay comfortable to hold during use. Spec limit = ≤ 45 °C after 3 consecutive boils; pass criteria = TBD.

Under NK1-R-107 (Water level readability, Attribute) the requirement reads: The level marks shall be readable at 0.5 m under 300 lx. Its specification is N/A. To pass, every sample must meet: 0 failures in n samples.

NK1-R-108 | Cord retraction endurance | Variable. The cord base shall withstand repeated cord retraction. Required limit: ≥ 5,000 cycles without damage. Acceptance: All samples complete 5,000 cycles.

<!-- page 3 -->
## Appendix B Previous model results (Nimbus K0, informative)

Boil time: ≤ 270 s. Lid opening force: 20 N to 40 N. Handle surface temperature: ≤ 50 °C.
