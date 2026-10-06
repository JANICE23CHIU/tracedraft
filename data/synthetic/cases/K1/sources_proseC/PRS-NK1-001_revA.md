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

NK1-R-101: The kettle shall boil 1.0 L of water starting from 20 °C quickly. (Boil time, variable). Limit ≤ 240 s for 1.0 L from 20 °C. Acceptance criterion: Mean + 3σ ≤ 240 s.

NK1-R-102 (Temperature hold accuracy; variable). The keep-warm function shall hold the selected temperature. Samples are accepted when All readings within 67 °C to 73 °C; the design limit itself is 70 °C ± 3 °C for 30 min.

Lid opening force — NK1-R-103, Variable type. Verification succeeds if All samples within 10 N to 30 N. The lid shall open with a moderate push on the release button. Target: 10 N to 30 N.

NK1-R-104: The kettle shall switch off within 10 s after the water boils. (Auto shut-off, attribute). Limit N/A. Acceptance criterion: 0 failures in n samples.

NK1-R-105 (Dry-boil protection; attribute). The heater shall cut power when the kettle is switched on empty. Samples are accepted when 0 failures in n samples; the design limit itself is N/A.

Handle surface temperature — NK1-R-106, Variable type. Verification succeeds if TBD. The handle shall stay comfortable to hold during use. Target: ≤ 45 °C after 3 consecutive boils.

NK1-R-107: The level marks shall be readable at 0.5 m under 300 lx. (Water level readability, attribute). Limit N/A. Acceptance criterion: 0 failures in n samples.

NK1-R-108 (Cord retraction endurance; variable). The cord base shall withstand repeated cord retraction. Samples are accepted when All samples complete 5,000 cycles; the design limit itself is ≥ 5,000 cycles without damage.

<!-- page 3 -->
## Appendix B Previous model results (Nimbus K0, informative)

Boil time: ≤ 270 s. Lid opening force: 20 N to 40 N. Handle surface temperature: ≤ 50 °C.
