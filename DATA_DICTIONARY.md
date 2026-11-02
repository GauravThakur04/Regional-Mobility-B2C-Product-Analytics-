## Data dictionary & metric definitions

**Source:** PostgreSQL `ab_commuter`, schema `public`, read-only. **As-of date:** 2026-10-28.

### Two datasets (sidebar switch)

| Dataset | What it includes | When a booking counts |
|---|---|---|
| **All B2C bookings** | Every channel: RSRTC, private operators (ITS / Mentis / Bitla), our buses, booth agents | `status = 1` **and** paid |
| **Our buses (source 1)** | `ticket_ticketnew.source = 1` only | App / Web: `status = 1` and paid online. Green Card: `status = 1` (the card is the payment) |

### Tables used
| Table | Role | Join |
|---|---|---|
| `ticket_ticketnew` | One row per ticket or checkout attempt | base |
| `ticket_ticketmeta` | Boarding and drop stop names, operator | `ticket_id` (unique, so 1:1) |
| `user_user` | Customer phone (used for de-duplication only; hashed), test-user flag | `id = user_id` |
| `replica_data_townreplica` | Town, district and state | `id = from_town_id / to_town_id` |
| `coupon_userpass` | Green Card purchases | `user_id` |

### Definitions
| Term | Meaning |
|---|---|
| **Customer** | One phone number. Exports and the dashboard show only an anonymised ID (`C…`). |
| **Journey** | Valid tickets de-duplicated on customer + date + from town + to town + service. |
| **Completed** | Journey date before the as-of date. This is inferred; there is no boarded flag. |
| **Green Card** | The `coupon_userpass` pass, applied to a ticket (`ticket_with_pass = true`). |
| **Long-route / App / Web** | Every other valid ticket. |
| **Repeat customer** | 2 or more journeys. |
| **Regular customer** | Travelled in 3 or more different calendar months. |
| **Route-regular** | 3 or more journeys on the same directed route. |
| **Region** | District (with state), from the town's district. |
| **Cohort** | Month of a customer's first journey. Month-k retention = % of that cohort who travelled in month cohort + k. |
| **Recency window** | 90 days. The median gap between a repeat customer's trips is 11 days and the 90th percentile is 122. |

### Limitations
- **Tickets before May 2024 ("old prod" migration) have no town or stop data.** They count toward customers and cohorts, but show as *Unmapped (legacy ticket)* in region and route views.
- **Customer residence is not recorded.** Region is the boarding or destination district, not where the customer lives.
- **Completion is inferred** from the journey date.
