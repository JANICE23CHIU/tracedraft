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

| Req ID | Test Name | Requirement | Type | Specification Limit | DV Acceptance Criteria |
|---|---|---|---|---|---|
| NK1-R-101 | Boil time | The kettle shall boil 1.0 L of water starting from 20 °C quickly. | Variable | ≤ 240 s for 1.0 L from 20 °C | Mean + 3σ ≤ 240 s |
| NK1-R-102 | Temperature hold accuracy | The keep-warm function shall hold the selected temperature. | Variable | 70 °C ± 3 °C for 30 min | All readings within 67 °C to 73 °C |
| NK1-R-103 | Lid opening force | The lid shall open with a moderate push on the release button. | Variable | 15 N to 35 N | All samples within 15 N to 35 N |
| NK1-R-104 | Auto shut-off | The kettle shall switch off within 10 s after the water boils. | Attribute | N/A | 0 failures in n samples |
| NK1-R-105 | Dry-boil protection | The heater shall cut power when the kettle is switched on empty. | Attribute | N/A | 0 failures in n samples |
| NK1-R-106 | Handle surface temperature | The handle shall stay comfortable to hold during use. | Variable | ≤ 45 °C after 3 consecutive boils | TBD |
| NK1-R-107 | Water level readability | The level marks shall be readable at 0.5 m under 300 lx. | Attribute | N/A | 0 failures in n samples |
| NK1-R-108 | Cord retraction endurance | The cord base shall withstand repeated cord retraction. | Variable | ≥ 5,000 cycles without damage | All samples complete 5,000 cycles |

Note: For Attribute requirements the Specification Limit is not numeric.

<!-- page 3 -->
## Appendix B Previous model results (Nimbus K0, informative)

| Test Name | Previous Result |
|---|---|
| Boil time | ≤ 270 s |
| Lid opening force | 20 N to 40 N |
| Handle surface temperature | ≤ 50 °C |
