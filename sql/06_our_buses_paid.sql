-- Our buses, paid tickets only: ticket_ticketnew.source = 1 AND is_paid = true (all statuses; cancelled
-- are dropped downstream). Towns come from the ticket itself; for migrated "old prod" tickets they are
-- recovered from the old ticket_ticket table, matched on PNR **and** the same user (1:1 via LATERAL LIMIT 1).
-- Green Card = pass_reward_id set (always the single Green Card pass_id) OR ticket_with_pass.
SELECT
    t.id                                                      AS ticket_id,
    md5(%(salt)s || coalesce(u.contact::text, 'uid:' || t.user_id::text)) AS customer_key,
    coalesce(u.is_test_user, false)                           AS is_test_user,
    t.status, t.is_deleted, coalesce(t.is_test_ticket, false)  AS is_test_ticket,
    t.meta ->> 'from'                                         AS meta_from,
    t.ticket_sourcing,
    t.pass_reward_id::text                                    AS pass_id,
    coalesce(t.ticket_with_pass, false)                       AS ticket_with_pass,
    t.service_id, t.payable_amount, t.distance_in_km,
    (t.created_at  AT TIME ZONE 'Asia/Kolkata')::date         AS booking_date,
    (t.journey_date AT TIME ZONE 'Asia/Kolkata')::date        AS journey_date,
    CASE WHEN ft.id IS NOT NULL THEN 'ticket' WHEN of.id IS NOT NULL THEN 'old ticket_ticket (PNR + user)' END AS town_source,
    coalesce(ft.id, of.id)                                    AS from_town_id,
    coalesce(tt.id, ot.id)                                    AS to_town_id,
    coalesce(ft.name, of.name, o.from_town_name)              AS from_town,
    coalesce(tt.name, ot.name, o.to_town_name)                AS to_town,
    coalesce(ft.district, of.district) ->> 'name'             AS from_district,
    coalesce(tt.district, ot.district) ->> 'name'             AS to_district,
    coalesce(ft.district, of.district) ->> 'state_name'       AS from_state_raw,
    coalesce(tt.district, ot.district) ->> 'state_name'       AS to_state_raw,
    coalesce(ft.latitude, of.latitude)                        AS from_lat,
    coalesce(ft.longitude, of.longitude)                      AS from_lon,
    coalesce(tt.latitude, ot.latitude)                        AS to_lat,
    coalesce(tt.longitude, ot.longitude)                      AS to_lon,
    coalesce(m.boarding_point_info, o.boarding_point_info) ->> 'name' AS boarding_stop_raw,
    coalesce(m.drop_point_info, o.drop_point_info) ->> 'name'         AS drop_stop_raw
FROM ticket_ticketnew t
LEFT JOIN user_user u                 ON u.id = t.user_id
LEFT JOIN ticket_ticketmeta m         ON m.ticket_id = t.id
LEFT JOIN replica_data_townreplica ft ON ft.id = t.from_town_id
LEFT JOIN replica_data_townreplica tt ON tt.id = t.to_town_id
LEFT JOIN LATERAL (
    SELECT o.* FROM ticket_ticket o
    WHERE t.from_town_id IS NULL AND t.pnr IS NOT NULL AND o.pnr = t.pnr AND o.user_id = t.user_id
    LIMIT 1) o ON true
LEFT JOIN replica_data_townreplica of ON of.uuid = o.from_town_id
LEFT JOIN replica_data_townreplica ot ON ot.uuid = o.to_town_id
WHERE t.source = 1 AND t.is_paid;
